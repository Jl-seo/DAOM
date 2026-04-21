"""
Regression test: GET /models must merge BOTH permission mechanisms.

Bug fixed: a non-superadmin whose group had a model-role entry
(group.permissions.models[*].modelId) could open the model by URL
(can_access_model OK) but never saw it in the model list, because
list_models only called get_accessible_models (the legacy
model.permissions path) and ignored the group-role path.

The endpoint must return the UNION of:
  (a) permission_service.get_accessible_models        — legacy
  (b) group_permission_utils.get_accessible_model_ids — group-role
"""
from __future__ import annotations

from typing import List
from unittest.mock import AsyncMock, patch

import pytest

from app.api.endpoints import models as models_endpoint
from app.core.auth import CurrentUser
from app.schemas.model import ExtractionModel, FieldDefinition


def _model(model_id: str, name: str = "M") -> ExtractionModel:
    return ExtractionModel(
        id=model_id,
        name=name,
        fields=[FieldDefinition(key="k", label="k")],
        is_active=True,
    )


def _admin_user() -> CurrentUser:
    return CurrentUser(
        id="user-abc",
        email="admin@example.com",
        name="Admin",
        tenant_id="tenant-1",
        roles=["Admin"],
        groups=["entra-group-1"],
        access_token="test-token",
    )


@pytest.mark.asyncio
async def test_list_models_returns_union_of_legacy_and_group_role_ids():
    """A model granted via group-role alone must appear in the list."""
    all_models: List[ExtractionModel] = [
        _model("m-legacy", "Legacy-permissioned"),
        _model("m-group",  "Group-role-assigned"),
        _model("m-neither", "Unassigned"),
    ]

    with patch.object(models_endpoint, "load_models", AsyncMock(return_value=all_models)), \
         patch("app.core.auth.is_super_admin", AsyncMock(return_value=False)), \
         patch(
             "app.services.permission_service.get_accessible_models",
             AsyncMock(return_value=["m-legacy"]),
         ), \
         patch(
             "app.core.group_permission_utils.get_accessible_model_ids",
             AsyncMock(return_value={"m-group"}),
         ):
        result = await models_endpoint.list_models(current_user=_admin_user())

    got = sorted(m.id for m in result)
    assert got == ["m-group", "m-legacy"], (
        f"Union failed — expected both legacy and group-role models, got {got}"
    )


@pytest.mark.asyncio
async def test_list_models_superadmin_sees_all():
    all_models = [_model("m1"), _model("m2"), _model("m3")]

    with patch.object(models_endpoint, "load_models", AsyncMock(return_value=all_models)), \
         patch("app.core.auth.is_super_admin", AsyncMock(return_value=True)):
        result = await models_endpoint.list_models(current_user=_admin_user())

    assert [m.id for m in result] == ["m1", "m2", "m3"]


@pytest.mark.asyncio
async def test_list_models_only_group_role_no_legacy():
    """User has NO legacy permissions but has group-role access — must still see the model."""
    all_models = [_model("m-group-only")]

    with patch.object(models_endpoint, "load_models", AsyncMock(return_value=all_models)), \
         patch("app.core.auth.is_super_admin", AsyncMock(return_value=False)), \
         patch(
             "app.services.permission_service.get_accessible_models",
             AsyncMock(return_value=[]),
         ), \
         patch(
             "app.core.group_permission_utils.get_accessible_model_ids",
             AsyncMock(return_value={"m-group-only"}),
         ):
        result = await models_endpoint.list_models(current_user=_admin_user())

    assert [m.id for m in result] == ["m-group-only"]


@pytest.mark.asyncio
async def test_list_models_no_access_empty_list():
    all_models = [_model("m1"), _model("m2")]

    with patch.object(models_endpoint, "load_models", AsyncMock(return_value=all_models)), \
         patch("app.core.auth.is_super_admin", AsyncMock(return_value=False)), \
         patch(
             "app.services.permission_service.get_accessible_models",
             AsyncMock(return_value=[]),
         ), \
         patch(
             "app.core.group_permission_utils.get_accessible_model_ids",
             AsyncMock(return_value=set()),
         ):
        result = await models_endpoint.list_models(current_user=_admin_user())

    assert result == []


@pytest.mark.asyncio
async def test_list_models_skips_inactive_models():
    """Soft-deleted models (is_active=False) must not appear regardless of permissions."""
    m_active = _model("m-active")
    m_inactive = ExtractionModel(
        id="m-inactive",
        name="Deleted",
        fields=[FieldDefinition(key="k", label="k")],
        is_active=False,
    )

    with patch.object(models_endpoint, "load_models", AsyncMock(return_value=[m_active, m_inactive])), \
         patch("app.core.auth.is_super_admin", AsyncMock(return_value=False)), \
         patch(
             "app.services.permission_service.get_accessible_models",
             AsyncMock(return_value=["m-active", "m-inactive"]),
         ), \
         patch(
             "app.core.group_permission_utils.get_accessible_model_ids",
             AsyncMock(return_value=set()),
         ):
        result = await models_endpoint.list_models(current_user=_admin_user())

    assert [m.id for m in result] == ["m-active"]


@pytest.mark.asyncio
async def test_list_models_deduplicates_overlapping_access():
    """A model granted via both legacy and group-role paths must appear exactly once."""
    all_models = [_model("m-both"), _model("m-legacy"), _model("m-group")]

    with patch.object(models_endpoint, "load_models", AsyncMock(return_value=all_models)), \
         patch("app.core.auth.is_super_admin", AsyncMock(return_value=False)), \
         patch(
             "app.services.permission_service.get_accessible_models",
             AsyncMock(return_value=["m-legacy", "m-both"]),
         ), \
         patch(
             "app.core.group_permission_utils.get_accessible_model_ids",
             AsyncMock(return_value={"m-both", "m-group"}),
         ):
        result = await models_endpoint.list_models(current_user=_admin_user())

    got = sorted(m.id for m in result)
    assert got == ["m-both", "m-group", "m-legacy"]
    # Duplicate guard: len must equal unique-set size.
    assert len(result) == len(set(m.id for m in result))
