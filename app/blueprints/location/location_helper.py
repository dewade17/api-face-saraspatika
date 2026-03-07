from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from flask import Request


@dataclass(frozen=True)
class PaginationParams:
    page: int
    page_size: int


def parse_pagination(
    req: Request,
    default_page: int = 1,
    default_page_size: int = 20,
    max_page_size: int = 100,
) -> PaginationParams:
    page = req.args.get("page", type=int, default=default_page)
    page_size = req.args.get("page_size", type=int, default=default_page_size)

    page = default_page if not page or page < 1 else page
    page_size = default_page_size if not page_size or page_size < 1 else min(page_size, max_page_size)

    return PaginationParams(page=page, page_size=page_size)


def paginate_query(query: Any, pagination: PaginationParams) -> tuple[int, list[Any]]:
    total = query.count()
    items = (
        query.offset((pagination.page - 1) * pagination.page_size)
        .limit(pagination.page_size)
        .all()
    )
    return total, items
