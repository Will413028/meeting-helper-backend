from typing import Annotated, TypeVar

from fastapi import Query
from pydantic import BaseModel


T = TypeVar("T")


class CreateGroupRequest(BaseModel):
    name: str

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "name": "RD",
                }
            ]
        }
    }


class GroupData(BaseModel):
    group_id: int
    name: str


class UpdateGroupsRequest(BaseModel):
    groups: list[GroupData]

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "groups": [
                        {
                            "group_id": 1,
                            "name": "RD",
                        }
                    ]
                }
            ]
        }
    }


class GetGroupResponse(BaseModel):
    group_id: int
    name: str
    role: str
    user_count: int

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "group_id": 1,
                    "name": "RD",
                    "role": "user",
                    "user_count": 5,
                }
            ]
        }
    }


class GetGroupsParams(BaseModel):
    page: Annotated[int, Query(ge=1)] = 1
    page_size: Annotated[int, Query(ge=1, le=100)] = 10
    name: Annotated[str | None, Query()] = None
