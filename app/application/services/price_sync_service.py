from typing import Any
import httpx
import logging
from decimal import Decimal, InvalidOperation

from app.application.normalization import (
    records,
    first_value,
    positive_int,
    shopify_price,
    error_message,
)
from app.application.ports import ExternalCatalogPort, IntegrationMappingPort, ShopifyCatalogPort
from app.infrastructure.se.client import ExternalSystemNotConfigured

logger = logging.getLogger(__name__)


class PriceSyncService:
    def __init__(
        self,
        integration_repo: IntegrationMappingPort,
        shopify_client: ShopifyCatalogPort,
        external_client: ExternalCatalogPort,
    ) -> None:
        self.integration_repo = integration_repo
        self.shopify_client = shopify_client
        self.external_client = external_client

    async def sync_prices(self, run: Any | None = None) -> dict[str, Any]:
        run = run or await self.integration_repo.start_sync_run("prices")
        try:
            data = await self.external_client.list_prices()
            prices = records(data)
            principal_prices = self._principal_prices_by_item(prices)
            existing_mappings = await self._existing_price_mappings_by_item_code(list(principal_prices))
            mapped = 0
            shopify_updated = 0
            skipped = 0
            shopify_skipped = 0
            for processed, (item_code, price) in enumerate(principal_prices.items(), start=1):
                amount = first_value(price, "facpre_Contado", "facpre_contado")
                existing = existing_mappings.get(item_code)
                if existing is None:
                    skipped += 1
                    await self.integration_repo.upsert_sku_map(
                        invitm_codigo=item_code,
                        sku=str(item_code),
                        last_price=amount,
                        active=True,
                    )
                    mapped += 1
                    await self._update_prices_sync_progress(
                        run,
                        len(prices),
                        len(principal_prices),
                        processed,
                        mapped,
                        shopify_updated,
                        shopify_skipped,
                        skipped,
                    )
                    continue

                if self._prices_equal(getattr(existing, "last_price", None), amount):
                    shopify_skipped += 1
                    await self._update_prices_sync_progress(
                        run,
                        len(prices),
                        len(principal_prices),
                        processed,
                        mapped,
                        shopify_updated,
                        shopify_skipped,
                        skipped,
                    )
                    continue

                sh_price = shopify_price(amount)
                if sh_price is None:
                    shopify_skipped += 1
                    await self.integration_repo.upsert_sku_map(
                        invitm_codigo=item_code,
                        sku=existing.sku if existing else str(item_code),
                        last_price=amount,
                        active=existing.active if existing else True,
                    )
                    mapped += 1
                    await self._update_prices_sync_progress(
                        run,
                        len(prices),
                        len(principal_prices),
                        processed,
                        mapped,
                        shopify_updated,
                        shopify_skipped,
                        skipped,
                    )
                    continue

                if (
                    positive_int(getattr(existing, "shopify_product_id", None)) is not None
                    and positive_int(getattr(existing, "shopify_variant_id", None)) is not None
                ):
                    await self.shopify_client.update_product(
                        int(existing.shopify_product_id),
                        {
                            "variants": [
                                {
                                    "id": int(existing.shopify_variant_id),
                                    "price": sh_price,
                                }
                            ]
                        },
                    )
                    shopify_updated += 1
                else:
                    shopify_skipped += 1
                await self.integration_repo.upsert_sku_map(
                    invitm_codigo=item_code,
                    sku=existing.sku if existing else str(item_code),
                    last_price=amount,
                    active=existing.active if existing else True,
                )
                mapped += 1
                await self._update_prices_sync_progress(
                    run,
                    len(prices),
                    len(principal_prices),
                    processed,
                    mapped,
                    shopify_updated,
                    shopify_skipped,
                    skipped,
                )
            await self.integration_repo.add_outbox_event(
                target="shopify",
                operation="prices.sync",
                payload={
                    "source": "se",
                    "received": len(prices),
                    "mapped": mapped,
                    "shopify_updated": shopify_updated,
                    "shopify_skipped": shopify_skipped,
                    "skipped": skipped,
                },
                status="done",
            )
            stats = {
                "received": len(prices),
                "mapped": mapped,
                "shopify_updated": shopify_updated,
                "shopify_skipped": shopify_skipped,
                "skipped": skipped,
            }
            await self.integration_repo.finish_sync_run(run, "success", stats)
            return {"status": "success", **stats}
        except (ExternalSystemNotConfigured, httpx.HTTPError) as exc:
            message = error_message(exc)
            logger.exception("Price sync failed")
            await self.integration_repo.finish_sync_run(run, "failed", error_message=message)
            return {"status": "failed", "error": message}

    async def _existing_price_mappings_by_item_code(self, item_codes: list[int]) -> dict[int, Any]:
        if hasattr(self.integration_repo, "get_sku_maps_by_item_codes"):
            return await self.integration_repo.get_sku_maps_by_item_codes(item_codes)
        mappings = {}
        for item_code in item_codes:
            mapping = await self.integration_repo.get_sku_map_by_item_code(item_code)
            if mapping is not None:
                mappings[item_code] = mapping
        return mappings

    async def _update_prices_sync_progress(
        self,
        run: Any,
        prices_received: int,
        principal_prices: int,
        processed: int,
        mapped: int,
        shopify_updated: int,
        shopify_skipped: int,
        skipped: int,
    ) -> None:
        if processed % 100 != 0:
            return
        update_stats = getattr(self.integration_repo, "update_sync_run_stats", None)
        if update_stats is None:
            return
        await update_stats(
            run,
            {
                "received": prices_received,
                "principal_prices": principal_prices,
                "processed": processed,
                "mapped": mapped,
                "shopify_updated": shopify_updated,
                "shopify_skipped": shopify_skipped,
                "skipped": skipped,
            },
        )
        session = getattr(self.integration_repo, "session", None)
        if session is not None:
            await session.commit()

    def _principal_prices_by_item(self, prices: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
        result = {}
        for price in prices:
            item_code = first_value(price, "invitm_Codigo", "invitm_codigo")
            if item_code is None:
                continue
            try:
                code = int(item_code)
            except (TypeError, ValueError):
                continue
            if self._is_principal_price(price):
                result[code] = price
            elif code not in result:
                result[code] = price
        return result

    def _is_principal_price(self, price: dict[str, Any]) -> bool:
        return bool(first_value(price, "facpre_Principal", "facpre_principal") in (True, 1, "1", "Y", "S"))

    def _prices_equal(self, left: Any, right: Any) -> bool:
        if left is None and right is None:
            return True
        if left is None or right is None:
            return False
        try:
            return Decimal(str(left)) == Decimal(str(right))
        except (ValueError, TypeError, InvalidOperation):
            return str(left) == str(right)
