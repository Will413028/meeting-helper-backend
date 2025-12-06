import time

from fastapi import HTTPException, Request, status
from fastapi.responses import ORJSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from src.core.logger import logger


class ProcessTimeMiddleware(BaseHTTPMiddleware):
    """Middleware to measure and log request processing time."""

    async def dispatch(self, request: Request, call_next):
        start_time = time.time()
        response = await call_next(request)
        process_time = time.time() - start_time
        response.headers["X-Process-Time"] = str(process_time)
        return response


class CatchExceptionMiddleware(BaseHTTPMiddleware):
    """Middleware to catch and handle all unhandled exceptions."""

    async def dispatch(self, request: Request, call_next):
        try:
            response = await call_next(request)
        except HTTPException as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
        except Exception as exc:
            logger.exception(exc, exc_info=True)
            return ORJSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={"detail": str(exc)},
            )
        return response
