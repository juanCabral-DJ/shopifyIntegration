from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.inventory_item import InventoryItem


class InventoryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_all(self) -> list[InventoryItem]:
        result = await self.session.execute(
            select(InventoryItem).order_by(InventoryItem.product_title, InventoryItem.variant_title)
        )
        return result.scalars().all()

    async def get_by_inventory_item_and_location(
        self,
        inventory_item_id: int,
        location_id: int,
    ) -> InventoryItem | None:
        result = await self.session.execute(
            select(InventoryItem).where(
                InventoryItem.inventory_item_id == inventory_item_id,
                InventoryItem.location_id == location_id,
            )
        )
        return result.scalars().first()

    async def list_by_inventory_item_id(self, inventory_item_id: int) -> list[InventoryItem]:
        result = await self.session.execute(
            select(InventoryItem).where(InventoryItem.inventory_item_id == inventory_item_id)
        )
        return result.scalars().all()

    async def add(self, inventory_item: InventoryItem) -> InventoryItem:
        self.session.add(inventory_item)
        await self.session.flush()
        return inventory_item

    async def save(self, inventory_item: InventoryItem) -> InventoryItem:
        self.session.add(inventory_item)
        await self.session.flush()
        return inventory_item
