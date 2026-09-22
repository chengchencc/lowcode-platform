"""统一分页。

注意：本模块**不能**加 `from __future__ import annotations`。
`PageParams.__init__` 的签名里用了 `Annotated[int, Query(...)]`，一旦注解被推迟成
字符串，FastAPI 就无法还原出它，会在请求处理时抛 PydanticUserError。
"""

from typing import Annotated

from fastapi import Query
from pydantic import BaseModel
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

MAX_PAGE_SIZE = 100


class PageParams:
    """作为 FastAPI 依赖使用：`paging: Annotated[PageParams, Depends()]`。"""

    def __init__(
        self,
        page: Annotated[int, Query(ge=1, description="页码，从 1 开始")] = 1,
        size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE, description="每页条数")] = 20,
    ) -> None:
        self.page = page
        self.size = size

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.size


class Page[T](BaseModel):
    items: list[T]
    total: int
    page: int
    size: int


def paginate(db: Session, stmt: Select, params: PageParams) -> tuple[list, int]:
    """执行分页查询，返回 (行列表, 总数)。"""
    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    rows = db.scalars(stmt.limit(params.size).offset(params.offset)).all()
    return list(rows), total


def build_page(items: list, total: int, params: PageParams) -> dict:
    return {"items": items, "total": total, "page": params.page, "size": params.size}
