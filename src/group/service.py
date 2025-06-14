from sqlalchemy import (
    asc,
    delete,
    func,
    insert,
    select,
    update,
)

from sqlalchemy.ext.asyncio import AsyncSession

from src.schemas import PaginatedDataResponse
from src.group.schemas import CreateGroupRequest, UpdateGroupsRequest, GetGroupResponse
from src.models import User, Group
from src.constants import Role


async def get_group_by_name(session: AsyncSession, name: str) -> Group:
    query = select(Group).where(Group.name == name)

    result = await session.execute(query)
    group = result.scalar()

    return group


async def get_groups(
    session: AsyncSession,
    name: str | None,
    page: int = 1,
    page_size: int = 10,
) -> PaginatedDataResponse[GetGroupResponse]:
    query = (
        select(
            Group.group_id,
            Group.name,
            Group.role,
            func.count(User.user_id).label("user_count"),
        )
        .select_from(Group)
        .outerjoin(User, Group.group_id == User.group_id)
        .group_by(Group.group_id, Group.name, Group.role)
        .order_by(asc(Group.group_id))
    )

    if name:
        query = query.filter(Group.name.like(f"%{name}%"))

    total_count = (
        await session.execute(select(func.count()).select_from(query.subquery()))
    ).scalar()

    total_pages = (total_count + page_size - 1) // page_size

    offset = (page - 1) * page_size

    results = (
        (await session.execute(query.offset(offset).limit(page_size))).mappings().all()
    )

    return PaginatedDataResponse[GetGroupResponse](
        total_count=total_count,
        total_pages=total_pages,
        current_page=page,
        data=results,
    )


async def create_admin_group(
    session: AsyncSession,
    group_data: CreateGroupRequest,
):
    try:
        insert_query = insert(Group).values(
            {"name": group_data.name, "role": Role.ADMIN.value}
        )
        await session.execute(insert_query)
        await session.commit()

    except Exception as e:
        await session.rollback()
        raise e


async def create_uncategorized_group(
    session: AsyncSession,
    group_data: CreateGroupRequest,
):
    try:
        insert_query = insert(Group).values(
            {"name": group_data.name, "role": Role.USER.value, "is_uncategorized": True}
        )
        await session.execute(insert_query)
        await session.commit()

    except Exception as e:
        await session.rollback()
        raise e


async def create_group(
    session: AsyncSession,
    group_data: CreateGroupRequest,
):
    try:
        insert_query = insert(Group).values(
            {"name": group_data.name, "role": Role.USER.value}
        )
        await session.execute(insert_query)
        await session.commit()

    except Exception as e:
        await session.rollback()
        raise e


async def update_groups(groups_data: UpdateGroupsRequest, session: AsyncSession):
    try:
        for group in groups_data.groups:
            update_query = (
                update(Group)
                .where(Group.group_id == group.group_id)
                .values(name=group.name)
            )
            await session.execute(update_query)

        await session.commit()

    except Exception as e:
        await session.rollback()
        raise e


async def delete_groups(session: AsyncSession, group_ids: list[str]):
    try:
        # First, find or create the "uncategorized" group
        uncategorized_group = await get_group_by_name(session, "未分類")

        if not uncategorized_group:
            # Create the uncategorized group if it doesn't exist
            insert_query = insert(Group).values(
                {
                    "name": "未分類",
                }
            )
            result = await session.execute(insert_query)
            await session.flush()  # Flush to get the group_id

            # Get the newly created group
            uncategorized_group = await get_group_by_name(session, "未分類")

        # Update all users in the groups to be deleted to the uncategorized group
        update_query = (
            update(User)
            .where(User.group_id.in_(group_ids))
            .values(group_id=uncategorized_group.group_id)
        )
        await session.execute(update_query)

        # Now delete the groups
        delete_query = delete(Group).where(Group.group_id.in_(group_ids))
        await session.execute(delete_query)

        await session.commit()

    except Exception as e:
        await session.rollback()
        raise e
