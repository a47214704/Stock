#!/usr/bin/env python3
"""產生示範資料到 web/demo/，讓前端在 ETL 還沒跑過之前就能開發與預覽。

刻意寫進 web/demo/ 而不是 data/：data/ 是 ETL 的產出區，混入合成資料會
分不清哪些是真實行情。前端在讀不到 data/ 時才會退回 demo/，並顯示提示帶。

用法：python tools/gen_demo_data.py
"""
from __future__ import annotations

import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from etl import config  # noqa: E402
from etl.build import build  # noqa: E402
from etl.storage import (  # noqa: E402
    SNAPSHOT_FIELDS, save_daily, to_key, update_stock_info,
)
from tests.synthetic import ideal_series  # noqa: E402

from datetime import date, timedelta  # noqa: E402

DEMO_DIR = os.path.join("web", "demo")
DAYS = 200

NAMES = [
    ("2330", "示範半導體"), ("2317", "示範精密"), ("2454", "示範通訊"),
    ("2412", "示範電信"), ("1301", "示範化工"), ("2882", "示範金控"),
    ("3008", "示範光學"), ("2603", "示範航運"), ("1216", "示範食品"),
    ("2308", "示範電子"), ("6505", "示範能源"), ("2891", "示範銀行"),
]


def noisy(series: dict, seed: int, drift: float) -> dict:
    """在理想走勢上加雜訊與漂移，做出深淺不一的樣本。"""
    rng = random.Random(seed)
    out = dict(series)
    scale = 0.6 + rng.random() * 2.2
    closes = [round(max(1.0, c * scale * (1 + drift * i / DAYS)
                        + rng.gauss(0, c * scale * 0.006)), 2)
              for i, c in enumerate(series["close"])]
    out["close"] = closes
    out["open"] = closes[:]
    out["high"] = [round(c * (1 + abs(rng.gauss(0, .009))), 2) for c in closes]
    out["low"] = [round(c * (1 - abs(rng.gauss(0, .009))), 2) for c in closes]
    # 成交額必須有值，流動性門檻才判得出來
    out["volume"] = [int(rng.uniform(3e6, 2e7)) for _ in closes]
    out["amount"] = [int(v * c) for v, c in zip(out["volume"], closes)]
    margin_dir = -1 if drift <= 0 else 1
    out["margin_balance"] = [
        max(300, int(30000 + margin_dir * -110 * i + rng.gauss(0, 400)))
        for i in range(DAYS)
    ]
    foreign_dir = 1 if drift >= -0.05 else -1
    out["foreign_shares"] = [
        max(10**6, int(2.4e8 + foreign_dir * 7.5e5 * i + rng.gauss(0, 1.6e6)))
        for i in range(DAYS)
    ]
    out["total_net"] = [int(rng.gauss(0, 900_000)) for _ in range(DAYS)]
    tail = 1 if foreign_dir > 0 else -1
    for k in range(1, 6):
        out["total_net"][-k] = int(tail * abs(rng.gauss(1_200_000, 400_000)))
    return out


def main() -> int:
    base = ideal_series(DAYS)
    # 第一檔保留為完全符合的理想型，其餘加上不同程度的漂移
    stocks = {NAMES[0][0]: dict(base, name=NAMES[0][1])}
    for i, (code, name) in enumerate(NAMES[1:], start=1):
        drift = [-0.02, 0.35, -0.4, 0.08, -0.12, 0.55, -0.3, 0.02, 0.2, -0.5, 0.12][i - 1]
        stocks[code] = dict(noisy(base, seed=i * 977, drift=drift), name=name)

    # 讓輸出全部落在 web/demo/
    config.DATA_DIR = DEMO_DIR
    config.DAILY_DIR = os.path.join(DEMO_DIR, "daily")
    config.HISTORY_DIR = os.path.join(DEMO_DIR, "history")
    config.STOCK_INFO_PATH = os.path.join(DEMO_DIR, "stock_info.json")
    config.SIGNALS_PATH = os.path.join(DEMO_DIR, "signals.json")
    config.SCREEN_ALL_PATH = os.path.join(DEMO_DIR, "screen_all.json")

    day = date(2026, 1, 5)
    for i in range(DAYS):
        while day.weekday() >= 5:
            day += timedelta(days=1)
        snapshot = {}
        for code, series in stocks.items():
            row = {f: (series[f][i] if isinstance(series.get(f), list) else None)
                   for f in SNAPSHOT_FIELDS}
            row["name"], row["market"] = series["name"], "twse"
            snapshot[code] = row
        save_daily(to_key(day), snapshot, ["twse"])
        update_stock_info(snapshot)
        day += timedelta(days=1)

    summary = build()
    print(f"示範資料已寫入 {DEMO_DIR}/：{summary}")

    # daily/ 只是產生 signals 的中間產物，前端不讀，刪掉以免無謂佔用 repo
    for name in os.listdir(config.DAILY_DIR):
        os.remove(os.path.join(config.DAILY_DIR, name))
    os.rmdir(config.DAILY_DIR)
    return 0


if __name__ == "__main__":
    sys.exit(main())
