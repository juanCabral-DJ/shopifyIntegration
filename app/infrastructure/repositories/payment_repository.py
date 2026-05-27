from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.domain.models.payment import Payment

class PaymentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_all(self) -> list[Payment]:
        result = await self.session.execute(select(Payment).order_by(Payment.processed_at.desc()))
        return result.scalars().all()

    async def add(self, payment: Payment) -> Payment:
        self.session.add(payment)
        await self.session.flush()
        return payment
