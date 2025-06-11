from typing import Annotated

from fastapi import Depends, HTTPException, status
import jwt
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.service import get_user_by_account, get_user_id_by_account
from src.auth.utils import oauth2_scheme
from src.config import settings
from src.constants import Role
from src.database import get_db_session
from src.models import User

from jwt.exceptions import InvalidTokenError


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )

        account: str = payload.get("sub")

        if account is None:
            raise credentials_exception

        user = await get_user_by_account(session=session, account=account)

        if user is None:
            raise credentials_exception
        return user

    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
        ) from exc
    except InvalidTokenError as exc:
        raise credentials_exception from exc
    except HTTPException as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


async def get_current_user_id(
    token: Annotated[str, Depends(oauth2_scheme)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )

        account: str = payload.get("sub")

        if account is None:
            raise credentials_exception

        user_id = await get_user_id_by_account(session=session, account=account)

        if user_id is None:
            raise credentials_exception
        return user_id

    except jwt.ExpiredSignatureError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
        ) from e
    except InvalidTokenError as e:
        raise credentials_exception from e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e


async def get_admin_user(current_user: Annotated[User, Depends(get_current_user)]):
    if current_user.role != Role.ADMIN.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have the permission to access this resource",
        )
    return current_user
