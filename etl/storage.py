"""資料落地。

設計重點是 **append-only 的每日快照**：`data/daily/YYYY-MM-DD.json` 一天一個檔，
寫進去之後就不再改動。這樣做的理由：

* git 只需要為新的一天新增一個 blob，不必重寫既有檔案，repo 成長線性且可控。
* 每日快照就是外資庫存那類「官方只給當日、沒有歷史端點」資料的唯一累積管道。
* 任何衍生產物（signals、個股歷史）都能從快照重建，壞掉了重跑就好。
"""
from __future__ import annotations

import json
import logging
import os
from datetime import date as Date, datetime, timedelta, timezone
from typing import Iterator

from . import config

log = logging.getLogger(__name__)

# 快照格式版本。改動 SNAPSHOT_FIELDS 或編碼方式時要一併調高，
# 讀取端才知道該用哪種方式解析既有檔案。
SNAPSHOT_VERSION = 2

# 每檔股票在快照中保留的欄位。順序即欄位化陣列的順序，
# 只能往後追加，不能插入或重排，否則舊快照會對錯欄位。
SNAPSHOT_FIELDS = (
    "market", "name", "open", "high", "low", "close", "volume", "amount",
    "margin_balance", "short_balance",
    "foreign_shares", "foreign_ratio",
    "foreign_net", "trust_net", "dealer_net", "total_net",
)


def now_iso() -> str:
    """UTC 時間戳。不用 datetime.utcnow()——它回傳沒有時區資訊的物件，
    自 Python 3.12 起已被標為 deprecated。"""
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _ensure_dir(path: str) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)


def write_json(path: str, payload, *, compact: bool = False) -> None:
    _ensure_dir(path)
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        if compact:
            json.dump(payload, fh, ensure_ascii=False, separators=(",", ":"))
        else:
            json.dump(payload, fh, ensure_ascii=False, indent=2, sort_keys=True)
            fh.write("\n")
    os.replace(tmp, path)          # 原子性寫入，避免中斷留下半份檔案


def read_json(path: str, default=None):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


# --- 每日快照 -------------------------------------------------------------

def daily_path(date: str) -> str:
    return os.path.join(config.DAILY_DIR, f"{date}.json")


def has_daily(date: str) -> bool:
    return os.path.exists(daily_path(date))


def save_daily(date: str, stocks: dict[str, dict], markets: list[str]) -> str:
    """寫入單日快照。

    採欄位化編碼：欄位名只在檔案裡出現一次，每檔股票是一個依 SNAPSHOT_FIELDS
    排列的值陣列。相較於每檔一個物件，實測 1800 檔可省下約 57% 的原始體積
    （554 KB → 240 KB），壓縮後省約 25%。這些快照是永久累積的，
    格式改動的成本只會隨時間變高，所以一開始就用省的那種。
    """
    payload = {
        "version": SNAPSHOT_VERSION,
        "date": date,
        "markets": markets,
        "count": len(stocks),
        "generated_at": now_iso(),
        "fields": list(SNAPSHOT_FIELDS),
        "stocks": {
            stock_id: [row.get(field) for field in SNAPSHOT_FIELDS]
            for stock_id, row in stocks.items()
        },
    }
    path = daily_path(date)
    write_json(path, payload, compact=True)
    return path


def snapshot_rows(snapshot: dict):
    """把快照攤成 (股票代號, {欄位: 值})，同時吃得下欄位化與早期的巢狀格式。"""
    stocks = snapshot.get("stocks")
    if not isinstance(stocks, dict):
        return
    fields = snapshot.get("fields")
    for stock_id, row in stocks.items():
        if isinstance(row, dict):            # version 1：每檔一個物件
            yield stock_id, row
        elif isinstance(row, list) and fields:
            yield stock_id, dict(zip(fields, row))


def patch_daily(date: str, updates: dict[str, dict]) -> int:
    """把補抓到的欄位併進既有快照。

    快照原則上是 append-only，這是唯一的例外：外資持股一類的報表當天抓不到，
    要等下一個交易日才公布，只能事後補。只更新快照裡已存在的個股——價格是錨，
    沒有 K 線的日期不該憑空長出籌碼資料。回傳實際更新的檔數。
    """
    snapshot = load_daily(date)
    if not snapshot:
        return 0

    rows = dict(snapshot_rows(snapshot))
    changed = 0
    for stock_id, patch in updates.items():
        row = rows.get(stock_id)
        if row is None:
            continue
        before = {k: row.get(k) for k in patch}
        row.update(patch)
        if before != patch:
            changed += 1

    if changed:
        save_daily(date, rows, snapshot.get("markets", []))
    return changed


def load_daily(date: str) -> dict | None:
    return read_json(daily_path(date))


def list_daily_dates() -> list[str]:
    if not os.path.isdir(config.DAILY_DIR):
        return []
    dates = [
        name[:-5] for name in os.listdir(config.DAILY_DIR)
        if name.endswith(".json") and not name.endswith(".tmp")
    ]
    return sorted(dates)


def load_recent(days: int) -> list[tuple[str, dict]]:
    """讀取最近 N 個交易日的快照，由舊到新。"""
    out: list[tuple[str, dict]] = []
    for date in list_daily_dates()[-days:]:
        snapshot = load_daily(date)
        if snapshot and isinstance(snapshot.get("stocks"), dict):
            out.append((date, snapshot))
    return out


def build_panel(days: int) -> tuple[list[str], dict[str, dict[str, list]]]:
    """把每日快照轉成以個股為主的時間序列。

    回傳 (交易日清單, {股票代號: {欄位: [依日期排列的值]}})。
    某天缺該股資料時補 None，保證每個序列長度都等於交易日清單長度，
    這樣指標函式才能安全地用索引對齊日期。
    """
    snapshots = load_recent(days)
    dates = [d for d, _ in snapshots]
    if not dates:
        return [], {}

    numeric_fields = [f for f in SNAPSHOT_FIELDS if f not in ("market", "name")]
    panel: dict[str, dict[str, list]] = {}

    for position, (_, snapshot) in enumerate(snapshots):
        for stock_id, row in snapshot_rows(snapshot):
            entry = panel.get(stock_id)
            if entry is None:
                entry = {f: [None] * len(dates) for f in numeric_fields}
                entry["name"] = ""
                entry["market"] = ""
                panel[stock_id] = entry
            for f in numeric_fields:
                entry[f][position] = row.get(f)
            if row.get("name"):
                entry["name"] = row["name"]
            if row.get("market"):
                entry["market"] = row["market"]

    return dates, panel


# --- 股票主檔 -------------------------------------------------------------

def update_stock_info(stocks: dict[str, dict]) -> dict:
    info = read_json(config.STOCK_INFO_PATH, default={}) or {}
    for stock_id, row in stocks.items():
        record = info.setdefault(stock_id, {})
        if row.get("name"):
            record["name"] = row["name"]
        if row.get("market"):
            record["market"] = row["market"]
    write_json(config.STOCK_INFO_PATH, info)
    return info


# --- 交易日 ---------------------------------------------------------------

def parse_date(text: str) -> Date:
    return datetime.strptime(text.replace("-", ""), "%Y%m%d").date()


def to_api_date(d: Date) -> str:
    """交易所 API 用的格式。"""
    return d.strftime("%Y%m%d")


def to_key(d: Date) -> str:
    """檔名與 JSON 中使用的格式。"""
    return d.strftime("%Y-%m-%d")


def weekdays(start: Date, end: Date) -> Iterator[Date]:
    """由舊到新列出區間內的平日。國定假日無法從行事曆得知，
    抓取時交易所會回報無資料，屆時跳過即可。"""
    current = start
    while current <= end:
        if current.weekday() < 5:
            yield current
        current += timedelta(days=1)
