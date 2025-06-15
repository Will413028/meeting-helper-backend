from typing import Annotated

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
