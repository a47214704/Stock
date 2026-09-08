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


def get_json(url: str, params: dict[str, Any] | None = None) -> Any:
    """抓取 JSON，失敗時指數退避重試。

    交易所在非交易日或查無資料時可能回 200 但內容為空／stat 非 OK，
    這裡只負責取得 JSON，語意判斷交給呼叫端。
    """
    last_err: Exception | None = None
    for attempt in range(config.MAX_RETRIES):
        _throttle()
        try:
            resp = session().get(url, params=params, timeout=config.REQUEST_TIMEOUT_SEC)
            if resp.status_code == 200:
                text = resp.text.strip()
                if not text:
                    return None
                return resp.json()
            # 429 / 5xx 值得重試，4xx 其他多半重試也沒用
            if resp.status_code not in (429, 500, 502, 503, 504):
                raise FetchError(f"{url} 回應 HTTP {resp.status_code}")
            last_err = FetchError(f"{url} 回應 HTTP {resp.status_code}")
        except (requests.RequestException, ValueError) as exc:
            last_err = exc

        backoff = config.RETRY_BACKOFF_SEC[min(attempt, len(config.RETRY_BACKOFF_SEC) - 1)]
        log.warning("抓取失敗 (%s/%s) %s：%s，%s 秒後重試",
                    attempt + 1, config.MAX_RETRIES, url, last_err, backoff)
        time.sleep(backoff)

    raise FetchError(f"抓取 {url} 失敗，已重試 {config.MAX_RETRIES} 次：{last_err}")
