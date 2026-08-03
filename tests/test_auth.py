import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from jwt.exceptions import PyJWKClientConnectionError

from lib import auth


@pytest.fixture
def keypair():
    priv = ec.generate_private_key(ec.SECP256R1())
    return priv, priv.public_key()


@pytest.fixture(autouse=True)
def stub_jwks(monkeypatch, keypair):
    """Point auth's JWKS client at the test public key, no network."""
    _, pub = keypair

    class _Key:
        def __init__(self, key):
            self.key = key

    class _Client:
        def get_signing_key_from_jwt(self, token):
            return _Key(pub)

    monkeypatch.setattr(auth, "_jwks_client", _Client())
    monkeypatch.setattr(auth, "CA_JWKS_URL", "https://ca.test/.well-known/jwks.json")
    monkeypatch.setattr(auth, "CA_ISSUER", None)


def _make_token(priv, *, memberships, exp_offset=900, iss="community-admin"):
    now = int(time.time())
    return jwt.encode(
        {
            "sub": "alice@example.com",
            "memberships": memberships,
            "iat": now,
            "exp": now + exp_offset,
            "iss": iss,
        },
        priv,
        algorithm="ES256",
    )


def test_member_token_returns_community_ids(keypair):
    priv, _ = keypair
    token = _make_token(
        priv,
        memberships=[{"community_id": 7, "role": "member"}, {"community_id": 12, "role": "admin"}],
    )
    assert auth.member_ids_from_request({"Authorization": f"Bearer {token}"}) == {"7", "12"}


def test_non_member_token_returns_empty(keypair):
    priv, _ = keypair
    token = _make_token(priv, memberships=[])
    assert auth.member_ids_from_request({"Authorization": f"Bearer {token}"}) == set()


def test_expired_token_returns_empty(keypair):
    priv, _ = keypair
    token = _make_token(priv, memberships=[{"community_id": 7, "role": "member"}], exp_offset=-3600)
    assert auth.member_ids_from_request({"Authorization": f"Bearer {token}"}) == set()


def test_tampered_signature_returns_empty(keypair):
    priv, _ = keypair
    token = _make_token(priv, memberships=[{"community_id": 7, "role": "member"}])
    head, payload, sig = token.split(".")
    # Flip the FIRST signature char (not the last - the last base64url char of a
    # P-256 signature carries unused padding bits, so flipping it is a no-op ~25%
    # of the time). Any other char encodes full bytes, so this always corrupts.
    bad_sig = ("A" if sig[0] != "A" else "B") + sig[1:]
    tampered = f"{head}.{payload}.{bad_sig}"
    assert auth.member_ids_from_request({"Authorization": f"Bearer {tampered}"}) == set()


# --- Issuer pinning -------------------------------------------------------
#
# The fixture above sets CA_ISSUER = None, which is NOT how production runs.
# Production pins an issuer, and that branch had no coverage at all until #16 —
# where a stale pin (community-admin's old Railway host, left behind by the
# 2026-08-02 domain migration) rejected every valid token for a day. The tests
# below exercise the configuration that actually ships.


def test_issuer_match_returns_community_ids(monkeypatch, keypair):
    priv, _ = keypair
    monkeypatch.setattr(auth, "CA_ISSUER", "https://admin.citizeninfra.org")
    token = _make_token(
        priv,
        memberships=[{"community_id": "scenius", "role": "admin"}],
        iss="https://admin.citizeninfra.org",
    )
    assert auth.member_ids_from_request({"Authorization": f"Bearer {token}"}) == {"scenius"}


def test_issuer_mismatch_returns_empty(monkeypatch, keypair):
    """The #16 regression: a cryptographically valid token, refused on a name.

    The signature verifies and the token is unexpired — only `iss` differs,
    because community-admin moved host and the pin did not follow. The caller
    is silently downgraded to public-only, which is indistinguishable from
    being anonymous.
    """
    priv, _ = keypair
    monkeypatch.setattr(
        auth, "CA_ISSUER", "https://community-admin-server-production.up.railway.app"
    )
    token = _make_token(
        priv,
        memberships=[{"community_id": "scenius", "role": "admin"}],
        iss="https://admin.citizeninfra.org",
    )
    assert auth.member_ids_from_request({"Authorization": f"Bearer {token}"}) == set()


def test_unset_issuer_skips_the_check(monkeypatch, keypair):
    """CA_ISSUER unset means no pinning, so any issuer is accepted."""
    priv, _ = keypair
    monkeypatch.setattr(auth, "CA_ISSUER", None)
    token = _make_token(priv, memberships=[{"community_id": 7}], iss="https://anything.example")
    assert auth.member_ids_from_request({"Authorization": f"Bearer {token}"}) == {"7"}


def test_unreachable_jwks_returns_empty(monkeypatch, keypair):
    """The second failure mode, which looks identical from outside.

    `admin.citizeninfra.org` sits behind Cloudflare, whose bot protection 403s
    Python's default user agent — and PyJWKClient fetches over urllib. So
    pointing CA_JWKS_URL at the proxied host makes the key fetch fail, and the
    caller is downgraded to public-only exactly as a stale issuer would. Two
    different causes, one indistinguishable symptom; see #16.
    """
    priv, _ = keypair

    class _Blocked:
        def get_signing_key_from_jwt(self, token):
            raise PyJWKClientConnectionError(
                'Fail to fetch data from the url, err: "HTTP Error 403: Forbidden"'
            )

    monkeypatch.setattr(auth, "_jwks_client", _Blocked())
    monkeypatch.setattr(auth, "CA_ISSUER", "https://admin.citizeninfra.org")
    token = _make_token(
        priv,
        memberships=[{"community_id": "scenius", "role": "admin"}],
        iss="https://admin.citizeninfra.org",
    )
    assert auth.member_ids_from_request({"Authorization": f"Bearer {token}"}) == set()


def test_rejection_is_logged_without_leaking_the_token(monkeypatch, keypair, capsys):
    """A silent close looks like normal operation. It must announce itself.

    Guards two things at once: that something is written, and that the token is
    not what gets written — it is a live credential until it expires.
    """
    priv, _ = keypair
    monkeypatch.setattr(auth, "CA_ISSUER", "https://wrong.example")
    token = _make_token(
        priv, memberships=[{"community_id": "scenius"}], iss="https://admin.citizeninfra.org"
    )
    assert auth.member_ids_from_request({"Authorization": f"Bearer {token}"}) == set()

    out = capsys.readouterr().out
    assert "[auth]" in out
    assert "InvalidIssuerError" in out, "the exception type is the diagnosis"
    assert token not in out, "the token must never reach the logs"


def test_anonymous_request_logs_nothing(capsys):
    """No Bearer header returns before the try block, so an anonymous caller
    must not produce log noise — otherwise the signal is worthless."""
    assert auth.member_ids_from_request({}) == set()
    assert capsys.readouterr().out == ""


def test_missing_token_returns_empty():
    assert auth.member_ids_from_request({}) == set()


def test_malformed_header_returns_empty():
    assert auth.member_ids_from_request({"Authorization": "Basic abc"}) == set()
