from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base
from app.core.config import settings

Base = declarative_base()

import app.domain.models.customer  # noqa: F401
import app.domain.models.inventory_item  # noqa: F401
import app.domain.models.integration  # noqa: F401
import app.domain.models.order  # noqa: F401
import app.domain.models.payment  # noqa: F401
import app.domain.models.payment_method  # noqa: F401
import app.domain.models.webhook_event  # noqa: F401

engine = create_async_engine(settings.database_url, future=True, echo=False)
async_session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
