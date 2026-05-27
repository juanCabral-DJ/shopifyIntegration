CANONICAL_PAYMENT_METHODS = {
    "efectivo": {
        "cash",
        "cash on delivery",
        "cod",
        "efectivo",
        "manual",
        "manual cash",
        "pago en efectivo",
    },
    "transferencia": {
        "bank deposit",
        "bank transfer",
        "deposito bancario",
        "depósito bancario",
        "transfer",
        "transferencia",
        "transferencia bancaria",
        "wire transfer",
    },
}


def normalize_payment_method(value: str | None) -> str | None:
    if not value:
        return None

    normalized = value.strip().lower()
    for method_code, aliases in CANONICAL_PAYMENT_METHODS.items():
        if normalized == method_code or normalized in aliases:
            return method_code
    return None
