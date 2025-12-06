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

from src.group.schemas import (
    CreateGroupRequest,
    GetGroupResponse,
    UpdateGroupsRequest,
    GetSimpleGroupResponse,
    GetGroupsParams,
)
from src.group.service import (
    create_group,
    create_admin_group,
    get_group_by_name,
    get_groups,
    update_groups,
    delete_groups,
    create_uncategorized_group,
    get_simple_groups,
)
from src.core.database import get_db_session
from src.core.schemas import (
    DetailResponse,
    PaginatedDataResponse,
    ListDataResponse,
)

router = APIRouter(
    tags=["group"],
)


@router.get(
    "/v1/groups/detail",
    response_model=PaginatedDataResponse[GetGroupResponse],
)
async def get_groups_handler(
    query_params: Annotated[GetGroupsParams, Query()],
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    return await get_groups(
        session=session,
        name=query_params.name,
        page=query_params.page,
        page_size=query_params.page_size,
    )


@router.get(
    "/v1/groups/simple",
    response_model=ListDataResponse[GetSimpleGroupResponse],
)
async def get_simple_groups_handler(
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    return await get_simple_groups(
        session=session,
    )


@router.post(
    "/v1/groups/admin",
    response_model=DetailResponse,
)
async def create_admin_group_handler(
    group_data: Annotated[CreateGroupRequest, Body()],
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    await create_admin_group(session=session, group_data=group_data)
    return DetailResponse(detail="Create group successfully")


@router.post(
    "/v1/groups",
    response_model=DetailResponse,
)
async def create_group_handler(
    group_data: Annotated[CreateGroupRequest, Body()],
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    db_group = await get_group_by_name(session=session, name=group_data.name)

    if db_group:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Group already exists"
        )

    await create_group(session=session, group_data=group_data)
    return DetailResponse(detail="Create group successfully")


@router.put(
    "/v1/groups",
    response_model=DetailResponse,
)
async def update_groups_handler(
    groups_data: Annotated[UpdateGroupsRequest, Body()],
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    await update_groups(groups_data=groups_data, session=session)
    return DetailResponse(detail="User password reset successfully")


@router.delete(
    "/v1/groups",
    response_model=DetailResponse,
)
async def delete_groups_handler(
    group_ids: Annotated[list[int], Body()],
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    await delete_groups(session=session, group_ids=group_ids)
    return DetailResponse(detail="Groups moved to 未分類 successfully")


@router.post(
    "/v1/groups/uncategorized",
    response_model=DetailResponse,
)
async def create_uncategorized_group_handler(
    group_data: Annotated[CreateGroupRequest, Body()],
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    await create_uncategorized_group(session=session, group_data=group_data)
    return DetailResponse(detail="Create group successfully")
