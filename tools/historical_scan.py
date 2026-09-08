#!/usr/bin/env python3
"""歷史掃描：用過去每一天當基準日重跑選股，並衡量訊號發生後的走勢。

回答兩個問題：

1. 這組條件多久出現一次？
2. 出現之後接下來 5／10／20 個交易日的報酬如何？

方法上的限制寫在產出的報告裡，請連同數字一起讀——樣本只有一年、
單一市場、未計交易成本，任何結論都只能當作參考而非驗證。

用法：python tools/historical_scan.py [--out docs/historical-scan.md]
"""
from __future__ import annotations

import argparse
import os
import statistics
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from etl.config import DEFAULT_SCREEN, ScreenConfig  # noqa: E402
from etl.screen import GROUPS, screen_all  # noqa: E402
from etl.storage import build_panel  # noqa: E402

# 選股實際用到的欄位。只留這些能大幅降低逐日切片的成本。
NEEDED = ("close", "high", "low", "amount", "margin_balance",
          "foreign_shares", "foreign_ratio", "total_net")

HORIZONS = (5, 10, 20)
GROUP_LABELS = {"consolidation": "盤整", "ma_turn_up": "季線扣底",
                "chips": "籌碼面", "macd": "MACD"}

# 籌碼面是三個條件的交集，拆開才看得出是三者都有貢獻，還是其中一個在帶動。
CHIP_LABELS = {
    "margin_declining": "融資遞減",
    "foreign_increasing": "外資庫存增加",
    "institutional_net_buy": "法人合計買超",
}


def trim(panel: dict) -> dict:
    return {sid: {**{k: s.get(k, []) for k in NEEDED},
                  "name": s.get("name", ""), "market": s.get("market", "")}
            for sid, s in panel.items()}


def slice_at(trimmed: dict, end: int) -> dict:
    return {sid: {**{k: v[k][:end + 1] for k in NEEDED},
                  "name": v["name"], "market": v["market"]}
            for sid, v in trimmed.items()}


def forward_return(closes: list, start: int, horizon: int) -> float | None:
    """自 start 起算 horizon 個交易日的收盤對收盤報酬。"""
    end = start + horizon
    if end >= len(closes):
        return None
    a, b = closes[start], closes[end]
    if a is None or b is None or a <= 0:
        return None
    return b / a - 1.0


def scan(cfg: ScreenConfig = DEFAULT_SCREEN, days: int = 400) -> dict:
    dates, panel = build_panel(days)
    need = cfg.ma_period + cfg.ma_slope_lookback + cfg.ma_downtrend_lookback
    if len(dates) < need:
        raise SystemExit(f"資料只有 {len(dates)} 天，季線扣底條件需要 {need} 天")

    trimmed = trim(panel)
    closes = {sid: v["close"] for sid, v in trimmed.items()}

    per_date = []          # 每個基準日的統計
    started = time.time()
    for t in range(need - 1, len(dates)):
        results = [r for r in screen_all(slice_at(trimmed, t), cfg) if r["tradable"]]
        row = {
            "date": dates[t], "index": t, "tradable": len(results),
            "groups": {g: [r["stock_id"] for r in results if r["groups"][g]]
                       for g in GROUPS},
            "conditions": {c: [r["stock_id"] for r in results
                               if r["conditions"][c]["pass"]]
                           for c in CHIP_LABELS},
            "matched": [r["stock_id"] for r in results if r["pass_all"]],
            "near_miss": [r["stock_id"] for r in results if len(r["missing"]) == 1],
            "universe": [r["stock_id"] for r in results],
        }
        per_date.append(row)
        done = len(per_date)
        if done % 20 == 0:
            rate = (time.time() - started) / done
            left = (len(dates) - need + 1 - done) * rate
            print(f"  {done}/{len(dates) - need + 1} 個基準日"
                  f"（剩約 {left / 60:.1f} 分鐘）", flush=True)

    return {"dates": dates, "closes": closes, "per_date": per_date,
            "need": need, "cfg": cfg}


def measure(scan_result: dict, pick, label: str) -> dict:
    """衡量某種訊號：出現次數，以及各期間的報酬中位數與勝率。

    同時計算同一天全體可交易個股的報酬中位數當基準——若不比對基準，
    「20 日中位報酬 +3%」看不出是訊號有效還是那段時間大盤都在漲。
    """
    closes = scan_result["closes"]
    occurrences = 0
    rets = {h: [] for h in HORIZONS}
    base = {h: [] for h in HORIZONS}
    excess = {h: [] for h in HORIZONS}

    for row in scan_result["per_date"]:
        picked = pick(row)
        occurrences += len(picked)
        for h in HORIZONS:
            # 當天全體可交易個股的報酬中位數，作為該筆訊號的比較基準
            day_base = [forward_return(closes.get(s, []), row["index"], h)
                        for s in row["universe"]]
            day_base = [x for x in day_base if x is not None]
            if not day_base:
                continue
            day_median = statistics.median(day_base)
            base[h].append(day_median)
            for sid in picked:
                r = forward_return(closes.get(sid, []), row["index"], h)
                if r is None:
                    continue
                rets[h].append(r)
                # 逐筆配對：減去同一天的基準，而不是最後拿兩個彙總中位數相減。
                # 訊號在各基準日的分布不均勻，彙總相減會混入日期組成的差異。
                excess[h].append(r - day_median)

    out = {"label": label, "occurrences": occurrences,
           "dates_with_signal": sum(1 for r in scan_result["per_date"] if pick(r)),
           "horizons": {}}
    for h in HORIZONS:
        vals = rets[h]
        out["horizons"][h] = {
            "n": len(vals),
            "median": statistics.median(vals) if vals else None,
            "win_rate": (sum(1 for v in vals if v > 0) / len(vals)) if vals else None,
            "baseline": statistics.median(base[h]) if base[h] else None,
            "excess": statistics.median(excess[h]) if excess[h] else None,
            "beat_rate": (sum(1 for v in excess[h] if v > 0) / len(excess[h]))
            if excess[h] else None,
        }
    return out


def pct(v, digits=2):
    return "—" if v is None else f"{v * 100:+.{digits}f}%"


def render(scan_result: dict) -> str:
    per_date = scan_result["per_date"]
    dates = scan_result["dates"]
    cfg = scan_result["cfg"]

    signals = [
        measure(scan_result, lambda r: r["matched"], "四組全過"),
        measure(scan_result, lambda r: r["near_miss"], "差一組"),
    ]
    for g in GROUPS:
        signals.append(measure(scan_result, (lambda g: lambda r: r["groups"][g])(g),
                               f"單獨：{GROUP_LABELS[g]}"))

    # 籌碼面拆解：三個子條件各自，以及兩兩交集
    chip_signals = []
    for c, label in CHIP_LABELS.items():
        chip_signals.append(measure(
            scan_result, (lambda c: lambda r: r["conditions"][c])(c),
            f"單獨：{label}"))
    keys = list(CHIP_LABELS)
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            a, b = keys[i], keys[j]
            chip_signals.append(measure(
                scan_result,
                (lambda a, b: lambda r: sorted(
                    set(r["conditions"][a]) & set(r["conditions"][b])))(a, b),
                f"{CHIP_LABELS[a]} ＋ {CHIP_LABELS[b]}"))
    chip_signals.append(measure(scan_result, lambda r: r["groups"]["chips"],
                                "三者全過（＝籌碼面）"))

    lines = [
        "# 歷史掃描",
        "",
        f"以 `data/daily` 的 {len(dates)} 個交易日"
        f"（{dates[0]} ~ {dates[-1]}）為基礎，"
        f"用其中 {len(per_date)} 天各自當基準日重跑選股，"
        f"再看訊號出現後的走勢。",
        "",
        "此檔由 `tools/historical_scan.py` 產生，請勿手動編輯。",
        "",
        "## 先讀這段：方法上的限制",
        "",
        "- **樣本只有一年、單一市場。** 出現次數少的訊號，統計上說不了什麼。",
        "- **未計交易成本與滑價。** 報酬是收盤對收盤，實務上拿不到。",
        "- **沒有處理下市。** 期間下市的個股在資料裡就是缺值，會被排除，"
        "這會讓結果偏樂觀。",
        "- **基準是同日全體可交易個股的報酬中位數。** 只看訊號的報酬會分不清"
        "「訊號有效」與「那段時間大盤都在漲」，所以每一欄都附上基準與超額。",
        "- **超額是逐筆配對算的**：每筆訊號的報酬減去同一天全體可交易個股的"
        "報酬中位數，再取中位數。訊號在各基準日分布不均勻，"
        "直接把兩個彙總中位數相減會混入日期組成的差異。",
        "- 只有距今超過 N 個交易日的基準日才進入 N 日報酬的統計，"
        "因此期間越長樣本越少。",
        "- **未扣交易成本。** 台股一買一賣約 0.44%"
        "（手續費 0.1425% × 2、假設無折扣，加證交稅 0.3%）。"
        "低於這個數字的超額報酬實務上拿不到。",
        "- **樣本數決定可信度。** 出現數十次的訊號，超額報酬在 ±3% 之間跳動"
        "是雜訊的常態；出現數千次的訊號才看得出方向。",
        "",
        "## 訊號出現頻率",
        "",
        "| 基準日 | 可交易 | " + " | ".join(GROUP_LABELS[g] for g in GROUPS)
        + " | 四組全過 | 差一組 |",
        "|---|---|" + "---|" * (len(GROUPS) + 2),
    ]

    # 只列出有全中或差一組的日期，加上每月最後一個基準日，避免表格過長
    interesting = []
    for i, row in enumerate(per_date):
        month_end = (i == len(per_date) - 1
                     or per_date[i + 1]["date"][:7] != row["date"][:7])
        if row["matched"] or row["near_miss"] or month_end:
            interesting.append(row)
    for row in interesting:
        cells = [str(len(row["groups"][g])) for g in GROUPS]
        lines.append(
            f"| {row['date']} | {row['tradable']} | " + " | ".join(cells)
            + f" | **{len(row['matched'])}** | {len(row['near_miss'])} |")

    lines += [
        "",
        f"（表格列出有訊號的日期與每月最後一個基準日，"
        f"共 {len(interesting)} / {len(per_date)} 天）",
        "",
        "## 訊號出現後的走勢",
        "",
        "「次數」是個股 × 基準日的計數；同一檔連續多天成立會重複計入。",
        "",
    ]

    for sig in signals:
        lines += [
            f"### {sig['label']}",
            "",
            f"出現 {sig['occurrences']} 次，分布在 {sig['dates_with_signal']} 個基準日。",
            "",
        ]
        if not sig["occurrences"]:
            lines += ["整個期間都沒有出現。", ""]
            continue
        lines += [
            "| 期間 | 樣本 | 報酬中位數 | 勝率 | 同日全市場中位數 "
            "| 超額中位數 | 贏過同日市場 |",
            "|---|---|---|---|---|---|---|",
        ]
        for h in HORIZONS:
            d = sig["horizons"][h]
            win = "—" if d["win_rate"] is None else f"{d['win_rate'] * 100:.0f}%"
            beat = "—" if d["beat_rate"] is None else f"{d['beat_rate'] * 100:.0f}%"
            lines.append(f"| {h} 日 | {d['n']} | {pct(d['median'])} | {win} "
                         f"| {pct(d['baseline'])} | {pct(d['excess'])} | {beat} |")
        lines.append("")

    lines += [
        "## 籌碼面拆解",
        "",
        "籌碼面是三個條件的交集。拆開看才知道是三者都有貢獻，"
        "還是其中一個在帶動、其他兩個只是在減少樣本。",
        "",
    ]
    for sig in chip_signals:
        lines += [
            f"### {sig['label']}",
            "",
            f"出現 {sig['occurrences']} 次，分布在 {sig['dates_with_signal']} 個基準日。",
            "",
        ]
        if not sig["occurrences"]:
            lines += ["整個期間都沒有出現。", ""]
            continue
        lines += [
            "| 期間 | 樣本 | 報酬中位數 | 勝率 | 同日全市場中位數 "
            "| 超額中位數 | 贏過同日市場 |",
            "|---|---|---|---|---|---|---|",
        ]
        for h in HORIZONS:
            d = sig["horizons"][h]
            win = "—" if d["win_rate"] is None else f"{d['win_rate'] * 100:.0f}%"
            beat = "—" if d["beat_rate"] is None else f"{d['beat_rate'] * 100:.0f}%"
            lines.append(f"| {h} 日 | {d['n']} | {pct(d['median'])} | {win} "
                         f"| {pct(d['baseline'])} | {pct(d['excess'])} | {beat} |")
        lines.append("")

    lines += [
        "## 使用的門檻",
        "",
        "```json",
        __import__("json").dumps(cfg.to_dict(), ensure_ascii=False, indent=2),
        "```",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="歷史掃描")
    ap.add_argument("--out", default="docs/historical-scan.md")
    ap.add_argument("--days", type=int, default=400)
    args = ap.parse_args()

    print("開始掃描…", flush=True)
    result = scan(days=args.days)
    report = render(result)

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write(report)
    print(f"\n報告已寫入 {args.out}（{len(report.splitlines())} 行）")

    matched = sum(len(r["matched"]) for r in result["per_date"])
    near = sum(len(r["near_miss"]) for r in result["per_date"])
    print(f"四組全過共出現 {matched} 次，差一組 {near} 次，"
          f"基準日 {len(result['per_date'])} 個")
    return 0


if __name__ == "__main__":
    sys.exit(main())
