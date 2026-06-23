from types import SimpleNamespace

from synthetic_traffic import Health, Worker, extract_csrf_token, parse_args


class _Resp:
    def __init__(self, status_code=200, text="", ok=True):
        self.status_code = status_code
        self.text = text
        self.ok = ok
        self.headers = {}


def _args(**overrides):
    values = {
        "base_url": "https://wiki-polis.test",
        "slug": "test",
        "conversation_id": "abc1234567",
        "csrf_token": None,
        "submit_text_prefix": "[test]",
        "insecure": False,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_extract_csrf_token_from_conversation_script():
    assert extract_csrf_token("var csrfToken = 'abc123';") == "abc123"


def test_act_submit_fetches_and_sends_flask_csrf(monkeypatch):
    worker = Worker(0, _args(), Health(), deadline=None, stop=SimpleNamespace(is_set=lambda: False))
    calls = []

    def fake_req(action, method, path, **kwargs):
        calls.append((action, method, path, kwargs))
        if action == "csrf":
            return _Resp(text="<script>var csrfToken = 'TOK123';</script>")
        return _Resp(status_code=201, text="{}")

    monkeypatch.setattr(worker, "_req", fake_req)

    worker.act_submit()

    submit = [c for c in calls if c[0] == "submit"][0]
    assert submit[3]["headers"]["X-CSRFToken"] == "TOK123"
    assert submit[3]["headers"]["Origin"] == "https://wiki-polis.test"


def test_act_submit_uses_cli_csrf_without_fetch(monkeypatch):
    worker = Worker(0, _args(csrf_token="CLI456"), Health(), deadline=None,
                    stop=SimpleNamespace(is_set=lambda: False))
    calls = []

    def fake_req(action, method, path, **kwargs):
        calls.append((action, method, path, kwargs))
        return _Resp(status_code=201, text="{}")

    monkeypatch.setattr(worker, "_req", fake_req)

    worker.act_submit()

    assert [c[0] for c in calls] == ["submit"]
    assert calls[0][3]["headers"]["X-CSRFToken"] == "CLI456"


def test_parse_args_accepts_csrf_token():
    args = parse_args(["--dry-run", "--csrf-token", "TOK"])
    assert args.csrf_token == "TOK"
