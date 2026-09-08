"""TWSE 抓取層。

注意：這裡的假回應是**依照程式假設的格式**構造的，能證明解析邏輯正確，
但不能證明交易所真的回這個格式。實際欄位要靠 `python -m etl verify` 確認。
"""
import pytest

from etl.sources import twse
from etl.sources.twse import DateMismatch, NoDataForDate

PRICE_PAYLOAD = {
    "stat": "OK",
    "date": "20260907",
    "title": "115年09月07日 每日收盤行情",
    "fields": ["證券代號", "證券名稱", "成交股數", "成交筆數", "成交金額",
               "開盤價", "最高價", "最低價", "收盤價", "漲跌價差"],
    "data": [
        ["2330", "台積電", "25,000,000", "40,000", "30,000,000,000",
         "1,200.00", "1,215.00", "1,195.00", "1,210.00", "+10.00"],
        ["0050", "元大台灣50", "10,000,000", "5,000", "2,000,000,000",
         "200.00", "202.00", "199.00", "201.00", "+1.00"],
        ["1234", "停牌股", "0", "0", "0", "--", "--", "--", "--", "--"],
    ],
}

T86_PAYLOAD = {
    "stat": "OK", "date": "20260907",
    "fields": ["證券代號", "證券名稱", "外陸資買賣超股數(不含外資自營商)",
               "外資自營商買賣超股數", "投信買賣超股數", "自營商買賣超股數",
               "三大法人買賣超股數"],
    "data": [["2330", "台積電", "5,000,000", "100,000", "1,200,000",
              "-300,000", "6,000,000"]],
}

# MI_MARGN 的真實表頭（取自 docs/endpoint-report.md）。
# 融資與融券的欄名完全相同，只能靠出現順序區分。
MARGIN_FIELDS = ["代號", "名稱", "買進", "賣出", "現金償還", "前日餘額", "今日餘額",
                 "次一營業日限額", "買進", "賣出", "現券償還", "前日餘額",
                 "今日餘額", "次一營業日限額", "資券互抵", "註記"]

MARGIN_PAYLOAD = {
    "stat": "OK", "date": "20260907",
    "tables": [
        {"fields": MARGIN_FIELDS, "data": [
            # 第一列是合計列，代號為空白，應被普通股過濾擋掉
            ["　", "合計", "320,493", "254,685", "2,713", "6,568,019", "6,631,114",
             "192,003,069", "25,169", "16,389", "654", "135,944", "126,510",
             "192,003,069", "5,567", "　"],
            ["2330", "台積電", "1,000", "1,500", "100", "50,000", "49,400",
             "999,999", "300", "200", "50", "3,500", "3,200", "999,999", "10", ""],
        ]},
    ],
}

FOREIGN_PAYLOAD = {
    "stat": "OK", "date": "20260907",
    "fields": ["證券代號", "證券名稱", "發行股數", "外資及陸資尚未取得股數",
               "全體外資及陸資持有股數", "全體外資及陸資持股比率"],
    "data": [["2330", "台積電", "25,930,380,458", "1,000,000",
              "18,000,000,000", "69.42"]],
}


@pytest.fixture
def fake_get(monkeypatch):
    def install(payload):
        monkeypatch.setattr(twse, "get_json", lambda url, params=None: payload)
    return install


class TestFetchPrice:
    def test_parses_ohlc(self, fake_get):
        fake_get(PRICE_PAYLOAD)
        rows = twse.fetch_price("20260907")
        assert rows["2330"]["close"] == 1210.0
        assert rows["2330"]["high"] == 1215.0
        assert rows["2330"]["volume"] == 25_000_000
        assert rows["2330"]["name"] == "台積電"

    def test_excludes_etf(self, fake_get):
        fake_get(PRICE_PAYLOAD)
        assert "0050" not in twse.fetch_price("20260907")

    def test_skips_stock_with_no_trade(self, fake_get):
        fake_get(PRICE_PAYLOAD)
        assert "1234" not in twse.fetch_price("20260907")


class TestFetchInstitutional:
    def test_uses_official_total_when_present(self, fake_get):
        fake_get(T86_PAYLOAD)
        row = twse.fetch_institutional("20260907")["2330"]
        assert row["total_net"] == 6_000_000
        assert row["foreign_net"] == 5_100_000      # 外資 + 外資自營商
        assert row["dealer_net"] == -300_000

    def test_sums_when_total_column_absent(self, fake_get):
        payload = dict(T86_PAYLOAD)
        payload["fields"] = T86_PAYLOAD["fields"][:-1]
        payload["data"] = [row[:-1] for row in T86_PAYLOAD["data"]]
        fake_get(payload)
        row = twse.fetch_institutional("20260907")["2330"]
        assert row["total_net"] == 5_000_000 + 100_000 + 1_200_000 - 300_000


class TestFetchMargin:
    def test_reads_the_margin_side_not_the_short_side(self, fake_get):
        """兩段欄名相同，錯一格就會把融券餘額當成融資餘額。"""
        fake_get(MARGIN_PAYLOAD)
        row = twse.fetch_margin("20260907")["2330"]
        assert row["margin_balance"] == 49_400     # 融資今日餘額
        assert row["short_balance"] == 3_200       # 融券今日餘額
        # 不能誤取前日餘額（50,000 / 3,500）
        assert row["margin_balance"] != 50_000
        assert row["short_balance"] != 3_500

    def test_excludes_the_total_row(self, fake_get):
        fake_get(MARGIN_PAYLOAD)
        rows = twse.fetch_margin("20260907")
        assert list(rows) == ["2330"]

    def test_prefers_labelled_headers_when_available(self, fake_get):
        """交易所日後若補上「融資今日餘額」這種欄名，應改用文字比對。"""
        fake_get({
            "stat": "OK", "date": "20260907",
            "fields": ["代號", "名稱", "融券今日餘額", "融資今日餘額"],
            "data": [["2330", "台積電", "3,200", "49,400"]],
        })
        row = twse.fetch_margin("20260907")["2330"]
        assert row["margin_balance"] == 49_400
        assert row["short_balance"] == 3_200

    def test_layout_change_fails_loudly(self, fake_get):
        """融資／融券只能靠位置區分，版面一變必須大聲失敗，
        而不是安靜地把融券餘額寫進融資欄位。"""
        swapped = list(MARGIN_FIELDS)
        # 把兩段的償還欄互換，模擬融券段被排到前面
        swapped[4], swapped[10] = swapped[10], swapped[4]
        fake_get({"stat": "OK", "date": "20260907", "fields": swapped,
                  "data": [MARGIN_PAYLOAD["tables"][0]["data"][1]]})
        with pytest.raises(RuntimeError, match="版面異常"):
            twse.fetch_margin("20260907")


class TestFetchForeign:
    def test_reads_shares_held(self, fake_get):
        fake_get(FOREIGN_PAYLOAD)
        row = twse.fetch_foreign("20260907")["2330"]
        assert row["foreign_shares"] == 18_000_000_000
        assert row["foreign_ratio"] == 69.42

    def test_derives_shares_from_ratio_when_column_missing(self, fake_get):
        """只有持股比率時，用發行股數還原庫存股數。"""
        payload = {
            "stat": "OK", "date": "20260907",
            "fields": ["證券代號", "證券名稱", "發行股數", "全體外資及陸資持股比率"],
            "data": [["2330", "台積電", "1,000,000,000", "50.00"]],
        }
        fake_get(payload)
        assert twse.fetch_foreign("20260907")["2330"]["foreign_shares"] == 500_000_000


class TestDateGuards:
    """回補歷史時，端點若忽略 date 參數會把今天的數字寫進過去的日期。
    這比抓不到資料危險得多，必須擋下來。"""

    def test_mismatched_date_raises(self, fake_get):
        fake_get({**PRICE_PAYLOAD, "date": "20260908"})
        with pytest.raises(DateMismatch):
            twse.fetch_price("20260907")

    def test_民國_date_in_title_is_accepted_when_matching(self, fake_get):
        payload = {k: v for k, v in PRICE_PAYLOAD.items() if k != "date"}
        payload["title"] = "115年09月07日 每日收盤行情(全部)"
        fake_get(payload)
        assert twse.fetch_price("20260907")["2330"]["close"] == 1210.0

    def test_民國_date_mismatch_is_caught(self, fake_get):
        payload = {k: v for k, v in PRICE_PAYLOAD.items() if k != "date"}
        payload["title"] = "115年09月08日 每日收盤行情(全部)"
        fake_get(payload)
        with pytest.raises(DateMismatch):
            twse.fetch_price("20260907")

    def test_undetectable_date_is_allowed_through(self, fake_get):
        """無法從回應判斷日期時只能放行，但不會假裝有驗證過。"""
        payload = {k: v for k, v in PRICE_PAYLOAD.items() if k not in ("date", "title")}
        fake_get(payload)
        assert "2330" in twse.fetch_price("20260907")


class TestNoData:
    def test_non_ok_stat_raises_no_data(self, fake_get):
        fake_get({"stat": "查詢日期小於81年1月4日，請重新查詢!"})
        with pytest.raises(NoDataForDate):
            twse.fetch_price("19900101")

    def test_empty_response_raises_no_data(self, fake_get):
        fake_get(None)
        with pytest.raises(NoDataForDate):
            twse.fetch_price("20260907")

    def test_unparseable_columns_raise_runtime_error(self, fake_get):
        fake_get({"stat": "OK", "date": "20260907",
                  "fields": ["日期", "指數"], "data": [["20260907", "23000"]]})
        with pytest.raises(RuntimeError, match="欄位解析失敗"):
            twse.fetch_price("20260907")
