"""
Tests for app.core.auth and app.core.group_permission_utils.

Notes on scope:
- `verify_token` currently calls `verify_signature=False`, so the tests
  reflect that behavior. Tests for proper signature verification will be
  added when the JWT security fix is merged from `feature/extraction-issues`.
- PyJWKClient is patched to avoid network calls to Entra JWKS.
"""
from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import jwt
import pytest

from app.core.auth import AzureADAuth, CurrentUser
from app.core.group_permission_utils import check_initial_admin


# ---------------------------------------------------------------------------
# CurrentUser dataclass
# ---------------------------------------------------------------------------

class TestCurrentUser:
    def test_construct_with_all_fields(self):
        u = CurrentUser(
            id="oid-1",
            email="alice@example.com",
            name="Alice",
            tenant_id="tenant-1",
            roles=["reader"],
            groups=["g1", "g2"],
        )
        assert u.id == "oid-1"
        assert u.email == "alice@example.com"
        assert u.roles == ["reader"]
        assert u.groups == ["g1", "g2"]

    def test_groups_default_none(self):
        u = CurrentUser(
            id="oid-1",
            email="alice@example.com",
            name="Alice",
            tenant_id="tenant-1",
            roles=[],
        )
        assert u.groups is None


# ---------------------------------------------------------------------------
# INITIAL_ADMIN_EMAILS bootstrap
# ---------------------------------------------------------------------------

class TestCheckInitialAdmin:
    def test_empty_env_returns_false(self, monkeypatch):
        from app.core import group_permission_utils as gpu
        monkeypatch.setattr(gpu.settings, "INITIAL_ADMIN_EMAILS", "")
        assert check_initial_admin("anyone@example.com") is False

    def test_empty_email_returns_false(self, monkeypatch):
        from app.core import group_permission_utils as gpu
        monkeypatch.setattr(gpu.settings, "INITIAL_ADMIN_EMAILS", "admin@example.com")
        assert check_initial_admin("") is False

    def test_exact_match(self, monkeypatch):
        from app.core import group_permission_utils as gpu
        monkeypatch.setattr(gpu.settings, "INITIAL_ADMIN_EMAILS", "admin@example.com")
        assert check_initial_admin("admin@example.com") is True

    def test_case_insensitive(self, monkeypatch):
        from app.core import group_permission_utils as gpu
        monkeypatch.setattr(gpu.settings, "INITIAL_ADMIN_EMAILS", "Admin@Example.com")
        assert check_initial_admin("ADMIN@example.COM") is True

    def test_comma_separated_list(self, monkeypatch):
        from app.core import group_permission_utils as gpu
        monkeypatch.setattr(
            gpu.settings,
            "INITIAL_ADMIN_EMAILS",
            "a@example.com, b@example.com , c@example.com",
        )
        assert check_initial_admin("a@example.com") is True
        assert check_initial_admin("b@example.com") is True
        assert check_initial_admin("c@example.com") is True
        assert check_initial_admin("d@example.com") is False


# ---------------------------------------------------------------------------
# verify_token — current behavior (signature check disabled)
# ---------------------------------------------------------------------------

def _make_token(claims: dict, expired: bool = False) -> str:
    """Build an unsigned-but-well-formed JWT for tests."""
    payload = dict(claims)
    if expired:
        payload["exp"] = int(time.time()) - 3600
    else:
        payload["exp"] = int(time.time()) + 3600
    return jwt.encode(payload, "dummy-secret", algorithm="HS256")


@pytest.fixture
def mock_jwks(monkeypatch):
    """Patch PyJWKClient.get_signing_key_from_jwt to skip network."""
    from app.core import auth as auth_module

    fake_key = MagicMock()
    fake_key.key = "fake-key"

    def _get_signing_key(self, token):
        return fake_key

    monkeypatch.setattr(
        auth_module.PyJWKClient,
        "get_signing_key_from_jwt",
        _get_signing_key,
    )
    return fake_key


class TestVerifyToken:
    def test_well_formed_token_returns_user(self, mock_jwks):
        token = _make_token({
            "oid": "user-oid-1",
            "name": "Alice",
            "upn": "alice@example.com",
            "tid": "tenant-1",
            "roles": ["reader"],
            "groups": ["g1"],
        })
        auth = AzureADAuth()
        user = auth.verify_token(token)

        assert user is not None
        assert user.id == "user-oid-1"
        assert user.name == "Alice"
        assert user.email == "alice@example.com"
        assert user.tenant_id == "tenant-1"
        assert user.roles == ["reader"]
        assert user.groups == ["g1"]

    def test_email_falls_back_through_claim_names(self, mock_jwks):
        # upn missing, unique_name provided
        token = _make_token({"oid": "u1", "unique_name": "u1@example.com"})
        user = AzureADAuth().verify_token(token)
        assert user.email == "u1@example.com"

        # Both upn and unique_name missing, preferred_username provided
        token = _make_token({"oid": "u2", "preferred_username": "u2@example.com"})
        user = AzureADAuth().verify_token(token)
        assert user.email == "u2@example.com"

        # Only email claim provided
        token = _make_token({"oid": "u3", "email": "u3@example.com"})
        user = AzureADAuth().verify_token(token)
        assert user.email == "u3@example.com"

    def test_name_defaults_to_unknown(self, mock_jwks):
        token = _make_token({"oid": "u1", "upn": "u1@x.com"})
        user = AzureADAuth().verify_token(token)
        assert user.name == "Unknown"

    def test_groups_falls_back_to_wids(self, mock_jwks):
        # Entra sometimes returns built-in role GUIDs under `wids`
        token = _make_token({"oid": "u1", "wids": ["role-guid-1"]})
        user = AzureADAuth().verify_token(token)
        assert user.groups == ["role-guid-1"]

    def test_malformed_token_returns_none(self, mock_jwks):
        user = AzureADAuth().verify_token("not.a.jwt")
        assert user is None

    def test_empty_token_returns_none(self, mock_jwks):
        user = AzureADAuth().verify_token("")
        assert user is None

    def test_jwks_failure_returns_none(self, monkeypatch):
        # If JWKS lookup raises, verify_token swallows and returns None
        from app.core import auth as auth_module

        def _raise(self, token):
            raise RuntimeError("JWKS down")

        monkeypatch.setattr(
            auth_module.PyJWKClient,
            "get_signing_key_from_jwt",
            _raise,
        )
        token = _make_token({"oid": "u1"})
        user = AzureADAuth().verify_token(token)
        assert user is None


# ---------------------------------------------------------------------------
# Auth middleware via FastAPI
# ---------------------------------------------------------------------------

class TestAuthViaHTTP:
    @pytest.mark.asyncio
    async def test_root_endpoint_is_public(self, async_client):
        # `/` has no auth dependency — should always 200
        resp = await async_client.get("/")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_protected_endpoint_rejects_missing_bearer(self, async_client):
        # /api/v1/users requires auth; no header → 403
        resp = await async_client.get("/api/v1/users/me")
        assert resp.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_protected_endpoint_rejects_wrong_scheme(self, async_client):
        resp = await async_client.get(
            "/api/v1/users/me",
            headers={"Authorization": "Basic abcdef"},
        )
        assert resp.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_protected_endpoint_accepts_overridden_user(
        self, async_client, override_current_user, sample_user
    ):
        # When the dependency is overridden, the endpoint sees sample_user
        # regardless of headers. Exact response shape depends on /users/me
        # impl; we only assert the auth gate no longer rejects.
        resp = await async_client.get("/api/v1/users/me")
        assert resp.status_code != 403
