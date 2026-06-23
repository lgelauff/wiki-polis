from ops.microservice_smoke import check_embedding_sidecar, check_wiki_health, ping_deadman


class _Resp:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload


class _Session:
    def __init__(self, gets=None, posts=None):
        self.gets = list(gets or [])
        self.posts = list(posts or [])
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append(("GET", url, kwargs))
        return self.gets.pop(0)

    def post(self, url, **kwargs):
        self.calls.append(("POST", url, kwargs))
        return self.posts.pop(0)


def test_check_wiki_health_ok():
    session = _Session(gets=[_Resp(payload={"status": "ok", "db": "ok", "particiapi": "ok"})])
    result = check_wiki_health("https://wiki-polis.test", session=session)
    assert result.ok is True
    assert session.calls[0][1] == "https://wiki-polis.test/health"


def test_check_wiki_health_fails_on_particiapi_unreachable():
    session = _Session(gets=[_Resp(payload={
        "status": "ok",
        "db": "ok",
        "particiapi": "unreachable",
    })])
    result = check_wiki_health("https://wiki-polis.test", session=session)
    assert result.ok is False
    assert "particiapi unreachable" in result.detail


def test_check_embedding_sidecar_similarity_contract():
    session = _Session(
        gets=[_Resp(payload={"status": "ok"})],
        posts=[_Resp(payload={"similarity": 0.999})],
    )
    result = check_embedding_sidecar("http://127.0.0.1:8015", session=session)
    assert result.ok is True
    assert session.calls[1][1] == "http://127.0.0.1:8015/similarity"


def test_ping_deadman_uses_fail_suffix_on_failure():
    session = _Session(gets=[_Resp()])
    ping_deadman("https://hc-ping.com/uuid", False, "bad", session=session)
    assert session.calls[0][1] == "https://hc-ping.com/uuid/fail"
    assert session.calls[0][2]["params"] == {"summary": "bad"}
