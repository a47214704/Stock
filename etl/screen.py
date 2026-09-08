"""把指標組合成選股條件。

四組條件：
  1. 盤整三個月以上
  2. 季線扣底、剛要翻揚
  3. 籌碼面（融資遞減 + 外資庫存增加 + 三大法人合計買超）
  4. MACD 收斂後由綠轉紅

每個條件回傳的不只是 True/False，還帶著判斷依據的數字，前端才能顯示
「為什麼入選」。資料長度不足時標記 status="insufficient"，與「條件不成立」
區分開來——專案剛上線、歷史還在累積的那幾個月，這個區別很重要。
"""
from __future__ import annotations

from typing import Sequence

from .config import ScreenConfig, DEFAULT_SCREEN
from .indicators import (
    consolidation, ma_deduction, ma_slope_pct, macd, macd_turns_red,
    percentile_rank, trend,
)

PASS = "pass"
FAIL = "fail"
INSUFFICIENT = "insufficient"


def _result(status: str, **detail) -> dict:
    return {"status": status, "pass": status == PASS, **detail}


def _count_valid(values: Sequence) -> int:
    return sum(1 for v in values if v is not None)


def check_consolidation(highs, lows, closes, cfg: ScreenConfig) -> dict:
    """條件 1：近三個月高低區間夠窄，且季線接近水平（排除緩跌股）。"""
    window = cfg.consolidation_window
    if _count_valid(closes) < window:
        return _result(INSUFFICIENT, need=window, have=_count_valid(closes))

    box = consolidation(highs, lows, closes, window)
    if box is None:
        return _result(INSUFFICIENT, need=window, have=_count_valid(closes))

    slope = ma_slope_pct(closes, cfg.ma_period, cfg.ma_slope_lookback)
    narrow = box["range_pct"] <= cfg.consolidation_max_range_pct
    flat = slope is None or abs(slope) <= cfg.consolidation_max_abs_slope_pct

    return _result(
        PASS if (narrow and flat) else FAIL,
        range_pct=round(box["range_pct"], 4),
        high=box["high"],
        low=box["low"],
        position=round(box["position"], 3) if box["position"] is not None else None,
        ma_slope_pct=round(slope, 6) if slope is not None else None,
        narrow=narrow,
        flat=flat,
        days=window,
    )


def check_ma_turn_up(closes, cfg: ScreenConfig) -> dict:
    """條件 2：季線扣底翻揚。

    「剛剛要往上」拆成三個同時成立的判斷：
      a. 季線目前仍下彎或剛走平（還沒翻揚，否則就追高了）
      b. 今日收盤 > 目前扣抵值 → 明日季線就會上揚
      c. 未來 N 日扣抵值的均價低於現價 → 價格只要守住，季線會「持續」上揚，
         而不是只揚一天。這條才是扣抵判斷的核心。
      d. 這段扣抵值落在近半年收盤的下半部 → 確認是在底檔扣低，不是高檔換手
    """
    need = cfg.ma_period + cfg.ma_slope_lookback
    if _count_valid(closes) < need:
        return _result(INSUFFICIENT, need=need, have=_count_valid(closes))

    ded = ma_deduction(closes, cfg.ma_period, cfg.deduction_forward_days)
    if ded is None:
        return _result(INSUFFICIENT, need=need, have=_count_valid(closes))

    slope = ma_slope_pct(closes, cfg.ma_period, cfg.ma_slope_lookback)
    still_falling = slope is not None and slope <= cfg.ma_slope_max

    population = [c for c in closes[-cfg.deduction_low_lookback:] if c is not None]
    mean_future = ded["future_deduction_mean"]
    rank = percentile_rank(mean_future, population) if mean_future is not None else None
    deducting_low = rank is not None and rank <= cfg.deduction_low_percentile

    last_close = next((c for c in reversed(closes) if c is not None), None)
    future_supports = (
        mean_future is not None and last_close is not None
        and float(last_close) > mean_future
    )

    passed = bool(still_falling and ded["rises_tomorrow"]
                  and future_supports and deducting_low)
    return _result(
        PASS if passed else FAIL,
        ma=round(ded["ma"], 2),
        deduction=ded["deduction"],
        future_deduction_mean=round(mean_future, 2) if mean_future is not None else None,
        deduction_percentile=round(rank, 3) if rank is not None else None,
        ma_slope_pct=round(slope, 6) if slope is not None else None,
        still_falling=still_falling,
        rises_tomorrow=ded["rises_tomorrow"],
        future_supports=future_supports,
        deducting_low=deducting_low,
    )


def check_margin_declining(margin, cfg: ScreenConfig) -> dict:
    """條件 3a：融資餘額近三個月持續減少。

    用迴歸斜率而非單純頭尾相減，避免被單日的融資異動誤判。
    """
    if _count_valid(margin) < cfg.margin_window:
        return _result(INSUFFICIENT, need=cfg.margin_window, have=_count_valid(margin))

    t = trend(margin, cfg.margin_window)
    if t is None or t["change_pct"] is None or t["slope"] is None:
        return _result(INSUFFICIENT, need=cfg.margin_window, have=_count_valid(margin))

    declined = t["change_pct"] <= -cfg.margin_min_decline_pct
    downtrend = t["slope"] < cfg.margin_max_slope
    return _result(
        PASS if (declined and downtrend) else FAIL,
        change_pct=round(t["change_pct"], 4),
        first=t["first"], last=t["last"],
        slope=round(t["slope"], 3),
        declined=declined, downtrend=downtrend,
    )


def check_foreign_increasing(foreign, cfg: ScreenConfig) -> dict:
    """條件 3b：外資庫存（持有股數）近三個月持續增加。"""
    if _count_valid(foreign) < cfg.foreign_window:
        return _result(INSUFFICIENT, need=cfg.foreign_window, have=_count_valid(foreign))

    t = trend(foreign, cfg.foreign_window)
    if t is None or t["change_pct"] is None or t["slope"] is None:
        return _result(INSUFFICIENT, need=cfg.foreign_window, have=_count_valid(foreign))

    increased = t["change_pct"] >= cfg.foreign_min_increase_pct
    uptrend = t["slope"] > cfg.foreign_min_slope
    return _result(
        PASS if (increased and uptrend) else FAIL,
        change_pct=round(t["change_pct"], 4),
        first=t["first"], last=t["last"],
        slope=round(t["slope"], 3),
        increased=increased, uptrend=uptrend,
    )


def check_institutional_net_buy(total_net, cfg: ScreenConfig) -> dict:
    """條件 3c：外資 + 投信 + 自營商在觀察窗口內合計買超。"""
    window = [v for v in total_net[-cfg.institutional_window:] if v is not None]
    if not window:
        return _result(INSUFFICIENT, need=cfg.institutional_window, have=0)

    net = sum(window)
    return _result(
        PASS if net > cfg.institutional_min_net_shares else FAIL,
        net_shares=int(net),
        days=len(window),
    )


def check_macd(closes, cfg: ScreenConfig) -> dict:
    """條件 4：MACD 柱狀體收斂後由綠轉紅。"""
    need = cfg.macd_slow + cfg.macd_signal
    if _count_valid(closes) < need:
        return _result(INSUFFICIENT, need=need, have=_count_valid(closes))

    osc = macd(closes, cfg.macd_fast, cfg.macd_slow, cfg.macd_signal)["osc"]
    state = macd_turns_red(osc, cfg.macd_converge_days, cfg.macd_within_days)
    if state["osc"] is None:
        return _result(INSUFFICIENT, need=need, have=_count_valid(closes))

    passed = bool(state["turned_red"] and state["converging"])
    return _result(
        PASS if passed else FAIL,
        osc=round(state["osc"], 4),
        prev_osc=round(state["prev_osc"], 4) if state["prev_osc"] is not None else None,
        turned_red=state["turned_red"],
        converging=state["converging"],
        converge_days=state["converge_days"],
        days_since_cross=state["days_since_cross"],
    )


# 條件 → 所屬群組。群組全過才算符合該項需求。
GROUPS = {
    "consolidation": ["consolidation"],
    "ma_turn_up": ["ma_turn_up"],
    "chips": ["margin_declining", "foreign_increasing", "institutional_net_buy"],
    "macd": ["macd"],
}


def screen_stock(stock_id: str, series: dict, cfg: ScreenConfig = DEFAULT_SCREEN) -> dict:
    closes = series.get("close", [])
    conditions = {
        "consolidation": check_consolidation(
            series.get("high", []), series.get("low", []), closes, cfg),
        "ma_turn_up": check_ma_turn_up(closes, cfg),
        "margin_declining": check_margin_declining(series.get("margin_balance", []), cfg),
        "foreign_increasing": check_foreign_increasing(series.get("foreign_shares", []), cfg),
        "institutional_net_buy": check_institutional_net_buy(series.get("total_net", []), cfg),
        "macd": check_macd(closes, cfg),
    }

    groups = {
        name: all(conditions[key]["pass"] for key in keys)
        for name, keys in GROUPS.items()
    }
    last_close = next((c for c in reversed(closes) if c is not None), None)

    return {
        "stock_id": stock_id,
        "name": series.get("name", ""),
        "market": series.get("market", ""),
        "close": last_close,
        "conditions": conditions,
        "groups": groups,
        "score": sum(1 for c in conditions.values() if c["pass"]),
        "insufficient": [k for k, c in conditions.items() if c["status"] == INSUFFICIENT],
        "pass_all": all(groups.values()),
    }


def screen_all(panel: dict[str, dict], cfg: ScreenConfig = DEFAULT_SCREEN) -> list[dict]:
    results = [screen_stock(sid, series, cfg) for sid, series in panel.items()]
    results.sort(key=lambda r: (-r["score"], r["stock_id"]))
    return results
