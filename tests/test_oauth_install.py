import hashlib
import hmac
import time
from urllib.parse import parse_qs, urlparse

from app.core.security import (
    build_shopify_install_url,
    sign_oauth_state,
    verify_oauth_state,
    verify_shopify_oauth_hmac,
)


def _signed_oauth_params(secret: str, params: dict[str, str]) -> dict[str, str]:
    message = "&".join(f"{key}={params[key]}" for key in sorted(params))
    params["hmac"] = hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()
    return params


def test_verify_shopify_oauth_hmac_valid_signature() -> None:
    params = _signed_oauth_params(
        "test-secret",
        {
            "shop": "test-shop.myshopify.com",
            "code": "oauth-code",
            "timestamp": "1710000000",
        },
    )

    assert verify_shopify_oauth_hmac("test-secret", params)


def test_verify_shopify_oauth_hmac_invalid_signature() -> None:
    params = {
        "shop": "test-shop.myshopify.com",
        "code": "oauth-code",
        "timestamp": "1710000000",
        "hmac": "invalid",
    }

    assert not verify_shopify_oauth_hmac("test-secret", params)


def test_oauth_state_is_bound_to_shop_and_secret() -> None:
    state = sign_oauth_state("test-secret", "test-shop.myshopify.com", timestamp=int(time.time()))

    assert verify_oauth_state("test-secret", state, "test-shop.myshopify.com")
    assert not verify_oauth_state("test-secret", state, "other-shop.myshopify.com")
    assert not verify_oauth_state("other-secret", state, "test-shop.myshopify.com")


def test_build_shopify_install_url_contains_expected_oauth_params() -> None:
    url = build_shopify_install_url(
        shop="test-shop.myshopify.com",
        client_id="client-id",
        scopes=["read_orders", "write_orders"],
        redirect_uri="https://app.example.com/auth/callback",
        state="state-token",
    )

    parsed = urlparse(url)
    query = parse_qs(parsed.query)

    assert parsed.scheme == "https"
    assert parsed.netloc == "test-shop.myshopify.com"
    assert parsed.path == "/admin/oauth/authorize"
    assert query["client_id"] == ["client-id"]
    assert query["scope"] == ["read_orders,write_orders"]
    assert query["redirect_uri"] == ["https://app.example.com/auth/callback"]
    assert query["state"] == ["state-token"]
