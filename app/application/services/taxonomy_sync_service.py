from typing import Any
import httpx
import logging

from app.application.normalization import (
    records,
    first_value,
    first_int,
    clean_text,
)
from app.application.ports import ExternalCatalogPort, IntegrationMappingPort, ShopifyCatalogPort
from app.infrastructure.se.client import ExternalSystemNotConfigured

logger = logging.getLogger(__name__)


class TaxonomySyncService:
    def __init__(
        self,
        integration_repo: IntegrationMappingPort,
        shopify_client: ShopifyCatalogPort,
        external_client: ExternalCatalogPort,
    ) -> None:
        self.integration_repo = integration_repo
        self.shopify_client = shopify_client
        self.external_client = external_client

    async def sync_catalog_taxonomy(self) -> dict[str, Any]:
        run = await self.integration_repo.start_sync_run("catalog_taxonomy")
        try:
            families = records(await self.external_client.list_families())
            brands = records(await self.external_client.list_brands())
            created_collections = 0
            existing_collections = 0
            seen_family_names: set[str] = set()
            for family in families:
                family_id = str(first_value(family, "invfam_codigo", "familia_codigo", "codigo", "id") or "")
                family_name = clean_text(first_value(family, "invfam_nombre", "familia_nombre", "nombre", "name"))
                if family_id:
                    shopify_collection_id = None
                    if family_name:
                        normalized_family_name = family_name.strip().casefold()
                        if normalized_family_name in seen_family_names:
                            continue
                        seen_family_names.add(normalized_family_name)
                        if hasattr(self.shopify_client, "get_or_create_custom_collection"):
                            collection = await self.shopify_client.get_or_create_custom_collection(family_name)
                        else:
                            collection = await self.shopify_client.ensure_custom_collection(family_name)
                        shopify_collection_id = first_int(collection, "id")
                        if collection.get("sync_status") == "created":
                            created_collections += 1
                        else:
                            existing_collections += 1
                    await self.integration_repo.upsert_family_map(
                        se_familia_id=family_id,
                        se_familia_nombre=family_name,
                        shopify_collection_id=shopify_collection_id,
                    )
            for brand in brands:
                brand_id = str(first_value(brand, "invmar_codigo", "marca_codigo", "codigo", "id") or "")
                brand_name = first_value(brand, "invmar_nombre", "marca_nombre", "nombre", "name")
                if brand_id:
                    await self.integration_repo.upsert_brand_map(
                        se_marca_id=brand_id,
                        se_marca_nombre=brand_name,
                        shopify_tag=str(brand_name or brand_id),
                    )
            stats = {
                "families": len(families),
                "brands": len(brands),
                "collections_created": created_collections,
                "collections_existing": existing_collections,
            }
            await self.integration_repo.finish_sync_run(run, "success", stats)
            return {"status": "success", **stats}
        except (ExternalSystemNotConfigured, httpx.HTTPError) as exc:
            logger.exception("Taxonomy sync failed")
            await self.integration_repo.finish_sync_run(run, "failed", error_message=str(exc))
            return {"status": "failed", "error": str(exc)}
