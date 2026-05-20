"""Smoke checks that the ORM model package imports and registers on Base.metadata."""

from __future__ import annotations

from app.db import models
from app.db.base import Base


def test_all_expected_tables_registered() -> None:
    tables = set(Base.metadata.tables)
    assert {"system_setting", "system_secret", "user", "ad_group", "user_ad_group"}.issubset(tables)


def test_model_classes_exported() -> None:
    assert hasattr(models, "User")
    assert hasattr(models, "ADGroup")
    assert hasattr(models, "UserADGroup")
    assert hasattr(models, "SystemSetting")
    assert hasattr(models, "SystemSecret")


def test_user_to_groups_relationship_metadata() -> None:
    # `user.groups` should be a many-to-many through user_ad_group.
    rel = models.User.__mapper__.relationships["groups"]
    assert rel.secondary is not None
    assert rel.secondary.name == "user_ad_group"
    assert rel.argument is models.ADGroup or rel.entity.class_ is models.ADGroup


def test_accounting_record_table_registered() -> None:
    tables = Base.metadata.tables
    assert "accounting_record" in tables
    cols = {c.name for c in tables["accounting_record"].columns}
    expected = {
        "id",
        "ts",
        "nas_ip",
        "username",
        "port",
        "nac_ip",
        "action",
        "service",
        "cmd",
        "priv_lvl",
        "elapsed_seconds",
        "task_id",
        "device_id",
        "raw_av_pairs",
    }
    assert expected.issubset(cols)
    indexes = {i.name for i in tables["accounting_record"].indexes}
    assert "ix_accounting_record_ts" in indexes
    assert "ix_accounting_record_username" in indexes
