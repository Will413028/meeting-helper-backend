from typing import TypeVar

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
