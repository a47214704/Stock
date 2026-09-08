"""回應解析與欄位對應。

交易所欄位名稱會變，所以定位方式是表頭文字而非索引。這裡驗證：
順序改變不會壞、欄位改名會**明確報錯**而不是默默算錯。
"""
import pytest

from etl.parsing import (
    ColumnMissing, clean_text, find_column, is_common_stock, iter_tables,
    pick_table, resolve_columns, to_int, to_num,
)

SPEC = {
    "stock_id": ["證券代號"],
    "close": ["收盤價"],
    "volume": ["成交股數"],
}
REQUIRED = ["stock_id", "close"]


class TestToNum:
    @pytest.mark.parametrize("raw,expected", [
        ("1,234", 1234.0), ("1,234.56", 1234.56), ("123", 123.0),
        ("+3.2", 3.2), ("-5", -5.0), ("(1,200)", -1200.0),
        ("  42  ", 42.0), ("1,234<br>", 1234.0), (7, 7.0), (7.5, 7.5),
    ])
    def test_parses(self, raw, expected):
        assert to_num(raw) == expected

    @pytest.mark.parametrize("raw", ["", "--", "-", "N/A", None, "不適用", "　"])
    def test_nulls_become_none(self, raw):
        assert to_num(raw) is None

    def test_to_int_rounds(self):
        assert to_int("1,234.6") == 1235
        assert to_int("--") is None


class TestIterTables:
    def test_plain_fields_data(self):
        tables = list(iter_tables({"fields": ["a", "b"], "data": [[1, 2]]}))
        assert tables == [(["a", "b"], [[1, 2]])]

    def test_nested_tables(self):
        payload = {"tables": [
            {"fields": ["a"], "data": [[1]]},
            {"fields": ["b"], "data": [[2]]},
        ]}
        assert len(list(iter_tables(payload))) == 2

    def test_numbered_variant(self):
        payload = {"fields1": ["a"], "data1": [[1]], "fields2": ["b"], "data2": [[2]]}
        headers = [f for f, _ in iter_tables(payload)]
        assert ["a"] in headers and ["b"] in headers

    def test_non_dict_yields_nothing(self):
        assert list(iter_tables([1, 2, 3])) == []

    def test_strips_html_from_headers(self):
        (fields, _), = list(iter_tables({"fields": ["收盤價<br>元"], "data": [[1]]}))
        assert fields == ["收盤價元"]


class TestFindColumn:
    def test_exact_match_wins_over_substring(self):
        fields = ["融資今日餘額", "融資餘額限額"]
        assert find_column(fields, ["融資今日餘額"]) == 0

    def test_substring_fallback(self):
        fields = ["外陸資買賣超股數(不含外資自營商)"]
        assert find_column(fields, ["外陸資買賣超股數"]) == 0

    def test_alias_order_is_priority(self):
        fields = ["股票代號", "證券代號"]
        assert find_column(fields, ["證券代號", "股票代號"]) == 1

    def test_missing_returns_none(self):
        assert find_column(["a", "b"], ["c"]) is None


class TestResolveColumns:
    def test_column_order_does_not_matter(self):
        a = resolve_columns(["證券代號", "收盤價", "成交股數"], SPEC, REQUIRED)
        b = resolve_columns(["成交股數", "收盤價", "證券代號"], SPEC, REQUIRED)
        assert a == {"stock_id": 0, "close": 1, "volume": 2}
        assert b == {"stock_id": 2, "close": 1, "volume": 0}

    def test_optional_column_may_be_missing(self):
        cols = resolve_columns(["證券代號", "收盤價"], SPEC, REQUIRED)
        assert cols["volume"] is None

    def test_missing_required_column_raises_with_actual_headers(self):
        """錯誤訊息必須帶出實際表頭，否則要重打一次 API 才知道怎麼修。"""
        with pytest.raises(ColumnMissing) as exc:
            resolve_columns(["證券代號", "成交價"], SPEC, REQUIRED)
        message = str(exc.value)
        assert "close" in message and "收盤價" in message and "成交價" in message


class TestPickTable:
    def test_selects_the_table_that_has_the_columns(self):
        payload = {"tables": [
            {"fields": ["說明"], "data": [["本表僅供參考"]]},
            {"fields": ["證券代號", "收盤價"], "data": [["2330", "1,000"]]},
        ]}
        cols, data = pick_table(payload, SPEC, REQUIRED)
        assert data[0][cols["stock_id"]] == "2330"

    def test_skips_empty_tables(self):
        payload = {"tables": [
            {"fields": ["證券代號", "收盤價"], "data": []},
            {"fields": ["證券代號", "收盤價"], "data": [["2317", "100"]]},
        ]}
        _, data = pick_table(payload, SPEC, REQUIRED)
        assert data == [["2317", "100"]]

    def test_no_matching_table_raises(self):
        with pytest.raises(LookupError):
            pick_table({"fields": ["日期"], "data": [["2026"]]}, SPEC, REQUIRED)


class TestIsCommonStock:
    @pytest.mark.parametrize("code", ["1101", "2330", "2317", "9958"])
    def test_accepts_common_stock(self, code):
        assert is_common_stock(code)

    @pytest.mark.parametrize("code", ["0050", "00878", "006208", "03019P",
                                      "2330A", "", "台積電", None])
    def test_rejects_etf_warrant_and_junk(self, code):
        assert not is_common_stock(code)


class TestCleanText:
    def test_strips_html_and_full_width_space(self):
        assert clean_text("<b>台積電</b>　") == "台積電"

    def test_none_becomes_empty(self):
        assert clean_text(None) == ""
