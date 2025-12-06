from datetime import timedelta
from typing import Annotated

from fastapi import (
    APIRouter,
    Body,
    Depends,
    HTTPException,
    status,
)
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.schemas import (
    CreateUserRequest,
    Token,
)
from src.auth.service import (
    authenticate_user,
    create_access_token,
    create_user,
    get_user_by_account,
)
from src.config import settings
from src.database import get_db_session
from src.schemas import DetailResponse

router = APIRouter(
    tags=["users"],
)


@router.post(
    "/v1/register",
    response_model=DetailResponse,
)
async def register_handler(
    user_data: Annotated[CreateUserRequest, Body()],
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    db_user = await get_user_by_account(session=session, account=user_data.account)

    if db_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="User already exists"
        )

    await create_user(session=session, user=user_data)
    return DetailResponse(detail="User registered successfully")


@router.post(
    "/v1/login",
    response_model=Token,
)
async def login_handler(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    user = await authenticate_user(
        session=session, account=form_data.username, password=form_data.password
    )

    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    access_token = await create_access_token(
        data={"sub": user.account}, expires_delta=access_token_expires
    )

    return Token(
        access_token=access_token,
        group_name=user.group_name,
        user_name=user.name,
        role=user.role,
    )


@router.post("/token")
async def login_for_access_token(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> Token:
    user = await authenticate_user(
        session=session, account=form_data.username, password=form_data.password
    )

    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    access_token = await create_access_token(
        data={"sub": user.account}, expires_delta=access_token_expires
    )

    return Token(access_token=access_token)
