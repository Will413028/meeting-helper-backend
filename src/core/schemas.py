from typing import Annotated, Generic, Literal, TypeVar

from fastapi import Query
from pydantic import BaseModel, Field

T = TypeVar("T")


class BasicPageQueryParams(BaseModel):
    page: Annotated[int, Query(ge=1)] = 1
    page_size: Annotated[int, Query(ge=1, le=100)] = 10
    sort_by: Annotated[
        Literal["created_at", "updated_at"],
        Query(description="Field to sort by", examples=["created_at"]),
    ] = "created_at"
    order_by: Annotated[
        Literal["asc", "desc"], Query(description="Sort order", examples=["desc"])
    ] = "desc"


class PaginatedDataResponse(BaseModel, Generic[T]):
    total_count: int = Field(
        ..., description="Total count of data", json_schema_extra={"examples": [100]}
    )
    total_pages: int = Field(
        ..., description="Total pages", json_schema_extra={"examples": [10]}
    )
    current_page: int = Field(
        ..., description="Current page", json_schema_extra={"examples": [1]}
    )
    data: list[T]


class ListDataResponse(BaseModel, Generic[T]):
    data: list[T]


class DataResponse(BaseModel, Generic[T]):
    data: T


class DetailResponse(BaseModel):
    detail: str = Field(..., json_schema_extra={"examples": ["successful"]})


class Error(BaseModel):
    detail: str
