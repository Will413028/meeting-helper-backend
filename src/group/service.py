from sqlalchemy import insert, select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession

from src.group.schemas import CreateGroupRequest, UpdateGroupsRequest
from src.models import User, Group


async def get_group_by_name(session: AsyncSession, name: str) -> Group:
    query = select(Group).where(Group.name == name)

    result = await session.execute(query)
    group = result.scalar()

    return group


async def get_groups(session: AsyncSession) -> list[Group]:
    query = select(Group)
    result = await session.execute(query)
    groups = result.scalars().all()
    return groups


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
