"""端到端：每日快照 → 面板 → 選股 → 前端產出。

證明整條線接得起來，而不只是各別函式正確。
"""
import json
import os
from datetime import date, timedelta

import pytest

from etl import build as build_mod
from etl import config, storage
from etl.storage import build_panel, save_daily
from tests.synthetic import flat_series, ideal_series


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    """把所有輸出路徑導到暫存目錄。"""
    for name, sub in [
        ("DATA_DIR", "data"), ("DAILY_DIR", "data/daily"),
        ("HISTORY_DIR", "data/history"),
    ]:
        monkeypatch.setattr(config, name, str(tmp_path / sub))
    for name, sub in [
        ("STOCK_INFO_PATH", "data/stock_info.json"),
        ("SIGNALS_PATH", "data/signals.json"),
        ("SCREEN_ALL_PATH", "data/screen_all.json"),
    ]:
        monkeypatch.setattr(config, name, str(tmp_path / sub))
    return tmp_path


def seed_snapshots(days: int = 200) -> list[str]:
    """把合成序列拆成一天一個快照寫進去，模擬每日累積的真實情形。"""
    winner = ideal_series(days)
    loser = flat_series(days)
    start = date(2026, 1, 5)

    keys = []
    trading_day = start
    for i in range(days):
        while trading_day.weekday() >= 5:
            trading_day += timedelta(days=1)
        key = storage.to_key(trading_day)
        stocks = {}
        for stock_id, series in (("9999", winner), ("8888", loser)):
            stocks[stock_id] = {
                field: (series[field][i] if isinstance(series.get(field), list) else None)
                for field in storage.SNAPSHOT_FIELDS
            }
            stocks[stock_id]["name"] = series["name"]
            stocks[stock_id]["market"] = series["market"]
        save_daily(key, stocks, ["twse"])
        keys.append(key)
        trading_day += timedelta(days=1)
    return keys


class TestSnapshotRoundTrip:
    def test_snapshot_is_written_and_read_back(self, workspace):
        save_daily("2026-09-07", {"2330": {"close": 1210.0, "market": "twse"}}, ["twse"])
        loaded = storage.load_daily("2026-09-07")
        assert loaded["date"] == "2026-09-07"
        rows = dict(storage.snapshot_rows(loaded))
        assert rows["2330"]["close"] == 1210.0
        assert rows["2330"]["market"] == "twse"

    def test_snapshot_is_stored_columnar(self, workspace):
        """欄位名只出現一次，每檔是值陣列——這是壓縮體積的關鍵。"""
        save_daily("2026-09-07", {"2330": {"close": 1210.0, "market": "twse"}}, ["twse"])
        loaded = storage.load_daily("2026-09-07")
        assert loaded["version"] == storage.SNAPSHOT_VERSION
        assert loaded["fields"] == list(storage.SNAPSHOT_FIELDS)
        row = loaded["stocks"]["2330"]
        assert isinstance(row, list) and len(row) == len(storage.SNAPSHOT_FIELDS)

    def test_reads_legacy_nested_snapshots(self, workspace):
        """早期的巢狀格式仍要讀得出來，否則換格式等於丟掉既有歷史。"""
        legacy = {"date": "2026-09-04", "markets": ["twse"], "count": 1,
                  "stocks": {"2330": {"close": 1200.0, "market": "twse"}}}
        storage.write_json(storage.daily_path("2026-09-04"), legacy, compact=True)
        rows = dict(storage.snapshot_rows(storage.load_daily("2026-09-04")))
        assert rows["2330"]["close"] == 1200.0

    def test_panel_mixes_legacy_and_columnar(self, workspace):
        legacy = {"date": "2026-09-04", "markets": ["twse"], "count": 1,
                  "stocks": {"2330": {"close": 1200.0, "market": "twse"}}}
        storage.write_json(storage.daily_path("2026-09-04"), legacy, compact=True)
        save_daily("2026-09-07", {"2330": {"close": 1210.0, "market": "twse"}}, ["twse"])
        dates, panel = build_panel(10)
        assert dates == ["2026-09-04", "2026-09-07"]
        assert panel["2330"]["close"] == [1200.0, 1210.0]

    def test_snapshots_are_one_file_per_day(self, workspace):
        keys = seed_snapshots(10)
        files = sorted(os.listdir(config.DAILY_DIR))
        assert len(files) == 10
        assert files[0] == f"{keys[0]}.json"

    def test_has_daily_detects_existing(self, workspace):
        seed_snapshots(3)
        assert storage.has_daily(storage.list_daily_dates()[0])
        assert not storage.has_daily("1999-01-01")


class TestPatchDaily:
    """快照原則上 append-only，補抓延遲公布的報表是唯一例外。

    外資持股當天抓不到（TWSE 回「查詢日期大於可查詢最大日期」），
    要等下一個交易日才公布，只能事後補進既有快照。
    """

    def test_merges_new_fields(self, workspace):
        save_daily("2026-09-07", {
            "2330": {"close": 1210.0, "market": "twse", "foreign_shares": None},
        }, ["twse"])
        changed = storage.patch_daily("2026-09-07", {
            "2330": {"foreign_shares": 18_000_000_000, "foreign_ratio": 69.4},
        })
        assert changed == 1
        rows = dict(storage.snapshot_rows(storage.load_daily("2026-09-07")))
        assert rows["2330"]["foreign_shares"] == 18_000_000_000
        assert rows["2330"]["close"] == 1210.0        # 原有欄位不動

    def test_ignores_stocks_absent_from_the_snapshot(self, workspace):
        """價格是錨。沒有 K 線的個股不該憑空長出籌碼資料。"""
        save_daily("2026-09-07", {"2330": {"close": 1210.0, "market": "twse"}}, ["twse"])
        changed = storage.patch_daily("2026-09-07", {
            "2330": {"foreign_shares": 100},
            "9999": {"foreign_shares": 200},       # 當天沒有這檔的行情
        })
        assert changed == 1
        rows = dict(storage.snapshot_rows(storage.load_daily("2026-09-07")))
        assert "9999" not in rows

    def test_missing_snapshot_is_a_noop(self, workspace):
        assert storage.patch_daily("1999-01-01", {"2330": {"foreign_shares": 1}}) == 0

    def test_keeps_the_columnar_format(self, workspace):
        save_daily("2026-09-07", {"2330": {"close": 1210.0, "market": "twse"}}, ["twse"])
        storage.patch_daily("2026-09-07", {"2330": {"foreign_shares": 5}})
        loaded = storage.load_daily("2026-09-07")
        assert loaded["version"] == storage.SNAPSHOT_VERSION
        assert isinstance(loaded["stocks"]["2330"], list)

    def test_preserves_markets_list(self, workspace):
        save_daily("2026-09-07", {"2330": {"close": 1.0, "market": "twse"}}, ["twse", "tpex"])
        storage.patch_daily("2026-09-07", {"2330": {"foreign_shares": 5}})
        assert storage.load_daily("2026-09-07")["markets"] == ["twse", "tpex"]

    def test_patched_values_reach_the_panel(self, workspace):
        """補進去的值必須真的進到選股用的時間序列。"""
        for day, close in (("2026-09-07", 100.0), ("2026-09-08", 101.0)):
            save_daily(day, {"2330": {"close": close, "market": "twse"}}, ["twse"])
        storage.patch_daily("2026-09-07", {"2330": {"foreign_shares": 10}})
        storage.patch_daily("2026-09-08", {"2330": {"foreign_shares": 20}})
        _, panel = build_panel(10)
        assert panel["2330"]["foreign_shares"] == [10, 20]


class TestBuildPanel:
    def test_series_align_with_dates(self, workspace):
        seed_snapshots(30)
        dates, panel = build_panel(300)
        assert len(dates) == 30
        for series in panel.values():
            assert len(series["close"]) == len(dates)

    def test_missing_stock_on_a_day_is_padded_with_none(self, workspace):
        save_daily("2026-09-07", {"1111": {"close": 10.0, "market": "twse"}}, ["twse"])
        save_daily("2026-09-08", {"2222": {"close": 20.0, "market": "twse"}}, ["twse"])
        dates, panel = build_panel(10)
        assert panel["1111"]["close"] == [10.0, None]
        assert panel["2222"]["close"] == [None, 20.0]

    def test_only_the_requested_number_of_days(self, workspace):
        seed_snapshots(30)
        dates, _ = build_panel(10)
        assert len(dates) == 10


class TestBuild:
    def test_finds_the_stock_matching_every_condition(self, workspace):
        seed_snapshots()
        summary = build_mod.build()

        assert summary["stocks"] == 2
        assert summary["matched"] == 1

        signals = json.loads(open(config.SIGNALS_PATH, encoding="utf-8").read())
        matched = [r for r in signals["results"] if r["pass_all"]]
        assert [r["stock_id"] for r in matched] == ["9999"]
        assert matched[0]["score"] == 6

    def test_signals_carry_the_reasoning(self, workspace):
        seed_snapshots()
        build_mod.build()
        signals = json.loads(open(config.SIGNALS_PATH, encoding="utf-8").read())
        winner = next(r for r in signals["results"] if r["stock_id"] == "9999")

        ma = winner["conditions"]["ma_turn_up"]
        assert ma["deduction"] is not None and ma["future_deduction_mean"] is not None
        assert winner["conditions"]["margin_declining"]["change_pct"] < 0
        assert winner["conditions"]["foreign_increasing"]["change_pct"] > 0
        assert winner["conditions"]["macd"]["turned_red"] is True
        # 門檻要一起輸出，否則事後看不出這份名單是用什麼標準跑的
        assert signals["criteria"]["ma_period"] == 60

    def test_screen_all_covers_the_whole_universe(self, workspace):
        seed_snapshots()
        build_mod.build()
        screen = json.loads(open(config.SCREEN_ALL_PATH, encoding="utf-8").read())
        assert len(screen["rows"]) == 2
        assert screen["columns"][0] == "stock_id"

    def test_history_written_only_for_shortlisted_stocks(self, workspace):
        seed_snapshots()
        build_mod.build()
        files = os.listdir(config.HISTORY_DIR)
        assert files == ["9999.json"], "歷史檔應只為入選名單產生，避免 repo 無謂膨脹"

        history = json.loads(open(os.path.join(config.HISTORY_DIR, "9999.json"),
                                  encoding="utf-8").read())
        assert len(history["dates"]) == len(history["close"]) == 200
        assert history["ma60"][-1] is not None
        assert history["macd_osc"][-1] is not None
        # 扣抵值序列：第 i 天即將被扣掉的是 60 天前那根
        assert history["deduction"][-1] == history["close"][-60]

    def test_history_is_pruned_when_a_stock_drops_out(self, workspace):
        seed_snapshots()
        build_mod.build()
        stale = os.path.join(config.HISTORY_DIR, "7777.json")
        with open(stale, "w") as fh:
            fh.write("{}")
        summary = build_mod.build()
        assert summary["history_pruned"] == 1
        assert not os.path.exists(stale)

    def test_build_without_data_does_not_crash(self, workspace):
        assert build_mod.build()["stocks"] == 0


class TestCoverage:
    def test_reports_what_is_not_ready_yet(self, workspace):
        # 40 天：夠算 MACD（需 26+9=35 天），但不足以判斷任何三個月的條件。
        # 這正是專案剛上線那幾個月的狀態。
        seed_snapshots(40)
        info = build_mod.coverage()
        assert info["trading_days"] == 40
        assert info["ready"]["macd"] is True
        assert info["ready"]["consolidation"] is False
        assert info["ready"]["ma_turn_up"] is False
        assert info["ready"]["margin_declining"] is False
        assert info["ready"]["foreign_increasing"] is False

    def test_everything_ready_with_full_history(self, workspace):
        seed_snapshots()
        info = build_mod.coverage()
        assert all(info["ready"].values())
        assert info["stocks"] == 2
