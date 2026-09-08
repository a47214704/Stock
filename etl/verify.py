"""端點探測。

因為交易所的欄位名稱可能與程式裡的別名對不上，第一次部署前先跑這個指令，
它會實際打每個端點、印出回應的表頭與第一列資料，並試著用現有的別名解析，
直接告訴你哪個欄位對不上、該補什麼別名。
"""
from __future__ import annotations

import json
from typing import Any

from . import config
from .http import NotJSON, get_json
from .parsing import clean_text, iter_tables, resolve_columns
from .sources import twse
from .storage import to_api_date, parse_date

# 各交易所的 OpenAPI 規格位置。discover 直接讀它，就不必靠猜端點名稱。
SWAGGER = {
    "tpex": "https://www.tpex.org.tw/openapi/swagger.json",
    "twse": "https://openapi.twse.com.tw/v1/swagger.json",
}

# 用來從規格中挑出候選端點的關鍵字。路徑與說明任一命中即列為候選。
DATASET_KEYWORDS = {
    "price": ["收盤", "行情", "close", "quote", "daily_close"],
    "institutional": ["三大法人", "法人", "institution", "3itrade", "trade_hedge",
                      "foreign_trust_dealer"],
    "margin": ["融資", "融券", "margin", "short_sale"],
    "foreign": ["外資", "持股", "僑外", "foreign", "shareholding", "holding"],
}

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


def _endpoint_paths(spec: dict) -> dict[str, str]:
    """從 OpenAPI 規格取出 {路徑: 說明}，同時吃 OAS2 與 OAS3 的形狀。"""
    out: dict[str, str] = {}
    paths = spec.get("paths")
    if not isinstance(paths, dict):
        return out
    for path, methods in paths.items():
        note = ""
        if isinstance(methods, dict):
            get = methods.get("get") or next(
                (v for v in methods.values() if isinstance(v, dict)), {})
            if isinstance(get, dict):
                note = clean_text(get.get("summary") or get.get("description") or "")
        out[str(path)] = note
    return out


def discover(market: str, grep: str | None = None) -> int:
    """列出交易所實際提供的端點，並比對目前設定的路徑是否存在。

    TPEx 的端點名稱無法從公開文件可靠地推斷，猜錯時伺服器會回 HTML 錯誤頁，
    只看 JSON 解析失敗的訊息完全查不出原因。這個指令直接讀官方的 OpenAPI
    規格，把真實路徑列出來。
    """
    url = SWAGGER.get(market)
    if not url:
        print(f"沒有 {market} 的 OpenAPI 規格位置")
        return 1

    print(f"讀取 {url}")
    try:
        spec = get_json(url)
    except Exception as exc:                          # noqa: BLE001
        print(f"✗ 取得規格失敗：{exc}")
        return 1

    endpoints = _endpoint_paths(spec if isinstance(spec, dict) else {})
    if not endpoints:
        print(f"✗ 規格中沒有 paths 區段：{_preview(spec, 200)}")
        return 1
    print(f"規格共 {len(endpoints)} 個端點\n")

    if grep:
        needle = grep.lower()
        hits = {p: n for p, n in endpoints.items()
                if needle in p.lower() or needle in n.lower()}
        print(f"{'=' * 72}\n符合「{grep}」的端點（{len(hits)} 個）")
        for path, note in sorted(hits.items()):
            print(f"  {path}\n      {note or '（無說明）'}")
        return 0

    configured = config.TPEX_ENDPOINTS if market == "tpex" else {}
    problems = 0

    print(f"{'=' * 72}\n目前設定的端點是否存在於規格中")
    known = set(endpoints)
    for kind, full_url in configured.items():
        suffix = "/" + full_url.split("/openapi/", 1)[-1] if "/openapi/" in full_url \
            else "/" + full_url.rsplit("/", 1)[-1]
        exists = suffix in known or any(k.endswith(suffix) for k in known)
        print(f"  {kind:<15} {suffix:<48} {'✓ 存在' if exists else '✗ 不存在'}")
        if not exists:
            problems += 1

    if problems:
        print(f"\n{'=' * 72}\n依關鍵字比對出的候選端點")
        suggestions: dict[str, str] = {}
        for kind, keywords in DATASET_KEYWORDS.items():
            matches = [
                (path, note) for path, note in sorted(endpoints.items())
                if any(k.lower() in path.lower() or k.lower() in note.lower()
                       for k in keywords)
            ]
            print(f"\n  [{kind}]  關鍵字 {keywords}")
            if not matches:
                print("      找不到候選，請用 --grep 自行搜尋")
                continue
            for path, note in matches[:6]:
                print(f"      {path}\n          {note or '（無說明）'}")
            suggestions[kind] = matches[0][0]

        if suggestions:
            base = SWAGGER[market].rsplit("/", 1)[0]
            print(f"\n{'=' * 72}\n把確認過的路徑填回 etl/config.py 的 "
                  f"{market.upper()}_ENDPOINTS，例如：\n")
            print(f"{market.upper()}_ENDPOINTS = {{")
            for kind, path in suggestions.items():
                print(f'    "{kind}": "{base}{path}",')
            print("}")
            print("\n（以上只是關鍵字命中的第一個候選，請對照上面的說明挑對的那個）")

    return problems


def probe_twse(date_text: str) -> int:
    """逐一試出 TWSE 各報表正確的 rwd 路徑。

    rwd 的路徑分段無法從網頁路徑推導，而且猜錯時伺服器回的是 HTML 而不是 404，
    只看 JSON 解析失敗的訊息完全查不出原因。這個指令把候選路徑一個個打過去，
    直接告訴你哪個可用。
    """
    api_date = to_api_date(parse_date(date_text))
    print(f"以 {api_date} 逐一測試候選路徑\n")
    working: dict[str, str] = {}

    for kind, candidates in config.TWSE_PATH_CANDIDATES.items():
        spec, required = SPECS[kind]
        params = dict(config.TWSE_PARAMS[kind])
        params["date"] = api_date
        print(f"{'=' * 72}\n[{kind}]  params={params}")

        for suffix in candidates:
            url = f"{config.TWSE_BASE}/{suffix}"
            try:
                payload = get_json(url, params)
            except NotJSON:
                print(f"  ✗ {suffix:<32} 回應不是 JSON（路徑不存在）")
                continue
            except Exception as exc:                  # noqa: BLE001
                print(f"  ✗ {suffix:<32} {type(exc).__name__}: {str(exc)[:90]}")
                continue

            if not isinstance(payload, dict):
                print(f"  ✗ {suffix:<32} 回應不是 JSON 物件")
                continue

            stat = clean_text(payload.get("stat"))
            if stat and stat.upper() != "OK":
                # 路徑是對的，只是這個日期沒有資料——仍算可用
                print(f"  △ {suffix:<32} 路徑可用，但 stat={stat!r}")
                working.setdefault(kind, suffix)
                continue

            rows = 0
            matched = False
            for fields, data in iter_tables(payload):
                if not data:
                    continue
                rows = len(data)
                try:
                    resolve_columns(fields, spec, required)
                    matched = True
                    break
                except LookupError:
                    continue
            if matched:
                print(f"  ✓ {suffix:<32} 可用，{rows} 列，欄位對得上")
                working.setdefault(kind, suffix)
            else:
                print(f"  △ {suffix:<32} 有回應（{rows} 列）但欄位對不上，"
                      f"請用 verify 看表頭")
                working.setdefault(kind, suffix)

    print(f"\n{'=' * 72}")
    missing = [k for k in config.TWSE_PATH_CANDIDATES if k not in working]
    if missing:
        print(f"以下資料集所有候選都失敗：{missing}")
        print("請到 TWSE 網站按下查詢、從瀏覽器的開發者工具 Network 分頁複製實際網址，"
              "再把路徑加進 etl/config.py 的 TWSE_PATH_CANDIDATES。")
    if working:
        print("\n可用的路徑（填回 etl/config.py 的 TWSE_ENDPOINTS）：\n")
        print("TWSE_ENDPOINTS = {")
        for kind, suffix in working.items():
            print(f'    "{kind}": f"{{TWSE_BASE}}/{suffix}",')
        print("}")
    return len(missing)


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
