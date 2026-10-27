"""React SPA static file mount + history-mode fallback for FastAPI.

Split out of ``src/geo_api.py`` so the FastAPI app factory stays free of static-
file concerns (``frontend_react/build`` may not exist in dev or CI). ``start_api``
calls :func:`mount_spa` only when the build directory is present; in dev the
Vite preview server (``npm run dev``) serves the SPA and proxies API calls.

Routing strategy (matches nginx/conf.d/firecast.conf):

    /                  -> index.html   (SPA shell, never cached)
    /assets/*          -> StaticFiles   (immutable, long max-age)
    /predict, /api/*, /geo/*, /analytics/*, /health,
    /docs, /openapi.json, /admin/*
                       -> FastAPI routes (declared BEFORE this mount)

Caveat: FastAPI route order matters. :func:`mount_spa` MUST be invoked **after**
every ``@app.get/post`` declaration in ``src/geo_api.py``. Mounts registered
later in the route table are checked last, so API routes win.

The SPA fallback catches everything that does not resolve to a static asset
and returns ``index.html``. This preserves React Router history-mode deep links
(e.g. ``/analysis``) on hard refresh.
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

logger = logging.getLogger(__name__)

# Path prefixes owned by the FastAPI backend. The SPA fallback handler must NOT
# swallow these — they are reserved for the API surface. Listing them here is
# defensive documentation; the real defence is route registration order (API
# routes are declared first, so FastAPI matches them before the mount).
API_PREFIXES: tuple[str, ...] = (
    "/predict",
    "/api",
    "/geo",
    "/analytics",
    "/admin",
    "/health",
    "/docs",
    "/openapi.json",
    "/redoc",
)

_INDEX_FILE = "index.html"
_ASSETS_DIR = "assets"


def mount_spa(app: FastAPI, static_dir: Path) -> bool:
    """Mount the compiled React SPA at ``/`` if ``static_dir`` exists.

    Returns ``True`` when the SPA was mounted, ``False`` when ``static_dir``
    is missing (dev mode — Vite serves the SPA itself). Never raises so a
    fresh checkout / CI run without a ``frontend_react/build`` directory can
    still boot the backend.

    Adds:

    - ``StaticFiles`` mount at ``/assets`` (immutable, long-lived cache)
    - ``GET /{path:path}`` catch-all that returns ``index.html`` for any
      non-asset GET (history-mode SPA fallback)
    """
    if not static_dir.exists() or not (static_dir / _INDEX_FILE).exists():
        logger.info("SPA mount skipped — %s/index.html not found (dev mode)", static_dir)
        return False

    assets_dir = static_dir / _ASSETS_DIR
    if assets_dir.exists():
        app.mount(
            "/assets",
            StaticFiles(directory=assets_dir),
            name="spa-assets",
        )

    index_path = static_dir / _INDEX_FILE

    # Catch-all SPA fallback. Declared LAST so all API routes above take
    # precedence. ``path`` matches any non-empty URI segment; the empty-root
    # case is handled by the explicit ``GET /`` handler below.
    @app.get("/", include_in_schema=False)
    async def _spa_root() -> FileResponse:
        return FileResponse(index_path, media_type="text/html")

    @app.get("/{path:path}", include_in_schema=False)
    async def _spa_fallback(path: str) -> FileResponse:
        # If the request maps to an actual static file (favicon.ico, robots.txt,
        # vite.svg, etc. in the build root), serve it directly. Otherwise fall
        # back to index.html so React Router can resolve the route client-side.
        #
        # Security (audit 2026-08-23, bug #14): the raw ``static_dir / path``
        # join followed no containment check, so ``GET /%2e%2e/%2e%2e/...``
        # escaped the build dir and served ANY file on disk (verified: .env,
        # secrets/*.json, the SQLite db) without auth. Resolve + is_relative_to
        # confines serving to files inside static_dir; anything else falls back
        # to index.html like any other unknown SPA route.
        resolved_root = static_dir.resolve()
        candidate = (static_dir / path).resolve()
        if candidate.is_file() and candidate.is_relative_to(resolved_root):
            media = _guess_media(path)
            return FileResponse(candidate, media_type=media)
        return FileResponse(index_path, media_type="text/html")

    # Cache-Control: index.html must never be cached (the asset references it
    # contains are content-hashed and live under /assets/). The hashed assets
    # themselves can be cached indefinitely. We attach headers via middleware so
    # the rule applies uniformly to both the root and fall-back handlers.
    @app.middleware("http")
    async def _spa_cache_headers(request, call_next):
        response = await call_next(request)
        url = request.url.path
        if url.startswith("/assets/"):
            response.headers.setdefault("Cache-Control", "public, max-age=31536000, immutable")
        elif url == "/" or (not url.startswith(API_PREFIXES) and url.startswith("/")):
            # index.html: revalidate always so a new deploy swaps the asset
            # hashed references promptly.
            response.headers.setdefault("Cache-Control", "no-cache, must-revalidate")
        return response

    logger.info("SPA mounted at / from %s", static_dir)
    return True


# Minimal MIME guesser to avoid pulling in ``mimetypes`` for the small set of
# files Vite emits at the build root (favicon, manifest, svg decorations).
_MEDIA_BY_EXT: dict[str, str] = {
    ".html": "text/html",
    ".js": "application/javascript",
    ".mjs": "application/javascript",
    ".css": "text/css",
    ".json": "application/json",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".ico": "image/x-icon",
    ".webp": "image/webp",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
    ".ttf": "font/ttf",
    ".eot": "application/vnd.ms-fontobject",
    ".txt": "text/plain",
    ".webmanifest": "application/manifest+json",
    ".map": "application/json",
}


def _guess_media(path: str) -> str:
    ext = Path(path).suffix.lower()
    return _MEDIA_BY_EXT.get(ext, "application/octet-stream")
