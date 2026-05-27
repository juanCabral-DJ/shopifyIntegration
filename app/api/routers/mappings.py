from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.infrastructure.repositories.integration_repository import IntegrationRepository

router = APIRouter()

ALLOWED_MAPPINGS = {
    "orders",
    "skus",
    "customers",
    "invoices",
    "receipts",
    "branches",
    "families",
    "brands",
    "params",
    "inventory_snapshots",
}


@router.get("/{mapping}")
async def list_mapping(
    mapping: str,
    limit: int = 100,
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    if mapping not in ALLOWED_MAPPINGS:
        raise HTTPException(status_code=404, detail="Unknown mapping")
    records = await IntegrationRepository(session).list_mapping(mapping, limit=min(limit, 500))
    return [_to_dict(record) for record in records]


def _to_dict(record) -> dict[str, Any]:
    return {
        column.name: getattr(record, column.name)
        for column in record.__table__.columns
    }
