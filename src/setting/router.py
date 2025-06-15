from typing import Annotated

import shutil
from fastapi import (
    APIRouter,
    Depends,
    Body,
    HTTPException,
    status,
)
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import get_current_user
from src.database import get_db_session
from src.logger import logger
from src.models import User
from src.setting.service import get_settings, update_settings
from src.setting.schemas import GetSettingResponse, UpdateSettingParam
from src.schemas import DataResponse, DetailResponse

router = APIRouter(
    tags=["settings"],
)


@router.get(
    "/v1/settings",
    response_model=DataResponse[GetSettingResponse],
)
async def _get_settings(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    try:
        return await get_settings(session=session)

    except HTTPException as exc:
        logger.exception(exc)
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    except Exception as exc:
        logger.exception(exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"get settings error: {str(exc)}",
        ) from exc


@router.put(
    "/v1/settings",
    response_model=DetailResponse,
)
async def _update_settings(
    current_user: Annotated[User, Depends(get_current_user)],
    setting_data: Annotated[UpdateSettingParam, Body()],
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    try:
        await update_settings(session=session, setting_data=setting_data)

        return DetailResponse(detail="Update settings successfully")

    except HTTPException as exc:
        logger.exception(exc)
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    except Exception as exc:
        logger.exception(exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"update settings error: {str(exc)}",
        ) from exc


@router.get("/v1/disk-space")
async def get_disk_space():
    """Get remaining disk space in GB"""
    try:
        # Get disk usage statistics for the root filesystem
        disk_usage = shutil.disk_usage("/")

        # Convert bytes to GB (1 GB = 1024^3 bytes)
        total_gb = disk_usage.total / (1024**3)
        used_gb = disk_usage.used / (1024**3)
        free_gb = disk_usage.free / (1024**3)

        # Calculate percentage used
        percent_used = (disk_usage.used / disk_usage.total) * 100

        return {
            "total_gb": round(total_gb, 2),
            "used_gb": round(used_gb, 2),
            "free_gb": round(free_gb, 2),
            "percent_used": round(percent_used, 2),
        }
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error getting disk space: {str(e)}"
        )
