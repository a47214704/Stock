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

    收斂指翻紅前的綠柱動能衰竭，是轉折的前兆；綠柱一路擴大後直接跳紅，
    多半只是急跌後的反彈。判斷方式是對該段綠柱的絕對值做迴歸，斜率為負
    即為收斂——不用「連續 N 天嚴格縮小」，那種寫法一次跳動就歸零，
    對真實資料太脆（實測有個案綠柱絕對值 0.009 → 0.031 → 0.005，
    整段明顯在衰竭，但嚴格連續數只有 1）。
    連續嚴格縮小的天數仍會回報，供參考。
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

    magnitudes = [abs(v) for v in negatives]
    streak = 0
    for older, newer in zip(magnitudes, magnitudes[1:]):
        streak = streak + 1 if newer < older else 0
    slope = linreg_slope(magnitudes) if len(magnitudes) >= 2 else None

    result["green_run"] = len(magnitudes)
    result["converge_days"] = streak
    result["converge_slope"] = slope
    result["converging"] = bool(
        (slope is not None and slope < 0 and len(magnitudes) >= 2)
        or streak >= converge_days
    )
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


def ma_turn_state(closes: Sequence[Num], period: int, recent: int,
                  downtrend: int) -> dict | None:
    """季線是否處於「下降段的末端、剛剛轉平轉揚」。

    不能只用「近 N 日斜率 <= 0」來表示「季線還在往下」——那與「明日就會上揚」
    幾乎互斥：收盤只要連續幾天高於扣抵值，季線這幾天就已經在上揚，斜率不會
    還是負的。實測全市場 1955 檔，兩者同時成立的只有 2 檔。

    「往下剛剛要往上」其實是個轉折：

        中期下彎：recent 日前的季線，低於再往前 downtrend 日的季線
        近期轉揚：最近 recent 日的季線斜率已經翻正或走平

    這樣抓到的是下降段剛結束的那一段，而不是「已經漲一個月」或
    「還在直線下墜」。同樣的資料下有 23 檔成立。
    """
    ma = [v for v in sma(closes, period) if v is not None]
    if len(ma) < recent + downtrend + 1 or not ma[-1]:
        return None

    pivot = ma[-(recent + 1)]                      # recent 日前的季線
    earlier = ma[-(recent + 1 + downtrend)]        # 再往前 downtrend 日
    recent_slope = (ma[-1] - pivot) / recent / ma[-1]

    return {
        "ma": ma[-1],
        "was_falling": pivot < earlier,
        "recent_slope_pct": recent_slope,
        "turning_up": recent_slope >= 0,
        "downtrend_pct": (pivot - earlier) / earlier if earlier else None,
    }


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


def consolidation_run(highs: Sequence[Num], lows: Sequence[Num],
                      closes: Sequence[Num], max_range_pct: float,
                      max_drift_ratio: float, min_window: int = 20) -> dict | None:
    """從最後一天往前擴張，回報「仍維持在同一個箱型內」的最長連續天數。

    condition 檢查的是固定窗口（最近 60 日）夠不夠窄；這裡回答另一個問題：
    這個箱型**已經走了多久**。盤整四個月和剛好三個月，用固定窗口看分數一樣，
    但前者的能量累積更久。

    做法分兩步，順序很重要：

    1. **只用幅度往前擴張**，直到區間幅度超過門檻為止，取最長的那個長度。
       箱型的定義就是價格待在一個範圍內，這一步在找那個範圍能回推多遠。
    2. **對找到的區段檢驗淨漂移**：

           drift_ratio = |迴歸斜率| × (天數 − 1) / (區間高 − 區間低)

       趨勢股單向走完整個區間，比值接近 1；盤整股在區間內來回，淨漂移遠小於
       區間寬度，比值明顯偏低。超過門檻表示這段其實是趨勢的前半段，不是箱型。

    漂移檢驗只做在最終區段上，不是每個長度都做。箱型內部本來就會有方向性的
    波段，最後二十天剛好是其中一段上行或下行時，逐長度檢驗會把整個箱型否定掉。

    幅度門檻單獨用會誤判：任何趨勢股在區間拉開前都有一段「夠窄」的天數
    （約為門檻 ÷ 每日漲跌幅），所以第 2 步不能省。反過來，固定的「每日斜率」
    門檻也不適用——那是為 60 日窗口定的，短窗口雜訊主導、長度不同不可比，
    改用相對於區間寬度的淨漂移才與長度和價位無關。

    回傳 None 表示構不成 min_window 天以上的箱型。
    """
    n = len(closes)
    if n == 0:
        return None

    high = float("-inf")
    low = float("inf")
    # 迴歸用的累加量。x 取「距今天數」的負值（昨天 -1、前天 -2……），
    # 這樣往前擴張只是新增一個點，四個累加量都能 O(1) 更新。
    sum_x = sum_y = sum_xy = sum_xx = 0.0
    count = 0
    best: dict | None = None

    for length in range(1, n + 1):
        i = n - length
        close = closes[i]
        if close is None:
            break                      # 資料斷點，無法再往前認定為連續
        close = float(close)
        h = highs[i] if i < len(highs) and highs[i] is not None else close
        low_i = lows[i] if i < len(lows) and lows[i] is not None else close
        high = max(high, float(h))
        low = min(low, float(low_i))

        x = float(i - n)
        sum_x += x
        sum_y += close
        sum_xy += x * close
        sum_xx += x * x
        count += 1

        mean = sum_y / count
        if mean <= 0:
            break
        range_pct = (high - low) / mean
        if range_pct > max_range_pct:
            break                      # 第 1 步：幅度撐不住就停在這裡

        if length < min_window:
            continue

        denom = count * sum_xx - sum_x * sum_x
        slope = ((count * sum_xy - sum_x * sum_y) / denom) if denom else 0.0
        best = {"days": length, "range_pct": range_pct,
                "slope": slope, "high": high, "low": low, "mean": mean}

    if best is None:
        return None

    # 第 2 步：只對最終區段檢驗淨漂移
    width = best["high"] - best["low"]
    best["drift_ratio"] = (
        abs(best["slope"]) * (best["days"] - 1) / width if width > 0 else 0.0
    )
    return best if best["drift_ratio"] <= max_drift_ratio else None


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
