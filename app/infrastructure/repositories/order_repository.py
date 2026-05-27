from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.domain.models.order import Order

class OrderRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, order_id: int) -> Order | None:
        result = await self.session.execute(
            select(Order).options(selectinload(Order.customer), selectinload(Order.line_items)).where(Order.id == order_id)
        )
        return result.scalars().first()

    async def get_by_shopify_id(self, shopify_order_id: int) -> Order | None:
        result = await self.session.execute(
            select(Order)
            .options(selectinload(Order.customer), selectinload(Order.line_items))
            .where(Order.shopify_order_id == shopify_order_id)
        )
        return result.scalars().first()

    async def list_all(self) -> list[Order]:
        result = await self.session.execute(
            select(Order).options(selectinload(Order.customer), selectinload(Order.line_items)).order_by(Order.created_at.desc())
        )
        return result.scalars().all()

    async def add(self, order: Order) -> Order:
        self.session.add(order)
        await self.session.flush()
        return order

    async def save(self, order: Order) -> Order:
        self.session.add(order)
        await self.session.flush()
        return order
