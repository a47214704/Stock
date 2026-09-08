"""抓取單日全市場資料並合併成一份快照。

每個交易日只需要 4 個「全市場報表」端點 × 市場數，約 8 次請求就能拿到
全部 1800 檔的價量與籌碼——不需要逐檔迴圈。這是整個架構能用免費排程
跑起來的關鍵。
"""
from __future__ import annotations

import logging
from datetime import date as Date

from .sources import twse, tpex
from .sources.twse import DateMismatch, NoDataForDate
from .storage import SNAPSHOT_FIELDS, load_daily, snapshot_rows, to_api_date

log = logging.getLogger(__name__)

MARKETS = {"twse": twse, "tpex": tpex}
DATASETS = ("price", "institutional", "margin", "foreign")

# 各資料集在快照裡的代表欄位，用來判斷某天是不是整組沒抓到。
DATASET_FIELDS = {
    "institutional": ("total_net",),
    "margin": ("margin_balance",),
    "foreign": ("foreign_shares", "foreign_ratio"),
}


def missing_datasets(date: str) -> list[str]:
    """回報某日快照裡整組缺漏的資料集。

    backfill 只補「完全沒有快照」的日期，對**部分完成**的快照無效——
    例如某天抓取時端點路徑還是錯的，之後路徑修好了，那天的融資餘額仍會
    永遠是空的（實測 2026-09-08 全市場 1950 檔的融資餘額都是 None，
    而前後幾天都有 1050 檔左右）。這裡逐一檢查代表欄位，讓 refresh
    只補真正缺的那幾組。

    價格不列入檢查：它是錨，沒有價格就不會有快照。
    """
    snapshot = load_daily(date)
    if not snapshot:
        return []
    rows = [row for _, row in snapshot_rows(snapshot)]
    if not rows:
        return []
    return [
        dataset for dataset, fields in DATASET_FIELDS.items()
        if not any(row.get(f) is not None for row in rows for f in fields)
    ]


def fetch_one(day: Date, market: str, dataset: str) -> dict[str, dict]:
    """只抓單一市場的單一資料集。供 refresh 事後補延遲公布的報表使用。"""
    api_date = to_api_date(day)
    try:
        return MARKETS[market].FETCHERS[dataset](api_date) or {}
    except NoDataForDate as exc:
        log.info("%s %s %s：無資料（%s）", market, dataset, api_date, exc)
    except DateMismatch as exc:
        log.warning("%s", exc)
    except Exception as exc:                              # noqa: BLE001
        log.error("%s %s %s 抓取失敗：%s", market, dataset, api_date, exc)
    return {}


def fetch_date(day: Date, markets: list[str]) -> dict[str, dict] | None:
    """抓取指定日期的全市場資料。

    回傳 {股票代號: {欄位: 值}}；若當天沒有任何行情（假日／尚未收盤）回傳 None。
    價格是錨——沒有價格就當作非交易日，其餘籌碼資料一律不寫入，
    避免在沒有 K 線的日期留下孤立的籌碼數字。
    """
    api_date = to_api_date(day)
    merged: dict[str, dict] = {}

    for market in markets:
        module = MARKETS[market]
        market_data: dict[str, dict[str, dict]] = {}

        for dataset in DATASETS:
            try:
                market_data[dataset] = module.FETCHERS[dataset](api_date)
            except NoDataForDate as exc:
                log.info("%s %s %s：無資料（%s）", market, dataset, api_date, exc)
                market_data[dataset] = {}
            except DateMismatch as exc:
                # 端點忽略 date 參數。寧可缺這格，也不要把今天的數字寫進過去。
                log.warning("%s", exc)
                market_data[dataset] = {}
            except Exception as exc:                      # noqa: BLE001
                log.error("%s %s %s 抓取失敗：%s", market, dataset, api_date, exc)
                market_data[dataset] = {}

        prices = market_data.get("price") or {}
        if not prices:
            log.info("%s %s 無成交資料，該市場略過", market, api_date)
            continue

        for stock_id, price in prices.items():
            row = {"market": market}
            row.update(price)
            for dataset in ("institutional", "margin", "foreign"):
                extra = market_data.get(dataset, {}).get(stock_id)
                if extra:
                    row.update(extra)
            merged[stock_id] = {k: row.get(k) for k in SNAPSHOT_FIELDS}

    return merged or None
