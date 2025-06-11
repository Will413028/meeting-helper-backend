from typing import TypeVar

from pydantic import BaseModel


T = TypeVar("T")


class CreateUserRequest(BaseModel):
    name: str
    account: str
    password: str

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "name": "John Doe",
                    "account": "account1",
                    "password": "password123",
                }
            ]
        }
    }


class Token(BaseModel):
    access_token: str


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
