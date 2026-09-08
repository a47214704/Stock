"""交易所回應的正規化與欄位對應。

因為 TWSE / TPEx 的欄位名稱與表格結構會隨時間微調，這裡刻意**以表頭文字**
定位欄位，而不是寫死索引。找不到欄位時會把實際表頭一併丟進錯誤訊息，
方便對照 `python -m etl verify` 的輸出快速修正。
"""
from __future__ import annotations

import re
from typing import Any, Iterable, Sequence

_NULLS = {"", "-", "--", "---", "N/A", "n/a", "null", "None"}


def to_num(value: Any) -> float | None:
    """把 '1,234'、'1,234.56'、'--'、'+1.2' 這類欄位轉成數字。"""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", "").replace("+", "")
    # 有些欄位會夾帶 HTML 或全形空白
    text = re.sub(r"<[^>]+>", "", text).replace("　", "").strip()
    if text in _NULLS:
        return None
    # 括號表示負數，例如 (1,234)
    negative = text.startswith("(") and text.endswith(")")
    if negative:
        text = text[1:-1]
    try:
        num = float(text)
    except ValueError:
        return None
    return -num if negative else num


def to_int(value: Any) -> int | None:
    num = to_num(value)
    return None if num is None else int(round(num))


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"<[^>]+>", "", str(value)).replace("　", " ").strip()


def iter_tables(payload: Any) -> Iterable[tuple[list[str], list[list[Any]]]]:
    """從各種形狀的回應中取出 (fields, data) 配對。

    TWSE 的 rwd 端點有時回 {"fields": [...], "data": [...]}，
    有時回 {"tables": [{"fields": [...], "data": [...]}, ...]}，
    偶爾是 {"fields1": ..., "data1": ...} 這種帶編號的變體，全部都吃。
    """
    if not isinstance(payload, dict):
        return

    if isinstance(payload.get("tables"), list):
        for table in payload["tables"]:
            if isinstance(table, dict):
                fields = table.get("fields") or table.get("field")
                data = table.get("data")
                if isinstance(fields, list) and isinstance(data, list):
                    yield [clean_text(f) for f in fields], data

    fields = payload.get("fields") or payload.get("field")
    data = payload.get("data")
    if isinstance(fields, list) and isinstance(data, list):
        yield [clean_text(f) for f in fields], data

    for key in payload:
        m = re.fullmatch(r"fields?(\d+)", str(key))
        if not m:
            continue
        data_key = f"data{m.group(1)}"
        f, d = payload.get(key), payload.get(data_key)
        if isinstance(f, list) and isinstance(d, list):
            yield [clean_text(x) for x in f], d


Alias = str | tuple[str, int]


def find_column(fields: Sequence[str], aliases: Sequence[Alias]) -> int | None:
    """依表頭文字找欄位索引。先求完全相等，再退回包含比對。

    別名可以是字串，也可以是 `(別名, 第幾次出現)` 的組合。後者是為了
    表頭本身無法區分欄位的情形——MI_MARGN 的表頭是

        代號 名稱 買進 賣出 現金償還 前日餘額 今日餘額 次一營業日限額
                  買進 賣出 現券償還 前日餘額 今日餘額 次一營業日限額 …

    前六欄是融資、後六欄是融券，但表頭裡沒有「融資／融券」字樣，
    「今日餘額」出現兩次且意義不同。這種情況只能靠出現順序區分，
    所以 `("今日餘額", 1)` 取融資、`("今日餘額", 2)` 取融券。

    別名依序嘗試，字串別名永遠優先，位置退路放在最後——這樣萬一交易所
    日後補上「融資今日餘額」這種明確欄名，會自動改用文字比對。
    """
    normalized = [clean_text(f).replace(" ", "") for f in fields]

    def hits(target: str, exact: bool) -> list[int]:
        if not target:
            return []
        return [idx for idx, name in enumerate(normalized)
                if (name == target if exact else target in name)]

    for exact in (True, False):
        for alias in aliases:
            target, nth = alias if isinstance(alias, tuple) else (alias, 1)
            found = hits(target.replace(" ", ""), exact)
            if len(found) >= nth:
                return found[nth - 1]
    return None


class ColumnMissing(LookupError):
    def __init__(self, label: str, aliases: Sequence[str], fields: Sequence[str]):
        super().__init__(
            f"找不到欄位「{label}」（比對別名 {list(aliases)}）。"
            f"實際表頭為 {list(fields)}。請跑 `python -m etl verify` 對照後更新 etl/sources 的欄位別名。"
        )
        self.label = label
        self.aliases = list(aliases)
        self.fields = list(fields)


def resolve_columns(fields: Sequence[str], spec: dict[str, Sequence[Alias]],
                    required: Sequence[str]) -> dict[str, int | None]:
    """把 {欄位名: 別名清單} 解析成 {欄位名: 索引}，缺必要欄位就丟錯。"""
    resolved: dict[str, int | None] = {}
    for key, aliases in spec.items():
        idx = find_column(fields, aliases)
        if idx is None and key in required:
            raise ColumnMissing(key, aliases, fields)
        resolved[key] = idx
    return resolved


def pick_table(payload: Any, spec: dict[str, Sequence[Alias]],
               required: Sequence[str]) -> tuple[dict[str, int | None], list[list[Any]]]:
    """在回應的多張表中挑出含有所需欄位的那一張。"""
    errors: list[str] = []
    for fields, data in iter_tables(payload):
        if not data:
            continue
        try:
            return resolve_columns(fields, spec, required), data
        except ColumnMissing as exc:
            errors.append(str(exc))
    if errors:
        raise LookupError("；".join(errors))
    raise LookupError("回應中找不到任何有資料的 fields/data 表格，可能是非交易日或端點格式已變更。")


STOCK_ID_RE = re.compile(r"^\d{4,6}[A-Z]?$")


def is_common_stock(stock_id: str) -> bool:
    """濾掉 ETF、權證、受益證券等非普通股。

    普通股為 4 碼數字且不以 0 開頭；0 開頭的 4~6 碼（0050、00878）是 ETF，
    5 碼以上或含英文字母的多為權證與存託憑證。
    """
    return bool(re.fullmatch(r"[1-9]\d{3}", stock_id or ""))
