from app.core.config import Settings


def test_offline_payment_methods_json_aliases_normalize_to_canonical_methods() -> None:
    settings = Settings(
        DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:5432/test",
        SHOPIFY_SHOP="test-shop.myshopify.com",
        SHOPIFY_ACCESS_TOKEN="token",
        SHOPIFY_WEBHOOK_SECRET="secret",
        APP_URL="https://example.com",
        OFFLINE_PAYMENT_METHODS='["efectivo","transferencia bancaria","bank deposit","cash","manual"]',
    )

    assert settings.offline_payment_methods == {"efectivo", "transferencia"}
