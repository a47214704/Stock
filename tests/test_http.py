"""抓取層的重試策略。

重點是**什麼情況不該重試**：路徑打錯時伺服器回 HTML 錯誤頁，
重試四次只是白等 30 秒的退避時間，而且錯誤訊息還看不出原因。
"""
import json

import pytest
import requests

from etl import config, http
from etl.http import FetchError, NotJSON, get_json


class FakeResponse:
    def __init__(self, status=200, text="", content_type="application/json", data=None):
        self.status_code = status
        # 給 data 時同時填好 text——真實回應不會有「內容為空但 json() 有值」的情形，
        # 替身若不一致就會誤觸「空內容回 None」的分支。
        self.text = json.dumps(data, ensure_ascii=False) if data is not None else text
        self.headers = {"Content-Type": content_type}
        self._data = data

    def json(self):
        return self._data if self._data is not None else json.loads(self.text)


class FakeSession:
    """記錄請求次數，用來驗證有沒有多餘的重試。"""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = 0

    def get(self, url, params=None, timeout=None):
        self.calls += 1
        item = self.responses[min(self.calls - 1, len(self.responses) - 1)]
        if isinstance(item, Exception):
            raise item
        return item


@pytest.fixture(autouse=True)
def no_waiting(monkeypatch):
    """把節流與退避的等待拿掉，測試不必真的睡 30 秒。"""
    monkeypatch.setattr(http, "_throttle", lambda: None)
    monkeypatch.setattr(http.time, "sleep", lambda _: None)


@pytest.fixture
def install(monkeypatch):
    def _install(*responses):
        fake = FakeSession(*responses)
        monkeypatch.setattr(http, "session", lambda: fake)
        return fake
    return _install


class TestSuccess:
    def test_returns_parsed_json(self, install):
        install(FakeResponse(data={"stat": "OK"}))
        assert get_json("https://example.test/x") == {"stat": "OK"}

    def test_empty_body_returns_none(self, install):
        install(FakeResponse(text="   "))
        assert get_json("https://example.test/x") is None


class TestNonJSON:
    """路徑打錯是最常見的情形，也是這次修正的重點。"""

    HTML = "<!DOCTYPE html><html><head><title>404</title></head><body>Not Found</body></html>"

    def test_raises_not_json_without_retrying(self, install):
        fake = install(FakeResponse(text=self.HTML, content_type="text/html"))
        with pytest.raises(NotJSON):
            get_json("https://example.test/wrong-path")
        assert fake.calls == 1, "非 JSON 的回應重試再多次也不會變成 JSON"

    def test_message_carries_enough_to_diagnose(self, install):
        install(FakeResponse(text=self.HTML, content_type="text/html"))
        with pytest.raises(NotJSON) as exc:
            get_json("https://example.test/wrong-path")
        message = str(exc.value)
        assert "HTTP 200" in message
        assert "text/html" in message
        assert "DOCTYPE" in message          # 帶出實際內容開頭
        assert "discover" in message         # 指向排錯的指令

    def test_body_snippet_is_truncated(self, install):
        install(FakeResponse(text="x" * 5000, content_type="text/html"))
        with pytest.raises(NotJSON) as exc:
            get_json("https://example.test/x")
        assert len(str(exc.value)) < 600

    def test_is_a_fetch_error_so_callers_can_catch_broadly(self):
        assert issubclass(NotJSON, FetchError)


class TestStatusCodes:
    def test_does_not_retry_404(self, install):
        fake = install(FakeResponse(status=404, text="nope", content_type="text/html"))
        with pytest.raises(FetchError):
            get_json("https://example.test/x")
        assert fake.calls == 1

    def test_retries_503_then_succeeds(self, install):
        fake = install(
            FakeResponse(status=503, text="busy"),
            FakeResponse(data={"ok": True}),
        )
        assert get_json("https://example.test/x") == {"ok": True}
        assert fake.calls == 2

    def test_gives_up_after_max_retries(self, install):
        fake = install(FakeResponse(status=503, text="busy"))
        with pytest.raises(FetchError, match="已重試"):
            get_json("https://example.test/x")
        assert fake.calls == config.MAX_RETRIES

    def test_retries_connection_errors(self, install):
        fake = install(
            requests.ConnectionError("斷線"),
            FakeResponse(data={"ok": True}),
        )
        assert get_json("https://example.test/x") == {"ok": True}
        assert fake.calls == 2


class TestNoWastedBackoff:
    def test_does_not_sleep_after_the_final_attempt(self, install, monkeypatch):
        """原本最後一輪也會記錄「N 秒後重試」並真的睡完，但後面已經沒有下一次嘗試。"""
        sleeps = []
        monkeypatch.setattr(http.time, "sleep", lambda s: sleeps.append(s))
        install(FakeResponse(status=503, text="busy"))
        with pytest.raises(FetchError):
            get_json("https://example.test/x")
        assert len(sleeps) == config.MAX_RETRIES - 1


class TestDescribe:
    def test_collapses_whitespace(self, install):
        resp = FakeResponse(text="a\n\n   b\t\tc", content_type="text/html")
        assert "'a b c'" in http._describe(resp)
