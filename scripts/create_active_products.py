import asyncio
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.core.config import settings
from app.infrastructure.shopify.client import ShopifyClient


ACTIVE_PRODUCTS = [
    {"title": "Hoodie Activo Negro", "sku": "ACTIVE-HOODIE-NEGRO", "price": "39.99", "stock": 12},
    {"title": "Sticker Pack Activo", "sku": "ACTIVE-STICKER-PACK", "price": "6.99", "stock": 50},
    {"title": "Botella Activa", "sku": "ACTIVE-BOTELLA", "price": "18.50", "stock": 18},
]


async def main() -> None:
    client = ShopifyClient(
        shop=settings.shopify_shop,
        api_version=settings.shopify_api_version,
        access_token=settings.shopify_access_token,
    )
    locations = await client.list_locations()
    location_id = locations[0]["id"] if locations else None
    created = []

    for item in ACTIVE_PRODUCTS:
        product = await client.create_product(
            {
                "title": item["title"],
                "body_html": "<p>Producto activo creado desde la integracion.</p>",
                "vendor": "Demo Store",
                "product_type": "Demo",
                "status": "active",
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
