from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_products_sync_rejects_string_company_code() -> None:
    response = client.post("/sync/products", json="101")

    assert response.status_code == 422


def test_inventory_sync_rejects_string_company_code() -> None:
    response = client.post("/sync/inventory", json="101")

    assert response.status_code == 422


def test_products_and_inventory_openapi_bodies_are_integer_numbers() -> None:
    schema = client.get("/openapi.json").json()

    products_schema = schema["paths"]["/sync/products"]["post"]["requestBody"]["content"]["application/json"][
        "schema"
    ]
    inventory_schema = schema["paths"]["/sync/inventory"]["post"]["requestBody"]["content"]["application/json"][
        "schema"
    ]

    assert products_schema["anyOf"][0]["type"] == "integer"
    assert inventory_schema["anyOf"][0]["type"] == "integer"
