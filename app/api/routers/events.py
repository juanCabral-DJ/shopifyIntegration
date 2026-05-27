from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.infrastructure.repositories.integration_repository import IntegrationRepository

router = APIRouter()


@router.get("/")
async def list_events(
    status: str | None = None,
    limit: int = 100,
    session: AsyncSession = Depends(get_session),
) -> dict[str, list[dict[str, Any]]]:
    repo = IntegrationRepository(session)
    inbox = await repo.list_inbox(status=status, limit=min(limit, 500))
    outbox = await repo.list_outbox(status=status, limit=min(limit, 500))
    return {
        "inbox": [_to_dict(event) for event in inbox],
        "outbox": [_to_dict(event) for event in outbox],
    }


def _to_dict(record) -> dict[str, Any]:
    return {
        column.name: getattr(record, column.name)
        for column in record.__table__.columns
    }
