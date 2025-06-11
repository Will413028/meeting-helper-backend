import asyncio
from concurrent.futures import ThreadPoolExecutor

import bcrypt
from fastapi import HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from fastapi.security.utils import get_authorization_scheme_param


class OAuth2PasswordBearerWithAccount(OAuth2PasswordBearer):
    def __init__(self, tokenUrl: str):
        super().__init__(tokenUrl=tokenUrl)

    def __call__(self, request: Request) -> str | None:
        authorization: str = request.headers.get("Authorization")
        scheme, param = get_authorization_scheme_param(authorization)
        if not authorization or scheme.lower() != "bearer":
            if self.auto_error:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Not authenticated",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            else:
                return None
        return param


oauth2_scheme = OAuth2PasswordBearerWithAccount(tokenUrl="/v1/login")


def blocking_verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode(), hashed_password.encode())


async def verify_password(plain_password: str, hashed_password: str) -> bool:
    loop = asyncio.get_event_loop()
    with ThreadPoolExecutor() as pool:
        return await loop.run_in_executor(
            pool, blocking_verify_password, plain_password, hashed_password
        )


def blocking_get_password_hash(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


async def get_password_hash(password: str) -> str:
    loop = asyncio.get_event_loop()
    with ThreadPoolExecutor() as pool:
        return await loop.run_in_executor(pool, blocking_get_password_hash, password)
