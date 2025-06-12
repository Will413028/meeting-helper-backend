from typing import Annotated

from fastapi import (
    APIRouter,
    Body,
    Depends,
    HTTPException,
    status,
)
from sqlalchemy.ext.asyncio import AsyncSession

from src.group.schemas import CreateGroupRequest, GetGroupResponse, UpdateGroupsRequest
from src.group.service import (
    create_group,
    get_group_by_name,
    get_groups,
    update_groups,
    delete_groups,
)
from src.database import get_db_session
from src.logger import logger
from src.schemas import DetailResponse, PaginatedDataResponse

router = APIRouter(
    tags=["group"],
)


@router.get(
    "/v1/groups",
    response_model=PaginatedDataResponse[GetGroupResponse],
)
async def _get_groups(
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    try:
        groups = await get_groups(session=session)

        # Convert to response format
        groups_data = [
            GetGroupResponse(group_id=group.group_id, name=group.name, role=group.role)
            for group in groups
        ]

        return PaginatedDataResponse(
            data=groups_data, total=len(groups_data), page=1, per_page=len(groups_data)
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
