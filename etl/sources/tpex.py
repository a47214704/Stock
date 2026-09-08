"""上櫃（TPEx）資料抓取與正規化。

與 TWSE 的差異有兩點，都會影響用法：

1. TPEx OpenAPI 回傳的是**物件陣列**（每列一個 dict），不是 fields/data 表格，
   因此以 dict 的 key 做別名比對。
2. 這些 openapi 端點多半**只提供當日資料、不吃 date 參數**，所以上櫃股票
   無法回補歷史，只能從導入日起每日累積。這是 TPEx 側的限制，不是程式的問題。

本模組的欄位別名尚未經實際請求驗證，請以 `python -m etl verify --market tpex`
的輸出為準再行調整。抓取失敗時整批跳過（回傳空 dict），不影響上市資料。
"""
from __future__ import annotations

import logging
from typing import Any, Sequence

from .. import config
from ..http import get_json
from ..parsing import clean_text, is_common_stock, to_int, to_num

log = logging.getLogger(__name__)

MARKET = "tpex"

STOCK_ID_KEYS = ["SecuritiesCompanyCode", "Code", "股票代號", "證券代號", "代號"]
NAME_KEYS = ["CompanyName", "Name", "公司名稱", "股票名稱", "證券名稱", "名稱"]


def _pick(row: dict[str, Any], aliases: Sequence[str]) -> Any:
    """依 key 別名取值，先完全相等再退回包含比對（忽略大小寫與空白）。"""
    keys = {str(k).strip(): k for k in row}
    for alias in aliases:
        if alias in keys:
            return row[keys[alias]]
    lowered = {k.lower().replace(" ", ""): orig for k, orig in keys.items()}
    for alias in aliases:
        target = alias.lower().replace(" ", "")
        if target in lowered:
            return row[lowered[target]]
        for k, orig in lowered.items():
            if target and target in k:
                return row[orig]
    return None


def _fetch_rows(kind: str) -> list[dict[str, Any]]:
    url = config.TPEX_ENDPOINTS[kind]
    payload = get_json(url)
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    if isinstance(payload, dict):
        for key in ("data", "aaData", "tables"):
            value = payload.get(key)
            if isinstance(value, list) and value and isinstance(value[0], dict):
                return value
    raise RuntimeError(f"TPEx {kind}：非預期的回應格式 {type(payload).__name__}")


def _iter(kind: str):
    for row in _fetch_rows(kind):
        stock_id = clean_text(_pick(row, STOCK_ID_KEYS))
        if is_common_stock(stock_id):
            yield stock_id, row


def _safe(kind: str, fn):
    """TPEx 抓不到就記 warning 跳過，不讓上櫃拖垮整批 ETL。"""
    try:
        return fn()
    except Exception as exc:                       # noqa: BLE001 — 刻意吞掉
        log.warning("TPEx %s 抓取失敗，本日上櫃資料略過：%s", kind, exc)
        return {}


def fetch_price(date: str) -> dict[str, dict]:
    def run():
        out: dict[str, dict] = {}
        for stock_id, row in _iter("price"):
            close = to_num(_pick(row, ["Close", "收盤", "收盤價"]))
            if close is None:
                continue
            out[stock_id] = {
                "name": clean_text(_pick(row, NAME_KEYS)),
                "open": to_num(_pick(row, ["Open", "開盤", "開盤價"])),
                "high": to_num(_pick(row, ["High", "最高", "最高價"])),
                "low": to_num(_pick(row, ["Low", "最低", "最低價"])),
                "close": close,
                "volume": to_int(_pick(row, ["TradingShares", "成交股數"])),
                "amount": to_int(_pick(row, ["TransactionAmount", "成交金額"])),
            }
        return out
    return _safe("price", run)


def fetch_institutional(date: str) -> dict[str, dict]:
    def run():
        out: dict[str, dict] = {}
        for stock_id, row in _iter("institutional"):
            foreign = to_int(_pick(row, ["ForeignInvestorsNet", "外資及陸資買賣超股數"])) or 0
            trust = to_int(_pick(row, ["SecuritiesInvestmentNet", "投信買賣超股數"])) or 0
            dealer = to_int(_pick(row, ["DealersNet", "自營商買賣超股數"])) or 0
            total = to_int(_pick(row, ["TotalNet", "三大法人買賣超股數"]))
            out[stock_id] = {
                "foreign_net": foreign,
                "trust_net": trust,
                "dealer_net": dealer,
                "total_net": total if total is not None else foreign + trust + dealer,
            }
        return out
    return _safe("institutional", run)


def fetch_margin(date: str) -> dict[str, dict]:
    def run():
        out: dict[str, dict] = {}
        for stock_id, row in _iter("margin"):
            balance = to_int(_pick(row, ["MarginBalance", "融資今日餘額", "融資餘額"]))
            if balance is None:
                continue
            out[stock_id] = {
                "margin_balance": balance,
                "short_balance": to_int(_pick(row, ["ShortBalance", "融券今日餘額", "融券餘額"])),
            }
        return out
    return _safe("margin", run)


def fetch_foreign(date: str) -> dict[str, dict]:
    def run():
        out: dict[str, dict] = {}
        for stock_id, row in _iter("foreign"):
            shares = to_int(_pick(row, [
                "ForeignShareholding", "全體外資及陸資持有股數",
                "外資及陸資持有股數", "持有股數",
            ]))
            ratio = to_num(_pick(row, [
                "ForeignShareholdingRatio", "全體僑外資及陸資持股比例",
                "僑外資及陸資持股比例", "持股比例", "持股比率",
            ]))
            if shares is None and ratio is None:
                continue
            out[stock_id] = {"foreign_shares": shares, "foreign_ratio": ratio}
        return out
    return _safe("foreign", run)


FETCHERS = {
    "price": fetch_price,
    "institutional": fetch_institutional,
    "margin": fetch_margin,
    "foreign": fetch_foreign,
}
