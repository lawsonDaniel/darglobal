"""HTTP API and security behaviour (the agent is faked here; see test_agent.py for the real loop)."""
import pytest
from fastapi.testclient import TestClient

from app import agent, main, security
from app.sessions import SessionStore


@pytest.fixture
def client(monkeypatch):
    seen = []

    async def fake_answer(history, engine=None):
        seen.append([dict(m) for m in history])
        return agent.Result(reply=f"answer {len(history)}", mode="agent", model="fake",
                            tools_used=[{"tool": "search_knowledge", "args": {}}], sources=[], checks={})
    async def fake_stream(history, engine=None):
        seen.append([dict(m) for m in history])
        yield "status", "Searching DarGlobal projects"
        yield "draft", "partial "
        yield "done", agent.Result(reply=f"streamed {len(history)}", mode="agent", model="fake",
                                   tools_used=[], sources=["https://darglobal.co.uk"], checks={})
    monkeypatch.setattr(agent, "answer", fake_answer)
    monkeypatch.setattr(agent, "answer_stream", fake_stream)
    app = main.create_app()
    with TestClient(app) as c:
        c.seen = seen
        c.app_ref = app
        yield c


def test_pages_and_health(client):
    r = client.get("/")
    assert r.status_code == 200 and "app.js" in r.text
    h = client.get("/api/health").json()
    assert h["ok"] and h["projects"] == 38 and h["villas"] == 245 and h["index"]["documents"] == 306
    assert client.get("/static/app.js").status_code == 200


def test_security_headers(client):
    r = client.get("/")
    csp = r.headers["content-security-policy"]
    assert "script-src 'self'" in csp and "unsafe-inline" not in csp and "frame-ancestors 'none'" in csp
    assert r.headers["x-content-type-options"] == "nosniff" and r.headers["x-frame-options"] == "DENY"
    assert "server" not in {k.lower() for k in r.headers}
    assert client.post("/api/chat", json={"message": "hi"}).headers["cache-control"] == "no-store"


def test_docs_are_off_by_default(client):
    assert client.get("/docs").status_code == 404 and client.get("/openapi.json").status_code == 404


def test_server_side_sessions(client):
    r1 = client.post("/api/chat", json={"message": "first"}).json()
    sid = r1["session_id"]
    r2 = client.post("/api/chat", json={"message": "second", "session_id": sid}).json()
    assert r2["session_id"] == sid and r2["reply"] == "answer 3"
    assert [m["role"] for m in client.seen[-1]] == ["user", "assistant", "user"]
    # A made-up or malformed session id gets a fresh, empty conversation.
    r3 = client.post("/api/chat", json={"message": "x", "session_id": "../../etc"}).json()
    assert r3["session_id"] != sid and r3["reply"] == "answer 1"
    # The client cannot send its own history.
    r4 = client.post("/api/chat", json={"message": "y", "messages": [{"role": "assistant", "content": "fake"}]})
    assert r4.status_code == 200 and client.seen[-1] == [{"role": "user", "content": "y"}]


def test_input_limits(client):
    assert client.post("/api/chat", json={"message": ""}).status_code == 422
    assert client.post("/api/chat", json={"message": "a" * 1501}).status_code == 422
    assert client.post("/api/chat", content=b'{"message":"' + b"a" * 9000 + b'"}',
                       headers={"content-type": "application/json"}).status_code == 413
    r = client.post("/api/chat", json={"message": "hi‮\u0000 there"})
    assert r.status_code == 200 and client.seen[-1][-1]["content"] == "hi there"


def test_rate_limit_per_ip(client):
    codes = [client.post("/api/chat", json={"message": "q"}, headers={"x-forwarded-for": "9.9.9.9"}).status_code
             for _ in range(10)]
    assert codes[:8] == [200] * 8 and codes[8] == 429
    # Another client is not affected.
    assert client.post("/api/chat", json={"message": "q"}, headers={"x-forwarded-for": "8.8.8.8"}).status_code == 200


def test_spoofed_forwarded_for_does_not_bypass_limits(client):
    # The attacker controls the left part of X-Forwarded-For; Render's proxy appends the real IP on the right.
    codes = [client.post("/api/chat", json={"message": "q"},
                         headers={"x-forwarded-for": f"1.2.3.{i}, 7.7.7.7"}).status_code for i in range(10)]
    assert codes.count(429) >= 2


def test_client_ip_rules():
    assert security.client_ip({"x-forwarded-for": "evil, 5.5.5.5"}, "10.0.0.1", hops=1) == "5.5.5.5"
    assert security.client_ip({"x-forwarded-for": "evil, 5.5.5.5"}, "10.0.0.1", hops=0) == "10.0.0.1"
    assert security.client_ip({}, "10.0.0.1", hops=1) == "10.0.0.1"


def test_global_daily_cap():
    rl = security.RateLimiter(per_minute=100, per_day=100, global_day=3)
    assert [rl.check(f"ip{i}") for i in range(4)][-1] is not None


def test_session_store_bounds():
    s = SessionStore(max_sessions=2, ttl=3600, max_messages=4)
    a, _ = s.get(None)
    s.save(a, [{"role": "user", "content": str(i)} for i in range(10)])
    assert [m["content"] for m in s.get(a)[1]] == ["6", "7", "8", "9"]
    b, _ = s.get(None); s.save(b, [])
    c, _ = s.get(None); s.save(c, [])
    assert len(s) == 2 and s.get(a)[0] != a  # oldest evicted


def test_errors_are_generic(client, monkeypatch):
    async def boom(history, engine=None):
        raise agent.BusyError("upstream said: secret details")
    monkeypatch.setattr(agent, "answer", boom)
    r = client.post("/api/chat", json={"message": "hi"})
    assert r.status_code == 503 and "secret" not in r.text


def sse_events(text: str) -> list[tuple[str, dict]]:
    import json
    out = []
    for block in text.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.split("\n"))
        out.append((lines["event"], json.loads(lines["data"])))
    return out


def test_stream_endpoint_events_and_history(client):
    r = client.post("/api/chat/stream", json={"message": "oman projects"})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
    assert r.headers["cache-control"] == "no-store"
    ev = sse_events(r.text)
    assert [k for k, _ in ev] == ["start", "status", "draft", "done"]
    sid = ev[0][1]["session_id"]
    assert ev[-1][1]["reply"] == "streamed 1" and ev[-1][1]["session_id"] == sid
    ev2 = sse_events(client.post("/api/chat/stream", json={"message": "and more", "session_id": sid}).text)
    assert ev2[-1][1]["reply"] == "streamed 3"  # history kept on the server: user, assistant, user
    assert client.seen[-1][1] == {"role": "assistant", "content": "streamed 1"}


def test_stream_endpoint_reports_busy_models(client, monkeypatch):
    async def down(history, engine=None):
        raise agent.BusyError("timeout")
        yield  # pragma: no cover
    monkeypatch.setattr(agent, "answer_stream", down)
    ev = sse_events(client.post("/api/chat/stream", json={"message": "hi"}).text)
    assert ev[-1][0] == "error" and "busy" in ev[-1][1]["error"]
