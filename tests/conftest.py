import os
import pytest
from httpx import AsyncClient

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/shopify_payments_test")
os.environ.setdefault("SHOPIFY_SHOP", "test-shop.myshopify.com")
os.environ.setdefault("SHOPIFY_ACCESS_TOKEN", "test-token")
os.environ.setdefault("SHOPIFY_WEBHOOK_SECRET", "test-secret")
os.environ.setdefault("APP_URL", "http://testserver")

from app.main import app

@pytest.fixture
async def async_client() -> AsyncClient:
    async with AsyncClient(app=app, base_url="http://testserver") as client:
        yield client
