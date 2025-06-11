import asyncio
from concurrent.futures import ThreadPoolExecutor

import bcrypt
from fastapi.security import OAuth2PasswordBearer


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/v1/login")


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
