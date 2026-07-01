import hashlib
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
from app.infrastructure.se.client import ExternalSystemNotConfigured

logger = logging.getLogger(__name__)


def image_hash(base64_data: Any) -> str:
    return hashlib.sha256(str(base64_data).strip().encode("utf-8")).hexdigest()


def image_external_id(image: dict[str, Any], item_code: int, img_hash: str) -> str:
    table = str(first_value(image, "admimg_tabla", "tabla") or "minvitm").strip().lower()
    line = first_value(image, "admimg_linea", "linea", "line", "id")
    if line not in (None, ""):
        return f"{table}:{item_code}:{line}"
    return f"{table}:{item_code}:{img_hash[:16]}"


class ImageSyncService:
    def __init__(
        self,
        integration_repo: IntegrationMappingPort,
        shopify_client: ShopifyCatalogPort,
        external_client: ExternalCatalogPort,
    ) -> None:
        self.integration_repo = integration_repo
        self.shopify_client = shopify_client
        self.external_client = external_client

    async def sync_images(self, run: Any | None = None) -> dict[str, Any]:
        run = run or await self.integration_repo.start_sync_run("images")
        try:
            images = records(await self.external_client.list_images())
            image_item_codes = [
                item_code
                for image in images
                if (item_code := first_int(image, "admimg_master", "invitm_codigo", "invitm_Codigo", "codigo")) is not None
            ]
            mappings_by_item = await self._existing_image_mappings_by_item_code(image_item_codes)
            uploaded = 0
            skipped = 0
            duplicate_skipped = 0
            received = len(images)
            item_image_counts: dict[int, int] = {}
            for image in images:
                item_code = first_int(image, "admimg_master", "invitm_codigo", "invitm_Codigo", "codigo")
                if item_code is None:
                    skipped += 1
                    continue
                mapping = mappings_by_item.get(item_code)
                if mapping is None:
                    skipped += 1
                    continue
                shopify_product_id = getattr(mapping, "shopify_product_id", None)
                if not shopify_product_id:
                    skipped += 1
                    continue
                base64_data = first_value(image, "base64", "admimg_imagen", "imagen", "image", "attachment")
                if not base64_data:
                    skipped += 1
                    continue
                img_hash = image_hash(base64_data)
                admimg_linea = first_int(image, "admimg_linea", "linea", "line", "id")
                ext_image_id = image_external_id(image, item_code, img_hash)
                existing_image = await self._existing_product_image_map(ext_image_id, item_code, img_hash)
                if (
                    existing_image is not None
                    and getattr(existing_image, "image_hash", None) == img_hash
                    and getattr(existing_image, "shopify_image_id", None)
                ):
                    skipped += 1
                    duplicate_skipped += 1
                    continue
                item_image_counts[item_code] = item_image_counts.get(item_code, 0) + 1
                filename = str(
                    first_value(image, "filename", "admimg_nombre", "nombre")
                    or f"{item_code}-{item_image_counts[item_code]}.jpg"
                )
                shopify_image = await self.shopify_client.upload_product_image(
                    int(shopify_product_id),
                    str(base64_data),
                    filename,
                )
                await self._upsert_product_image_map(
                    external_image_id=ext_image_id,
                    invitm_codigo=item_code,
                    admimg_linea=admimg_linea,
                    image_hash=img_hash,
                    shopify_product_id=int(shopify_product_id),
                    shopify_image_id=first_int(shopify_image, "id"),
                    filename=filename,
                )
                uploaded += 1
            stats = {"received": received, "uploaded": uploaded, "skipped": skipped, "duplicate_skipped": duplicate_skipped}
            await self.integration_repo.finish_sync_run(run, "success", stats)
            return {"status": "success", **stats}
        except (ExternalSystemNotConfigured, httpx.HTTPError, ValueError) as exc:
            message = error_message(exc)
            logger.exception("Image sync failed")
            await self.integration_repo.finish_sync_run(run, "failed", error_message=message)
            return {"status": "failed", "error": message}

    async def _existing_image_mappings_by_item_code(self, item_codes: list[int]) -> dict[int, Any]:
        if not item_codes:
            return {}
        if hasattr(self.integration_repo, "get_sku_maps_by_item_codes"):
            return await self.integration_repo.get_sku_maps_by_item_codes(item_codes)
        mappings = {}
        for item_code in item_codes:
            mapping = await self.integration_repo.get_sku_map_by_item_code(item_code)
            if mapping is not None:
                mappings[item_code] = mapping
        return mappings

    async def _existing_product_image_map(
        self,
        external_image_id: str,
        invitm_codigo: int,
        img_hash: str,
    ) -> Any | None:
        if hasattr(self.integration_repo, "get_product_image_map"):
            return await self.integration_repo.get_product_image_map(
                external_image_id,
                invitm_codigo=invitm_codigo,
                image_hash=img_hash,
            )
        return None

    async def _upsert_product_image_map(
        self,
        external_image_id: str,
        invitm_codigo: int,
        image_hash: str,
        shopify_product_id: int,
        admimg_linea: int | None = None,
        shopify_image_id: int | None = None,
        filename: str | None = None,
    ) -> Any:
        if hasattr(self.integration_repo, "upsert_product_image_map"):
            return await self.integration_repo.upsert_product_image_map(
                external_image_id=external_image_id,
                invitm_codigo=invitm_codigo,
                image_hash=image_hash,
                shopify_product_id=shopify_product_id,
                admimg_linea=admimg_linea,
                shopify_image_id=shopify_image_id,
                filename=filename,
            )
        return None
