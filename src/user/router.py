from typing import Annotated

from fastapi import (
    APIRouter,
    Body,
    Depends,
    Query,
    Path,
    HTTPException,
    status,
)
from sqlalchemy.ext.asyncio import AsyncSession

from src.user.schemas import (
    DeleteUserRequest,
    GetUserResponse,
    GetUsersParams,
    UpdateUserRequest,
    UpdateUsersGroupRequest,
    GetUserDetailResponse,
)
from src.user.service import (
    get_users,
    delete_user,
    update_user,
    update_users_group,
    get_user_by_id,
    delete_user_by_id,
)
from src.database import get_db_session
from src.logger import logger
from src.schemas import DetailResponse, PaginatedDataResponse, DataResponse

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


@router.get("/users/{user_id}", response_model=DataResponse[GetUserDetailResponse])
async def _get_user_detail(
    user_id: Annotated[int, Path()],
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    try:
        return await get_user_by_id(
            user_id=user_id,
            session=session,
        )

    except HTTPException as exc:
        logger.exception(exc)
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    except Exception as exc:
        logger.exception(exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc


@router.put("/users/groups")
async def _update_users_groups(
    users_data: Annotated[UpdateUsersGroupRequest, Body()],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> DetailResponse:
    try:
        await update_users_group(session=session, users_data=users_data)

        return DetailResponse(detail="Updated successfully")

    except HTTPException as exc:
        logger.exception(exc)
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    except Exception as exc:
        logger.exception(exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc


@router.put("/users/{user_id}")
async def _update_users(
    user_id: Annotated[int, Path()],
    user_data: Annotated[UpdateUserRequest, Body()],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> DetailResponse:
    try:
        await update_user(session=session, user_id=user_id, user_data=user_data)

        return DetailResponse(detail="Updated successfully")

    except HTTPException as exc:
        logger.exception(exc)
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    except Exception as exc:
        logger.exception(exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc


@router.delete("/users/{user_id}")
async def _delete_user_by_id(
    user_id: Annotated[int, Path()],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> DetailResponse:
    try:
        await delete_user_by_id(session=session, user_id=user_id)

        return DetailResponse(detail="Deleted successfully")

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
        await delete_user(session=session, user_ids=user_ids.user_ids)

        return DetailResponse(detail="Deleted successfully")

    except HTTPException as exc:
        logger.exception(exc)
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    except Exception as exc:
        logger.exception(exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
