import pytest
from httpx import AsyncClient

from app.infrastructure.se.client import SEClient


@pytest.mark.asyncio
async def test_list_products_sends_empty_string_when_company_code_is_omitted(monkeypatch):
    captured = {}

    class FakeResponse:
        status_code = 200
        content = b'{"factrx_numero": 123}'

        def raise_for_status(self):
            pass

        def json(self):
            return [{"invitm_codigo": 10}]

    async def fake_post(self, url, json, headers):
        captured["url"] = url
        captured["json"] = json
        captured["headers"] = headers
        return FakeResponse()

    monkeypatch.setattr(AsyncClient, "post", fake_post)
    client = SEClient(base_url="http://se.example", company_code=1)

    result = await client.list_products()

    assert result == [{"invitm_codigo": 10}]
    assert captured["url"] == "http://se.example/api/Minvitm/get"
    assert captured["json"] == ""
    assert captured["headers"] == {"Content-Type": "application/json"}


@pytest.mark.asyncio
async def test_list_products_sends_optional_company_code_as_integer(monkeypatch):
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return [{"invitm_codigo": 10}]

    async def fake_post(self, url, json, headers):
        captured["url"] = url
        captured["json"] = json
        captured["headers"] = headers
        return FakeResponse()

    monkeypatch.setattr(AsyncClient, "post", fake_post)
    client = SEClient(base_url="http://se.example", company_code=1)

    result = await client.list_products("2")

    assert result == [{"invitm_codigo": 10}]
    assert captured["url"] == "http://se.example/api/Minvitm/get"
    assert captured["json"] == 2
    assert captured["headers"] == {"Content-Type": "application/json"}


@pytest.mark.asyncio
async def test_list_products_converts_legacy_company_code_object_to_integer(monkeypatch):
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return [{"invitm_codigo": 10}]

    async def fake_post(self, url, json, headers):
        captured["json"] = json
        return FakeResponse()

    monkeypatch.setattr(AsyncClient, "post", fake_post)
    client = SEClient(base_url="http://se.example", company_code=1)

    await client.list_products({"admcia_codigo": 2})

    assert captured["json"] == 2


@pytest.mark.asyncio
async def test_list_prices_sends_company_and_price_codes(monkeypatch):
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return [{"invitm_codigo": 10, "facpre_Contado": 99}]

    async def fake_post(self, url, json, headers):
        captured["url"] = url
        captured["json"] = json
        captured["headers"] = headers
        return FakeResponse()

    monkeypatch.setattr(AsyncClient, "post", fake_post)
    client = SEClient(base_url="http://se.example", company_code=101)

    result = await client.list_prices()

    assert result == [{"invitm_codigo": 10, "facpre_Contado": 99}]
    assert captured["url"] == "http://se.example/api/Mfacpre/get"
    assert captured["json"] == [
        {
            "admCia_Codigo": 101,
            "facpre_Codigo": 101,
            "facpre_Nombre": "string",
            "invitm_Codigo": 0,
            "admuni_Codigo": "string",
            "facpre_Contado": 0,
            "facpre_Minimo": 0,
            "facpre_Perdec": 0,
            "facpre_Principal": 0,
        }
    ]
    assert captured["headers"] == {"Content-Type": "application/json"}


@pytest.mark.asyncio
async def test_list_prices_accepts_explicit_price_code(monkeypatch):
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return [{"invitm_codigo": 10, "facpre_Contado": 99}]

    async def fake_post(self, url, json, headers):
        captured["json"] = json
        return FakeResponse()

    monkeypatch.setattr(AsyncClient, "post", fake_post)
    client = SEClient(base_url="http://se.example", company_code=1)

    await client.list_prices({"admCia_Codigo": "101", "facpre_Codigo": "101"})

    assert captured["json"] == [
        {
            "admCia_Codigo": 101,
            "facpre_Codigo": 101,
            "facpre_Nombre": "string",
            "invitm_Codigo": 0,
            "admuni_Codigo": "string",
            "facpre_Contado": 0,
            "facpre_Minimo": 0,
            "facpre_Perdec": 0,
            "facpre_Principal": 0,
        }
    ]


@pytest.mark.asyncio
async def test_insert_invoice_sends_mfactrx_array_payload_with_company_code(monkeypatch):
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"factrx_numero": 123}

    async def fake_post(self, url, json, headers):
        captured["url"] = url
        captured["json"] = json
        captured["headers"] = headers
        return FakeResponse()

    monkeypatch.setattr(AsyncClient, "post", fake_post)
    client = SEClient(base_url="http://se.example", company_code=7)

    result = await client.insert_invoice(
        [
            {
                "admcia_codigo": 0,
                "admsuc_codigo": 1,
                "factrx_numero": 0,
                "factrx_tipo": 1,
                "factrx_fecha": "2026-05-20",
                "cxccte_codigo": 10,
                "factrx_linea": 1,
                "factrx_movil_id": "123",
                "factrx_cant": 1,
                "invitm_codigo": 20,
                "factrx_netod": 118,
            }
        ]
    )

    assert result == {"factrx_numero": 123}
    assert captured["url"] == "http://se.example/api/Factura/Insertar"
    assert isinstance(captured["json"], list)
    assert captured["json"][0]["admcia_codigo"] == 7
    assert captured["json"][0]["factrx_linea"] == 1
    assert captured["json"][0]["factrx_movil_id"] == ""
    assert captured["headers"] == {"Content-Type": "application/json"}


@pytest.mark.asyncio
async def test_insert_invoice_accepts_empty_200_response(monkeypatch):
    class FakeResponse:
        status_code = 200
        content = b""

        def raise_for_status(self):
            pass

    async def fake_post(self, url, json, headers):
        return FakeResponse()

    monkeypatch.setattr(AsyncClient, "post", fake_post)
    client = SEClient(base_url="http://se.example", company_code=7)

    result = await client.insert_invoice([{"factrx_numero": 0}])

    assert result == {}
    assert client.last_status_code == 200


@pytest.mark.asyncio
async def test_insert_invoice_visit_sends_array_payload_with_company_code(monkeypatch):
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"ok": True}

    async def fake_post(self, url, json, headers):
        captured["url"] = url
        captured["json"] = json
        captured["headers"] = headers
        return FakeResponse()

    monkeypatch.setattr(AsyncClient, "post", fake_post)
    client = SEClient(base_url="http://se.example", company_code=7)

    result = await client.insert_invoice_visit(
        [
            {
                "admcia_codigo": 0,
                "facvis_master": 0,
                "facvdr_codigo": 0,
                "cxccte_codigo": 0,
                "admvis_fecha": "2026-05-20",
                "admvis_comentario": "Factura Shopify",
                "factrx_numero": 0,
            }
        ]
    )

    assert result == {"ok": True}
    assert captured["url"] == "http://se.example/api/Factura/InsertarVisita"
    assert captured["json"][0]["admcia_codigo"] == 7
    assert captured["json"][0]["admvis_comentario"] == "Factura Shopify"
    assert captured["headers"] == {"Content-Type": "application/json"}
