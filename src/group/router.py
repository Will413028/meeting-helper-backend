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
from src.database import get_db_session
from src.logger import logger
from src.schemas import (
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
async def _get_groups(
    query_params: Annotated[GetGroupsParams, Query()],
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    try:
        return await get_groups(
            session=session,
            name=query_params.name,
            page=query_params.page,
            page_size=query_params.page_size,
        )

    except HTTPException as exc:
        logger.error("get_groups error")
        logger.exception(exc)
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    except Exception as exc:
        logger.error("get_groups error")
        logger.exception(exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc


@router.get(
    "/v1/groups/simple",
    response_model=ListDataResponse[GetSimpleGroupResponse],
)
async def _get_simple_groups(
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    try:
        return await get_simple_groups(
            session=session,
        )

    except HTTPException as exc:
        logger.error("get_groups error")
        logger.exception(exc)
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    except Exception as exc:
        logger.error("get_groups error")
        logger.exception(exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc


@router.post(
    "/v1/groups/admin",
    response_model=DetailResponse,
)
async def _create_admin_group(
    group_data: Annotated[CreateGroupRequest, Body()],
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    try:
        await create_admin_group(session=session, group_data=group_data)

        return DetailResponse(detail="Create group successfully")

    except HTTPException as exc:
        logger.exception(exc)
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    except Exception as exc:
        logger.exception(exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc


@router.post(
    "/v1/groups",
    response_model=DetailResponse,
)
async def _create_group(
    group_data: Annotated[CreateGroupRequest, Body()],
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    try:
        db_group = await get_group_by_name(session=session, name=group_data.name)

        if db_group:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Group already exists"
            )

        await create_group(session=session, group_data=group_data)

        return DetailResponse(detail="Create group successfully")

    except HTTPException as exc:
        logger.exception(exc)
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    except Exception as exc:
        logger.exception(exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc


@router.put(
    "/v1/groups",
    response_model=DetailResponse,
)
async def _update_groups(
    groups_data: Annotated[UpdateGroupsRequest, Body()],
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    try:
        await update_groups(groups_data=groups_data, session=session)

        return DetailResponse(detail="User password reset successfully")

    except HTTPException as exc:
        logger.error("Update group error")
        logger.exception(exc)
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    except Exception as exc:
        logger.error("Update group error")
        logger.exception(exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc


@router.delete(
    "/v1/groups",
    response_model=DetailResponse,
)
async def _delete_groups(
    group_ids: Annotated[list[str], Body()],
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    try:
        await delete_groups(session=session, group_ids=group_ids)

        return DetailResponse(detail="Groups moved to 未分類 successfully")

    except HTTPException as exc:
        logger.exception(exc)
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    except Exception as exc:
        logger.exception(exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc


@router.post(
    "/v1/groups/uncategorized",
    response_model=DetailResponse,
)
async def _create_uncategorized_group(
    group_data: Annotated[CreateGroupRequest, Body()],
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    try:
        await create_uncategorized_group(session=session, group_data=group_data)

        return DetailResponse(detail="Create group successfully")

    except HTTPException as exc:
        logger.exception(exc)
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    except Exception as exc:
        logger.exception(exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
