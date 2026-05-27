from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.domain.models.webhook_event import WebhookEvent

class WebhookRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add_event(self, topic: str, payload: dict, headers: dict, verified: bool, attempt_count: int) -> WebhookEvent:
        event = WebhookEvent(
            topic=topic,
            payload=payload,
            headers=headers,
            verified=verified,
            attempt_count=attempt_count,
        )
        self.session.add(event)
        await self.session.flush()
        return event

    async def list_events(self) -> list[WebhookEvent]:
        result = await self.session.execute(select(WebhookEvent).order_by(WebhookEvent.received_at.desc()))
        return result.scalars().all()
