from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.domain.models.payment_method import PaymentMethod

class PaymentMethodRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_code(self, code: str) -> PaymentMethod | None:
        result = await self.session.execute(select(PaymentMethod).where(PaymentMethod.code == code))
        return result.scalars().first()

    async def list_all(self) -> list[PaymentMethod]:
        result = await self.session.execute(select(PaymentMethod).order_by(PaymentMethod.code.asc()))
        return result.scalars().all()
