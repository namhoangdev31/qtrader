import secrets
import time
from urllib.parse import urlparse

import jwt


def build_rest_jwt(*, rest_base: str, method: str, path: str, key_name: str, private_key_pem: str) -> str:
    """
    Build a Coinbase CDP JWT for Advanced Trade REST.

    Based on Coinbase docs:
    - alg: ES256
    - header: { "kid": key_name, "nonce": <random> }
    - payload includes: sub, iss="cdp", nbf, exp, uri="<METHOD> <host><path>"
    """
    parsed = urlparse(rest_base)
    host = parsed.netloc
    uri = f"{method.upper()} {host}{path}"

    now = int(time.time())
    payload = {
        "sub": key_name,
        "iss": "cdp",
        "nbf": now,
        "exp": now + 120,
        "uri": uri,
    }
    headers = {"kid": key_name, "nonce": secrets.token_hex()}
    token = jwt.encode(payload, private_key_pem, algorithm="ES256", headers=headers)
    # pyjwt may return bytes in older versions; normalize to str.
    return token.decode("utf-8") if isinstance(token, bytes) else token

