import time
import os
from contextlib import asynccontextmanager
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse
from fastapi import FastAPI, Request, status

from src.auth.router import router as auth_router
from src.transcription.router import router as transcription_router
from src.group.router import router as group_router
from src.user.router import router as user_router
from src.setting.router import router as setting_router
from src.config import settings
from src.constants import DEFAULT_ERROR_RESPONSE
from src.logger import logger
from src.database import engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        logger.info("Starting application")
        os.makedirs(settings.OUTPUT_DIR, exist_ok=True)
    except Exception as e:
        logger.exception(f"Application startup failed, error: {e}")
    yield
    # Cleanup on shutdown
    logger.info("Shutting down application")
    await engine.dispose()


app = FastAPI(
    root_path="/api",
    lifespan=lifespan,
    responses=DEFAULT_ERROR_RESPONSE,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    response.headers["X-Process-Time"] = str(process_time)
    return response


@app.exception_handler(Exception)
async def exception_handler(request: Request, exc: Exception):
    return ORJSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": str(exc)},
    )


@app.get("/")
def read_root():
    return {"Hello": "World"}


app.include_router(auth_router)
app.include_router(group_router)
app.include_router(transcription_router)
app.include_router(user_router)
app.include_router(setting_router)
