"""FastAPI app: chat page, /api/chat, /api/health."""
from __future__ import annotations

import json
import logging
import re
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import agent, retrieval, tools, websearch
from .config import openrouter_key, settings
from .security import ConcurrencyGate, RateLimiter, SecurityMiddleware, client_ip, ip_tag
from .sessions import SessionStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("app")
STATIC = Path(__file__).resolve().parent / "static"
CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f​-‏‪-‮⁦-⁩]")


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=settings.max_message_chars)
    session_id: str | None = Field(None, max_length=64)


class ResetIn(BaseModel):
    session_id: str | None = Field(None, max_length=64)


def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        retrieval.get_retriever()  # load the vector index and the embedding model before the first request
        log.info("ready: %s; web search: %s; models: %s", retrieval.index_info(), websearch.provider() or "off",
                 ",".join(settings.models))
        yield

    docs = "/docs" if settings.enable_docs else None
    app = FastAPI(title="DarGlobal Property Assistant", docs_url=docs, redoc_url=None,
                  openapi_url="/openapi.json" if settings.enable_docs else None, lifespan=lifespan)
    app.add_middleware(SecurityMiddleware)
    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    app.state.sessions = SessionStore()
    app.state.limiter = RateLimiter()
    app.state.gate = ConcurrencyGate()

    @app.exception_handler(RequestValidationError)
    async def bad_request(request: Request, exc: RequestValidationError):
        return JSONResponse({"error": "Invalid request. Messages must be 1-%d characters." % settings.max_message_chars},
                            status_code=422)

    @app.exception_handler(Exception)
    async def crashed(request: Request, exc: Exception):
        log.exception("unhandled error on %s", request.url.path)
        return JSONResponse({"error": "Something went wrong. Please try again."}, status_code=500)

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(STATIC / "index.html")

    @app.get("/api/health")
    def health():
        return {"ok": True, "projects": len(tools.load("darglobal_projects")), "villas": len(tools.load("wasalt_villas")),
                "index": retrieval.index_info(), "models": list(settings.models), "key_set": bool(openrouter_key()),
                "web_search": websearch.provider() or "off"}

    @app.post("/api/reset")
    def reset(body: ResetIn):
        app.state.sessions.reset(body.session_id)
        return {"ok": True}

    def prepare(body: ChatIn, request: Request):
        """Shared checks for both chat endpoints: rate limit, clean text, load the session."""
        ip = client_ip({k.lower(): v for k, v in request.headers.items()}, request.client.host if request.client else None)
        refused = app.state.limiter.check(ip)
        if refused:
            return JSONResponse({"error": refused}, status_code=429)
        text = CONTROL.sub("", body.message).strip()
        if not text:
            return JSONResponse({"error": "Please type a question."}, status_code=422)
        sid, history = app.state.sessions.get(body.session_id)
        history.append({"role": "user", "content": text})
        return ip, sid, history

    def finish(ip: str, sid: str, history: list[dict], res: agent.Result, t0: float) -> dict:
        history.append({"role": "assistant", "content": res.reply})
        app.state.sessions.save(sid, history)
        log.info("chat ip=%s mode=%s model=%s tools=%d checks=%s %.1fs", ip_tag(ip), res.mode, res.model,
                 len(res.tools_used), res.checks, time.time() - t0)
        return {"session_id": sid, "reply": res.reply, "sources": res.sources, "mode": res.mode, "model": res.model,
                "tools_used": [t["tool"] for t in res.tools_used], "checks": res.checks}

    BUSY = "The assistant is busy. Please try again shortly."
    NOT_CONFIGURED = "The AI model is not configured on this server."
    MODELS_BUSY = "The free AI models are busy or rate-limited right now. Please try again in a minute."

    @app.post("/api/chat")
    async def chat(body: ChatIn, request: Request):
        ready = prepare(body, request)
        if isinstance(ready, JSONResponse):
            return ready
        ip, sid, history = ready
        if not await app.state.gate.acquire():
            return JSONResponse({"error": BUSY, "session_id": sid}, status_code=503)
        t0 = time.time()
        try:
            res = await agent.answer(history)
        except agent.ConfigError:
            log.error("chat: model not configured or key rejected")
            return JSONResponse({"error": NOT_CONFIGURED, "session_id": sid}, status_code=503)
        except agent.BusyError as e:
            log.warning("chat: all models failed (%s) ip=%s", e, ip_tag(ip))
            return JSONResponse({"error": MODELS_BUSY, "session_id": sid}, status_code=503)
        finally:
            app.state.gate.release()
        return finish(ip, sid, history, res, t0)

    @app.post("/api/chat/stream")
    async def chat_stream(body: ChatIn, request: Request):
        """Server-Sent Events: start, status*, draft*, then done (the checked reply) or error."""
        ready = prepare(body, request)
        if isinstance(ready, JSONResponse):
            return ready
        ip, sid, history = ready

        def sse(event: str, data: dict) -> str:
            return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

        async def events():
            yield sse("start", {"session_id": sid})
            if not await app.state.gate.acquire():
                yield sse("error", {"error": BUSY})
                return
            t0 = time.time()
            try:
                async for kind, data in agent.answer_stream(history):
                    if kind == "done":
                        yield sse("done", finish(ip, sid, history, data, t0))
                    else:
                        yield sse(kind, {"text": data})
            except agent.ConfigError:
                log.error("chat: model not configured or key rejected")
                yield sse("error", {"error": NOT_CONFIGURED})
            except agent.BusyError as e:
                log.warning("chat: all models failed (%s) ip=%s", e, ip_tag(ip))
                yield sse("error", {"error": MODELS_BUSY})
            except Exception:
                log.exception("chat stream failed")
                yield sse("error", {"error": "Something went wrong. Please try again."})
            finally:
                app.state.gate.release()

        return StreamingResponse(events(), media_type="text/event-stream",
                                 headers={"X-Accel-Buffering": "no"})

    return app


app = create_app()
