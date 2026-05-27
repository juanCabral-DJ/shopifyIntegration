import asyncio
import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.infrastructure.db import async_session
from app.domain.models.payment_method import PaymentMethod
from app.core.payment_methods import CANONICAL_PAYMENT_METHODS
from app.infrastructure.repositories.payment_method_repository import PaymentMethodRepository

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

async def seed() -> None:
    async with async_session() as session:
        repo = PaymentMethodRepository(session)
        created = 0
        for code in sorted(CANONICAL_PAYMENT_METHODS):
            existing = await repo.get_by_code(code)
            if existing:
                continue
            session.add(PaymentMethod(code=code, display_name=code.title()))
            created += 1
        await session.commit()
        print(f"Seeded {created} offline payment methods.")

if __name__ == '__main__':
    asyncio.run(seed())
