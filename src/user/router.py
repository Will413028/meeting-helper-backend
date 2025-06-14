from typing import Annotated

from fastapi import (
    APIRouter,
    Body,
    Depends,
    Query,
    HTTPException,
    status,
)
from sqlalchemy.ext.asyncio import AsyncSession

from src.user.schemas import (
    DeleteUserRequest,
    GetUserResponse,
    GetUsersParams,
)
from src.user.service import (
    get_users,
    delete_user,
)
from src.database import get_db_session
from src.logger import logger
from src.schemas import DetailResponse, PaginatedDataResponse

router = APIRouter(
    tags=["users"],
)


@router.get("/users", response_model=PaginatedDataResponse[GetUserResponse])
async def _get_users(
    query_params: Annotated[GetUsersParams, Query()],
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    try:
        return await get_users(
            session=session,
            name=query_params.name,
            page=query_params.page,
            page_size=query_params.page_size,
        )

    except HTTPException as exc:
        logger.exception(exc)
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    except Exception as exc:
        logger.exception(exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc


@router.delete("/users")
async def _delete_users(
    user_ids: Annotated[DeleteUserRequest, Body()],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> DetailResponse:
    try:
        await delete_user(session=session, user_ids=user_ids)

        return DetailResponse(detail="Deleted successfully")

    except HTTPException as exc:
        logger.exception(exc)
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    except Exception as exc:
        logger.exception(exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
