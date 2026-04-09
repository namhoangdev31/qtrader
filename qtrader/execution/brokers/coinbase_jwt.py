import secrets
import time
from urllib.parse import urlparse

import jwt


def build_rest_jwt(
    *, rest_base: str, method: str, path: str, key_name: str, private_key_pem: str
) -> str:
    parsed = urlparse(rest_base)
    host = parsed.netloc
    uri = f"{method.upper()} {host}{path}"
    now = int(time.time())
    payload = {"sub": key_name, "iss": "cdp", "nbf": now, "exp": now + 120, "uri": uri}
    headers = {"kid": key_name, "nonce": secrets.token_hex()}
    token = jwt.encode(payload, private_key_pem, algorithm="ES256", headers=headers)
    return token.decode("utf-8") if isinstance(token, bytes) else token
