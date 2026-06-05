from typing import Any

import httpx


class ExternalSystemNotConfigured(RuntimeError):
    pass


SE_TIMEOUT_SECONDS = 300.0


class SEClient:
    def __init__(self, base_url: str, api_key: str = "", company_code: int = 1) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.company_code = company_code
        self.last_status_code: int | None = None

    def _require_configured(self) -> None:
        if not self.base_url:
            raise ExternalSystemNotConfigured("SE_BASE_URL is required to call the external system")

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _raise_for_status(self, response: httpx.Response) -> None:
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            detail = response.text.strip()
            if detail:
                message = f"{exc} Response body: {detail[:1000]}"
                raise httpx.HTTPStatusError(message, request=exc.request, response=exc.response) from exc
            raise

    def with_company(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        body = dict(payload or {})
        body.setdefault("admcia_codigo", self.company_code)
        body.setdefault("admcia_Codigo", self.company_code)
        return body

    async def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        self._require_configured()
        async with httpx.AsyncClient(trust_env=False, timeout=SE_TIMEOUT_SECONDS) as client:
            response = await client.get(f"{self.base_url}{path}", params=params, headers=self._headers())
            self._raise_for_status(response)
            return response.json()

    async def post(self, path: str, payload: dict[str, Any] | None = None) -> Any:
        self._require_configured()
        async with httpx.AsyncClient(trust_env=False, timeout=SE_TIMEOUT_SECONDS) as client:
            response = await client.post(
                f"{self.base_url}{path}",
                json=self.with_company(payload),
                headers=self._headers(),
            )
            self._raise_for_status(response)
            self.last_status_code = getattr(response, "status_code", None)
            if not getattr(response, "content", b"data"):
                return {}
            return response.json()

    async def post_json_value(self, path: str, value: Any) -> Any:
        self._require_configured()
        async with httpx.AsyncClient(trust_env=False, timeout=SE_TIMEOUT_SECONDS) as client:
            response = await client.post(
                f"{self.base_url}{path}",
                json=value,
                headers=self._headers(),
            )
            self._raise_for_status(response)
            self.last_status_code = getattr(response, "status_code", None)
            if not getattr(response, "content", b"data"):
                return {}
            return response.json()

    async def insert_invoice(self, payload: list[dict[str, Any]] | dict[str, Any]) -> Any:
        rows = payload.get("mfactrx_rows", [payload]) if isinstance(payload, dict) else payload
        return await self.post_json_value("/api/Factura/Insertar", self.with_company_rows(rows))

    async def insert_invoice_visit(self, payload: list[dict[str, Any]]) -> Any:
        return await self.post_json_value("/api/Factura/InsertarVisita", self.with_company_rows(payload))

    def with_company_rows(self, payload: list[dict[str, Any]]) -> list[dict[str, Any]]:
        rows = []
        for item in payload:
            row = dict(item)
            if row.get("admcia_codigo") in (None, "", 0, "0"):
                row["admcia_codigo"] = self.company_code
            if "factrx_movil_id" in row:
                row["factrx_movil_id"] = ""
            rows.append(row)
        return rows
 

    async def list_receipt_types(self, payload: dict[str, Any] | None = None) -> Any:
        return await self.post("/api/Madmtco/get", payload)

    async def list_company(self, payload: dict[str, Any] | None = None) -> Any:
        return await self.post("/api/madmcia/get", payload)

    async def list_parameters(self, payload: dict[str, Any] | None = None) -> Any:
        return await self.post("/api/madmpar/get", payload)

    async def list_branches(self, payload: dict[str, Any] | None = None) -> Any:
        return await self.post("/api/madmsuc/get", payload)

    async def list_customers(self, payload: dict[str, Any] | None = None) -> Any:
        return await self.post("/api/mcxccte/get", payload)

    async def update_customer(self, payload: dict[str, Any]) -> Any:
        return await self.post("/api/mcxccte/Actualizar", payload)

    async def list_payment_terms(self, payload: dict[str, Any] | None = None) -> Any:
        return await self.post("/api/mcxccte/CondPago", payload)

    async def list_customer_debts(self, payload: dict[str, Any] | None = None) -> Any:
        return await self.post("/api/mcxccte/deudas", payload)

    async def list_customer_advances(self, payload: dict[str, Any] | None = None) -> Any:
        return await self.post("/api/mcxcant/get", payload)

    async def total_collections(self, payload: dict[str, Any] | None = None) -> Any:
        return await self.post("/api/mcxccte/GetTotalCobros", payload)

    async def list_products(self, payload: Any = None) -> Any:
        return await self.post_json_value("/api/Minvitm/get", self._product_company_body(payload))

    def _product_company_body(self, payload: Any = None) -> Any:
        if isinstance(payload, dict):
            company_code = payload.get("admcia_codigo", payload.get("admcia_Codigo"))
            return self._coerce_company_code(company_code) if company_code is not None else ""
        if payload is None:
            return ""
        return self._coerce_company_code(payload)

    def _coerce_company_code(self, value: Any) -> Any:
        if isinstance(value, str):
            stripped = value.strip()
            if stripped.isdigit():
                return int(stripped)
            return stripped
        return value

    async def read_product_price(self, payload: dict[str, Any] | None = None) -> Any:
        return await self.post("/api/Minvitm/LectorPrecio", payload)

    async def list_families(self) -> Any:
        return await self.get("/api/Minvitm/familias")

    async def list_brands(self) -> Any:
        return await self.get("/api/Minvitm/marcas")

    async def list_prices(self, payload: Any = None) -> Any:
        return await self.post_json_value("/api/Mfacpre/get", self._price_body(payload))

    def _price_body(self, payload: Any = None) -> list[dict[str, Any]]:
        if isinstance(payload, list):
            return [self._price_row(item) for item in payload if isinstance(item, dict)]
        return [self._price_row(payload if isinstance(payload, dict) else {"admCia_Codigo": payload})]

    def _price_row(self, payload: dict[str, Any]) -> dict[str, Any]:
        if isinstance(payload, dict):
            company_code = self._first_payload_value(payload, "admCia_Codigo", "admcia_codigo", "admcia_Codigo")
            price_code = self._first_payload_value(payload, "facpre_Codigo", "facpre_codigo")
            company_code = self._coerce_company_code(company_code if company_code is not None else self.company_code)
            price_code = self._coerce_company_code(price_code if price_code is not None else company_code)
            return {
                "admCia_Codigo": company_code,
                "facpre_Codigo": price_code,
                "facpre_Nombre": payload.get("facpre_Nombre", "string"),
                "invitm_Codigo": self._coerce_company_code(payload.get("invitm_Codigo", payload.get("invitm_codigo", 0))),
                "admuni_Codigo": payload.get("admuni_Codigo", payload.get("admuni_codigo", "string")),
                "facpre_Contado": payload.get("facpre_Contado", payload.get("facpre_contado", 0)),
                "facpre_Minimo": payload.get("facpre_Minimo", payload.get("facpre_minimo", 0)),
                "facpre_Perdec": payload.get("facpre_Perdec", payload.get("facpre_perdec", 0)),
                "facpre_Principal": payload.get("facpre_Principal", payload.get("facpre_principal", 0)),
            }
        code = self._coerce_company_code(self.company_code)
        return {
            "admCia_Codigo": code,
            "facpre_Codigo": code,
            "facpre_Nombre": "string",
            "invitm_Codigo": 0,
            "admuni_Codigo": "string",
            "facpre_Contado": 0,
            "facpre_Minimo": 0,
            "facpre_Perdec": 0,
            "facpre_Principal": 0,
        }

    def _first_payload_value(self, payload: dict[str, Any], *keys: str) -> Any:
        for key in keys:
            if key in payload and payload[key] not in (None, ""):
                return payload[key]
        return None

    def _company_dict_body(self, payload: Any = None) -> dict[str, Any] | None:
        if isinstance(payload, dict):
            return payload
        if payload is None:
            return None
        company_code = self._coerce_company_code(payload)
        return {"admcia_codigo": company_code, "admcia_Codigo": company_code}

    async def list_images(self, table: str, master_id: int) -> Any:
        return await self.post("/api/Madmimg/get", {"admimg_tabla": table, "admimg_master": master_id})

    async def list_physical_inventory(self) -> Any:
        return await self.get("/api/Minvfismovil/getfisico")

    async def update_physical_inventory(self, payload: dict[str, Any]) -> Any:
        return await self.post("/api/inventario/fisico", payload)

    async def sales_by_family(self, payload: dict[str, Any] | None = None) -> Any:
        return await self.post("/api/Factura/GetVentasProductosFamilia", payload)

    async def sales_by_family_detail(self, payload: dict[str, Any] | None = None) -> Any:
        return await self.post("/api/Factura/GetDetalleVentasProductosFamilia", payload)

    async def purchased_products(self, params: dict[str, Any] | None = None) -> Any:
        return await self.get("/api/Factura/ProductosComprados", params)
