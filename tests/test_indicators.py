"""指標的數學正確性。"""
import math

import pytest

from etl.indicators import (
    consolidation, consolidation_run, ema, linreg_slope, ma_deduction,
    ma_slope_pct, macd, macd_turns_red, percentile_rank, sma, trend,
)


class TestSMA:
    def test_basic(self):
        assert sma([1, 2, 3, 4, 5], 3) == [None, None, 2.0, 3.0, 4.0]

    def test_shorter_than_period(self):
        assert sma([1, 2], 5) == [None, None]

    def test_constant_series(self):
        assert sma([7] * 10, 4)[-1] == 7.0

    def test_rejects_bad_period(self):
        with pytest.raises(ValueError):
            sma([1, 2, 3], 0)


class TestEMA:
    def test_seeded_with_sma(self):
        # period=2：index1 種子 = (1+2)/2 = 1.5；index2 = 3*(2/3) + 1.5*(1/3) = 2.5
        assert ema([1, 2, 3], 2) == [None, 1.5, 2.5]

    def test_constant_series_stays_constant(self):
        assert ema([5] * 20, 6)[-1] == pytest.approx(5.0)

    def test_insufficient_data(self):
        assert ema([1, 2], 5) == [None, None]


class TestMACD:
    def test_constant_price_gives_zero(self):
        result = macd([50.0] * 100)
        assert result["dif"][-1] == pytest.approx(0.0)
        assert result["osc"][-1] == pytest.approx(0.0)

    def test_osc_equals_dif_minus_dea(self):
        closes = [100 + 10 * math.sin(i / 7) for i in range(120)]
        r = macd(closes)
        for dif, dea, osc in zip(r["dif"], r["dea"], r["osc"]):
            if osc is not None:
                assert osc == pytest.approx(dif - dea)

    def test_leading_values_are_none(self):
        r = macd(list(range(1, 60)))
        # DIF 要等 slow=26 根才有值
        assert r["dif"][24] is None and r["dif"][25] is not None
        # OSC 還要再等 signal=9 根
        assert r["osc"][32] is None and r["osc"][33] is not None

    def test_linear_trend_has_constant_momentum(self):
        """等差變動的動能是常數，OSC 會收斂到 0——這是 MACD 的正確行為，
        代表柱狀體衡量的是加速度而不是漲跌本身。"""
        osc = [v for v in macd([100 - i for i in range(80)])["osc"] if v is not None]
        assert abs(osc[-1]) < 1e-6

    def test_accelerating_decline_then_reversal_crosses_up(self):
        # 先加速下跌（綠柱擴大），再反轉走揚（柱狀體翻紅）
        closes = [100 - 0.02 * i * i for i in range(60)] + [28 + 1.5 * i for i in range(40)]
        osc = [v for v in macd(closes)["osc"] if v is not None]
        assert min(osc) < 0 < max(osc)
        assert osc[-1] > 0

    def test_osc_sign_flips_exactly_once_on_a_clean_reversal(self):
        closes = [100 - 0.02 * i * i for i in range(60)] + [28 + 1.5 * i for i in range(40)]
        osc = [v for v in macd(closes)["osc"] if v is not None]
        flips = sum(1 for a, b in zip(osc, osc[1:]) if (a <= 0) != (b <= 0))
        assert flips == 1


class TestMACDTurnsRed:
    def test_detects_cross_up(self):
        state = macd_turns_red([-5, -3, -2, -1, 0.5], converge_days=3)
        assert state["turned_red"] is True
        assert state["converging"] is True
        assert state["converge_days"] == 3

    def test_no_cross_when_still_negative(self):
        assert macd_turns_red([-5, -4, -3, -2])["turned_red"] is False

    def test_no_cross_when_already_red_yesterday(self):
        assert macd_turns_red([-1, 0.5, 1.0])["turned_red"] is False

    def test_cross_without_convergence(self):
        # 綠柱一路擴大後直接跳紅，不算收斂後轉折
        state = macd_turns_red([-1, -2, -3, -4, 0.5], converge_days=3)
        assert state["turned_red"] is True
        assert state["converging"] is False

    def test_zero_counts_as_green(self):
        assert macd_turns_red([-1, 0.0, 0.3])["turned_red"] is True

    def test_convergence_tolerates_noise(self):
        """「連續 N 天嚴格縮小」一次跳動就歸零，對真實資料太脆。

        這組數字取自實跑：綠柱絕對值 0.009 → 0.031 → 0.005，整段明顯在衰竭，
        但嚴格連續數只有 1。改用迴歸斜率判斷才抓得到。
        """
        state = macd_turns_red([-0.009, -0.031, -0.005, 0.042], converge_days=3)
        assert state["turned_red"] is True
        assert state["converge_days"] == 1          # 嚴格連續數確實只有 1
        assert state["converge_slope"] < 0
        assert state["converging"] is True

    def test_expanding_green_is_not_converging(self):
        state = macd_turns_red([-0.005, -0.020, -0.040, 0.010], converge_days=3)
        assert state["converge_slope"] > 0
        assert state["converging"] is False

    def test_reports_green_run_length(self):
        state = macd_turns_red([-1, -2, -3, 0.5])
        assert state["green_run"] == 3

    def test_single_green_bar_cannot_show_convergence(self):
        state = macd_turns_red([0.5, -0.1, 0.2], converge_days=3)
        assert state["green_run"] == 1
        assert state["converge_slope"] is None
        assert state["converging"] is False


class TestMADeduction:
    """扣抵值是整套季線判斷的地基，這裡驗證它的數學恆等式。"""

    def test_deduction_is_the_value_about_to_leave_the_window(self):
        closes = [float(i) for i in range(100)]
        result = ma_deduction(closes, period=60)
        # 目前均線涵蓋 closes[40:100]，下一步會扣掉 closes[40]
        assert result["deduction"] == closes[100 - 60]
        assert result["deduction"] == 40.0

    def test_ma_step_identity(self):
        """MA[t+1] - MA[t] 必須等於 (新收盤 - 扣抵值) / period。"""
        closes = [100 + 13 * math.sin(i / 5) for i in range(90)]
        period = 60
        result = ma_deduction(closes, period=period)
        ma_today = sma(closes, period)[-1]

        for tomorrow in (80.0, 100.0, 130.0):
            ma_tomorrow = sma(closes + [tomorrow], period)[-1]
            expected = (tomorrow - result["deduction"]) / period
            assert ma_tomorrow - ma_today == pytest.approx(expected)

    def test_rises_tomorrow_flag_matches_reality(self):
        closes = [float(i) for i in range(100)]       # 一路上漲，扣低
        result = ma_deduction(closes, period=60)
        assert result["rises_tomorrow"] is True

        falling = [float(100 - i) for i in range(100)]  # 一路下跌，扣高
        assert ma_deduction(falling, period=60)["rises_tomorrow"] is False

    def test_future_deductions_are_the_next_n_to_leave(self):
        closes = [float(i) for i in range(100)]
        result = ma_deduction(closes, period=60, forward_days=5)
        assert result["future_deductions"] == [40.0, 41.0, 42.0, 43.0, 44.0]

    def test_insufficient_history(self):
        assert ma_deduction([1.0] * 30, period=60) is None


class TestMASlope:
    def test_uptrend_positive_downtrend_negative(self):
        rising = [float(i) for i in range(100)]
        falling = [float(100 - i) for i in range(100)]
        assert ma_slope_pct(rising, 60, 5) > 0
        assert ma_slope_pct(falling, 60, 5) < 0

    def test_flat_is_zero(self):
        assert ma_slope_pct([50.0] * 100, 60, 5) == pytest.approx(0.0)


class TestLinregSlope:
    def test_perfect_lines(self):
        assert linreg_slope([1, 2, 3, 4]) == pytest.approx(1.0)
        assert linreg_slope([4, 3, 2, 1]) == pytest.approx(-1.0)

    def test_flat(self):
        assert linreg_slope([3, 3, 3, 3]) == pytest.approx(0.0)

    def test_ignores_none_and_needs_two_points(self):
        assert linreg_slope([None, 1, 2, 3]) == pytest.approx(1.0)
        assert linreg_slope([None, 5]) is None
        assert linreg_slope([]) is None


class TestPercentileRank:
    def test_ranks(self):
        pop = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
        assert percentile_rank(1, pop) == pytest.approx(0.1)
        assert percentile_rank(5, pop) == pytest.approx(0.5)
        assert percentile_rank(10, pop) == pytest.approx(1.0)

    def test_empty_population(self):
        assert percentile_rank(5, []) is None


class TestConsolidation:
    def test_narrow_range(self):
        closes = [100 + (i % 3) for i in range(60)]
        box = consolidation(closes, closes, closes, 60)
        assert box["range_pct"] < 0.05

    def test_wide_range(self):
        closes = [float(50 + i * 2) for i in range(60)]
        box = consolidation(closes, closes, closes, 60)
        assert box["range_pct"] > 0.5

    def test_position_within_box(self):
        closes = [float(x) for x in [100] * 59 + [110]]
        box = consolidation([110.0] * 60, [100.0] * 60, closes, 60)
        assert box["position"] == pytest.approx(1.0)

    def test_insufficient_data(self):
        assert consolidation([1.0] * 10, [1.0] * 10, [1.0] * 10, 60) is None


class TestConsolidationRun:
    """盤整持續天數。兩步判定：先用幅度往前擴張，再對最終區段檢驗淨漂移。"""

    MAX_RANGE = 0.15
    MAX_DRIFT = 0.5

    def run(self, closes, **kwargs):
        highs = [c * 1.01 for c in closes]
        lows = [c * 0.99 for c in closes]
        return consolidation_run(highs, lows, closes,
                                 kwargs.get("max_range", self.MAX_RANGE),
                                 kwargs.get("max_drift", self.MAX_DRIFT),
                                 kwargs.get("min_window", 20))

    def test_flat_series_runs_the_whole_length(self):
        result = self.run([100.0 + (i % 3) * 0.5 for i in range(160)])
        assert result["days"] == 160
        assert result["drift_ratio"] < 0.05

    def test_uptrend_is_not_a_consolidation(self):
        """關鍵案例：趨勢股在區間拉開前必然有一段『夠窄』的天數，
        只看幅度會把一路上漲報成盤整一個月。淨漂移檢驗就是為了擋這個。"""
        assert self.run([float(50 + i) for i in range(160)]) is None

    def test_slow_decline_is_not_a_consolidation(self):
        assert self.run([100 - 0.15 * i for i in range(200)]) is None

    def test_run_stops_at_the_edge_of_the_box(self):
        """崩跌後才進入箱型：持續天數應該約等於箱型長度，不含崩跌段。"""
        closes = [200 - 1.5 * i for i in range(60)] + [110 + (i % 4) * 0.8 for i in range(100)]
        result = self.run(closes)
        # 幅度門檻允許往前多吃幾天崩跌，但不該回推到整段崩跌
        assert 100 <= result["days"] <= 115

    def test_breakout_ends_the_run(self):
        """已經突破起漲的股票，現在不是在盤整。"""
        closes = [100.0 + (i % 3) * 0.5 for i in range(140)] + [101 + i * 0.9 for i in range(20)]
        assert self.run(closes) is None

    def test_oscillating_box_survives_a_directional_final_leg(self):
        """箱型內部本來就有方向性波段。最後二十天剛好是其中一段上行時，
        整個箱型不該被否定——這是漂移檢驗只做在最終區段而非逐長度的理由。"""
        closes = [100 + 6 * math.sin(i / 9) for i in range(120)]
        result = self.run(closes)
        assert result is not None
        assert result["days"] >= 40

    def test_returns_none_below_min_window(self):
        assert self.run([100.0] * 10, min_window=20) is None

    def test_data_gap_stops_the_run(self):
        closes = [100.0] * 50 + [None] + [100.0] * 40
        highs = [None if c is None else c * 1.01 for c in closes]
        lows = [None if c is None else c * 0.99 for c in closes]
        result = consolidation_run(highs, lows, closes, 0.15, 0.5, 20)
        assert result["days"] == 40          # 只算到斷點為止

    def test_tighter_drift_threshold_rejects_more(self):
        closes = [100 + 6 * math.sin(i / 9) for i in range(120)]
        assert self.run(closes) is not None
        assert self.run(closes, max_drift=0.05) is None

    def test_reports_the_box_bounds(self):
        closes = [100.0 if i % 2 else 104.0 for i in range(60)]
        result = self.run(closes)
        assert result["days"] == 60
        assert result["low"] == pytest.approx(99.0)     # 100 × 0.99
        assert result["high"] == pytest.approx(105.04)  # 104 × 1.01

    def test_a_single_step_to_a_new_level_is_not_a_box(self):
        """價格換到另一個水位後停住，淨漂移會超過箱寬——那是重新評價，不是箱型。"""
        assert self.run([100.0] * 30 + [104.0] * 30) is None


class TestTrend:
    def test_declining_series(self):
        t = trend([100, 95, 90, 85, 80], 5)
        assert t["change_pct"] == pytest.approx(-0.2)
        assert t["slope"] < 0

    def test_rising_series(self):
        t = trend([80, 85, 90, 95, 100], 5)
        assert t["change_pct"] == pytest.approx(0.25)
        assert t["slope"] > 0

    def test_ignores_none(self):
        t = trend([None, 100, 90, 80], 4)
        assert t["points"] == 3
        assert t["change_pct"] == pytest.approx(-0.2)

    def test_zero_base_does_not_divide_by_zero(self):
        t = trend([0, 5, 10], 3)
        assert t["change_pct"] is None
