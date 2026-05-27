import base64
import hashlib
import hmac
import time
from urllib.parse import urlencode


def verify_shopify_webhook(secret: str, raw_body: bytes, hmac_header: str) -> bool:
    digest = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).digest()
    computed_hmac = base64.b64encode(digest).decode()
    return hmac.compare_digest(computed_hmac, hmac_header)


def verify_shopify_oauth_hmac(secret: str, query_params: dict[str, str]) -> bool:
    hmac_header = query_params.get("hmac")
    if not hmac_header:
        return False

    params = {
        key: value
        for key, value in query_params.items()
        if key not in {"hmac", "signature"} and value is not None
    }
    message = "&".join(f"{key}={params[key]}" for key in sorted(params))
    digest = hmac.new(secret.encode("utf-8"), message.encode("utf-8"), hashlib.sha256).hexdigest()
    return hmac.compare_digest(digest, hmac_header)


def sign_oauth_state(secret: str, shop: str, timestamp: int | None = None) -> str:
    issued_at = timestamp or int(time.time())
    payload = f"{shop}|{issued_at}"
    signature = hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    token = base64.urlsafe_b64encode(f"{payload}|{signature}".encode("utf-8")).decode("utf-8")
    return token.rstrip("=")


def verify_oauth_state(secret: str, state: str, shop: str, max_age_seconds: int = 600) -> bool:
    try:
        padded_state = state + "=" * (-len(state) % 4)
        decoded = base64.urlsafe_b64decode(padded_state.encode("utf-8")).decode("utf-8")
        state_shop, issued_at_raw, signature = decoded.rsplit("|", 2)
        issued_at = int(issued_at_raw)
    except (ValueError, TypeError):
        return False

    if state_shop != shop or int(time.time()) - issued_at > max_age_seconds:
        return False

    payload = f"{state_shop}|{issued_at}"
    expected = hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def build_shopify_install_url(
    shop: str,
    client_id: str,
    scopes: list[str],
    redirect_uri: str,
    state: str,
) -> str:
    query = urlencode(
        {
            "client_id": client_id,
            "scope": ",".join(scopes),
            "redirect_uri": redirect_uri,
            "state": state,
        }
    )
    return f"https://{shop}/admin/oauth/authorize?{query}"
