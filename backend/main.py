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
from legal_api.api import router, RateLimitExceeded

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
    await async_engine.dispose()
    logger.info("CaseLens API shut down.")


app = FastAPI(
    title="CaseLens API",
    lifespan=lifespan,
)

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
    gets index.html - except under /api/, where a miss must stay a 404."""

    async def get_response(self, path: str, scope):
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            # The request path, not `path`: StaticFiles normalises that with the
            # OS separator, so on Windows it reads api\... and never matches.
            if exc.status_code != 404 or scope["path"].startswith("/api/"):
                raise
            return await super().get_response("index.html", scope)


if settings.STATIC_DIR and Path(settings.STATIC_DIR).is_dir():
    app.mount("/", SinglePageApp(directory=settings.STATIC_DIR, html=True), name="frontend")
