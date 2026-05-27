from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import RedirectResponse

from app.core.config import settings
from app.core.security import (
    build_shopify_install_url,
    sign_oauth_state,
    verify_oauth_state,
    verify_shopify_oauth_hmac,
)

router = APIRouter()


def _normalize_shop(shop: str) -> str:
    normalized = shop.strip().lower().replace("https://", "").replace("http://", "").strip("/")
    if not normalized.endswith(".myshopify.com") or "/" in normalized:
        raise HTTPException(status_code=400, detail="Invalid Shopify shop domain")
    return normalized


def _oauth_redirect_uri() -> str:
    return f"{settings.app_url.rstrip('/')}/auth/callback"


def _require_oauth_config() -> None:
    if not settings.shopify_client_id or not settings.shopify_client_secret:
        raise HTTPException(
            status_code=500,
            detail="SHOPIFY_CLIENT_ID and SHOPIFY_CLIENT_SECRET are required for OAuth install.",
        )


@router.get("/install")
async def install(shop: str = Query(default="")) -> RedirectResponse:
    _require_oauth_config()
    shop_domain = _normalize_shop(shop or settings.shopify_shop)
    state = sign_oauth_state(settings.shopify_client_secret, shop_domain)
    install_url = build_shopify_install_url(
        shop=shop_domain,
        client_id=settings.shopify_client_id,
        scopes=settings.shopify_scopes,
        redirect_uri=_oauth_redirect_uri(),
        state=state,
    )
    return RedirectResponse(install_url)


@router.get("/callback")
async def oauth_callback(request: Request) -> dict[str, Any]:
    _require_oauth_config()
    params = {key: value for key, value in request.query_params.items()}
    shop_domain = _normalize_shop(params.get("shop", ""))
    code = params.get("code")
    state = params.get("state", "")

    if not code:
        raise HTTPException(status_code=400, detail="Missing OAuth code")
    if not verify_oauth_state(settings.shopify_client_secret, state, shop_domain):
        raise HTTPException(status_code=401, detail="Invalid OAuth state")
    if not verify_shopify_oauth_hmac(settings.shopify_client_secret, params):
        raise HTTPException(status_code=401, detail="Invalid Shopify OAuth HMAC")

    token_url = f"https://{shop_domain}/admin/oauth/access_token"
    payload = {
        "client_id": settings.shopify_client_id,
        "client_secret": settings.shopify_client_secret,
        "code": code,
    }
    async with httpx.AsyncClient(trust_env=False) as client:
        response = await client.post(token_url, json=payload, timeout=30.0)
        response.raise_for_status()
        token_payload = response.json()

    return {
        "status": "installed",
        "shop": shop_domain,
        "scope": token_payload.get("scope"),
        "access_token": token_payload.get("access_token"),
        "next_step": "Set SHOPIFY_ACCESS_TOKEN with this token and restart the service.",
    }
