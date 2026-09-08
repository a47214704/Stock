"""選股條件。"""
from etl.config import ScreenConfig
from etl.screen import (
    INSUFFICIENT, check_consolidation, check_foreign_increasing,
    check_institutional_net_buy, check_macd, check_margin_declining,
    check_ma_turn_up, screen_stock,
)
from tests.synthetic import flat_series, ideal_closes, ideal_series

CFG = ScreenConfig()


class TestInsufficientData:
    """歷史不足必須標成 insufficient，不能跟「條件不成立」混為一談——
    專案剛上線、資料還在往前累積的那幾個月全靠這個區分。"""

    def test_short_price_history(self):
        short = [50.0] * 30
        assert check_consolidation(short, short, short, CFG)["status"] == INSUFFICIENT
        assert check_ma_turn_up(short, CFG)["status"] == INSUFFICIENT
        assert check_macd(short, CFG)["status"] == INSUFFICIENT

    def test_short_chip_history(self):
        assert check_margin_declining([100] * 10, CFG)["status"] == INSUFFICIENT
        assert check_foreign_increasing([100] * 10, CFG)["status"] == INSUFFICIENT

    def test_insufficient_is_not_a_pass(self):
        result = check_ma_turn_up([50.0] * 30, CFG)
        assert result["pass"] is False

    def test_missing_data_listed_on_the_stock(self):
        result = screen_stock("1234", flat_series(n=20))
        assert set(result["insufficient"]) >= {"consolidation", "ma_turn_up", "macd"}
        assert result["pass_all"] is False


class TestConsolidation:
    def test_tight_box_passes(self):
        closes = ideal_closes()
        assert check_consolidation(
            [c * 1.01 for c in closes], [c * 0.99 for c in closes], closes, CFG)["pass"]

    def test_trending_stock_fails_on_width(self):
        closes = [float(50 + i) for i in range(200)]
        result = check_consolidation(closes, closes, closes, CFG)
        assert result["pass"] is False
        assert result["narrow"] is False

    def test_reports_actual_run_length(self):
        """過與不過看固定 60 日窗口，run_days 另外回報箱型實際走了多久。"""
        closes = ideal_closes()
        result = check_consolidation(
            [c * 1.01 for c in closes], [c * 0.99 for c in closes], closes, CFG)
        assert result["pass"] is True
        assert result["days"] == CFG.consolidation_window      # 判定用的窗口
        assert result["run_days"] > CFG.consolidation_window   # 實際走得更久
        assert result["drift_ratio"] < CFG.consolidation_max_drift_ratio

    def test_run_length_absent_when_not_a_box(self):
        closes = [float(50 + i) for i in range(200)]
        result = check_consolidation(closes, closes, closes, CFG)
        assert result["pass"] is False
        assert result["run_days"] is None

    def test_slow_decline_fails_even_when_narrow(self):
        """緩跌股的高低區間可能夠窄，但季線持續下彎，不該算盤整。

        每日跌 0.15 元：近 60 日區間約 12%，寬度是過關的，
        但季線斜率約 -0.21%/日，遠超過 flat 的門檻。"""
        closes = [100 - 0.15 * i for i in range(200)]
        result = check_consolidation(closes, closes, closes, CFG)
        assert result["narrow"] is True
        assert result["flat"] is False
        assert result["pass"] is False

    def test_very_gentle_drift_still_counts_as_consolidation(self):
        """門檻的另一側：三個月漂移不到 5% 仍視為盤整，避免把窄幅整理誤殺。"""
        closes = [100 - 0.06 * i for i in range(200)]
        result = check_consolidation(closes, closes, closes, CFG)
        assert result["flat"] is True
        assert result["pass"] is True


class TestMATurnUp:
    def test_ideal_pattern_passes(self):
        result = check_ma_turn_up(ideal_closes(), CFG)
        assert result["pass"] is True
        assert result["still_falling"] is True
        assert result["rises_tomorrow"] is True
        assert result["future_supports"] is True
        assert result["deducting_low"] is True

    def test_already_rising_ma_is_rejected(self):
        """季線早就翻揚的股票不算「剛剛要往上」。"""
        closes = [float(50 + i * 0.5) for i in range(200)]
        result = check_ma_turn_up(closes, CFG)
        assert result["still_falling"] is False
        assert result["pass"] is False

    def test_falling_stock_fails_because_close_is_below_deduction(self):
        closes = [float(200 - i * 0.5) for i in range(200)]
        result = check_ma_turn_up(closes, CFG)
        assert result["rises_tomorrow"] is False
        assert result["pass"] is False


class TestMarginDeclining:
    def test_steady_decline_passes(self):
        assert check_margin_declining([40000 - 130 * i for i in range(200)], CFG)["pass"]

    def test_rising_margin_fails(self):
        assert not check_margin_declining([10000 + 50 * i for i in range(200)], CFG)["pass"]

    def test_small_decline_below_threshold_fails(self):
        # 只減少 2%，未達 10% 門檻
        series = [10000 - 3 * i for i in range(70)]
        result = check_margin_declining(series, CFG)
        assert result["downtrend"] is True
        assert result["declined"] is False
        assert result["pass"] is False

    def test_noise_does_not_break_the_trend(self):
        """單日跳動不該推翻三個月的趨勢——這是用迴歸斜率而非頭尾相減的理由。"""
        series = [40000 - 130 * i + (900 if i % 7 == 0 else 0) for i in range(200)]
        assert check_margin_declining(series, CFG)["pass"]


class TestForeignIncreasing:
    def test_accumulation_passes(self):
        assert check_foreign_increasing([int(3e8 + 9e5 * i) for i in range(200)], CFG)["pass"]

    def test_reduction_fails(self):
        assert not check_foreign_increasing([int(3e8 - 9e5 * i) for i in range(200)], CFG)["pass"]

    def test_flat_holding_fails(self):
        assert not check_foreign_increasing([int(3e8)] * 200, CFG)["pass"]

    def test_uses_shares_when_available(self):
        result = check_foreign_increasing(
            [int(3e8 + 9e5 * i) for i in range(200)], CFG,
            ratio=[10.0] * 200)          # 比例持平也不該影響結果
        assert result["basis"] == "shares"
        assert result["pass"] is True

    def test_falls_back_to_ratio_when_shares_missing(self):
        """上櫃的來源只給持股比例、沒有股數，此時用比例判斷趨勢。"""
        result = check_foreign_increasing(
            [None] * 200, CFG, ratio=[20.0 + 0.02 * i for i in range(200)])
        assert result["basis"] == "ratio"
        assert result["pass"] is True

    def test_ratio_fallback_still_needs_an_uptrend(self):
        result = check_foreign_increasing(
            [None] * 200, CFG, ratio=[20.0 - 0.02 * i for i in range(200)])
        assert result["basis"] == "ratio"
        assert result["pass"] is False

    def test_insufficient_when_neither_is_available(self):
        result = check_foreign_increasing([None] * 200, CFG, ratio=[None] * 200)
        assert result["status"] == INSUFFICIENT


class TestInstitutionalNetBuy:
    def test_net_buy_passes(self):
        assert check_institutional_net_buy([0] * 60 + [100, 200, 300, 400, 500], CFG)["pass"]

    def test_net_sell_fails(self):
        assert not check_institutional_net_buy([0] * 60 + [-100, -200, 50, 0, 10], CFG)["pass"]

    def test_only_the_recent_window_counts(self):
        """窗口外的大買超不該把今天的賣超蓋掉。"""
        series = [999999] * 60 + [-100, -100, -100, -100, -100]
        assert not check_institutional_net_buy(series, CFG)["pass"]


class TestMACD:
    def test_ideal_pattern_turns_red(self):
        result = check_macd(ideal_closes(), CFG)
        assert result["pass"] is True
        assert result["turned_red"] is True
        assert result["converging"] is True

    def test_flat_price_does_not_trigger(self):
        assert not check_macd([50.0] * 200, CFG)["pass"]

    def test_long_standing_red_is_not_a_fresh_cross(self):
        """已經紅很久的不算「由綠轉紅」。"""
        closes = [100 - 0.02 * i * i for i in range(60)] + [28 + 1.5 * i for i in range(60)]
        result = check_macd(closes, CFG)
        assert result["days_since_cross"] > CFG.macd_within_days
        assert result["pass"] is False


class TestScreenStock:
    def test_ideal_stock_matches_every_group(self):
        result = screen_stock("9999", ideal_series())
        assert result["pass_all"] is True, result["conditions"]
        assert result["score"] == 6
        assert all(result["groups"].values())

    def test_flat_stock_matches_nothing(self):
        result = screen_stock("8888", flat_series())
        assert result["pass_all"] is False
        assert result["groups"]["ma_turn_up"] is False
        assert result["groups"]["macd"] is False

    def test_result_carries_evidence_for_the_ui(self):
        """入選理由要能顯示給使用者看，不能只有一個布林值。"""
        result = screen_stock("9999", ideal_series())
        ma = result["conditions"]["ma_turn_up"]
        assert ma["deduction"] is not None
        assert ma["future_deduction_mean"] is not None
        assert result["conditions"]["margin_declining"]["change_pct"] < 0
        assert result["conditions"]["foreign_increasing"]["change_pct"] > 0

    def test_chips_group_needs_all_three(self):
        series = ideal_series()
        series["margin_balance"] = [int(1e4 + 50 * i) for i in range(200)]   # 融資反而增加
        result = screen_stock("9999", series)
        assert result["groups"]["chips"] is False
        assert result["pass_all"] is False
