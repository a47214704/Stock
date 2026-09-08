"""OpenAPI 規格的解析。

TPEx 的端點名稱無法從公開文件可靠推斷，猜錯時伺服器回 HTML 錯誤頁。
discover 直接讀官方規格，所以規格的形狀要吃得夠寬。
"""
from etl import config, verify
from etl.verify import _endpoint_paths, discover

OAS3 = {
    "openapi": "3.0.1",
    "paths": {
        "/v1/tpex_mainboard_daily_close_quotes": {
            "get": {"summary": "上櫃股票每日收盤行情"},
        },
        "/v1/tpex_3insti_trading_stock": {
            "get": {"description": "上櫃股票三大法人買賣明細"},
        },
        "/v1/tpex_margin_trading": {"get": {"summary": "上櫃股票融資融券餘額"}},
        "/v1/unrelated_endpoint": {"get": {}},
    },
}

OAS2 = {
    "swagger": "2.0",
    "paths": {
        "/v1/foo": {"post": {"summary": "只有 post 的端點"}},
        "/v1/bar": {"get": {"summary": "一般端點"}},
    },
}


class TestEndpointPaths:
    def test_reads_summary(self):
        paths = _endpoint_paths(OAS3)
        assert paths["/v1/tpex_mainboard_daily_close_quotes"] == "上櫃股票每日收盤行情"

    def test_falls_back_to_description(self):
        paths = _endpoint_paths(OAS3)
        assert paths["/v1/tpex_3insti_trading_stock"] == "上櫃股票三大法人買賣明細"

    def test_endpoint_without_note_is_still_listed(self):
        assert _endpoint_paths(OAS3)["/v1/unrelated_endpoint"] == ""

    def test_falls_back_to_any_method_when_no_get(self):
        assert _endpoint_paths(OAS2)["/v1/foo"] == "只有 post 的端點"

    def test_missing_paths_section(self):
        assert _endpoint_paths({"openapi": "3.0.1"}) == {}
        assert _endpoint_paths({}) == {}


class TestDiscover:
    def test_reports_configured_endpoints_that_do_not_exist(self, monkeypatch, capsys):
        monkeypatch.setattr(verify, "get_json", lambda url, params=None: OAS3)
        monkeypatch.setattr(config, "TPEX_ENDPOINTS", {
            "price": "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes",
            "institutional": "https://www.tpex.org.tw/openapi/v1/tpex_3itrade_hedge_daily",
        })
        problems = discover("tpex")
        out = capsys.readouterr().out

        assert problems == 1                       # 只有 institutional 對不上
        assert "tpex_mainboard_daily_close_quotes" in out and "✓ 存在" in out
        assert "tpex_3itrade_hedge_daily" in out and "✗ 不存在" in out
        # 要給出候選，而不是只說「找不到」
        assert "tpex_3insti_trading_stock" in out
        # 要能直接貼回設定檔
        assert "TPEX_ENDPOINTS = {" in out

    def test_all_endpoints_present_reports_no_problem(self, monkeypatch, capsys):
        monkeypatch.setattr(verify, "get_json", lambda url, params=None: OAS3)
        monkeypatch.setattr(config, "TPEX_ENDPOINTS", {
            "margin": "https://www.tpex.org.tw/openapi/v1/tpex_margin_trading",
        })
        assert discover("tpex") == 0
        assert "✗ 不存在" not in capsys.readouterr().out

    def test_grep_filters_by_path_and_note(self, monkeypatch, capsys):
        monkeypatch.setattr(verify, "get_json", lambda url, params=None: OAS3)
        discover("tpex", grep="法人")
        out = capsys.readouterr().out
        assert "tpex_3insti_trading_stock" in out
        assert "tpex_margin_trading" not in out

    def test_fetch_failure_is_reported_not_raised(self, monkeypatch, capsys):
        def boom(url, params=None):
            raise RuntimeError("連不上")
        monkeypatch.setattr(verify, "get_json", boom)
        assert discover("tpex") == 1
        assert "取得規格失敗" in capsys.readouterr().out

    def test_unknown_market(self, capsys):
        assert discover("nowhere") == 1
        assert "沒有 nowhere" in capsys.readouterr().out

    def test_spec_without_paths_is_reported(self, monkeypatch, capsys):
        monkeypatch.setattr(verify, "get_json", lambda url, params=None: {"x": 1})
        assert discover("tpex") == 1
        assert "沒有 paths" in capsys.readouterr().out
