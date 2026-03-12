"""Code Conductor — FastAPI entry point."""

import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import structlog
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from conductor.api import chat_router, memory_router, sessions_router, threads_router, ws_router
from conductor.core.config import init_conductor_home

# --- Structlog setup ---

structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(0),
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
    cache_logger_on_first_use=True,
)

log = structlog.get_logger()


# --- Lifespan ---


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    home = init_conductor_home()
    log.info("code_conductor_started", home=str(home))

    # Mount static files if the build directory exists
    static_dir = Path(__file__).parent / "web" / "static"
    if static_dir.is_dir():
        app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")
        log.info("static_files_mounted", path=str(static_dir))

    yield


# --- App ---

app = FastAPI(title="Code Conductor", version="0.1.0", lifespan=lifespan)

# CORS — allow all origins for local dev.
# SECURITY(A04): In production, replace ["*"] with explicit allowed origins
# e.g. allow_origins=["https://your-domain.com"]
# allow_credentials=True with allow_origins=["*"] is technically rejected by browsers,
# but an explicit origin list is still recommended for defense in depth.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Regex matching static assets with content hash in filename (e.g. main.a1b2c3d4.js)
_HASHED_ASSET_RE = re.compile(r"\.[0-9a-f]{8,}\.(js|css|woff2?|ttf|eot|svg|png|jpg|gif|ico|webp)$", re.IGNORECASE)


@app.middleware("http")
async def cache_control_middleware(request: Request, call_next):
    """Set Cache-Control headers based on resource type.

    Strategy:
    - HTML files: no-cache (always revalidate to pick up new JS/CSS references)
    - Hashed static assets (*.abc123.js): long-term immutable cache
    - API responses (/api/): no-cache (dynamic data)
    - Everything else: no explicit header (use defaults)
    """
    response: Response = await call_next(request)
    path = request.url.path
    content_type = response.headers.get("content-type", "")

    if "text/html" in content_type:
        # HTML must always be fresh — references hashed asset URLs
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    elif _HASHED_ASSET_RE.search(path):
        # Content-hashed assets are immutable — cache forever
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    elif path.startswith("/api/"):
        # API responses should not be cached by browsers/proxies
        response.headers["Cache-Control"] = "no-cache"

    return response


# --- Routes ---

app.include_router(sessions_router)
app.include_router(chat_router)
app.include_router(threads_router)
app.include_router(memory_router)
app.include_router(ws_router)


@app.get("/api/health")
async def health():
    return {"status": "ok", "version": app.version}


if __name__ == "__main__":
    import uvicorn

    from conductor.core.config import load_config

    cfg = load_config()
    uvicorn.run("server:app", host="0.0.0.0", port=cfg.server_port, reload=True)
