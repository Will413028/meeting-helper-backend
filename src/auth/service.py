from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
import jwt
from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.schemas import (
    CreateUserRequest,
    GetUserByAccountResponse,
)
from src.auth.utils import get_password_hash, verify_password
from src.config import settings
from src.models import User, Group


async def create_access_token(
    data: dict, expires_delta: timedelta | None = None
) -> str:
    to_encode = data.copy()

    if expires_delta:
        expire = datetime.now(UTC) + expires_delta
    else:
        expire = datetime.now(UTC) + timedelta(minutes=525600)
    to_encode.update({"exp": expire})

    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


async def get_user_by_account(
    session: AsyncSession, account: str
) -> GetUserByAccountResponse:
    query = (
        select(
            User.user_id,
            User.name,
            User.account,
            User.password,
            User.group_id,
            Group.name.label("group_name"),
            Group.role,
        )
        .join(Group, User.group_id == Group.group_id)
        .where(User.account == account)
    )

    result = await session.execute(query)
    user = result.mappings().first()

    return user


async def create_user(
    session: AsyncSession,
    user: CreateUserRequest,
) -> User:
    try:
        user.password = await get_password_hash(password=user.password)

        insert_query = (
            insert(User)
            .values(
                {
                    "name": user.name,
                    "account": user.account,
                    "password": user.password,
                    "group_id": user.group_id,
                }
            )
            .returning(User)
        )
        new_user = (await session.execute(insert_query)).scalars().one()

        await session.commit()

        return new_user

    except Exception as e:
        await session.rollback()
        raise e


async def authenticate_user(
    session: AsyncSession, account: str, password: str
) -> GetUserByAccountResponse:
    db_user = await get_user_by_account(session=session, account=account)

    if not db_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    if not await verify_password(
        plain_password=password, hashed_password=db_user.password
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Invalid password or account"
        )

    return db_user
