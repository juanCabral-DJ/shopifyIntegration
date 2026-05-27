from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.domain.models.customer import Customer

class CustomerRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_or_create(self, shopify_customer_id: int, email: str | None, first_name: str | None, last_name: str | None) -> Customer:
        result = await self.session.execute(select(Customer).where(Customer.shopify_customer_id == shopify_customer_id))
        customer = result.scalars().first()
        if customer:
            customer.email = email
            customer.first_name = first_name
            customer.last_name = last_name
            self.session.add(customer)
            await self.session.flush()
            return customer

        customer = Customer(
            shopify_customer_id=shopify_customer_id,
            email=email,
            first_name=first_name,
            last_name=last_name,
        )
        self.session.add(customer)
        await self.session.flush()
        return customer
