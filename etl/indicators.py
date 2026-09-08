"""技術指標。純函式、不依賴外部套件，可完整單元測試。

慣例：所有函式接受由舊到新排序的序列，回傳的序列長度與輸入相同，
資料不足的位置以 None 表示。
"""
from __future__ import annotations

from typing import Sequence

Num = float | int | None


def _clean_tail(values: Sequence[Num]) -> tuple[int, list[float]]:
    """回傳 (第一個非 None 的索引, 之後的數值)。中間若有 None 視為斷點以最後一段為準。"""
    start = 0
    for i, v in enumerate(values):
        if v is None:
            start = i + 1
    return start, [float(v) for v in values[start:]]


def sma(values: Sequence[Num], period: int) -> list[float | None]:
    """簡單移動平均。"""
    if period <= 0:
        raise ValueError("period 必須為正整數")
    out: list[float | None] = [None] * len(values)
    window_sum = 0.0
    count = 0
    for i, v in enumerate(values):
        if v is None:
            window_sum, count = 0.0, 0
            continue
        window_sum += float(v)
        count += 1
        if count > period:
            prev = values[i - period]
            window_sum -= float(prev)
            count = period
        if count == period:
            out[i] = window_sum / period
    return out


def ema(values: Sequence[Num], period: int) -> list[float | None]:
    """指數移動平均，以前 period 筆的 SMA 作為種子（與多數看盤軟體一致）。"""
    if period <= 0:
        raise ValueError("period 必須為正整數")
    out: list[float | None] = [None] * len(values)
    offset, series = _clean_tail(values)
    if len(series) < period:
        return out
    seed = sum(series[:period]) / period
    out[offset + period - 1] = seed
    k = 2.0 / (period + 1)
    prev = seed
    for i in range(period, len(series)):
        prev = series[i] * k + prev * (1 - k)
        out[offset + i] = prev
    return out


def macd(closes: Sequence[Num], fast: int = 12, slow: int = 26,
         signal: int = 9) -> dict[str, list[float | None]]:
    """MACD。

    DIF  = EMA(fast) - EMA(slow)
    DEA  = EMA(DIF, signal)      即訊號線，看盤軟體上的 MACD 線
    OSC  = DIF - DEA             即柱狀體，由負轉正就是「綠轉紅」
    """
    fast_ema = ema(closes, fast)
    slow_ema = ema(closes, slow)
    dif: list[float | None] = [
        (f - s) if (f is not None and s is not None) else None
        for f, s in zip(fast_ema, slow_ema)
    ]
    dea = ema(dif, signal)
    osc: list[float | None] = [
        (d - e) if (d is not None and e is not None) else None
        for d, e in zip(dif, dea)
    ]
    return {"dif": dif, "dea": dea, "osc": osc}


def macd_turns_red(osc: Sequence[Num], converge_days: int = 3,
                   within_days: int = 1) -> dict:
    """判斷柱狀體是否「收斂後由綠轉紅」。

    轉紅是**單日事件**：OSC 由 <= 0 變成 > 0。若嚴格只認當天，每天入選的
    股票會非常少，而且晚看一天就錯過，因此用 within_days 允許「最近 N 天內
    翻紅且至今未再轉綠」。within_days=1 即為嚴格的當日轉折。

    收斂指翻紅前的綠柱絕對值逐日縮小，代表下跌動能衰竭，是轉折的前兆；
    綠柱一路擴大後直接跳紅，多半只是急跌後的反彈，不算數。
    """
    result = {
        "turned_red": False,
        "converging": False,
        "osc": None,
        "prev_osc": None,
        "converge_days": 0,
        "days_since_cross": None,
    }
    values = [v for v in osc if v is not None]
    if len(values) < 2:
        return result

    result["osc"] = values[-1]
    result["prev_osc"] = values[-2]

    if values[-1] <= 0:
        return result          # 現在是綠柱，談不上轉紅

    # 由後往前找最近一次的翻紅點：values[i] > 0 >= values[i-1]
    cross = None
    for i in range(len(values) - 1, 0, -1):
        if values[i] <= 0:
            break              # 中間又轉綠過，最近一段紅柱到此為止
        if values[i - 1] <= 0:
            cross = i
            break
    if cross is None:
        return result          # 整段可見範圍都是紅柱，找不到轉折點

    days_since = len(values) - 1 - cross
    result["days_since_cross"] = days_since
    result["turned_red"] = days_since < within_days

    # 翻紅前那段綠柱是否逐日收斂
    negatives: list[float] = []
    for v in reversed(values[:cross]):
        if v > 0:
            break
        negatives.append(v)
    negatives.reverse()

    streak = 0
    for older, newer in zip(negatives, negatives[1:]):
        streak = streak + 1 if abs(newer) < abs(older) else 0
    result["converge_days"] = streak
    result["converging"] = streak >= converge_days
    return result


def linreg_slope(values: Sequence[Num]) -> float | None:
    """最小平方法斜率，x 取 0,1,2,...。用來判斷趨勢方向，比頭尾相減抗雜訊。"""
    pts = [(i, float(v)) for i, v in enumerate(values) if v is not None]
    n = len(pts)
    if n < 2:
        return None
    sum_x = sum(x for x, _ in pts)
    sum_y = sum(y for _, y in pts)
    sum_xy = sum(x * y for x, y in pts)
    sum_xx = sum(x * x for x, _ in pts)
    denom = n * sum_xx - sum_x * sum_x
    if denom == 0:
        return None
    return (n * sum_xy - sum_x * sum_y) / denom


def ma_deduction(closes: Sequence[Num], period: int = 60,
                 forward_days: int = 20) -> dict | None:
    """季線扣抵分析。

    均線由 t 走到 t+1 時，會扣掉 close[t-period+1]、加進 close[t+1]，
    因此「扣抵值」就是 close[t-period+1]：

        MA[t+1] - MA[t] = (close[t+1] - 扣抵值) / period

    也就是說，只要明日收盤高於扣抵值，季線就會上揚。
    未來 N 日的扣抵值就是 close[t-period+1 : t-period+1+N]，這段愈低，
    季線愈容易翻揚——即所謂「扣低」「扣底」。
    """
    n = len(closes)
    if n < period:
        return None
    ma = sma(closes, period)
    if ma[-1] is None:
        return None

    idx = n - period            # 即將被扣掉的那一根的索引 (= t-period+1)
    current = closes[idx]
    if current is None:
        return None

    future = [float(c) for c in closes[idx:idx + forward_days] if c is not None]
    last_close = closes[-1]

    return {
        "ma": ma[-1],
        "deduction": float(current),
        "future_deductions": future,
        "future_deduction_mean": (sum(future) / len(future)) if future else None,
        "future_deduction_slope": linreg_slope(future),
        # 明日季線是否上揚
        "rises_tomorrow": last_close is not None and float(last_close) > float(current),
    }


def ma_slope_pct(closes: Sequence[Num], period: int, lookback: int) -> float | None:
    """季線近 lookback 日的平均每日變動率（相對於股價），用來判斷是否仍在下彎。"""
    ma = sma(closes, period)
    tail = [v for v in ma if v is not None]
    if len(tail) < lookback + 1 or not tail[-1]:
        return None
    return (tail[-1] - tail[-1 - lookback]) / lookback / tail[-1]


def percentile_rank(value: float, population: Sequence[Num]) -> float | None:
    """value 在 population 中的分位數（0~1）。用來判斷扣抵值是否處於低檔。"""
    pop = [float(v) for v in population if v is not None]
    if not pop:
        return None
    return sum(1 for v in pop if v <= value) / len(pop)


def consolidation(highs: Sequence[Num], lows: Sequence[Num], closes: Sequence[Num],
                  window: int) -> dict | None:
    """盤整判斷：區間高低幅度相對均價。

    只看幅度會把「緩跌股」也算進來，因此另外回傳季線斜率供呼叫端一併過濾。
    """
    if len(closes) < window:
        return None
    h = [float(v) for v in highs[-window:] if v is not None]
    l = [float(v) for v in lows[-window:] if v is not None]
    c = [float(v) for v in closes[-window:] if v is not None]
    if not h or not l or not c:
        return None
    avg = sum(c) / len(c)
    if avg <= 0:
        return None
    top, bottom = max(h), min(l)
    return {
        "window": window,
        "high": top,
        "low": bottom,
        "mean": avg,
        "range_pct": (top - bottom) / avg,
        "position": (c[-1] - bottom) / (top - bottom) if top > bottom else None,
    }


def trend(values: Sequence[Num], window: int) -> dict | None:
    """籌碼序列的趨勢：期間變化率 + 迴歸斜率（正規化為每日變化率）。"""
    series = [float(v) for v in values[-window:] if v is not None]
    if len(series) < 2:
        return None
    first, last = series[0], series[-1]
    slope = linreg_slope(series)
    base = abs(first) if first else None
    return {
        "first": first,
        "last": last,
        "change": last - first,
        "change_pct": (last - first) / base if base else None,
        "slope": slope,
        "slope_pct": (slope / base) if (slope is not None and base) else None,
        "points": len(series),
    }
