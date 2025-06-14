from typing import TypeVar

from pydantic import BaseModel


T = TypeVar("T")


class CreateUserRequest(BaseModel):
    name: str
    account: str
    password: str
    group_id: int

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "name": "John Doe",
                    "account": "account1",
                    "password": "password123",
                    "group_id": 1,
                }
            ]
        }
    }


class Token(BaseModel):
    access_token: str
    group_name: str
    user_name: str


class UpdatePasswordRequest(BaseModel):
    phone: str
    password: str
    code: str

    model_config = {
        "json_schema_extra": {
            "examples": [
                {"phone": "886912345678", "password": "password123", "code": "123456"}
            ]
        }
    }


class GetUserByAccountResponse(BaseModel):
    user_id: int
    name: str
    account: str
    password: str
    group_id: int
    group_name: str
