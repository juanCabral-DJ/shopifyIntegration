from app.application.services import middleware_service
from app.application.services.middleware_service import _invoice_rows, _invoice_visit_rows, _records, _se_customer_to_shopify
from app.application.transformers.shopify_to_se import MFACTRX_FIELDS, order_to_mfactrx_rows


def test_records_accepts_nested_se_wrappers() -> None:
    payload = {"status": "success", "response": {"datos": [{"cxccte_Codigo": 10}, {"cxccte_Codigo": 11}]}}

    assert _records(payload) == [{"cxccte_Codigo": 10}, {"cxccte_Codigo": 11}]


def test_records_ignores_metadata_only_response() -> None:
    assert _records({"status": "success", "received": 0, "mapped": 0}) == []


def test_invoice_visit_rows_accepts_single_row_and_applies_company_code(monkeypatch) -> None:
    monkeypatch.setattr(middleware_service.settings, "se_company_code", 23)

    rows = _invoice_visit_rows(
        {
            "admcia_codigo": 0,
            "facvis_master": 0,
            "facvdr_codigo": 0,
            "cxccte_codigo": 0,
            "admvis_fecha": "2026-05-20",
            "admvis_comentario": "Factura Shopify",
            "factrx_numero": 0,
        }
    )

    assert len(rows) == 1
    assert rows[0]["admcia_codigo"] == 23
    assert rows[0]["admvis_comentario"] == "Factura Shopify"


def test_invoice_rows_accepts_mfactrx_wrapper_and_applies_company_code(monkeypatch) -> None:
    monkeypatch.setattr(middleware_service.settings, "se_company_code", 23)

    rows = _invoice_rows(
        {
            "mfactrx_rows": [
                {
                    "admcia_codigo": 0,
                    "admsuc_codigo": 1,
                    "factrx_numero": 0,
                    "factrx_tipo": 1,
                    "factrx_fecha": "2026-05-20",
                    "cxccte_codigo": 10,
                    "factrx_linea": 1,
                    "factrx_cant": 1,
                    "invitm_codigo": 20,
                    "factrx_netod": 118,
                }
            ]
        }
    )

    assert len(rows) == 1
    assert rows[0]["admcia_codigo"] == 23
    assert rows[0]["factrx_linea"] == 1


def test_order_to_mfactrx_rows_uses_intermediate_maps_and_complete_detail_fields() -> None:
    order = {
        "id": 123,
        "name": "#1001",
        "created_at": "2026-05-12T17:15:24-04:00",
        "currency": "DOP",
        "current_subtotal_price": "100.00",
        "current_total_discounts": "0.00",
        "current_total_tax": "18.00",
        "current_total_price": "118.00",
        "customer": {"first_name": "Juan", "last_name": "Cabral", "phone": "8090000000"},
        "line_items": [
            {
                "variant_id": 52984449925399,
                "sku": "FLOW-URL-20260430-122258",
                "title": "Producto",
                "quantity": 1,
                "price": "100.00",
                "total_discount": "0.00",
                "tax_lines": [{"price": "18.00", "rate": 0.18}],
            }
        ],
    }

    rows = order_to_mfactrx_rows(
        order,
        company_code=1,
        branch_code=2,
        customer_code=3,
        vendor_code=4,
        receipt_type_code=5,
        price_list_code=6,
        variant_to_item_code={52984449925399: 700},
    )

    assert rows[0]["cxccte_codigo"] == 3
    assert rows[0]["invitm_codigo"] == 700
    assert rows[0]["facvdr_codigo"] == 4
    assert rows[0]["admtco_codigo"] == 5
    assert rows[0]["facpre_codigo"] == 6
    assert rows[0]["factrx_movil_id"] == ""
    assert rows[0]["admusr_codigo"] == "ADMIN"
    assert set(rows[0]) == MFACTRX_FIELDS
    assert all(value is not None for value in rows[0].values())
    assert rows[0]["factrx_totald"] == 100.0
    assert rows[0]["factrx_impd"] == 18.0
    assert rows[0]["factrx_netod"] == 118.0


def test_order_to_mfactrx_rows_sends_missing_invoice_codes_as_zeroes() -> None:
    order = {
        "id": 123,
        "name": "#1001",
        "created_at": "2026-05-12T17:15:24-04:00",
        "currency": "DOP",
        "current_total_price": "0.00",
        "line_items": [],
    }

    rows = order_to_mfactrx_rows(order, company_code=101)

    assert rows[0]["admsuc_codigo"] == 0
    assert rows[0]["cxccte_codigo"] == 0
    assert rows[0]["facvdr_codigo"] == 0
    assert rows[0]["admtco_codigo"] == 0
    assert rows[0]["facpre_codigo"] == 0
    assert set(rows[0]) == MFACTRX_FIELDS


def test_se_customer_to_shopify_payload_keeps_se_identity() -> None:
    customer = {
        "cxccte_Codigo": 5,
        "cxccte_Nombre": "INMOVILIARA E INVERSIONES",
        "cxccte_Rnc": "130910405",
        "cxcdir_Nombre": "JUAN CABALLERO #50, PROVINCIA PERAVIA",
        "cxccon_Nombre": "JUAN RODRIGUEZ A.",
        "cxccte_telef1": "809-380-2323",
    }

    payload = _se_customer_to_shopify(customer)

    assert payload["phone"] == "+18093802323"
    assert payload["addresses"][0]["company"] == "INMOVILIARA E INVERSIONES"
    assert payload["metafields"][0]["value"] == "5"
    assert "cxccte:5" in payload["tags"]
