from decimal import Decimal
from typing import Any


MFACTRX_FIELDS = {
    "admcia_codigo",
    "admsuc_codigo",
    "factrx_numero",
    "factrx_tipo",
    "factrx_fecha",
    "factrx_fechaped",
    "factrx_refer",
    "admmon_codigo",
    "admmon_tasa",
    "cxccte_codigo",
    "cxccte_nombre",
    "cxcdir_seq",
    "cxcdir_nombre",
    "cxccon_seq",
    "cxccon_nombre",
    "factrx_plazo",
    "facpre_codigo",
    "factrx_total",
    "factrx_pdescgral",
    "factrx_descgral",
    "factrx_pcargogral",
    "factrx_cargogral",
    "factrx_pdesc",
    "factrx_totdesc",
    "factrx_pcargos",
    "factrx_totcargos",
    "factrx_valor",
    "factrx_totimp",
    "factrx_neto",
    "admtco_codigo",
    "cxccte_rnc",
    "facvdr_codigo",
    "cxccpg_codigo",
    "cxccpg_cantidad",
    "cxccte_telef1",
    "admusr_codigo",
    "admncf_serial",
    "factrx_movil_id",
    "factrx_modo",
    "factrx_linea",
    "factrx_cant",
    "invitm_codigo",
    "invitm_nombre",
    "admuni_codigo",
    "factrx_precio",
    "factrx_totald",
    "factrx_pdescd",
    "factrx_descd",
    "factrx_pdescgrald",
    "factrx_descgrald",
    "factrx_pcargod",
    "factrx_cargod",
    "factrx_pcargograld",
    "factrx_cargograld",
    "factrx_valord",
    "factrx_pimpd",
    "factrx_impd",
    "factrx_netod",
    "factrx_preciobr",
    "factrx_oferta",
    "invcla_codigo",
}


def _money(value: Any) -> float:
    if value in (None, ""):
        return 0.0
    return float(Decimal(str(value)))


def _text(value: Any) -> str:
    if value in (None, ""):
        return ""
    return str(value)


def _code_or_blank(value: Any) -> int | str:
    if value in (None, ""):
        return 0
    return value


def _discount_percentage(order: dict[str, Any]) -> float:
    discounts = order.get("discount_codes") or []
    if not discounts:
        return 0.0
    try:
        return _money(discounts[0].get("percentage"))
    except (AttributeError, ValueError):
        return 0.0


def order_to_mfactrx_rows(
    order: dict[str, Any],
    *,
    company_code: int,
    branch_code: int | str | None = None,
    customer_code: int | str | None = None,
    vendor_code: int | str | None = None,
    receipt_type_code: int | str | None = None,
    price_list_code: int | str | None = None,
    ncf_serial: str | None = None,
    variant_to_item_code: dict[int, int] | None = None,
    sku_to_item_code: dict[str, int] | None = None,
    line_item_branch_codes: dict[int, int] | None = None,
) -> list[dict[str, Any]]:
    variant_map = variant_to_item_code or {}
    sku_map = {key.upper(): value for key, value in (sku_to_item_code or {}).items()}
    line_branch_map = line_item_branch_codes or {}
    customer = order.get("customer") or {}
    full_name = " ".join(
        part for part in [customer.get("first_name"), customer.get("last_name")] if part
    ) or customer.get("email") or order.get("email") or order.get("contact_email")
    subtotal = _order_money(order, "current_subtotal_price", "subtotal_price")
    total = _order_money(order, "current_total_price", "total_price")
    tax = _order_money(order, "current_total_tax", "total_tax")
    discount = _order_money(order, "current_total_discounts", "total_discounts")

    base = {
        "admcia_codigo": company_code,
        "admsuc_codigo": _code_or_blank(branch_code),
        "factrx_numero": 0,
        "factrx_tipo": 1,
        "factrx_fecha": _text(order.get("created_at")),
        "factrx_fechaped": _text(order.get("created_at")),
        "factrx_refer": _text(order.get("name")),
        "admmon_codigo": _text(order.get("currency") or order.get("currency_code") or "USD"),
        "admmon_tasa": 1,
        "cxccte_codigo": _code_or_blank(customer_code),
        "cxccte_nombre": _text(full_name),
        "cxcdir_seq": 0,
        "cxcdir_nombre": _shipping_address(order),
        "cxccon_seq": 0,
        "cxccon_nombre": _text(full_name),
        "factrx_plazo": 0,
        "facpre_codigo": _code_or_blank(price_list_code),
        "factrx_total": total,
        "factrx_pdescgral": _discount_percentage(order),
        "factrx_descgral": discount,
        "factrx_pcargogral": 0,
        "factrx_cargogral": 0,
        "factrx_pdesc": 0,
        "factrx_totdesc": discount,
        "factrx_pcargos": 0,
        "factrx_totcargos": 0,
        "factrx_valor": subtotal,
        "factrx_totimp": tax,
        "factrx_neto": total,
        "admtco_codigo": _code_or_blank(receipt_type_code),
        "cxccte_rnc": _text(customer.get("tax_exemptions", [""])[0] if customer.get("tax_exemptions") else ""),
        "facvdr_codigo": _code_or_blank(vendor_code),
        "cxccpg_codigo": 0,
        "cxccpg_cantidad": 0,
        "cxccte_telef1": _text(customer.get("phone") or order.get("phone")),
        "admusr_codigo": "ADMIN",
        "admncf_serial": _text(ncf_serial),
        "factrx_movil_id": "",
        "factrx_modo": 1,
    }

    rows: list[dict[str, Any]] = []
    for index, item in enumerate(order.get("line_items") or [], start=1):
        qty = _money(item.get("quantity"))
        price = _money(item.get("price"))
        line_total = qty * price
        line_discount = _money(item.get("total_discount"))
        line_tax = _line_tax(item)
        line_value = max(line_total - line_discount, 0)
        item_code = _line_item_code(item, variant_map, sku_map)
        row = dict(base)
        row.update(
            {
                "admsuc_codigo": _code_or_blank(line_branch_map.get(index, branch_code)),
                "factrx_linea": index,
                "factrx_cant": qty,
                "invitm_codigo": item_code,
                "invitm_nombre": _text(item.get("title") or item.get("name")),
                "admuni_codigo": _text(item.get("unit") or "UND"),
                "factrx_precio": price,
                "factrx_totald": line_total,
                "factrx_pdescd": 0,
                "factrx_descd": line_discount,
                "factrx_pdescgrald": 0,
                "factrx_descgrald": 0,
                "factrx_pcargod": 0,
                "factrx_cargod": 0,
                "factrx_pcargograld": 0,
                "factrx_cargograld": 0,
                "factrx_valord": line_value,
                "factrx_pimpd": _line_tax_rate(item),
                "factrx_impd": line_tax,
                "factrx_netod": line_value + line_tax,
                "factrx_preciobr": price,
                "factrx_oferta": 0,
                "invcla_codigo": 0,
            }
        )
        rows.append(_complete_mfactrx_row(row))

    return rows or [_complete_mfactrx_row(base)]


def _order_money(order: dict[str, Any], *keys: str) -> float:
    for key in keys:
        if order.get(key) not in (None, ""):
            return _money(order.get(key))
    return 0.0


def _line_item_code(item: dict[str, Any], variant_map: dict[int, int], sku_map: dict[str, int]) -> int:
    variant_id = item.get("variant_id")
    if variant_id not in (None, ""):
        try:
            return variant_map.get(int(variant_id), 0)
        except (TypeError, ValueError):
            pass
    sku = item.get("sku")
    if sku:
        return sku_map.get(str(sku).upper(), 0)
    return 0


def _line_tax(item: dict[str, Any]) -> float:
    tax_lines = item.get("tax_lines") or []
    return sum(_money(tax_line.get("price")) for tax_line in tax_lines if isinstance(tax_line, dict))


def _line_tax_rate(item: dict[str, Any]) -> float:
    tax_lines = item.get("tax_lines") or []
    if not tax_lines or not isinstance(tax_lines[0], dict):
        return 0.0
    return _money(tax_lines[0].get("rate")) * 100


def _shipping_address(order: dict[str, Any]) -> str | None:
    address = order.get("shipping_address") or order.get("billing_address") or {}
    parts = [
        address.get("address1"),
        address.get("address2"),
        address.get("city"),
        address.get("province"),
        address.get("country"),
    ]
    return ", ".join(part for part in parts if part) or ""


def _complete_mfactrx_row(row: dict[str, Any]) -> dict[str, Any]:
    defaults: dict[str, Any] = {
        "factrx_linea": 0,
        "factrx_cant": 0,
        "invitm_codigo": 0,
        "invitm_nombre": "",
        "admuni_codigo": "",
        "factrx_precio": 0,
        "factrx_totald": 0,
        "factrx_pdescd": 0,
        "factrx_descd": 0,
        "factrx_pdescgrald": 0,
        "factrx_descgrald": 0,
        "factrx_pcargod": 0,
        "factrx_cargod": 0,
        "factrx_pcargograld": 0,
        "factrx_cargograld": 0,
        "factrx_valord": 0,
        "factrx_pimpd": 0,
        "factrx_impd": 0,
        "factrx_netod": 0,
        "factrx_preciobr": 0,
        "factrx_oferta": 0,
        "invcla_codigo": 0,
    }
    completed = {**defaults, **row}
    return {key: completed.get(key) for key in completed if key in MFACTRX_FIELDS}
