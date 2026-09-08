"""HTTP 抓取：重試、退避、節流。"""
from __future__ import annotations

import logging
import time
from typing import Any

import requests

from . import config

log = logging.getLogger(__name__)

_session: requests.Session | None = None
_last_request_at = 0.0


def session() -> requests.Session:
    global _session
    if _session is None:
        s = requests.Session()
        s.headers.update({"User-Agent": config.USER_AGENT, "Accept": "application/json"})
        _session = s
    return _session


def _throttle() -> None:
    """確保兩次請求之間至少間隔 REQUEST_DELAY_SEC。"""
    global _last_request_at
    wait = config.REQUEST_DELAY_SEC - (time.monotonic() - _last_request_at)
    if wait > 0:
        time.sleep(wait)
    _last_request_at = time.monotonic()


class FetchError(RuntimeError):
    pass


class NotJSON(FetchError):
    """回應是 200 但內容不是 JSON——通常是路徑錯誤時傳回的 HTML 錯誤頁。

    這種失敗重試再多次也不會變成 JSON，所以獨立成一類、不進退避重試。
    """


RETRYABLE_STATUS = (429, 500, 502, 503, 504)


def _describe(resp: requests.Response, limit: int = 200) -> str:
    """把非 JSON 的回應描述成可診斷的訊息。

    只說「Expecting value: line 1 column 1」對排錯毫無幫助——那只是
    json 模組在抱怨第一個字元不是 JSON。真正需要知道的是伺服器到底回了什麼。
    """
    body = " ".join(resp.text.split())[:limit]
    return (f"HTTP {resp.status_code}"
            f"，Content-Type: {resp.headers.get('Content-Type', '未提供')}"
            f"，內容開頭：{body!r}")


def get_json(url: str, params: dict[str, Any] | None = None) -> Any:
    """抓取 JSON。連線問題與伺服器端暫時性錯誤會指數退避重試。

    交易所在非交易日或查無資料時可能回 200 但內容為空／stat 非 OK，
    這裡只負責取得 JSON，語意判斷交給呼叫端。

    不重試的情況：
    * 200 但內容不是 JSON（通常是路徑打錯，伺服器回 HTML 錯誤頁）
    * 429 與 5xx 以外的 HTTP 錯誤狀態
    這兩種重試再多次結果都一樣，只是白等退避時間。
    """
    last_err: Exception | None = None
    for attempt in range(config.MAX_RETRIES):
        _throttle()
        try:
            resp = session().get(url, params=params, timeout=config.REQUEST_TIMEOUT_SEC)
            if resp.status_code == 200:
                if not resp.text.strip():
                    return None
                try:
                    return resp.json()
                except ValueError as exc:
                    raise NotJSON(
                        f"{url} 的回應不是 JSON（{_describe(resp)}）。"
                        f"請確認端點路徑是否正確——可用 `python -m etl discover` "
                        f"列出交易所實際提供的路徑。原始錯誤：{exc}"
                    ) from exc
            if resp.status_code not in RETRYABLE_STATUS:
                raise FetchError(f"{url} 回應 {_describe(resp, 120)}")
            last_err = FetchError(f"{url} 回應 HTTP {resp.status_code}")
        except requests.RequestException as exc:
            last_err = exc

        # 最後一輪不必再等——後面沒有下一次嘗試了
        if attempt == config.MAX_RETRIES - 1:
            break
        backoff = config.RETRY_BACKOFF_SEC[min(attempt, len(config.RETRY_BACKOFF_SEC) - 1)]
        log.warning("抓取失敗 (%s/%s) %s：%s，%s 秒後重試",
                    attempt + 1, config.MAX_RETRIES, url, last_err, backoff)
        time.sleep(backoff)

    raise FetchError(f"抓取 {url} 失敗，已重試 {config.MAX_RETRIES} 次：{last_err}")
