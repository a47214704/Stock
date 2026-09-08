"""從每日快照重建前端要用的衍生檔案。

產出三種：
  data/signals.json     入選個股的完整判斷依據（含每個條件為什麼過／沒過）
  data/screen_all.json  全市場精簡結果，供前端做排序與統計
  data/history/<代號>.json  入選個股的歷史序列與已算好的指標，供圖表 lazy load

歷史檔只為入選名單產生，並在每次 build 時清掉已落榜的，避免 1800 檔
每天全量改寫造成 repo 無謂膨脹。
"""
from __future__ import annotations

import logging
import os

from . import config
from .config import DEFAULT_SCREEN, ScreenConfig
from .indicators import macd, sma
from .screen import screen_all
from .storage import build_panel, now_iso, write_json

log = logging.getLogger(__name__)

HISTORY_FIELDS = ("close", "high", "low", "volume",
                  "margin_balance", "foreign_shares", "total_net")


def _round(values, digits=2):
    return [None if v is None else round(float(v), digits) for v in values]


def write_history(stock_id: str, dates: list[str], series: dict,
                  cfg: ScreenConfig) -> None:
    closes = series.get("close", [])
    osc = macd(closes, cfg.macd_fast, cfg.macd_slow, cfg.macd_signal)["osc"]
    ma = sma(closes, cfg.ma_period)

    payload = {"stock_id": stock_id, "name": series.get("name", ""),
               "market": series.get("market", ""), "dates": dates}
    for field in HISTORY_FIELDS:
        payload[field] = list(series.get(field, []))
    payload["ma60"] = _round(ma)
    payload["macd_osc"] = _round(osc, 4)
    # 扣抵值序列：第 i 天即將被扣掉的那一根收盤價
    period = cfg.ma_period
    payload["deduction"] = [
        closes[i - period + 1] if i - period + 1 >= 0 and i >= period - 1 else None
        for i in range(len(closes))
    ]

    write_json(os.path.join(config.HISTORY_DIR, f"{stock_id}.json"), payload,
               compact=True)


def prune_history(keep: set[str]) -> int:
    """刪掉不在名單內的歷史檔。"""
    if not os.path.isdir(config.HISTORY_DIR):
        return 0
    removed = 0
    for name in os.listdir(config.HISTORY_DIR):
        if not name.endswith(".json"):
            continue
        if name[:-5] not in keep:
            os.remove(os.path.join(config.HISTORY_DIR, name))
            removed += 1
    return removed


def build(days: int = 260, cfg: ScreenConfig = DEFAULT_SCREEN) -> dict:
    dates, panel = build_panel(days)
    if not dates:
        log.warning("data/daily 沒有任何快照，請先執行 `python -m etl fetch`")
        return {"stocks": 0, "listed": 0, "dates": 0}

    results = screen_all(panel, cfg)
    data_date = dates[-1]
    generated_at = now_iso()

    listed = [r for r in results if r["pass_all"] or r["score"] >= cfg.min_score_to_list]
    write_json(config.SIGNALS_PATH, {
        "generated_at": generated_at,
        "data_date": data_date,
        "trading_days": len(dates),
        "universe": len(results),
        "criteria": cfg.to_dict(),
        "matched": sum(1 for r in results if r["pass_all"]),
        "results": listed,
    })

    write_json(config.SCREEN_ALL_PATH, {
        "generated_at": generated_at,
        "data_date": data_date,
        "columns": ["stock_id", "name", "market", "close", "score",
                    "consolidation", "ma_turn_up", "chips", "macd", "run_days"],
        "rows": [
            [r["stock_id"], r["name"], r["market"], r["close"], r["score"],
             int(r["groups"]["consolidation"]), int(r["groups"]["ma_turn_up"]),
             int(r["groups"]["chips"]), int(r["groups"]["macd"]),
             r["conditions"]["consolidation"].get("run_days")]
            for r in results
        ],
    }, compact=True)

    keep = {r["stock_id"] for r in listed}
    for result in listed:
        write_history(result["stock_id"], dates, panel[result["stock_id"]], cfg)
    pruned = prune_history(keep)

    summary = {
        "stocks": len(results),
        "listed": len(listed),
        "matched": sum(1 for r in results if r["pass_all"]),
        "dates": len(dates),
        "data_date": data_date,
        "history_pruned": pruned,
    }
    log.info("build 完成：%s", summary)
    return summary


def coverage() -> dict:
    """回報目前累積的資料量，用來判斷各條件是否已經有足夠歷史可判斷。"""
    dates, panel = build_panel(400)
    if not dates:
        return {"trading_days": 0}

    def field_days(field: str) -> int:
        return max((sum(1 for v in s.get(field, []) if v is not None)
                    for s in panel.values()), default=0)

    cfg = DEFAULT_SCREEN
    return {
        "trading_days": len(dates),
        "first_date": dates[0],
        "last_date": dates[-1],
        "stocks": len(panel),
        "price_days": field_days("close"),
        "margin_days": field_days("margin_balance"),
        "foreign_days": field_days("foreign_shares"),
        "ready": {
            "consolidation": field_days("close") >= cfg.consolidation_window,
            "ma_turn_up": field_days("close") >= cfg.ma_period + cfg.ma_slope_lookback,
            "margin_declining": field_days("margin_balance") >= cfg.margin_window,
            "foreign_increasing": field_days("foreign_shares") >= cfg.foreign_window,
            "macd": field_days("close") >= cfg.macd_slow + cfg.macd_signal,
        },
    }
