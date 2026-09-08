"""上市（TWSE）資料抓取與正規化。

欄位一律以表頭文字定位（見 etl/parsing.py），因此交易所小幅調整欄位順序不會壞掉；
欄位「改名」才需要來這裡補別名。
"""
from __future__ import annotations

import logging
import re
from typing import Any

from .. import config
from ..http import get_json
from ..parsing import (
    ColumnMissing, clean_text, is_common_stock, pick_table, to_int, to_num,
)

log = logging.getLogger(__name__)

MARKET = "twse"

PRICE_SPEC = {
    "stock_id": ["證券代號", "股票代號", "代號"],
    "name": ["證券名稱", "股票名稱", "名稱"],
    "volume": ["成交股數"],
    "amount": ["成交金額"],
    "open": ["開盤價"],
    "high": ["最高價"],
    "low": ["最低價"],
    "close": ["收盤價"],
}
PRICE_REQUIRED = ["stock_id", "close", "high", "low"]

INSTITUTIONAL_SPEC = {
    "stock_id": ["證券代號", "股票代號", "代號"],
    "name": ["證券名稱", "股票名稱", "名稱"],
    "foreign_net": [
        "外陸資買賣超股數(不含外資自營商)", "外陸資買賣超股數", "外資買賣超股數",
    ],
    "foreign_dealer_net": ["外資自營商買賣超股數"],
    "trust_net": ["投信買賣超股數"],
    "dealer_net": ["自營商買賣超股數"],
    "total_net": ["三大法人買賣超股數"],
}
INSTITUTIONAL_REQUIRED = ["stock_id"]

MARGIN_SPEC = {
    "stock_id": ["股票代號", "證券代號", "代號"],
    "name": ["股票名稱", "證券名稱", "名稱"],
    "margin_balance": ["融資今日餘額", "融資餘額"],
    "margin_prev": ["融資前日餘額"],
    "short_balance": ["融券今日餘額", "融券餘額"],
}
MARGIN_REQUIRED = ["stock_id", "margin_balance"]

FOREIGN_SPEC = {
    "stock_id": ["證券代號", "股票代號", "代號"],
    "name": ["證券名稱", "股票名稱", "名稱"],
    "issued_shares": ["發行股數"],
    "shares_held": [
        "全體外資及陸資持有股數", "外資及陸資持有股數", "全體外資持有股數", "持有股數",
    ],
    "holding_ratio": [
        "全體外資及陸資持股比率", "外資及陸資持股比率", "全體外資持股比率", "持股比率",
    ],
    "remaining_shares": ["外資及陸資尚可投資股數", "尚可投資股數"],
}
FOREIGN_REQUIRED = ["stock_id"]


class NoDataForDate(RuntimeError):
    """非交易日或該日尚無資料。"""


class DateMismatch(RuntimeError):
    """端點忽略了 date 參數，回傳了其他日期的資料。

    這比抓不到資料更危險——若不擋下來，回補歷史時會把今天的數字寫進過去的日期。
    """


# 標題可能是「115年09月07日」（民國）或「2026/09/07」「2026-09-07」。
# 民國年是 3 碼，所以年份要收 3~4 碼，且中文格式必須帶年月日字樣才不會誤抓其他數字。
_DATE_PATTERNS = (
    re.compile(r"(\d{3,4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日"),
    re.compile(r"\b(\d{4})[/-](\d{1,2})[/-](\d{1,2})\b"),
)


def _extract_date(payload: dict[str, Any]) -> str | None:
    """從回應中盡可能找出資料日期，正規化為 YYYYMMDD。"""
    raw = payload.get("date")
    if isinstance(raw, str) and re.fullmatch(r"\d{8}", raw.strip()):
        return raw.strip()

    for key in ("title", "subtitle", "reportDate"):
        text = clean_text(payload.get(key))
        if not text:
            continue
        for pattern in _DATE_PATTERNS:
            m = pattern.search(text)
            if not m:
                continue
            year, month, day = (int(g) for g in m.groups())
            if year < 1911:                  # 民國年轉西元
                year += 1911
            if 1 <= month <= 12 and 1 <= day <= 31:
                return f"{year:04d}{month:02d}{day:02d}"
    return None


def _fetch(kind: str, date: str) -> dict[str, Any]:
    params = dict(config.TWSE_PARAMS[kind])
    params["date"] = date
    payload = get_json(config.TWSE_ENDPOINTS[kind], params)

    if not isinstance(payload, dict):
        raise NoDataForDate(f"TWSE {kind} {date}：回應非 JSON 物件")
    stat = clean_text(payload.get("stat"))
    if stat and stat.upper() != "OK":
        raise NoDataForDate(f"TWSE {kind} {date}：stat={stat}")

    found = _extract_date(payload)
    if found and found != date:
        raise DateMismatch(
            f"TWSE {kind}：要求 {date} 但回應的資料日期為 {found}。"
            f"該端點可能不支援歷史查詢，已跳過以免污染歷史資料。"
        )
    if not found:
        log.debug("TWSE %s %s：回應中無法辨識資料日期，無法驗證是否為該日資料", kind, date)
    return payload


def _rows(kind: str, date: str, spec: dict, required: list[str]):
    payload = _fetch(kind, date)
    try:
        cols, data = pick_table(payload, spec, required)
    except (LookupError, ColumnMissing) as exc:
        raise RuntimeError(f"TWSE {kind} {date} 欄位解析失敗：{exc}") from exc

    def cell(row: list, key: str):
        idx = cols.get(key)
        if idx is None or idx >= len(row):
            return None
        return row[idx]

    for row in data:
        if not isinstance(row, list):
            continue
        stock_id = clean_text(cell(row, "stock_id"))
        if not is_common_stock(stock_id):
            continue
        yield stock_id, cell, row


def fetch_price(date: str) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for stock_id, cell, row in _rows("price", date, PRICE_SPEC, PRICE_REQUIRED):
        close = to_num(cell(row, "close"))
        if close is None:
            continue          # 全日無成交
        out[stock_id] = {
            "name": clean_text(cell(row, "name")),
            "open": to_num(cell(row, "open")),
            "high": to_num(cell(row, "high")),
            "low": to_num(cell(row, "low")),
            "close": close,
            "volume": to_int(cell(row, "volume")),
            "amount": to_int(cell(row, "amount")),
        }
    return out


def fetch_institutional(date: str) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for stock_id, cell, row in _rows("institutional", date, INSTITUTIONAL_SPEC,
                                     INSTITUTIONAL_REQUIRED):
        foreign = to_int(cell(row, "foreign_net")) or 0
        foreign_dealer = to_int(cell(row, "foreign_dealer_net")) or 0
        trust = to_int(cell(row, "trust_net")) or 0
        dealer = to_int(cell(row, "dealer_net")) or 0
        total = to_int(cell(row, "total_net"))
        if total is None:
            # 沒有現成的合計欄位就自己加。外資自營商併入外資。
            total = foreign + foreign_dealer + trust + dealer
        out[stock_id] = {
            "foreign_net": foreign + foreign_dealer,
            "trust_net": trust,
            "dealer_net": dealer,
            "total_net": total,
        }
    return out


def fetch_margin(date: str) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for stock_id, cell, row in _rows("margin", date, MARGIN_SPEC, MARGIN_REQUIRED):
        balance = to_int(cell(row, "margin_balance"))
        if balance is None:
            continue
        out[stock_id] = {
            "margin_balance": balance,
            "short_balance": to_int(cell(row, "short_balance")),
        }
    return out


def fetch_foreign(date: str) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for stock_id, cell, row in _rows("foreign", date, FOREIGN_SPEC, FOREIGN_REQUIRED):
        shares = to_int(cell(row, "shares_held"))
        ratio = to_num(cell(row, "holding_ratio"))
        issued = to_int(cell(row, "issued_shares"))
        if shares is None and ratio is not None and issued:
            # 只有比率時用發行股數還原庫存張數
            shares = int(round(issued * ratio / 100.0))
        if shares is None and ratio is None:
            continue
        out[stock_id] = {"foreign_shares": shares, "foreign_ratio": ratio}
    return out


FETCHERS = {
    "price": fetch_price,
    "institutional": fetch_institutional,
    "margin": fetch_margin,
    "foreign": fetch_foreign,
}
