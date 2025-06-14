from typing import Annotated, TypeVar

from fastapi import Query
from pydantic import BaseModel


T = TypeVar("T")


class GetUsersParams(BaseModel):
    page: Annotated[int, Query(ge=1)] = 1
    page_size: Annotated[int, Query(ge=1, le=100)] = 10
    name: Annotated[str | None, Query()] = None


class GetUserResponse(BaseModel):
    group_name: str
    user_id: int
    account: str
    name: str

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "group_name": "開發部",
                    "user_id": 1,
                    "account": "rd1",
                    "name": "RD1",
                }
            ]
        }
    }


class DeleteUserRequest(BaseModel):
    user_ids: list[int]

    model_config = {"json_schema_extra": {"examples": [{"user_ids": [1, 2, 3]}]}}
