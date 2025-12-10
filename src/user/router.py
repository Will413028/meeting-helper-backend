from typing import Annotated

from fastapi import (
    APIRouter,
    Body,
    Depends,
    Query,
    Path,
)
from sqlalchemy.ext.asyncio import AsyncSession

from src.user.schemas import (
    DeleteUserRequest,
    GetUserResponse,
    GetUsersParams,
    UpdateUserRequest,
    UpdateUsersGroupRequest,
    GetUserDetailResponse,
    GetListUserResponse,
)
from src.user.service import (
    get_users,
    delete_user,
    update_user,
    update_users_group,
    get_user_by_id,
    delete_user_by_id,
    get_list_users,
)
from src.core.database import get_db_session
from src.core.schemas import (
    DetailResponse,
    ListDataResponse,
    PaginatedDataResponse,
    DataResponse,
)

router = APIRouter(
    tags=["users"],
)


@router.get("/users/list", response_model=ListDataResponse[GetListUserResponse])
async def get_list_users_handler(
    group_id: Annotated[int, Query()],
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    return await get_list_users(
        session=session,
        group_id=group_id,
    )


@router.get("/users", response_model=PaginatedDataResponse[GetUserResponse])
async def get_users_handler(
    query_params: Annotated[GetUsersParams, Query()],
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    return await get_users(
        session=session,
        name=query_params.name,
        page=query_params.page,
        page_size=query_params.page_size,
    )


@router.get("/users/{user_id}", response_model=DataResponse[GetUserDetailResponse])
async def get_user_detail_handler(
    user_id: Annotated[int, Path()],
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    return await get_user_by_id(
        user_id=user_id,
        session=session,
    )


@router.put("/users/groups")
async def update_users_groups_handler(
    users_data: Annotated[UpdateUsersGroupRequest, Body()],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> DetailResponse:
    await update_users_group(session=session, users_data=users_data)
    return DetailResponse(detail="Updated successfully")


@router.put("/users/{user_id}")
async def update_users_handler(
    user_id: Annotated[int, Path()],
    user_data: Annotated[UpdateUserRequest, Body()],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> DetailResponse:
    await update_user(session=session, user_id=user_id, user_data=user_data)
    return DetailResponse(detail="Updated successfully")


@router.delete("/users/{user_id}")
async def delete_user_by_id_handler(
    user_id: Annotated[int, Path()],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> DetailResponse:
    await delete_user_by_id(session=session, user_id=user_id)
    return DetailResponse(detail="Deleted successfully")


@router.delete("/users")
async def delete_users_handler(
    user_ids: Annotated[DeleteUserRequest, Body()],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> DetailResponse:
    await delete_user(session=session, user_ids=user_ids.user_ids)
    return DetailResponse(detail="Deleted successfully")
