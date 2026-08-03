"""Verify community-admin identity tokens (IdP S2).

scenius-digest is a resource server: it verifies short-lived ES256 JWTs issued
by community-admin (offline, against the published JWKS) and reads the caller's
community memberships from the verified claims. No member lists, no self-asserted
identity. See community-admin#21 and docs/plans/2026-06-27-s2-idp-design.md.
"""

import os

import jwt
from jwt import PyJWKClient

# Public key set published by community-admin's /.well-known/jwks.json.
CA_JWKS_URL = os.getenv("CA_JWKS_URL")
# Optional issuer pinning (= community-admin's API_URL). Skipped when unset.
CA_ISSUER = os.getenv("CA_ISSUER")

# Lazily-built JWKS client; caches keys ~1h across warm serverless invocations.
_jwks_client = None


def _get_jwks_client():
    global _jwks_client
    if _jwks_client is None and CA_JWKS_URL:
        _jwks_client = PyJWKClient(CA_JWKS_URL, cache_keys=True, lifespan=3600)
    return _jwks_client


def member_ids_from_request(headers) -> set[str]:
    """Return the set of community ids (as strings) the caller is a verified
    member of. Anonymous / invalid / expired token, or an unreachable JWKS with
    no cache, all return an empty set (public only). Never raises."""
    auth_header = headers.get("Authorization", "") or ""
    if not auth_header.startswith("Bearer "):
        return set()
    token = auth_header[len("Bearer "):].strip()
    if not token:
        return set()

    client = _get_jwks_client()
    if client is None:
        return set()

    try:
        signing_key = client.get_signing_key_from_jwt(token)
        decode_kwargs = {
            "algorithms": ["ES256"],
            "leeway": 30,
            "options": {"require": ["exp"]},
        }
        if CA_ISSUER:
            decode_kwargs["issuer"] = CA_ISSUER
        claims = jwt.decode(token, signing_key.key, **decode_kwargs)
    except Exception as e:
        # Log it. Returning an empty set is the right behaviour, but it is
        # indistinguishable from an anonymous caller, so without this line a
        # misconfiguration presents as normal operation. That is exactly how #16
        # ran for a day: a stale CA_ISSUER rejected every valid token and served
        # verified members public-only content, silently.
        #
        # The exception type is the diagnosis. InvalidIssuerError means CA_ISSUER
        # disagrees with what community-admin stamps; PyJWKClientConnectionError
        # means CA_JWKS_URL is unreachable (e.g. Cloudflare's bot protection
        # 403ing urllib on the proxied host). Both look identical from outside.
        #
        # Never log the token itself — it is a live credential until it expires.
        print(f"[auth] token rejected: {type(e).__name__}: {e}")
        return set()

    memberships = claims.get("memberships") or []
    return {
        str(m["community_id"])
        for m in memberships
        if isinstance(m, dict) and m.get("community_id") is not None
    }
