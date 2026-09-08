"""端點探測。

因為交易所的欄位名稱可能與程式裡的別名對不上，第一次部署前先跑這個指令，
它會實際打每個端點、印出回應的表頭與第一列資料，並試著用現有的別名解析，
直接告訴你哪個欄位對不上、該補什麼別名。
"""
from __future__ import annotations

import json
from typing import Any

from . import config
from .http import get_json
from .parsing import iter_tables, resolve_columns
from .sources import twse
from .storage import to_api_date, parse_date

SPECS = {
    "price": (twse.PRICE_SPEC, twse.PRICE_REQUIRED),
    "institutional": (twse.INSTITUTIONAL_SPEC, twse.INSTITUTIONAL_REQUIRED),
    "margin": (twse.MARGIN_SPEC, twse.MARGIN_REQUIRED),
    "foreign": (twse.FOREIGN_SPEC, twse.FOREIGN_REQUIRED),
}


def _preview(value: Any, limit: int = 400) -> str:
    text = json.dumps(value, ensure_ascii=False)
    return text if len(text) <= limit else text[:limit] + " …"


def verify_twse(date_text: str) -> int:
    api_date = to_api_date(parse_date(date_text))
    problems = 0

    for kind, url in config.TWSE_ENDPOINTS.items():
        params = dict(config.TWSE_PARAMS[kind])
        params["date"] = api_date
        print(f"\n{'=' * 72}\n[TWSE] {kind}\n  {url}\n  params={params}")
        try:
            payload = get_json(url, params)
        except Exception as exc:                          # noqa: BLE001
            print(f"  ✗ 請求失敗：{exc}")
            problems += 1
            continue

        if not isinstance(payload, dict):
            print(f"  ✗ 回應不是 JSON 物件：{type(payload).__name__}")
            problems += 1
            continue

        print(f"  stat={payload.get('stat')!r}  date={payload.get('date')!r}")
        print(f"  回應中的資料日期（推斷）={twse._extract_date(payload)!r}")
        print(f"  top-level keys={list(payload)[:12]}")

        spec, required = SPECS[kind]
        matched = False
        for i, (fields, data) in enumerate(iter_tables(payload)):
            if not data:
                continue
            print(f"\n  -- 表格 {i}：{len(data)} 列")
            print(f"     表頭：{_preview(fields)}")
            print(f"     首列：{_preview(data[0])}")
            try:
                cols = resolve_columns(fields, spec, required)
            except LookupError as exc:
                print(f"     欄位對應：✗ {exc}")
                continue
            matched = True
            print("     欄位對應：✓")
            for key, idx in sorted(cols.items()):
                if idx is None:
                    print(f"       {key:<20} → （未對到，此欄為選用）")
                else:
                    sample = data[0][idx] if idx < len(data[0]) else "?"
                    print(f"       {key:<20} → [{idx}] {fields[idx]!r} = {sample!r}")
            break

        if not matched:
            print("  ✗ 沒有任何表格能對應到必要欄位，請依上面的表頭更新 etl/sources/twse.py 的別名")
            problems += 1

    return problems


def verify_tpex() -> int:
    problems = 0
    for kind, url in config.TPEX_ENDPOINTS.items():
        print(f"\n{'=' * 72}\n[TPEx] {kind}\n  {url}")
        try:
            payload = get_json(url)
        except Exception as exc:                          # noqa: BLE001
            print(f"  ✗ 請求失敗：{exc}")
            problems += 1
            continue
        if isinstance(payload, list) and payload:
            print(f"  回傳 {len(payload)} 列")
            print(f"  首列 keys：{list(payload[0])}")
            print(f"  首列：{_preview(payload[0])}")
        else:
            print(f"  ✗ 非預期格式：{_preview(payload, 200)}")
            problems += 1
    return problems
