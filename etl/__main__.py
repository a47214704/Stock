"""指令進入點：python -m etl <command>"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date as Date, datetime, timedelta, timezone

from . import build as build_mod
from . import config, storage, verify as verify_mod
from .pipeline import MARKETS, fetch_date, fetch_one, missing_datasets

# 台北時間。GitHub Actions 的 runner 跑在 UTC，交易日的判斷要用台北日期。
TAIPEI = timezone(timedelta(hours=8))

log = logging.getLogger("etl")


def setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def parse_markets(text: str) -> list[str]:
    markets = [m.strip() for m in text.split(",") if m.strip()]
    unknown = [m for m in markets if m not in MARKETS]
    if unknown:
        raise SystemExit(f"未知的市場：{unknown}，可用的有 {list(MARKETS)}")
    return markets


def today_taipei() -> Date:
    return datetime.now(TAIPEI).date()


def cmd_fetch(args) -> int:
    day = storage.parse_date(args.date) if args.date else today_taipei()
    key = storage.to_key(day)

    if storage.has_daily(key) and not args.force:
        log.info("%s 的快照已存在，略過（要重抓請加 --force）", key)
        return 0
    if day.weekday() >= 5:
        log.info("%s 是週末，非交易日", key)
        return 0

    markets = parse_markets(args.markets)
    stocks = fetch_date(day, markets)
    if not stocks:
        log.info("%s 沒有取得任何行情，判定為非交易日或資料尚未公布", key)
        return 0

    path = storage.save_daily(key, stocks, markets)
    storage.update_stock_info(stocks)
    log.info("已寫入 %s（%s 檔）", path, len(stocks))
    return 0


def cmd_backfill(args) -> int:
    start = storage.parse_date(args.start)
    end = storage.parse_date(args.end) if args.end else today_taipei()
    markets = parse_markets(args.markets)

    days = [d for d in storage.weekdays(start, end)]
    pending = [d for d in days if args.force or not storage.has_daily(storage.to_key(d))]
    log.info("回補區間 %s ~ %s：平日 %s 天，待抓 %s 天（約需 %.0f 分鐘）",
             args.start, storage.to_key(end), len(days), len(pending),
             len(pending) * len(markets) * 4 * config.REQUEST_DELAY_SEC / 60)

    written = 0
    for day in pending:
        key = storage.to_key(day)
        try:
            stocks = fetch_date(day, markets)
        except KeyboardInterrupt:
            log.warning("使用者中斷，已完成的日期保留")
            break
        except Exception as exc:                          # noqa: BLE001
            log.error("%s 抓取失敗，跳過：%s", key, exc)
            continue
        if not stocks:
            log.info("%s 無資料（假日或休市）", key)
            continue
        storage.save_daily(key, stocks, markets)
        storage.update_stock_info(stocks)
        written += 1
        log.info("%s ✓ %s 檔（累計 %s 天）", key, len(stocks), written)

    log.info("回補結束，新增 %s 天", written)
    return 0


def cmd_build(args) -> int:
    summary = build_mod.build(days=args.days)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def cmd_export(args) -> int:
    """輸出全市場的歷史圖資到指定目錄，供部署時使用。"""
    summary = build_mod.export_history(args.out, days=args.days)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def cmd_coverage(args) -> int:
    info = build_mod.coverage()
    print(json.dumps(info, ensure_ascii=False, indent=2))
    not_ready = [k for k, v in info.get("ready", {}).items() if not v]
    if not_ready:
        print(f"\n尚未累積足夠歷史的條件：{', '.join(not_ready)}", file=sys.stderr)
    return 0


def cmd_probe(args) -> int:
    date_text = args.date or storage.to_key(today_taipei() - timedelta(days=1))
    missing = verify_mod.probe_twse(date_text)
    return 1 if missing else 0


def cmd_refresh(args) -> int:
    """補抓缺漏或延遲公布的報表，寫進既有快照。

    兩種情形都靠這個修：

    * 延遲公布——外資持股當天抓不到（TWSE 回「查詢日期大於可查詢最大日期」），
      要等下一個交易日。
    * 當日抓取失敗——某天抓的時候端點路徑還是錯的，之後修好了，
      但 backfill 只補「完全沒有快照」的日期，那天仍會永遠缺那一組。

    未指定 --datasets 時會逐日偵測整組缺漏的資料集，只補真正缺的，
    另外一律嘗試延遲公布的那幾組。
    """
    explicit = ([d.strip() for d in args.datasets.split(",") if d.strip()]
                if args.datasets else None)
    markets = parse_markets(args.markets)
    dates = storage.list_daily_dates()[-args.days:]
    if not dates:
        log.info("還沒有任何快照可補")
        return 0

    log.info("檢查最近 %s 個交易日（市場 %s，資料集 %s）",
             len(dates), markets, explicit or "自動偵測")
    total = 0
    for key in dates:
        datasets = explicit
        if datasets is None:
            datasets = sorted(set(missing_datasets(key)) | set(config.LATE_DATASETS))
        if not datasets:
            continue

        day = storage.parse_date(key)
        updates: dict[str, dict] = {}
        for market in markets:
            for dataset in datasets:
                for stock_id, fields in fetch_one(day, market, dataset).items():
                    updates.setdefault(stock_id, {}).update(fields)
        if not updates:
            log.info("%s %s：沒有取得資料", key, datasets)
            continue
        changed = storage.patch_daily(key, updates)
        total += changed
        log.info("%s ✓ 補 %s，更新 %s 檔", key, datasets, changed)

    log.info("補抓結束，共更新 %s 筆", total)
    return 0


def cmd_discover(args) -> int:
    problems = verify_mod.discover(args.market, args.grep, args.all)
    if problems:
        print(f"\n有 {problems} 個端點需要更正。")
    return 0


def cmd_verify(args) -> int:
    date_text = args.date or storage.to_key(today_taipei() - timedelta(days=1))
    problems = 0
    if args.market in ("twse", "both"):
        problems += verify_mod.verify_twse(date_text)
    if args.market in ("tpex", "both"):
        problems += verify_mod.verify_tpex()

    print(f"\n{'=' * 72}")
    if problems:
        print(f"有 {problems} 個端點需要處理，請依上面印出的表頭調整 etl/sources/ 的欄位別名。")
    else:
        print("所有端點都能正常解析。")
    return 1 if problems else 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m etl", description="台股選股 ETL")
    parser.add_argument("-v", "--verbose", action="store_true", help="輸出除錯訊息")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("fetch", help="抓取單日全市場資料並寫成快照")
    p.add_argument("--date", help="YYYY-MM-DD，預設為台北時間今天")
    p.add_argument("--markets", default="twse,tpex")
    p.add_argument("--force", action="store_true", help="快照已存在也重抓")
    p.set_defaults(func=cmd_fetch)

    p = sub.add_parser("backfill", help="回補一段區間的歷史快照")
    p.add_argument("--start", required=True, help="YYYY-MM-DD")
    p.add_argument("--end", help="YYYY-MM-DD，預設為今天")
    p.add_argument("--markets", default="twse")
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=cmd_backfill)

    p = sub.add_parser("build", help="由快照重建 signals 與前端資料")
    p.add_argument("--days", type=int, default=260, help="納入計算的交易日數")
    p.set_defaults(func=cmd_build)

    p = sub.add_parser(
        "export",
        help="輸出全市場歷史圖資（不進 git，部署時現算）")
    p.add_argument("--out", default="_site/data/history", help="輸出目錄")
    p.add_argument("--days", type=int, default=260)
    p.set_defaults(func=cmd_export)

    p = sub.add_parser("coverage", help="檢查已累積的資料是否足以判斷各條件")
    p.set_defaults(func=cmd_coverage)

    p = sub.add_parser(
        "probe",
        help="逐一試出 TWSE 各報表正確的 rwd 路徑")
    p.add_argument("--date", help="YYYY-MM-DD，預設為昨天")
    p.set_defaults(func=cmd_probe)

    p = sub.add_parser(
        "refresh",
        help="補抓延遲公布的報表（例如外資持股），寫進既有快照")
    p.add_argument("--datasets", default=None,
                   help="要補的資料集，逗號分隔。不給則逐日偵測整組缺漏的，"
                        f"並一律嘗試 {','.join(config.LATE_DATASETS)}")
    p.add_argument("--days", type=int, default=5, help="往回補幾個交易日")
    p.add_argument("--markets", default="twse")
    p.set_defaults(func=cmd_refresh)

    p = sub.add_parser(
        "discover",
        help="讀交易所的 OpenAPI 規格，列出實際端點並檢查設定是否正確")
    p.add_argument("--market", choices=["tpex", "twse"], default="tpex")
    p.add_argument("--grep", help="只列出路徑或說明含此關鍵字的端點")
    p.add_argument("--all", action="store_true", help="列出規格中的全部端點")
    p.set_defaults(func=cmd_discover)

    p = sub.add_parser("verify", help="探測端點並印出實際欄位，用來校正欄位別名")
    p.add_argument("--market", choices=["twse", "tpex", "both"], default="both")
    p.add_argument("--date", help="YYYY-MM-DD，預設為昨天")
    p.set_defaults(func=cmd_verify)

    args = parser.parse_args(argv)
    setup_logging(args.verbose)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
