import asyncio
import sys
from pathlib import Path

import httpx

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.core.config import settings
from app.infrastructure.shopify.client import ShopifyClient


DEMO_PRODUCTS = [
    {"title": "Camiseta Basica Negra", "sku": "DEMO-CAM-NEGRA", "price": "19.99", "stock": 25},
    {"title": "Camiseta Basica Blanca", "sku": "DEMO-CAM-BLANCA", "price": "19.99", "stock": 25},
    {"title": "Gorra Clasica", "sku": "DEMO-GORRA", "price": "14.99", "stock": 15},
    {"title": "Mug Shopify Demo", "sku": "DEMO-MUG", "price": "12.50", "stock": 30},
    {"title": "Bolsa Tote Demo", "sku": "DEMO-TOTE", "price": "16.00", "stock": 20},
]


async def main() -> None:
    client = ShopifyClient(
        shop=settings.shopify_shop,
        api_version=settings.shopify_api_version,
        access_token=settings.shopify_access_token,
    )
    try:
        locations = await client.list_locations()
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code != 403:
            raise
        print("No se pudo leer locations; se crearan productos sin stock inicial.")
        locations = []
    location_id = locations[0]["id"] if locations else None
    created = []

    for item in DEMO_PRODUCTS:
        product = await client.create_product(
            {
                "title": item["title"],
                "body_html": "<p>Producto demo creado desde la integracion.</p>",
                "vendor": "Demo Store",
                "product_type": "Demo",
                "status": "draft",
                "variants": [
                    {
                        "option1": "Default Title",
                        "price": item["price"],
                        "sku": item["sku"],
                        "inventory_management": "shopify",
                        "inventory_policy": "deny",
                        "requires_shipping": True,
                    }
                ],
            }
        )
        variant = product["variants"][0]
        if location_id and variant.get("inventory_item_id"):
            await client.set_inventory_level(
                inventory_item_id=int(variant["inventory_item_id"]),
                location_id=int(location_id),
                available=int(item["stock"]),
            )
        created.append(
            {
                "id": product["id"],
                "title": product["title"],
                "sku": variant.get("sku"),
                "stock": item["stock"],
                "status": product.get("status"),
            }
        )

    for product in created:
        print(
            f'{product["id"]} | {product["title"]} | {product["sku"]} | '
            f'stock={product["stock"]} | status={product["status"]}'
        )


if __name__ == "__main__":
    asyncio.run(main())
