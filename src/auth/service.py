from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
import jwt
from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.schemas import (
    CreateUserRequest,
    UpdatePasswordRequest,
)
from src.auth.utils import get_password_hash, verify_password
from src.config import settings
from src.constants import Role
from src.models import User


async def create_access_token(
    data: dict, expires_delta: timedelta | None = None
) -> str:
    to_encode = data.copy()

    if expires_delta:
        expire = datetime.now(UTC) + expires_delta
    else:
        expire = datetime.now(UTC) + timedelta(minutes=15)
    to_encode.update({"exp": expire})

    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


async def get_user_by_account(session: AsyncSession, account: str) -> User:
    query = select(User).where(User.account == account)

    result = await session.execute(query)
    user = result.scalar()

    return user


async def get_user_id_by_account(session: AsyncSession, account: str) -> User:
    query = select(User.user_id).where(User.account == account)

    return (await session.execute(query)).scalar()


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
                    "role": Role.USER.value,
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


async def authenticate_user(session: AsyncSession, account: str, password: str) -> User:
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


async def reset_password(reset_data: UpdatePasswordRequest, session: AsyncSession):
    try:
        db_user = await get_user_by_account(session=session, account=reset_data.phone)

        if not db_user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
            )

        if db_user.role != Role.USER.value:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Invalid role"
            )

        db_user.password = await get_password_hash(password=reset_data.password)

        await session.commit()

    except Exception as e:
        await session.rollback()
        raise e
