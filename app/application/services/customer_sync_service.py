from typing import Any
import httpx
import logging

from app.application.normalization import (
    records,
    first_int,
    first_value,
    error_message,
)
from app.application.ports import ExternalCatalogPort, IntegrationMappingPort, ShopifyCatalogPort
from app.application.transformers.se_to_shopify import se_customer_to_shopify
from app.infrastructure.se.client import ExternalSystemNotConfigured

logger = logging.getLogger(__name__)


def normalize_phone(value: Any) -> str | None:
    if value in (None, ""):
        return None
    digits = "".join(character for character in str(value) if character.isdigit())
    if len(digits) == 10 and digits[0] in {"8", "9"}:
        return f"+1{digits}"
    if len(digits) == 11 and digits.startswith("1"):
        return f"+{digits}"
    return f"+{digits}" if digits else None


def se_customer_email(customer: dict[str, Any]) -> str | None:
    value = first_value(customer, "email", "cxccte_Email", "cxccte_email")
    if value and "@" in str(value):
        return str(value).strip()
    refer = first_value(customer, "cxccte_Refer", "cxccte_refer")
    if refer and "@" in str(refer):
        return str(refer).strip()
    return None


class CustomerSyncService:
    def __init__(
        self,
        integration_repo: IntegrationMappingPort,
        shopify_client: ShopifyCatalogPort,
        external_client: ExternalCatalogPort,
    ) -> None:
        self.integration_repo = integration_repo
        self.shopify_client = shopify_client
        self.external_client = external_client

    async def sync_customers(self) -> dict[str, Any]:
        run = await self.integration_repo.start_sync_run("customers")
        try:
            customers = records(await self.external_client.list_customers())
            mapped = 0
            for customer in customers:
                customer_code = first_int(customer, "cxccte_Codigo", "cxccte_codigo", "codigo")
                if customer_code is None:
                    continue
                payload = se_customer_to_shopify(customer)
                existing = await self.integration_repo.upsert_customer_map(
                    cxccte_codigo=customer_code,
                    email=payload.get("email"),
                    phone=payload.get("phone"),
                )
                if existing.shopify_customer_id:
                    shopify_customer = await self.shopify_client.update_customer(
                        int(existing.shopify_customer_id),
                        payload,
                    )
                else:
                    shopify_customer = await self.shopify_client.create_customer(payload)
                await self.integration_repo.upsert_customer_map(
                    cxccte_codigo=customer_code,
                    shopify_customer_id=first_int(shopify_customer, "id"),
                    email=shopify_customer.get("email") or payload.get("email"),
                    phone=shopify_customer.get("phone") or payload.get("phone"),
                )
                mapped += 1
            await self.integration_repo.finish_sync_run(run, "success", {"received": len(customers), "mapped": mapped})
            return {"status": "success", "received": len(customers), "mapped": mapped}
        except (ExternalSystemNotConfigured, httpx.HTTPError, ValueError) as exc:
            message = error_message(exc)
            logger.exception("Customer sync failed")
            await self.integration_repo.finish_sync_run(run, "failed", error_message=message)
            return {"status": "failed", "error": message}

    async def import_se_customer_to_shopify(self, customer: dict[str, Any]) -> dict[str, Any]:
        customer_code = first_int(customer, "cxccte_Codigo", "cxccte_codigo", "codigo")
        if customer_code is None:
            return {"status": "failed", "error": "cxccte_Codigo is required"}

        await self.integration_repo.set_param_cache(f"se_customer:{customer_code}", customer)
        existing_map = await self.integration_repo.upsert_customer_map(
            cxccte_codigo=customer_code,
            email=se_customer_email(customer),
            phone=normalize_phone(first_value(customer, "cxccte_telef1", "cxccte_Telef1", "telefono", "phone")),
        )
        shopify_payload = se_customer_to_shopify(customer)
        if existing_map.shopify_customer_id:
            shopify_customer = await self.shopify_client.update_customer(
                int(existing_map.shopify_customer_id),
                shopify_payload,
            )
            action = "updated"
        else:
            shopify_customer = await self.shopify_client.create_customer(shopify_payload)
            action = "created"

        shopify_customer_id = first_int(shopify_customer, "id")
        if shopify_customer_id is None:
            return {"status": "failed", "error": "Shopify response did not include customer id"}
        await self.integration_repo.upsert_customer_map(
            cxccte_codigo=customer_code,
            shopify_customer_id=shopify_customer_id,
            email=shopify_customer.get("email") or se_customer_email(customer),
            phone=shopify_customer.get("phone") or normalize_phone(
                first_value(customer, "cxccte_telef1", "cxccte_Telef1", "telefono", "phone")
            ),
        )
        await self.integration_repo.add_outbox_event(
            target="shopify",
            operation=f"customers.{action}",
            payload={
                "cxccte_codigo": customer_code,
                "shopify_customer_id": shopify_customer_id,
                "source": "se_manual",
            },
            status="done",
        )
        return {
            "status": "success",
            "action": action,
            "cxccte_codigo": customer_code,
            "shopify_customer_id": shopify_customer_id,
        }
