from sqlalchemy import insert, select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession

from src.group.schemas import CreateGroupRequest, UpdateGroupsRequest
from src.models import User, Group


async def get_group_by_name(session: AsyncSession, name: str) -> Group:
    query = select(Group).where(Group.name == name)

    result = await session.execute(query)
    group = result.scalar()

    return group


async def create_group(
    session: AsyncSession,
    group_data: CreateGroupRequest,
) -> User:
    try:
        insert_query = insert(Group).values(
            {
                "name": group_data.name,
            }
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
        delete_query = delete(Group).where(Group.group_id.in_(group_ids))
        await session.execute(delete_query)
        await session.commit()

    except Exception as e:
        await session.rollback()
        raise e
