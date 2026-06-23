from types import SimpleNamespace

import pytest

from app.application.services.middleware_service import MiddlewareService
from app.application.transformers.se_to_shopify import (
    se_customer_to_shopify,
    shopify_customer_to_se,
    shopify_product_payload,
)


class FakeRunRepo:
    def __init__(self):
        self.finished = None

    async def start_sync_run(self, sync_type):
        return {"sync_type": sync_type}

    async def finish_sync_run(self, run, status, stats=None, error_message=None):
        self.finished = {"status": status, "stats": stats, "error_message": error_message}
        return self.finished


def test_se_product_payload_handles_casing_stock_and_nullable_fields():
    payload = shopify_product_payload(
        {
            "invitm_Codigo": "42",
            "invitm_nombre": "Cafe",
            "invfam_nombre": "Bebidas",
            "facpre_Contado": "12.50",
            "invcos_Exist": "7",
            "admsts_codigo": "A",
        }
    )

    assert payload["title"] == "Cafe"
    assert payload["product_type"] == "Bebidas"
    assert payload["status"] == "active"
    assert payload["variants"][0]["sku"] == "42"
    assert payload["variants"][0]["price"] == "12.50"
    assert payload["variants"][0]["inventory_quantity"] == 7


def test_se_product_payload_marks_zero_stock_as_unlisted():
    payload = shopify_product_payload(
        {
            "invitm_Codigo": "43",
            "invitm_nombre": "Cafe sin stock",
            "facpre_Contado": "12.50",
            "invcos_Exist": "0",
            "admsts_codigo": "A",
        }
    )

    assert payload["status"] == "unlisted"
    assert payload["variants"][0]["inventory_quantity"] == 0


def test_se_product_payload_omits_negative_price():
    payload = shopify_product_payload(
        {
            "invitm_Codigo": "44",
            "invitm_nombre": "Cafe ajuste",
            "facpre_Contado": "-1.00",
            "admsts_codigo": "A",
        }
    )

    assert "price" not in payload["variants"][0]


def test_se_product_payload_omits_nan_price():
    payload = shopify_product_payload(
        {
            "invitm_Codigo": "45",
            "invitm_nombre": "Cafe precio raro",
            "facpre_Contado": "NaN",
            "admsts_codigo": "A",
        }
    )

    assert "price" not in payload["variants"][0]


def test_se_customer_transformers_map_both_directions():
    shopify_payload = se_customer_to_shopify(
        {
            "cxccte_Codigo": "9",
            "cxccte_Nombre": "Ada Lovelace",
            "cxccte_Email": "ada@example.com",
            "cxccte_Telef1": "8095551111",
            "cxcdir_Nombre": "Main St",
        }
    )
    se_payload = shopify_customer_to_se(
        {
            "id": 77,
            "first_name": "Ada",
            "last_name": "Lovelace",
            "email": "ada@example.com",
            "phone": "+18095551111",
            "default_address": {"address1": "Main St", "city": "Santo Domingo"},
        }
    )

    assert shopify_payload["email"] == "ada@example.com"
    assert shopify_payload["phone"] == "+18095551111"
    assert se_payload["shopify_customer_id"] == 77
    assert se_payload["cxccte_nombre"] == "Ada Lovelace"


class FakeOutboxRepo:
    def __init__(self):
        self.event = SimpleNamespace(
            id="evt-1",
            target="se",
            operation="Factura.Insertar",
            payload={"shopify_order_id": 100, "mfactrx_rows": [{"factrx_movil_id": "100"}]},
            status="pending",
            retry_count=0,
            next_retry_at=None,
        )
        self.invoice_maps = []
        self.order_status = None
        self.outbox_events = []

    async def list_due_outbox(self, limit=50):
        return [self.event]

    async def mark_outbox_processing(self, event):
        event.status = "processing"
        return event

    async def mark_outbox_done(self, event, response=None):
        event.status = "done"
        event.response = response
        return event

    async def mark_outbox_failed(self, event, error, max_retries=5):
        event.status = "pending"
        event.retry_count += 1
        event.error_message = error
        return event

    async def get_order_map(self, shopify_order_id):
        return SimpleNamespace(shopify_order_name="#100", factrx_movil_id=str(shopify_order_id), factrx_numero=None)

    async def upsert_order_map(self, **kwargs):
        self.order_status = kwargs["status"]
        return SimpleNamespace(**kwargs)

    async def upsert_invoice_map(self, **kwargs):
        self.invoice_maps.append(kwargs)
        return SimpleNamespace(**kwargs)

    async def add_outbox_event(self, target, operation, payload, status="pending"):
        event = {
            "target": target,
            "operation": operation,
            "payload": payload,
            "status": status,
        }
        self.outbox_events.append(event)
        return event


class FakeInvoiceSE:
    last_status_code = 200

    async def insert_invoice(self, payload):
        return {"factrx_numero": "F-100", "ncf": "B0100001"}


class FakeFulfillmentShopify:
    def __init__(self):
        self.fulfilled_orders = []
        self.paid_orders = []

    async def update_order_financial_status(self, shopify_order_id, financial_status):
        self.paid_orders.append((shopify_order_id, financial_status))
        return {"order": {"id": shopify_order_id, "financial_status": financial_status}}

    async def fulfill_order(self, shopify_order_id):
        self.fulfilled_orders.append(shopify_order_id)
        return {"status": "fulfilled", "fulfillment": {"id": 900}}


@pytest.mark.asyncio
async def test_process_pending_outbox_inserts_invoice_and_marks_done():
    repo = FakeOutboxRepo()
    shopify = FakeFulfillmentShopify()
    service = MiddlewareService(integration_repo=repo, se_client=FakeInvoiceSE(), shopify_client=shopify)

    result = await service.process_pending_outbox()

    assert result == {"status": "success", "processed": 1, "done": 1, "failed": 0}
    assert repo.event.status == "done"
    assert repo.event.response["invoice"]["factrx_numero"] == "F-100"
    assert repo.event.response["shopify"]["status"] == "paid_and_fulfilled"
    assert repo.event.response["shopify"]["fulfillment"]["status"] == "fulfilled"
    assert shopify.paid_orders == [(100, "paid")]
    assert shopify.fulfilled_orders == [100]
    assert repo.order_status == "invoiced"
    assert repo.invoice_maps[0]["factrx_numero"] == "F-100"


@pytest.mark.asyncio
async def test_send_invoice_marks_shopify_paid_and_fulfilled_after_se_success():
    repo = FakeOutboxRepo()
    shopify = FakeFulfillmentShopify()
    service = MiddlewareService(integration_repo=repo, se_client=FakeInvoiceSE(), shopify_client=shopify)

    result = await service.send_invoice({"shopify_order_id": 100, "mfactrx_rows": [{"factrx_movil_id": "100"}]})

    assert result["status"] == "success"
    assert result["response"]["shopify"]["status"] == "paid_and_fulfilled"
    assert shopify.paid_orders == [(100, "paid")]
    assert shopify.fulfilled_orders == [100]
    assert repo.outbox_events[0]["status"] == "done"


@pytest.mark.asyncio
async def test_process_pending_outbox_does_not_update_shopify_when_se_status_is_not_200():
    class CreatedInvoiceSE(FakeInvoiceSE):
        last_status_code = 201

    repo = FakeOutboxRepo()
    shopify = FakeFulfillmentShopify()
    service = MiddlewareService(integration_repo=repo, se_client=CreatedInvoiceSE(), shopify_client=shopify)

    result = await service.process_pending_outbox()

    assert result == {"status": "success", "processed": 1, "done": 1, "failed": 0}
    assert repo.event.response == {"factrx_numero": "F-100", "ncf": "B0100001"}
    assert shopify.paid_orders == []
    assert shopify.fulfilled_orders == []


@pytest.mark.asyncio
async def test_process_pending_outbox_marks_done_when_shopify_update_fails_after_se_200():
    class FailingShopify(FakeFulfillmentShopify):
        async def fulfill_order(self, shopify_order_id):
            raise RuntimeError("missing fulfillment scope")

    repo = FakeOutboxRepo()
    shopify = FailingShopify()
    service = MiddlewareService(integration_repo=repo, se_client=FakeInvoiceSE(), shopify_client=shopify)

    result = await service.process_pending_outbox()

    assert result == {"status": "success", "processed": 1, "done": 1, "failed": 0}
    assert repo.event.status == "done"
    assert repo.event.response["shopify"]["status"] == "failed"
    assert "missing fulfillment scope" in repo.event.response["shopify"]["error"]


class FakeInvoiceBuildRepo:
    def __init__(self):
        self.branch_maps_by_name = {
            "santiago": SimpleNamespace(admsuc_codigo=2, name="Santiago"),
        }

    async def get_param_cache(self, key):
        if key == "se_defaults":
            return SimpleNamespace(
                value={
                    "admsuc_codigo": 1,
                    "cxccte_codigo": 10,
                    "facvdr_codigo": 20,
                    "admtco_codigo": 30,
                    "facpre_codigo": 40,
                }
            )
        return None

    async def get_customer_map_by_shopify_id(self, shopify_customer_id):
        return None

    async def get_customer_map_by_email(self, email):
        return None

    async def get_customer_map_by_phone(self, phone):
        return None

    async def get_branch_map_by_name(self, name):
        return self.branch_maps_by_name.get(name.strip().casefold())

    async def get_branch_map_by_shopify_location_id(self, shopify_location_id):
        return SimpleNamespace(admsuc_codigo=99, name="Location branch")

    async def get_latest_inventory_with_stock(self, invitm_codigo, min_stock=1):
        return None


@pytest.mark.asyncio
async def test_order_invoice_payload_uses_branch_name_from_shopify_tag():
    service = MiddlewareService(integration_repo=FakeInvoiceBuildRepo())

    payload, errors = await service._build_order_invoice_payload(
        {
            "id": 200,
            "name": "#200",
            "tags": "VIP, Santiago",
            "location_id": 111,
            "current_total_price": "0.00",
            "line_items": [],
        }
    )

    assert errors == []
    assert payload["mapping_context"]["branch_code"] == 2
    assert payload["mfactrx_rows"][0]["admsuc_codigo"] == 2


class FakeInvoiceInventoryRepo(FakeInvoiceBuildRepo):
    async def get_sku_map_by_variant_id(self, shopify_variant_id):
        if shopify_variant_id == 111:
            return SimpleNamespace(invitm_codigo=700)
        return None

    async def get_sku_map_by_sku(self, sku):
        return None

    async def get_latest_inventory_with_stock(self, invitm_codigo, min_stock=1):
        if invitm_codigo == 700 and min_stock == 2.0:
            return SimpleNamespace(admsuc_codigo=5, se_stock=4)
        return None


@pytest.mark.asyncio
async def test_order_invoice_payload_uses_branch_with_product_stock():
    service = MiddlewareService(integration_repo=FakeInvoiceInventoryRepo())

    payload, errors = await service._build_order_invoice_payload(
        {
            "id": 201,
            "name": "#201",
            "location_id": 111,
            "current_total_price": "20.00",
            "line_items": [
                {
                    "variant_id": 111,
                    "sku": "ABC",
                    "title": "Producto",
                    "quantity": 2,
                    "price": "10.00",
                }
            ],
        }
    )

    assert errors == []
    assert payload["mapping_context"]["branch_code"] == 99
    assert payload["mapping_context"]["line_branch_codes"] == {1: 5}
    assert payload["mfactrx_rows"][0]["admsuc_codigo"] == 5


class FakeImageRepo(FakeRunRepo):
    def __init__(self):
        super().__init__()
        self.image_maps = {}
        self.upserted_image_maps = []

    async def get_sku_maps_by_item_codes(self, invitm_codigos):
        mappings = {
            1: SimpleNamespace(invitm_codigo=1, shopify_product_id=10),
            2: SimpleNamespace(invitm_codigo=2, shopify_product_id=None),
        }
        return {item_code: mappings[item_code] for item_code in invitm_codigos if item_code in mappings}

    async def get_product_image_map(self, external_image_id, invitm_codigo=None, image_hash=None):
        return self.image_maps.get(external_image_id)

    async def upsert_product_image_map(self, **kwargs):
        mapping = SimpleNamespace(**kwargs)
        self.image_maps[kwargs["external_image_id"]] = mapping
        self.upserted_image_maps.append(kwargs)
        return mapping


class FakeImageSE:
    async def list_images(self):
        return [{"admimg_tabla": "minvitm", "admimg_master": 1, "admimg_linea": 1, "base64": "abc123", "filename": "one.jpg"}]


class FakeImageShopify:
    def __init__(self):
        self.uploads = []

    async def upload_product_image(self, product_id, base64_data, filename):
        self.uploads.append((product_id, base64_data, filename))
        return {"id": 99}


@pytest.mark.asyncio
async def test_sync_images_uploads_mapped_product_images():
    repo = FakeImageRepo()
    shopify = FakeImageShopify()
    service = MiddlewareService(integration_repo=repo, se_client=FakeImageSE(), shopify_client=shopify)

    result = await service.sync_images()

    assert result["uploaded"] == 1
    assert result["skipped"] == 0
    assert result["duplicate_skipped"] == 0
    assert shopify.uploads == [(10, "abc123", "one.jpg")]
    assert repo.upserted_image_maps[0]["external_image_id"] == "minvitm:1:1"
    assert repo.upserted_image_maps[0]["shopify_image_id"] == 99


@pytest.mark.asyncio
async def test_sync_images_skips_previously_uploaded_product_images():
    repo = FakeImageRepo()
    repo.image_maps["minvitm:1:1"] = SimpleNamespace(
        external_image_id="minvitm:1:1",
        invitm_codigo=1,
        image_hash="6ca13d52ca70c883e0f0bb101e425a89e8624de51db2d2392593af6a84118090",
        shopify_image_id=99,
    )
    shopify = FakeImageShopify()
    service = MiddlewareService(integration_repo=repo, se_client=FakeImageSE(), shopify_client=shopify)

    result = await service.sync_images()

    assert result["uploaded"] == 0
    assert result["skipped"] == 1
    assert result["duplicate_skipped"] == 1
    assert shopify.uploads == []


class FakePriceRepo(FakeRunRepo):
    def __init__(self):
        super().__init__()
        self.sku_maps = {
            1: SimpleNamespace(
                invitm_codigo=1,
                sku="SKU-1",
                shopify_product_id=100,
                shopify_variant_id=200,
                last_price="10.00",
                active=True,
            ),
            2: SimpleNamespace(
                invitm_codigo=2,
                sku="SKU-2",
                shopify_product_id=101,
                shopify_variant_id=201,
                last_price="20.00",
                active=True,
            ),
        }
        self.upserts = []
        self.outbox_events = []
        self.progress_updates = []
        self.bulk_mapping_calls = 0

    async def get_sku_map_by_item_code(self, invitm_codigo):
        return self.sku_maps.get(invitm_codigo)

    async def get_sku_maps_by_item_codes(self, invitm_codigos):
        self.bulk_mapping_calls += 1
        return {
            item_code: self.sku_maps[item_code]
            for item_code in invitm_codigos
            if item_code in self.sku_maps
        }

    async def update_sync_run_stats(self, run, stats):
        self.progress_updates.append({"run": run, "stats": stats})
        return SimpleNamespace(**stats)

    async def upsert_sku_map(self, **kwargs):
        self.upserts.append(kwargs)
        mapping = SimpleNamespace(**kwargs)
        self.sku_maps[kwargs["invitm_codigo"]] = mapping
        return mapping

    async def add_outbox_event(self, target, operation, payload, status="pending"):
        event = {"target": target, "operation": operation, "payload": payload, "status": status}
        self.outbox_events.append(event)
        return event


class FakePriceSE:
    async def list_prices(self):
        return [
            {"invitm_Codigo": 1, "facpre_Contado": "9.00", "facpre_Principal": 0},
            {"invitm_Codigo": 1, "facpre_Contado": "12.50", "facpre_Principal": 1},
            {"invitm_Codigo": 2, "facpre_Contado": "20.00", "facpre_Principal": 1},
        ]


class FakeNegativePriceSE:
    async def list_prices(self):
        return [
            {"invitm_Codigo": 1, "facpre_Contado": "-3.00", "facpre_Principal": 1},
            {"invitm_Codigo": 2, "facpre_Contado": "20.00", "facpre_Principal": 1},
        ]


class FakeNanPriceSE:
    async def list_prices(self):
        return [
            {"invitm_Codigo": 1, "facpre_Contado": "NaN", "facpre_Principal": 1},
            {"invitm_Codigo": 2, "facpre_Contado": "20.00", "facpre_Principal": 1},
        ]


class FakePriceShopify:
    def __init__(self):
        self.updates = []

    async def update_product(self, product_id, product):
        self.updates.append((product_id, product))
        return {"id": product_id, **product}


@pytest.mark.asyncio
async def test_sync_prices_uses_principal_price_and_updates_shopify_variant():
    repo = FakePriceRepo()
    shopify = FakePriceShopify()
    service = MiddlewareService(integration_repo=repo, se_client=FakePriceSE(), shopify_client=shopify)

    result = await service.sync_prices()

    assert result == {
        "status": "success",
        "received": 3,
        "mapped": 1,
        "shopify_updated": 1,
        "shopify_skipped": 1,
        "skipped": 0,
    }
    assert shopify.updates == [(100, {"variants": [{"id": 200, "price": "12.50"}]})]
    assert repo.upserts[0]["last_price"] == "12.50"
    assert len(repo.upserts) == 1
    assert repo.bulk_mapping_calls == 1
    assert repo.outbox_events[0]["status"] == "done"


@pytest.mark.asyncio
async def test_sync_prices_skips_negative_shopify_price_without_failing_run():
    repo = FakePriceRepo()
    shopify = FakePriceShopify()
    service = MiddlewareService(integration_repo=repo, se_client=FakeNegativePriceSE(), shopify_client=shopify)

    result = await service.sync_prices()

    assert result == {
        "status": "success",
        "received": 2,
        "mapped": 1,
        "shopify_updated": 0,
        "shopify_skipped": 2,
        "skipped": 0,
    }
    assert shopify.updates == []
    assert repo.upserts[0]["last_price"] == "-3.00"
    assert repo.finished["status"] == "success"


@pytest.mark.asyncio
async def test_sync_prices_skips_nan_shopify_price_without_failing_run():
    repo = FakePriceRepo()
    shopify = FakePriceShopify()
    service = MiddlewareService(integration_repo=repo, se_client=FakeNanPriceSE(), shopify_client=shopify)

    result = await service.sync_prices()

    assert result == {
        "status": "success",
        "received": 2,
        "mapped": 1,
        "shopify_updated": 0,
        "shopify_skipped": 2,
        "skipped": 0,
    }
    assert shopify.updates == []
    assert repo.upserts[0]["last_price"] == "NaN"
    assert repo.finished["status"] == "success"


class FakePriceProgressRepo(FakePriceRepo):
    def __init__(self):
        super().__init__()
        self.session = FakeCommitSession()
        self.sku_maps = {
            item_code: SimpleNamespace(
                invitm_codigo=item_code,
                sku=f"SKU-{item_code}",
                shopify_product_id=1000 + item_code,
                shopify_variant_id=2000 + item_code,
                last_price=f"{item_code}.00",
                active=True,
            )
            for item_code in range(1, 206)
        }


class FakePriceProgressSE:
    async def list_prices(self):
        return [
            {"invitm_Codigo": item_code, "facpre_Contado": f"{item_code + 1}.00", "facpre_Principal": 1}
            for item_code in range(1, 206)
        ]


@pytest.mark.asyncio
async def test_sync_prices_updates_progress_every_100_processed_prices():
    repo = FakePriceProgressRepo()
    service = MiddlewareService(integration_repo=repo, se_client=FakePriceProgressSE(), shopify_client=FakePriceShopify())

    result = await service.sync_prices()

    assert result["status"] == "success"
    assert result["mapped"] == 205
    assert result["shopify_updated"] == 205
    assert [update["stats"]["processed"] for update in repo.progress_updates] == [100, 200]
    assert repo.session.commits == 2


class FakeCommitSession:
    def __init__(self):
        self.commits = 0

    async def commit(self):
        self.commits += 1


class FakeInventoryRepo(FakeRunRepo):
    def __init__(self):
        super().__init__()
        self.session = FakeCommitSession()
        self.progress_updates = []
        self.snapshots = []

    async def update_sync_run_stats(self, run, stats):
        self.progress_updates.append({"run": run, "stats": stats})
        return SimpleNamespace(**stats)

    async def get_first_branch_map_with_location(self):
        return SimpleNamespace(shopify_location_id=500)

    async def get_sku_map_by_item_code(self, invitm_codigo):
        return SimpleNamespace(
            invitm_codigo=invitm_codigo,
            sku=str(invitm_codigo),
            shopify_inventory_item_id=9000 + invitm_codigo,
        )

    async def add_inventory_snapshot(self, **kwargs):
        self.snapshots.append(kwargs)
        return SimpleNamespace(**kwargs)


class FakeInventorySE:
    async def list_products(self, payload=None):
        assert payload == 101
        return [
            {
                "invitm_codigo": item_code,
                "invitm_refer": str(item_code),
                "invitm_nombre": f"Producto {item_code}",
                "invcos_Exist": item_code,
                "admsuc_codigo": 101,
            }
            for item_code in range(1, 206)
        ]


class FakeInventoryShopify:
    def __init__(self):
        self.inventory_updates = []

    async def set_inventory_level(self, inventory_item_id, location_id, available):
        self.inventory_updates.append((inventory_item_id, location_id, available))
        return {"inventory_item_id": inventory_item_id, "location_id": location_id, "available": available}


@pytest.mark.asyncio
async def test_sync_inventory_updates_progress_every_100_records():
    repo = FakeInventoryRepo()
    run = {"sync_type": "inventory"}
    service = MiddlewareService(
        integration_repo=repo,
        se_client=FakeInventorySE(),
        shopify_client=FakeInventoryShopify(),
    )

    result = await service.sync_inventory(101, run=run)

    assert result["status"] == "success"
    assert result["products_received"] == 205
    assert len(repo.snapshots) == 205
    assert [update["stats"]["processed"] for update in repo.progress_updates] == [100, 200]
    assert repo.session.commits == 2
    assert repo.finished["status"] == "success"


class FakePaymentRepo(FakeRunRepo):
    def __init__(self):
        super().__init__()
        self.receipts = []
        self.status = None

    async def get_order_map(self, shopify_order_id):
        return SimpleNamespace(shopify_order_name="#200", factrx_movil_id=str(shopify_order_id), factrx_numero="F-200", status="invoiced")

    async def upsert_receipt_map(self, **kwargs):
        self.receipts.append(kwargs)
        return SimpleNamespace(**kwargs)

    async def upsert_order_map(self, **kwargs):
        self.status = kwargs["status"]
        return SimpleNamespace(**kwargs)


class FakePaymentSE:
    async def get_invoices(self, payload):
        return [{"factrx_movil_id": "200", "eftrcb_numero": 55, "factrx_total": "20.00"}]


class FakePaymentShopify:
    def __init__(self):
        self.updates = []

    async def update_order_financial_status(self, shopify_order_id, financial_status):
        self.updates.append((shopify_order_id, financial_status))
        return {"order": {"id": shopify_order_id, "financial_status": financial_status}}


@pytest.mark.asyncio
async def test_payment_polling_marks_shopify_order_paid_and_saves_receipt():
    repo = FakePaymentRepo()
    shopify = FakePaymentShopify()
    service = MiddlewareService(integration_repo=repo, se_client=FakePaymentSE(), shopify_client=shopify)

    result = await service.payment_polling()

    assert result["paid"] == 1
    assert shopify.updates == [(200, "paid")]
    assert repo.receipts[0]["eftrcb_numero"] == 55
    assert repo.status == "paid"


class FakeRetryRepo:
    async def reset_outbox_for_retry(self, shopify_order_id, operations):
        assert shopify_order_id == 300
        assert "Factura.Insertar" in operations
        return SimpleNamespace(
            id="evt-2",
            target="se",
            operation="Factura.Insertar",
            status="pending",
            retry_count=0,
            next_retry_at=None,
            payload={"shopify_order_id": 300},
        )


@pytest.mark.asyncio
async def test_retry_outbox_event_resets_failed_event():
    service = MiddlewareService(integration_repo=FakeRetryRepo())

    result = await service.retry_order_invoice(300)

    assert result["status"] == "pending"
    assert result["operation"] == "Factura.Insertar"
