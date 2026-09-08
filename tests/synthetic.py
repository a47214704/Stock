"""測試用的合成股票走勢。

`ideal_series` 產生一檔同時符合全部四組條件的走勢：高檔緩跌 → 加速趕底 →
底部盤整三個月 → 尾段轉強，搭配融資遞減、外資加碼、法人買超。
參數是掃描出來的（28 組可行解中取中間值），改動請重新確認六項是否仍全過。
"""
from __future__ import annotations

import math


def ideal_closes(n: int = 200, amp: float = 0.8, rally: int = 176,
                 lift: float = 1.0) -> list[float]:
    closes = []
    for i in range(n):
        if i < 70:                      # 高檔緩跌 120 → 90
            close = 120 - 30 * (i / 70)
        elif i < 130:                   # 加速趕底 90 → 62
            close = 90 - 28 * ((i - 70) / 60) ** 1.4
        else:                           # 底部盤整，尾段轉強
            close = 62 + amp * math.sin((i - 130) / 6) + lift * max(0, i - rally) / 10
        closes.append(round(close, 2))
    return closes


def ideal_series(n: int = 200) -> dict:
    closes = ideal_closes(n)
    return {
        "name": "測試電子",
        "market": "twse",
        "close": closes,
        "high": [round(c * 1.012, 2) for c in closes],
        "low": [round(c * 0.988, 2) for c in closes],
        # 融資從 40000 張一路減到 14000 張
        "margin_balance": [int(40000 - 130 * i) for i in range(n)],
        # 外資庫存持續增加
        "foreign_shares": [int(3e8 + 9e5 * i) for i in range(n)],
        # 最近五日三大法人合計買超
        "total_net": [0] * (n - 5) + [1200, 800, 1500, 600, 2000],
        "short_balance": [1000] * n,
        "volume": [10_000_000] * n,
        # 成交額要填，否則流動性門檻判不出來（見 screen.check_liquidity）
        "amount": [int(10_000_000 * c) for c in closes],
        "open": closes[:],
        "foreign_ratio": [None] * n,
        "trust_net": [0] * n,
        "dealer_net": [0] * n,
        "foreign_net": [0] * n,
    }


def flat_series(n: int = 200, price: float = 50.0) -> dict:
    """完全不動的股票，用來當作「什麼條件都不該成立」的對照組。"""
    return {
        "name": "對照組", "market": "twse",
        "close": [price] * n, "high": [price] * n, "low": [price] * n,
        "margin_balance": [10000] * n, "foreign_shares": [1_000_000] * n,
        "total_net": [0] * n, "short_balance": [0] * n, "volume": [1_000_000] * n,
        "amount": [int(1_000_000 * price)] * n, "open": [price] * n,
        "foreign_ratio": [None] * n,
        "trust_net": [0] * n, "dealer_net": [0] * n, "foreign_net": [0] * n,
    }
