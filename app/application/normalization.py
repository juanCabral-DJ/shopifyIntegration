from typing import Any


def records(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        for key in (
            "data",
            "items",
            "item",
            "result",
            "results",
            "response",
            "value",
            "values",
            "records",
            "rows",
            "datos",
            "detalles",
        ):
            value = data.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
            if isinstance(value, dict):
                nested = records(value)
                if nested:
                    return nested
        list_values = [value for value in data.values() if isinstance(value, list)]
        if len(list_values) == 1:
            return [item for item in list_values[0] if isinstance(item, dict)]
        return [data] if looks_like_record(data) else []
    return []


def error_message(exc: Exception) -> str:
    message = str(exc).strip()
    return message or f"{type(exc).__name__}: {exc!r}"


def first_value(record: dict[str, Any] | None, *keys: str) -> Any:
    if not record:
        return None
    for key in keys:
        if key in record and record[key] not in (None, ""):
            return record[key]
    return None


def first_int(record: dict[str, Any] | None, *keys: str) -> int | None:
    value = first_value(record, *keys)
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def positive_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def clean_text(value: Any) -> str | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    return text or None


def product_sku(product: dict[str, Any], item_code: int) -> str:
    return str(first_value(product, "invitm_refer", "invitm_Refer", "sku", "referencia") or item_code).strip()


def product_title(product: dict[str, Any], fallback: str) -> str:
    return str(
        first_value(product, "invitm_nombre", "invitm_Nombre", "title", "nombre", "descripcion")
        or fallback
    ).strip()[:255]


def product_price(product: dict[str, Any]) -> Any:
    return first_value(product, "facpre_Contado", "facpre_contado", "precio", "price")


def shopify_product_payload(product: dict[str, Any]) -> dict[str, Any]:
    from app.application.transformers.se_to_shopify import shopify_product_payload as transformer

    return transformer(product)


def first_variant(product: dict[str, Any]) -> dict[str, Any]:
    variants = product.get("variants")
    if isinstance(variants, list) and variants and isinstance(variants[0], dict):
        return variants[0]
    return {}


def branch_name(branch: dict[str, Any], branch_code: int) -> str:
    return str(
        first_value(
            branch,
            "admsuc_nombre",
            "admsuc_Nombre",
            "nombre",
            "name",
            "descripcion",
            "description",
        )
        or f"Sucursal {branch_code}"
    ).strip()[:255]


def shopify_location_payload(branch: dict[str, Any], name: str) -> dict[str, Any]:
    address = {
        "address1": clean_text(first_value(branch, "admsuc_direccion", "admsuc_Direccion", "direccion", "address1", "address")),
        "address2": clean_text(first_value(branch, "address2", "direccion2")),
        "city": clean_text(first_value(branch, "admsuc_ciudad", "ciudad", "city")),
        "zip": clean_text(first_value(branch, "admsuc_zip", "zip", "postal_code", "codigo_postal")),
        "provinceCode": clean_text(first_value(branch, "provinceCode", "province_code", "estado_codigo")),
        "countryCode": shopify_country_code(first_value(branch, "countryCode", "country_code", "pais_codigo")),
    }
    return {
        "name": name,
        "address": {key: value for key, value in address.items() if value not in (None, "")},
        "fulfillsOnlineOrders": bool(
            first_value(branch, "fulfillsOnlineOrders", "fulfills_online_orders", "cumple_online") in (None, True, 1, "1", "A")
        ),
    }


def shopify_country_code(value: Any) -> str:
    country_code = str(value or "").strip().upper()
    return country_code if len(country_code) == 2 else "DO"


def stock_quantity(value: Any) -> int:
    try:
        return max(0, int(float(value)))
    except (TypeError, ValueError):
        return 0


def looks_like_record(record: dict[str, Any]) -> bool:
    for key in record:
        normalized = key.lower()
        if "_" in normalized or normalized.endswith(("codigo", "code", "id")):
            return True
    return False
