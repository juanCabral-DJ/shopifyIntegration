import base64
import hashlib
import hmac
from app.core.security import verify_shopify_webhook


def test_verify_shopify_webhook_valid_signature() -> None:
    secret = "test_secret"
    payload = b'{"id": 1}'
    digest = hmac.new(secret.encode(), payload, hashlib.sha256).digest()
    header = base64.b64encode(digest).decode()

    assert verify_shopify_webhook(secret, payload, header)


def test_verify_shopify_webhook_invalid_signature() -> None:
    assert not verify_shopify_webhook("secret", b"{}", "invalid")
