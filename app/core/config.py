import json
from functools import lru_cache
from typing import Annotated
from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict
from app.core.payment_methods import normalize_payment_method

class Settings(BaseSettings):
    database_url: str
    shopify_shop: str
    shopify_api_version: str = "2026-01"
    shopify_client_id: str = ""
    shopify_client_secret: str = ""
    shopify_access_token: str = ""
    shopify_webhook_secret: str
    shopify_scopes: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: [
            "read_orders",
            "write_orders",
            "read_customers",
            "write_customers",
            "read_products",
            "write_products",
            "read_inventory",
            "write_inventory",
            "read_locations",
            "write_locations",
            "read_fulfillments",
            "write_fulfillments",
            "read_merchant_managed_fulfillment_orders",
            "write_merchant_managed_fulfillment_orders",
            "read_third_party_fulfillment_orders",
            "write_third_party_fulfillment_orders",
        ],
    )
    app_url: str
    se_base_url: str = ""
    se_api_key: str = ""
    se_company_code: int = 1
    redis_url: str = ""
    inventory_discrepancy_threshold: int = 1
    outbox_batch_size: int = 50
    s3_bucket: str = ""
    s3_public_base_url: str = ""
    debug_errors: bool = True
    offline_payment_methods: Annotated[set[str], NoDecode] = Field(
        default_factory=lambda: {"efectivo", "transferencia"},
    )

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False, extra="ignore")

    @field_validator("database_url")
    @classmethod
    def require_postgresql(cls, value: str) -> str:
        if value.startswith("sqlite"):
            raise ValueError("DATABASE_URL must use PostgreSQL, not SQLite")
        return value

    @field_validator("offline_payment_methods", mode="before")
    @classmethod
    def parse_offline_methods(cls, value: str | set[str] | list[str]) -> set[str]:
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
                if isinstance(parsed, list):
                    value = parsed
                else:
                    value = value.split(",")
            except json.JSONDecodeError:
                value = value.split(",")

        normalized_methods = set()
        for item in value:
            normalized = normalize_payment_method(str(item))
            if normalized:
                normalized_methods.add(normalized)
        return normalized_methods or {"efectivo", "transferencia"}

    @field_validator("shopify_scopes", mode="before")
    @classmethod
    def parse_shopify_scopes(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, str):
            value = value.split(",")
        scopes = []
        seen = set()
        for item in value:
            scope = str(item).strip()
            if scope and scope not in seen:
                scopes.append(scope)
                seen.add(scope)
        return scopes

@lru_cache()
def get_settings() -> Settings:
    return Settings()

settings = get_settings()
