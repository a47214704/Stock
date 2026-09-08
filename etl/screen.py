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

import statistics
from typing import Sequence

from .config import ScreenConfig, DEFAULT_SCREEN
from .indicators import (
    consolidation, consolidation_run, ma_deduction, ma_slope_pct, ma_turn_state,
    macd, macd_turns_red, percentile_rank, trend,
)

PASS = "pass"
FAIL = "fail"
INSUFFICIENT = "insufficient"


def _result(status: str, **detail) -> dict:
    return {"status": status, "pass": status == PASS, **detail}


def _count_valid(values: Sequence) -> int:
    return sum(1 for v in values if v is not None)


def check_liquidity(amounts, cfg: ScreenConfig) -> dict:
    """流動性門檻。這不是選股條件，而是「這檔能不能買」的前提。

    成交量太小的個股不只買不到，籌碼數字也全是雜訊：融資餘額 10 張減到
    6 張就是 -40%，會直接通過「融資三個月遞減」。實測不設門檻時四組全過的
    兩檔，20 日中位成交額只有 70 萬與 170 萬；設門檻後歸零——那兩檔完全是
    低流動性造成的假訊號。
    """
    window = [v for v in amounts[-cfg.liquidity_window:] if v]
    if not window:
        return _result(INSUFFICIENT, need=cfg.liquidity_window, have=0)

    median = statistics.median(window)
    return _result(
        PASS if median >= cfg.min_median_amount else FAIL,
        median_amount=int(median),
        threshold=int(cfg.min_median_amount),
        days=len(window),
    )


def check_consolidation(highs, lows, closes, cfg: ScreenConfig) -> dict:
    """條件 1：近三個月高低區間夠窄，且季線接近水平（排除緩跌股）。

    過與不過看固定窗口（最近 60 日）；另外回報 `run_days`，即這個箱型實際
    已經走了多久。通過與否只要求「至少三個月」，run_days 讓盤整四個月的
    個股能和剛好三個月的區分開來——箱型走得越久，累積的能量越多。
    """
    window = cfg.consolidation_window
    if _count_valid(closes) < window:
        return _result(INSUFFICIENT, need=window, have=_count_valid(closes))

    box = consolidation(highs, lows, closes, window)
    if box is None:
        return _result(INSUFFICIENT, need=window, have=_count_valid(closes))

    slope = ma_slope_pct(closes, cfg.ma_period, cfg.ma_slope_lookback)
    narrow = box["range_pct"] <= cfg.consolidation_max_range_pct
    flat = slope is None or abs(slope) <= cfg.consolidation_max_abs_slope_pct

    run = consolidation_run(
        highs, lows, closes,
        cfg.consolidation_max_range_pct,
        cfg.consolidation_max_drift_ratio,
        cfg.consolidation_run_min_days,
    )

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
        run_days=run["days"] if run else None,
        run_range_pct=round(run["range_pct"], 4) if run else None,
        drift_ratio=round(run["drift_ratio"], 3) if run else None,
    )


def check_ma_turn_up(closes, cfg: ScreenConfig) -> dict:
    """條件 2：季線扣底翻揚。

    「往下剛剛要往上」拆成四個同時成立的判斷：
      a. 季線處於下降段的末端且剛轉平轉揚——中期下彎、近期斜率翻正。
         不能只寫「近 5 日斜率 <= 0」，那與 b 幾乎互斥：收盤連續幾天高於
         扣抵值，季線這幾天就已經在上揚了。實測兩者同時成立的只有 2 檔。
      b. 今日收盤 > 目前扣抵值 → 明日季線就會上揚
      c. 未來 N 日扣抵值的均價低於現價 → 價格只要守住，季線會「持續」上揚，
         而不是只揚一天。這條才是扣抵判斷的核心。
      d. 這段扣抵值落在近半年收盤的下半部 → 確認是在底檔扣低，不是高檔換手
    """
    need = cfg.ma_period + cfg.ma_slope_lookback + cfg.ma_downtrend_lookback
    if _count_valid(closes) < need:
        return _result(INSUFFICIENT, need=need, have=_count_valid(closes))

    ded = ma_deduction(closes, cfg.ma_period, cfg.deduction_forward_days)
    turn = ma_turn_state(closes, cfg.ma_period, cfg.ma_slope_lookback,
                         cfg.ma_downtrend_lookback)
    if ded is None or turn is None:
        return _result(INSUFFICIENT, need=need, have=_count_valid(closes))

    slope = turn["recent_slope_pct"]
    turning = bool(turn["was_falling"] and turn["turning_up"])

    population = [c for c in closes[-cfg.deduction_low_lookback:] if c is not None]
    mean_future = ded["future_deduction_mean"]
    rank = percentile_rank(mean_future, population) if mean_future is not None else None
    deducting_low = rank is not None and rank <= cfg.deduction_low_percentile

    last_close = next((c for c in reversed(closes) if c is not None), None)
    future_supports = (
        mean_future is not None and last_close is not None
        and float(last_close) > mean_future
    )

    passed = bool(turning and ded["rises_tomorrow"]
                  and future_supports and deducting_low)
    return _result(
        PASS if passed else FAIL,
        ma=round(ded["ma"], 2),
        deduction=ded["deduction"],
        future_deduction_mean=round(mean_future, 2) if mean_future is not None else None,
        deduction_percentile=round(rank, 3) if rank is not None else None,
        ma_slope_pct=round(slope, 6) if slope is not None else None,
        downtrend_pct=round(turn["downtrend_pct"], 4)
        if turn["downtrend_pct"] is not None else None,
        was_falling=turn["was_falling"],
        turning_up=turn["turning_up"],
        turning=turning,
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
    # 融資餘額太小時百分比變化沒有意義：10 張減到 6 張就是 -40%
    meaningful = t["first"] >= cfg.margin_min_balance
    return _result(
        PASS if (declined and downtrend and meaningful) else FAIL,
        change_pct=round(t["change_pct"], 4),
        first=t["first"], last=t["last"],
        slope=round(t["slope"], 3),
        declined=declined, downtrend=downtrend,
        meaningful=meaningful, min_balance=cfg.margin_min_balance,
    )


def check_foreign_increasing(foreign, cfg: ScreenConfig,
                             ratio=None) -> dict:
    """條件 3b：外資庫存近三個月持續增加。

    優先看持有股數。上櫃的來源只提供持股比例、沒有股數，此時退回用比例
    判斷趨勢——比例上升通常等同庫存增加，但遇到現金增資這類股本變動時，
    股數增加而比例被稀釋，兩者會不一致。結果會標明用的是哪一種，
    前端可據此說明。
    """
    series = foreign
    basis = "shares"
    if _count_valid(series) < cfg.foreign_window and ratio is not None:
        series = ratio
        basis = "ratio"

    if _count_valid(series) < cfg.foreign_window:
        return _result(INSUFFICIENT, need=cfg.foreign_window,
                       have=_count_valid(series), basis=basis)

    t = trend(series, cfg.foreign_window)
    if t is None or t["change_pct"] is None or t["slope"] is None:
        return _result(INSUFFICIENT, need=cfg.foreign_window,
                       have=_count_valid(series), basis=basis)

    increased = t["change_pct"] >= cfg.foreign_min_increase_pct
    uptrend = t["slope"] > cfg.foreign_min_slope
    return _result(
        PASS if (increased and uptrend) else FAIL,
        change_pct=round(t["change_pct"], 4),
        first=t["first"], last=t["last"],
        slope=round(t["slope"], 6 if basis == "ratio" else 3),
        increased=increased, uptrend=uptrend, basis=basis,
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

    passed = bool(state["turned_red"]
                  and (state["converging"] or not cfg.macd_require_convergence))
    return _result(
        PASS if passed else FAIL,
        osc=round(state["osc"], 4),
        prev_osc=round(state["prev_osc"], 4) if state["prev_osc"] is not None else None,
        turned_red=state["turned_red"],
        converging=state["converging"],
        converge_days=state["converge_days"],
        green_run=state.get("green_run"),
        converge_slope=round(state["converge_slope"], 6)
        if state.get("converge_slope") is not None else None,
        days_since_cross=state["days_since_cross"],
    )


# 條件 → 所屬群組。群組全過才算符合該項需求。
# 這份是完整對應（含所有條件），供前端列出標籤與工具列舉群組使用；
# 實際評估時用 group_conditions()，籌碼面的成員會依設定調整。
GROUPS = {
    "consolidation": ["consolidation"],
    "ma_turn_up": ["ma_turn_up"],
    "chips": ["margin_declining", "foreign_increasing", "institutional_net_buy"],
    "macd": ["macd"],
}


def group_conditions(cfg: ScreenConfig) -> dict[str, list[str]]:
    """評估時實際採用的群組成員。

    法人合計買超是否列入籌碼面由 cfg.institutional_required 決定——
    歷史掃描顯示它對籌碼面沒有貢獻，只會砍掉一半以上的候選（見 config 註解）。
    """
    chips = ["margin_declining", "foreign_increasing"]
    if cfg.institutional_required:
        chips.append("institutional_net_buy")
    return {**GROUPS, "chips": chips}


def screen_stock(stock_id: str, series: dict, cfg: ScreenConfig = DEFAULT_SCREEN) -> dict:
    closes = series.get("close", [])
    liquidity = check_liquidity(series.get("amount", []), cfg)
    conditions = {
        "consolidation": check_consolidation(
            series.get("high", []), series.get("low", []), closes, cfg),
        "ma_turn_up": check_ma_turn_up(closes, cfg),
        "margin_declining": check_margin_declining(series.get("margin_balance", []), cfg),
        "foreign_increasing": check_foreign_increasing(
            series.get("foreign_shares", []), cfg, series.get("foreign_ratio", [])),
        "institutional_net_buy": check_institutional_net_buy(series.get("total_net", []), cfg),
        "macd": check_macd(closes, cfg),
    }

    groups = {
        name: all(conditions[key]["pass"] for key in keys)
        for name, keys in group_conditions(cfg).items()
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
        # 缺哪幾組。四項同時成立於可交易個股的機率極低，實用的產出是
        # 「差一項」的觀察名單，所以把缺口一併算好給前端。
        "missing": [name for name, ok in groups.items() if not ok],
        "liquidity": liquidity,
        "tradable": liquidity["pass"],
        "pass_all": all(groups.values()) and liquidity["pass"],
    }


def screen_all(panel: dict[str, dict], cfg: ScreenConfig = DEFAULT_SCREEN) -> list[dict]:
    results = [screen_stock(sid, series, cfg) for sid, series in panel.items()]
    results.sort(key=lambda r: (-r["score"], r["stock_id"]))
    return results
