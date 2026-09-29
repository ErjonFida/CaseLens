import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from config import settings
from database import async_engine
from legal_api.api import drop_queued_uploads, router, RateLimitExceeded

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("main_server")


@asynccontextmanager
async def lifespan(app: FastAPI):

    logger.info("CaseLens API starting up...")
    yield
    drop_queued_uploads()
    await async_engine.dispose()
    logger.info("CaseLens API shut down.")


app = FastAPI(
    title="CaseLens API",
    lifespan=lifespan,
)


class BodySizeLimit:
    """Refuse a request body over the upload cap while it arrives.

    Starlette parses a multipart upload, spooling it to disk, before the
    endpoint runs - and before the sign-in check it depends on - so the size
    check in the upload endpoint only fires once the whole body is on disk.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        limit = settings.MAX_FILE_SIZE_BYTES + 1024 * 1024  # room for the multipart framing
        detail = f"Request too large. Maximum: {settings.MAX_FILE_SIZE_BYTES // (1024 * 1024)}MB"

        declared = dict(scope["headers"]).get(b"content-length")
        if declared and int(declared) > limit:
            return await JSONResponse({"detail": detail}, status_code=413)(scope, receive, send)

        received = 0

        async def counted():  # a chunked body declares no length
            nonlocal received
            message = await receive()
            received += len(message.get("body", b""))
            if received > limit:
                raise StarletteHTTPException(status_code=413, detail=detail)
            return message

        await self.app(scope, counted, send)


app.add_middleware(BodySizeLimit)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(RateLimitExceeded)
async def on_rate_limit(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={"detail": "Too many requests. Please try again later."},
    )


app.include_router(router)


class SinglePageApp(StaticFiles):
    """The built frontend. A path that is no file is a client-side route, so it
    gets index.html - except under /api/, where a miss must stay a 404, and for
    a name with an extension, which asked for a file that is not there."""

    async def get_response(self, path: str, scope):
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            # The request path, not `path`: StaticFiles normalises that with the
            # OS separator, so on Windows it reads api\... and never matches.
            request_path = scope["path"]
            if exc.status_code != 404 or request_path.startswith("/api/") or "." in request_path.rsplit("/", 1)[-1]:
                raise
            return await super().get_response("index.html", scope)


if settings.STATIC_DIR and Path(settings.STATIC_DIR).is_dir():
    app.mount("/", SinglePageApp(directory=settings.STATIC_DIR, html=True), name="frontend")
