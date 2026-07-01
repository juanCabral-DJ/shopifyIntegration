from typing import Any
import httpx
import logging

from app.application.normalization import (
    first_int,
    first_value,
    positive_int,
    error_message,
)
from app.application.ports import ExternalCatalogPort, IntegrationMappingPort, ShopifyCatalogPort
from app.application.transformers.shopify_to_se import order_to_mfactrx_rows
from app.core.config import settings

logger = logging.getLogger(__name__)


def shopify_tags(order: dict[str, Any]) -> list[str]:
    tags_str = order.get("tags") or ""
    if isinstance(tags_str, list):
        return [str(tag).strip() for tag in tags_str]
    return [tag.strip() for tag in tags_str.split(",") if tag.strip()]


def mapped_line_item_code(
    item: dict[str, Any],
    variant_map: dict[int, int],
    sku_map: dict[str, int],
) -> int | None:
    variant_id = first_int(item, "variant_id")
    if variant_id is not None and variant_id in variant_map:
        return variant_map[variant_id]
    sku = str(item.get("sku") or "").strip().upper()
    if sku and sku in sku_map:
        return sku_map[sku]
    return None


def positive_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def company_rows(payload: list[dict[str, Any]] | dict[str, Any], wrapper_key: str | None = None) -> list[dict[str, Any]]:
    rows = []
    raw_rows = payload
    if isinstance(payload, dict) and wrapper_key:
        raw_rows = payload.get(wrapper_key) or [payload]
    if isinstance(raw_rows, list):
        for item in raw_rows:
            if isinstance(item, dict):
                row = dict(item)
                if row.get("admcia_codigo") in (None, "", 0, "0"):
                    row["admcia_codigo"] = settings.se_company_code
                rows.append(row)
    elif isinstance(raw_rows, dict):
        row = dict(raw_rows)
        if row.get("admcia_codigo") in (None, "", 0, "0"):
            row["admcia_codigo"] = settings.se_company_code
        rows.append(row)
    return rows


def invoice_rows(payload: list[dict[str, Any]] | dict[str, Any]) -> list[dict[str, Any]]:
    return company_rows(payload, "mfactrx_rows")


def invoice_visit_rows(payload: list[dict[str, Any]] | dict[str, Any]) -> list[dict[str, Any]]:
    return company_rows(payload, "mfactrx_rows")


class InvoiceSyncService:
    def __init__(
        self,
        integration_repo: IntegrationMappingPort,
        shopify_client: ShopifyCatalogPort,
        external_client: ExternalCatalogPort,
    ) -> None:
        self.integration_repo = integration_repo
        self.shopify_client = shopify_client
        self.external_client = external_client

    async def retry_order_invoice(self, shopify_order_id: int) -> dict[str, Any]:
        return await self.retry_outbox_event(shopify_order_id, {"Factura.Insertar"})

    async def retry_outbox_event(self, shopify_order_id: int, operations: set[str]) -> dict[str, Any]:
        event = await self.integration_repo.reset_outbox_for_retry(shopify_order_id, operations)
        if event is None:
            return {"status": "skipped", "reason": "no_matching_outbox_event_found"}
        status = getattr(event, "status", None) or event.get("status")
        event_id = getattr(event, "id", None) or event.get("id")
        operation = getattr(event, "operation", None) or event.get("operation")
        return {"status": status, "event_id": event_id, "operation": operation}

    async def send_invoice(self, payload: list[dict[str, Any]] | dict[str, Any]) -> dict[str, Any]:
        rows = invoice_rows(payload)
        if not rows:
            return {"status": "failed", "error": "Invoice payload must include at least one mfactrx row"}
        response = await self._process_invoice_insert(payload)
        await self.integration_repo.add_outbox_event(
            target="se",
            operation="Factura.Insertar",
            payload=rows,
            status="done",
        )
        return {"status": "success", "sent": len(rows), "response": response}

    async def send_invoice_visit(self, payload: list[dict[str, Any]] | dict[str, Any]) -> dict[str, Any]:
        rows = invoice_visit_rows(payload)
        if not rows:
            return {"status": "failed", "error": "Invoice visit payload must include at least one row"}
        response = await self.external_client.insert_invoice_visit(rows)
        await self.integration_repo.add_outbox_event(
            target="se",
            operation="Factura.InsertarVisita",
            payload=rows,
            status="done",
        )
        return {"status": "success", "sent": len(rows), "response": response}

    async def _dispatch_outbox_event(self, operation: str, payload: dict[str, Any]) -> Any:
        rows = payload.get("mfactrx_rows", [payload]) if isinstance(payload, dict) else payload
        if operation == "Factura.Insertar":
            return await self._process_invoice_insert(payload)
        elif operation == "Factura.InsertarVisita":
            return await self.external_client.insert_invoice_visit(rows)
        elif operation == "Factura.cancel":
            shopify_order_id = payload.get("shopify_order_id")
            if shopify_order_id:
                order_map = await self.integration_repo.get_order_map(int(shopify_order_id))
                invoice_id = getattr(order_map, "factrx_numero", None) if order_map else None
                if invoice_id:
                    return await self.external_client.post("/api/Factura/Anular", {"factrx_numero": invoice_id})
            return {"status": "skipped", "reason": "no_active_invoice_found_to_cancel"}
        else:
            raise ValueError(f"Unknown outbox operation: {operation}")

    async def _process_invoice_insert(self, payload: dict[str, Any]) -> Any:
        response = await self.external_client.insert_invoice(payload)
        se_status_code = getattr(self.external_client, "last_status_code", None)
        shopify_order_id = first_int(payload, "shopify_order_id")
        if shopify_order_id is None:
            first_row = invoice_rows(payload)[0] if invoice_rows(payload) else {}
            shopify_order_id = first_int(first_row, "factrx_movil_id")
        shopify_response = None
        if shopify_order_id is not None:
            factrx_numero = str(first_value(response if isinstance(response, dict) else {}, "factrx_numero", "numero") or "")
            if not factrx_numero:
                rows = invoice_rows(payload)
                factrx_numero = str(first_value(rows[0] if rows else {}, "factrx_numero") or shopify_order_id)
            mapping = await self.integration_repo.get_order_map(shopify_order_id)
            await self.integration_repo.upsert_order_map(
                shopify_order_id=shopify_order_id,
                shopify_order_name=getattr(mapping, "shopify_order_name", str(shopify_order_id)),
                factrx_movil_id=None,
                factrx_numero=factrx_numero,
                status="invoiced",
            )
            await self.integration_repo.upsert_invoice_map(
                shopify_order_id=shopify_order_id,
                factrx_numero=factrx_numero,
                status="invoiced",
                payload=payload,
                ncf=str(first_value(response if isinstance(response, dict) else {}, "ncf") or "") or None,
            )
            if se_status_code == 200:
                try:
                    shopify_response = await self._mark_shopify_order_paid_and_fulfilled(shopify_order_id)
                except Exception as exc:
                    logger.exception("Shopify update failed after SE invoice insert")
                    shopify_response = {"status": "failed", "error": error_message(exc)}
        if shopify_response is None:
            return response
        return {"invoice": response, "shopify": shopify_response}

    async def _mark_shopify_order_paid_and_fulfilled(self, shopify_order_id: int) -> dict[str, Any]:
        if self.shopify_client is None:
            return {"status": "skipped", "reason": "shopify_client_not_available"}
        payment_response = None
        if hasattr(self.shopify_client, "create_manual_payment_transaction"):
            order = await self.shopify_client.get_order(shopify_order_id)
            if str(order.get("financial_status") or "").lower() == "paid":
                payment_response = {"status": "skipped", "reason": "already_paid"}
            else:
                amount = positive_float(order.get("total_outstanding")) or positive_float(order.get("total_price"))
                if amount is None:
                    raise ValueError("Shopify order total must be greater than zero to mark as paid")
                payment_response = await self.shopify_client.create_manual_payment_transaction(
                    shopify_order_id,
                    amount,
                    str(order.get("currency") or "USD"),
                    gateway="manual",
                )
        elif hasattr(self.shopify_client, "update_order_financial_status"):
            payment_response = await self.shopify_client.update_order_financial_status(shopify_order_id, "paid")
        fulfillment_response = await self._fulfill_shopify_order_after_invoice(shopify_order_id)
        return {
            "status": "paid_and_fulfilled",
            "payment": payment_response,
            "fulfillment": fulfillment_response,
        }

    async def _fulfill_shopify_order_after_invoice(self, shopify_order_id: int) -> dict[str, Any]:
        if self.shopify_client is None:
            return {"status": "skipped", "reason": "shopify_client_not_available"}
        if not hasattr(self.shopify_client, "fulfill_order"):
            return {"status": "skipped", "reason": "fulfill_order_not_supported"}
        return await self.shopify_client.fulfill_order(shopify_order_id)

    async def build_order_invoice_payload(self, order: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
        defaults = await self._se_invoice_defaults()
        mapping_errors: list[str] = []
        customer_code = await self._resolve_customer_code(order)
        if customer_code is None:
            customer_code = positive_int(defaults.get("cxccte_codigo"))

        branch_code = await self._resolve_branch_code(order, defaults)
        vendor_code = positive_int(defaults.get("facvdr_codigo"))
        receipt_type_code = positive_int(defaults.get("admtco_codigo"))
        price_list_code = positive_int(defaults.get("facpre_codigo"))

        variant_map, sku_map, item_errors = await self._resolve_line_item_codes(order)
        mapping_errors.extend(item_errors)
        line_branch_codes = await self._resolve_line_item_branch_codes(order, variant_map, sku_map)
        invoice_payload = {
            "shopify_order_id": order["id"],
            "mfactrx_rows": order_to_mfactrx_rows(
                order,
                company_code=settings.se_company_code,
                branch_code=branch_code,
                customer_code=customer_code,
                vendor_code=vendor_code,
                receipt_type_code=receipt_type_code,
                price_list_code=price_list_code,
                ncf_serial=defaults.get("admncf_serial"),
                variant_to_item_code=variant_map,
                sku_to_item_code=sku_map,
                line_item_branch_codes=line_branch_codes,
            ),
            "mapping_errors": mapping_errors,
            "mapping_context": {
                "branch_code": branch_code,
                "line_branch_codes": line_branch_codes,
                "customer_code": customer_code,
                "vendor_code": vendor_code,
                "receipt_type_code": receipt_type_code,
                "price_list_code": price_list_code,
            },
        }
        return invoice_payload, mapping_errors

    async def _se_invoice_defaults(self) -> dict[str, Any]:
        defaults: dict[str, Any] = {}
        for key in ("se_defaults", "factura_insertar_defaults"):
            cached = await self.integration_repo.get_param_cache(key)
            if cached and isinstance(cached.value, dict):
                defaults.update(cached.value)
        for key in ("admsuc_codigo", "cxccte_codigo", "facvdr_codigo", "admtco_codigo", "facpre_codigo", "admncf_serial"):
            cached = await self.integration_repo.get_param_cache(key)
            if cached:
                value = cached.value.get("value") if isinstance(cached.value, dict) else cached.value
                defaults[key] = value
        return defaults

    async def _resolve_customer_code(self, order: dict[str, Any]) -> int | None:
        customer = order.get("customer") or {}
        customer_id = positive_int(customer.get("id"))
        if customer_id is not None:
            mapping = await self.integration_repo.get_customer_map_by_shopify_id(customer_id)
            if mapping:
                return mapping.cxccte_codigo
        for email in (customer.get("email"), order.get("email"), order.get("contact_email")):
            if email:
                mapping = await self.integration_repo.get_customer_map_by_email(str(email))
                if mapping:
                    return mapping.cxccte_codigo
        for phone in (customer.get("phone"), order.get("phone")):
            if phone:
                mapping = await self.integration_repo.get_customer_map_by_phone(str(phone))
                if mapping:
                    return mapping.cxccte_codigo
        return None

    async def _resolve_branch_code(
        self,
        order: dict[str, Any],
        defaults: dict[str, Any],
    ) -> int | None:
        for tag in shopify_tags(order):
            get_by_name = getattr(self.integration_repo, "get_branch_map_by_name", None)
            if get_by_name is None:
                break
            mapping = await get_by_name(tag)
            if mapping:
                return mapping.admsuc_codigo

        location_id = positive_int(order.get("location_id"))
        if location_id is not None:
            mapping = await self.integration_repo.get_branch_map_by_shopify_location_id(location_id)
            if mapping:
                return mapping.admsuc_codigo
        return positive_int(defaults.get("admsuc_codigo"))

    async def _resolve_line_item_codes(
        self,
        order: dict[str, Any],
    ) -> tuple[dict[int, int], dict[str, int], list[str]]:
        variant_map: dict[int, int] = {}
        sku_map: dict[str, int] = {}
        errors: list[str] = []
        for item in order.get("line_items") or []:
            variant_id = positive_int(item.get("variant_id"))
            sku = str(item.get("sku") or "").strip()
            mapping = None
            if variant_id is not None:
                mapping = await self.integration_repo.get_sku_map_by_variant_id(variant_id)
            if mapping is None and sku:
                mapping = await self.integration_repo.get_sku_map_by_sku(sku)
            if mapping:
                if variant_id is not None:
                    variant_map[variant_id] = mapping.invitm_codigo
                if sku:
                    sku_map[sku] = mapping.invitm_codigo
                continue
            label = sku or item.get("name") or item.get("title") or "line_item"
            errors.append(f"Falta mapeo de producto Shopify '{label}' -> invitm_codigo.")
        return variant_map, sku_map, errors

    async def _resolve_line_item_branch_codes(
        self,
        order: dict[str, Any],
        variant_map: dict[int, int],
        sku_map: dict[str, int],
    ) -> dict[int, int]:
        get_inventory = getattr(self.integration_repo, "get_latest_inventory_with_stock", None)
        if get_inventory is None:
            return {}

        line_branch_codes: dict[int, int] = {}
        normalized_sku_map = {key.upper(): value for key, value in sku_map.items()}
        for index, item in enumerate(order.get("line_items") or [], start=1):
            item_code = mapped_line_item_code(item, variant_map, normalized_sku_map)
            if item_code is None:
                continue
            from app.application.normalization import positive_int as normal_pos_int
            quantity = normal_pos_int(item.get("quantity")) or 1
            snapshot = await get_inventory(item_code, quantity)
            branch_code = positive_int(getattr(snapshot, "admsuc_codigo", None))
            if branch_code is not None:
                line_branch_codes[index] = branch_code
        return line_branch_codes
