from fastapi import HTTPException

from app.infrastructure.db import async_session
from app.infrastructure.se.client import SEClient
from app.infrastructure.shopify.client import ShopifyClient
from app.core.config import settings

async def get_session():
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def get_shopify_client() -> ShopifyClient:
    if not settings.shopify_access_token:
        raise HTTPException(
            status_code=500,
            detail="SHOPIFY_ACCESS_TOKEN is required for Shopify API calls. Configure the private/custom app token in .env and restart the server.",
        )
    return ShopifyClient(
        shop=settings.shopify_shop,
        api_version=settings.shopify_api_version,
        access_token=settings.shopify_access_token,
    )


def get_se_client() -> SEClient:
    return SEClient(
        base_url=settings.se_base_url,
        api_key=settings.se_api_key,
        company_code=settings.se_company_code,
    )
