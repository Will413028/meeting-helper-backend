from typing import TypeVar

from pydantic import BaseModel


T = TypeVar("T")


class GetSettingResponse(BaseModel):
    is_auto_delete: bool
    is_auto_clean: bool

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "is_auto_delete": True,
                    "is_auto_clean": True,
                }
            ]
        }
    }


class UpdateSettingParam(BaseModel):
    is_auto_delete: bool
    is_auto_clean: bool

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "is_auto_delete": True,
                    "is_auto_clean": True,
                }
            ]
        }
    }
