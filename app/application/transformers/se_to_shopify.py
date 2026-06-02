from typing import Any

from app.application.normalization import clean_text, first_int, first_value, product_price, product_sku, product_title


def shopify_product_payload(product: dict[str, Any]) -> dict[str, Any]:
    item_code = first_int(product, "invitm_codigo", "invitm_Codigo", "invitmCodigo", "codigo") or 0
    sku = product_sku(product, item_code)
    title = product_title(product, sku)
    price = product_price(product)
    family_name = clean_text(first_value(product, "invfam_nombre", "invfam_Nombre", "familia_nombre", "product_type"))
    brand_name = clean_text(first_value(product, "invmar_nombre", "invmar_Nombre", "marca_nombre", "vendor"))
    stock = first_value(product, "invcos_Exist", "invcos_exist", "se_stock", "stock", "existencia", "invitm_existencia")

    tags = [f"se-item:{item_code}"]
    if family_name:
        tags.append(family_name)
    if brand_name:
        tags.append(brand_name)

    variant: dict[str, Any] = {
        "sku": sku,
        "inventory_management": "shopify",
        "inventory_policy": "deny",
    }
    if price is not None:
        variant["price"] = str(price)
    stock_quantity = _stock_quantity(stock) if stock is not None else None
    if stock_quantity is not None:
        variant["inventory_quantity"] = stock_quantity

    payload: dict[str, Any] = {
        "title": title,
        "vendor": brand_name or "SE",
        "product_type": family_name,
        "tags": ", ".join(tags),
        "status": _product_status(product, stock_quantity),
        "variants": [variant],
    }
    return {key: value for key, value in payload.items() if value not in (None, "", [])}


def se_customer_to_shopify(customer: dict[str, Any]) -> dict[str, Any]:
    contact_name = str(first_value(customer, "cxccon_Nombre", "cxccon_nombre") or "").strip()
    legal_name = str(first_value(customer, "cxccte_Nombre", "cxccte_nombre", "nombre") or contact_name or "").strip()
    first_name, last_name = _split_name(contact_name or legal_name)
    customer_code = first_int(customer, "cxccte_Codigo", "cxccte_codigo", "cxccteCodigo", "codigo")
    rnc = first_value(customer, "cxccte_Rnc", "cxccte_rnc")
    phone = _normalize_phone(first_value(customer, "cxccte_telef1", "cxccte_Telef1", "telefono", "phone"))

    payload: dict[str, Any] = {
        "first_name": first_name,
        "last_name": last_name,
        "phone": phone,
        "note": f"SE cxccte_codigo={customer_code}; RNC={rnc or ''}".strip(),
        "tags": ", ".join(
            tag
            for tag in [
                "se-customer",
                f"cxccte:{customer_code}" if customer_code else "",
                f"rnc:{rnc}" if rnc else "",
            ]
            if tag
        ),
        "addresses": [_se_customer_address(customer, legal_name)],
        "metafields": [
            {
                "namespace": "se_data",
                "key": "cxccte_codigo",
                "value": str(customer_code),
                "type": "single_line_text_field",
            },
        ],
    }
    email = _se_customer_email(customer)
    if email:
        payload["email"] = email
    return {key: value for key, value in payload.items() if value not in (None, "", [])}


def shopify_customer_to_se(customer: dict[str, Any]) -> dict[str, Any]:
    address = customer.get("default_address") or {}
    name = " ".join(
        part for part in [customer.get("first_name"), customer.get("last_name")] if part
    ).strip() or customer.get("email") or str(customer.get("id") or "")
    return {
        "cxccte_codigo": first_int(customer, "cxccte_codigo", "cxccte_Codigo") or 0,
        "cxccte_nombre": name,
        "cxccte_email": first_value(customer, "email"),
        "cxccte_telef1": first_value(customer, "phone"),
        "cxcdir_nombre": first_value(address, "address1"),
        "cxcdir_direccion2": first_value(address, "address2"),
        "cxcdir_ciudad": first_value(address, "city"),
        "cxcdir_pais": first_value(address, "country", "country_name"),
        "shopify_customer_id": first_int(customer, "id"),
    }


def _se_customer_address(customer: dict[str, Any], legal_name: str) -> dict[str, Any]:
    first_name, last_name = _split_name(str(first_value(customer, "cxccon_Nombre", "cxccon_nombre") or legal_name))
    address = {
        "first_name": first_name,
        "last_name": last_name,
        "company": legal_name,
        "address1": first_value(customer, "cxcdir_Nombre", "cxcdir_nombre", "direccion", "address1"),
        "phone": _normalize_phone(first_value(customer, "cxccte_telef1", "cxccte_Telef1", "telefono", "phone")),
        "country": "Dominican Republic",
        "country_code": "DO",
        "default": True,
    }
    return {key: value for key, value in address.items() if value not in (None, "")}


def _se_customer_email(customer: dict[str, Any]) -> str | None:
    value = first_value(customer, "email", "cxccte_Email", "cxccte_email")
    if value and "@" in str(value):
        return str(value).strip()
    refer = first_value(customer, "cxccte_Refer", "cxccte_refer")
    if refer and "@" in str(refer):
        return str(refer).strip()
    return None


def _split_name(value: str) -> tuple[str, str]:
    parts = [part for part in value.strip().split() if part]
    if not parts:
        return "SE", "Customer"
    if len(parts) == 1:
        return parts[0][:255], "Customer"
    return parts[0][:255], " ".join(parts[1:])[:255]


def _normalize_phone(value: Any) -> str | None:
    if value in (None, ""):
        return None
    digits = "".join(character for character in str(value) if character.isdigit())
    if len(digits) == 10 and digits[0] in {"8", "9"}:
        return f"+1{digits}"
    if len(digits) == 11 and digits.startswith("1"):
        return f"+{digits}"
    return f"+{digits}" if digits else None


def _stock_quantity(value: Any) -> int:
    try:
        return max(0, int(float(value)))
    except (TypeError, ValueError):
        return 0


def _product_status(product: dict[str, Any], stock_quantity: int | None) -> str:
    if stock_quantity is not None and stock_quantity <= 0:
        return "unlisted"
    if first_value(product, "admsts_codigo", "admsts_Codigo", "active", "activo") in (None, True, 1, "1", "A"):
        return "active"
    return "draft"
