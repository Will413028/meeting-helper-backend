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
    description: str | None = None

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "group_name": "開發部",
                    "user_id": 1,
                    "account": "rd1",
                    "name": "RD1",
                    "description": "權限描述",
                }
            ]
        }
    }


class GetUserDetailResponse(BaseModel):
    user_id: int
    group_name: str
    name: str
    account: str
    password: str
    description: str | None = None


class UpdateUserRequest(BaseModel):
    group_id: int
    name: str
    account: str
    password: str

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "group_id": 1,
                    "name": "RD1",
                    "account": "rd1",
                    "password": "password123",
                }
            ]
        }
    }


class DeleteUserRequest(BaseModel):
    user_ids: list[int]

    model_config = {"json_schema_extra": {"examples": [{"user_ids": [1, 2, 3]}]}}


class UpdateUserGroup(BaseModel):
    user_id: int
    group_id: int


class UpdateUsersGroupRequest(BaseModel):
    users_data: list[UpdateUserGroup]

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "users_data": [
                        {
                            "user_id": 1,
                            "group_id": 2,
                        }
                    ]
                }
            ]
        }
    }
