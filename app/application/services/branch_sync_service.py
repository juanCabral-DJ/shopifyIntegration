from typing import Any

import httpx

from app.application.normalization import (
    branch_name,
    first_int,
    first_value,
    records,
    shopify_location_payload,
)
from app.application.ports import ExternalCatalogPort, IntegrationMappingPort, ShopifyCatalogPort
from app.infrastructure.se.client import ExternalSystemNotConfigured


class BranchSyncService:
    def __init__(
        self,
        integration_repo: IntegrationMappingPort,
        shopify_client: ShopifyCatalogPort,
        external_client: ExternalCatalogPort,
    ) -> None:
        self.integration_repo = integration_repo
        self.shopify_client = shopify_client
        self.external_client = external_client

    async def sync_branches(self) -> dict[str, Any]:
        run = await self.integration_repo.start_sync_run("branches")
        try:
            branches = records(await self.external_client.list_branches())
            mapped = 0
            created = 0
            existing = 0
            shopify_locations_by_name: dict[str, dict[str, Any]] | None = None

            for branch in branches:
                branch_code = first_int(branch, "admsuc_codigo", "admsuc_Codigo", "codigo")
                if branch_code is None:
                    continue
                name = branch_name(branch, branch_code)
                location_id = first_int(branch, "shopify_location_id")
                if location_id is None:
                    if shopify_locations_by_name is None:
                        shopify_locations_by_name = await self._shopify_locations_by_name()
                    location = await self._ensure_shopify_location(branch, name, shopify_locations_by_name)
                    location_id = first_int(location, "legacyResourceId", "legacy_resource_id", "id")
                    if location.get("sync_status") == "created":
                        created += 1
                    elif location_id is not None:
                        existing += 1

                await self.integration_repo.upsert_branch_map(
                    admsuc_codigo=branch_code,
                    shopify_location_id=location_id,
                    name=name,
                    active=bool(first_value(branch, "activo", "active", "admsts_codigo") in (None, True, 1, "1", "A")),
                )
                mapped += 1

            stats = {
                "received": len(branches),
                "mapped": mapped,
                "shopify_locations_created": created,
                "shopify_locations_existing": existing,
            }
            await self.integration_repo.finish_sync_run(run, "success", stats)
            return {"status": "success", **stats}
        except (ExternalSystemNotConfigured, httpx.HTTPError, ValueError) as exc:
            await self.integration_repo.finish_sync_run(run, "failed", error_message=str(exc))
            return {"status": "failed", "error": str(exc)}

    async def _shopify_locations_by_name(self) -> dict[str, dict[str, Any]]:
        locations: dict[str, dict[str, Any]] = {}
        for location in await self.shopify_client.list_locations():
            normalized_name = str(location.get("name") or "").strip().casefold()
            if normalized_name and normalized_name not in locations:
                locations[normalized_name] = location
        return locations

    async def _ensure_shopify_location(
        self,
        branch: dict[str, Any],
        name: str,
        shopify_locations_by_name: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        normalized_name = name.strip().casefold()
        existing_location = shopify_locations_by_name.get(normalized_name)
        if existing_location:
            result = dict(existing_location)
            result["sync_status"] = "exists"
            return result

        created = await self.shopify_client.create_location(shopify_location_payload(branch, name))
        if normalized_name:
            shopify_locations_by_name[normalized_name] = created
        return created
