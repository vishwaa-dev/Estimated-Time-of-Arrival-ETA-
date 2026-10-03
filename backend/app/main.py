"""RailCast AI — FastAPI application entrypoint."""
import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import router
from app.config import settings
from app.database import SessionLocal, init_db
from app.services.railradar_service import ExternalAPIError
from app.services.refresh_service import background_loop
from app.services.seed_service import seed_all

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger("railcast")

_scheduler_task: asyncio.Task | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _scheduler_task

    # --- Phase: DB + seed -------------------------------------------------
    init_db()
    db = SessionLocal()
    try:
        seeded = seed_all(db)
        if seeded:
            logger.info("Seeded trains: %s", ", ".join(seeded))
        # First refresh for every train so the dashboard is populated
        # immediately (demo trains: instant; live trains: one API call).
        from app.models import Train
        from app.services.refresh_service import refresh_train

        for train in db.query(Train).all():
            try:
                refresh_train(db, train.train_number)
            except Exception:
                logger.exception("Initial refresh failed for %s", train.train_number)
    finally:
        db.close()

    # --- Phase: continuous re-forecast scheduler ---------------------------
    _scheduler_task = asyncio.create_task(background_loop(app))
    logger.info("RailCast AI backend ready (mode=%s)", settings.data_mode)
    yield
    if _scheduler_task:
        _scheduler_task.cancel()
        try:
            await _scheduler_task
        except asyncio.CancelledError:
            pass
    logger.info("RailCast AI backend stopped")


app = FastAPI(
    title="RailCast AI",
    description="Dynamic Delay Trajectory & ETA Intelligence for Coaching Trains "
                "(SIH26028 prototype). Multi-factor continuous ETA prediction with "
                "recovery estimation and explainable output.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(ExternalAPIError)
async def external_api_error_handler(request: Request, exc: ExternalAPIError):
    return JSONResponse(status_code=503, content={"detail": str(exc)})


@app.exception_handler(HTTPException)
async def http_error_handler(request: Request, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.exception_handler(Exception)
async def unexpected_error_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    # Never leak internals/keys to the client.
    return JSONResponse(status_code=500, content={"detail": "Internal server error — the dashboard retains the last valid prediction."})


app.include_router(router)


@app.get("/")
def root():
    return {"service": "RailCast AI", "docs": "/docs", "api": "/api"}
