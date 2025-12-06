from sqlalchemy import select, delete, func, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.schemas import PaginatedDataResponse, DataResponse, ListDataResponse
from src.user.schemas import (
    GetUserResponse,
    UpdateUserRequest,
    UpdateUsersGroupRequest,
    GetUserDetailResponse,
    GetListUserResponse,
)
from src.models import User, Group
from src.auth.utils import get_password_hash


async def get_users(
    session: AsyncSession,
    name: str | None,
    page: int = 1,
    page_size: int = 10,
) -> PaginatedDataResponse[GetUserResponse]:
    query = select(
        User.user_id,
        User.name,
        User.account,
        Group.name.label("group_name"),
        Group.description,
    ).join(Group, User.group_id == Group.group_id)

    if name:
        query = query.filter(User.name.like(f"%{name}%"))

    total_count = (
        await session.execute(select(func.count()).select_from(query.subquery()))
    ).scalar()

    total_pages = (total_count + page_size - 1) // page_size

    offset = (page - 1) * page_size

    results = (
        (await session.execute(query.offset(offset).limit(page_size))).mappings().all()
    )

    return PaginatedDataResponse[GetUserResponse](
        total_count=total_count,
        total_pages=total_pages,
        current_page=page,
        data=results,
    )


async def get_list_users(
    session: AsyncSession,
    group_id: int,
) -> ListDataResponse[GetListUserResponse]:
    query = select(
        User.user_id,
        User.name,
        User.account,
    ).where(User.group_id == group_id)

    results = (await session.execute(query)).mappings().all()

    return ListDataResponse[GetListUserResponse](
        data=results,
    )


async def get_user_by_id(
    session: AsyncSession, user_id: int
) -> DataResponse[GetUserDetailResponse]:
    query = (
        select(
            User.user_id,
            User.name,
            User.account,
            User.password,
            Group.name.label("group_name"),
            Group.description,
        )
        .join(Group, User.group_id == Group.group_id)
        .where(User.user_id == user_id)
    )

    result = (await session.execute(query)).mappings().one()

    return DataResponse[GetUserDetailResponse](data=result)


async def delete_user_by_id(session: AsyncSession, user_id: int):
    try:
        delete_query = delete(User).where(User.user_id == user_id)
        await session.execute(delete_query)
        await session.commit()

    except Exception as e:
        await session.rollback()
        raise e


async def delete_user(session: AsyncSession, user_ids: list[int]):
    try:
        delete_query = delete(User).where(User.user_id.in_(user_ids))
        await session.execute(delete_query)
        await session.commit()

    except Exception as e:
        await session.rollback()
        raise e


async def update_user(
    session: AsyncSession, user_id: int, user_data: UpdateUserRequest
):
    try:
        user_data.password = await get_password_hash(password=user_data.password)

        update_query = (
            update(User)
            .where(User.user_id == user_id)
            .values(
                {
                    "name": user_data.name,
                    "account": user_data.account,
                    "password": user_data.password,
                    "group_id": user_data.group_id,
                }
            )
        )
        await session.execute(update_query)
        await session.commit()

    except Exception as e:
        await session.rollback()
        raise e


async def update_users_group(
    session: AsyncSession, users_data: UpdateUsersGroupRequest
):
    try:
        for user_data in users_data.users_data:
            update_query = (
                update(User)
                .where(User.user_id == user_data.user_id)
                .values(
                    {
                        "group_id": user_data.group_id,
                    }
                )
            )
            await session.execute(update_query)
        await session.commit()

    except Exception as e:
        await session.rollback()
        raise e
