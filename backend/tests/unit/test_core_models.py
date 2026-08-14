"""Contracts for the core app's abstract base models.

The load-bearing test here is the last one. ADR-003 settles that M1 creates no
concrete models, because `AuditLog` has a foreign key to `User` and the custom
user model must exist before the first migration is ever applied. An assertion
is the only thing that turns that decision into a property the build enforces.
"""

from __future__ import annotations

import uuid

from django.apps import apps as django_apps
from django.db.migrations.autodetector import MigrationAutodetector
from django.db.migrations.loader import MigrationLoader
from django.db.migrations.questioner import NonInteractiveMigrationQuestioner
from django.db.migrations.state import ProjectState


class TestTimestampedModel:
    def test_is_abstract(self) -> None:
        from apps.core.models import TimestampedModel

        assert TimestampedModel._meta.abstract is True

    def test_records_creation_and_update_times(self) -> None:
        from apps.core.models import TimestampedModel

        fields = {f.name: f for f in TimestampedModel._meta.get_fields()}

        assert fields["created_at"].auto_now_add is True
        assert fields["updated_at"].auto_now is True

    def test_timestamps_cannot_be_edited(self) -> None:
        """These describe what happened, not what someone would like to have
        happened. Leaving them editable puts them in ModelForms and the admin."""
        from apps.core.models import TimestampedModel

        fields = {f.name: f for f in TimestampedModel._meta.get_fields()}

        assert fields["created_at"].editable is False
        assert fields["updated_at"].editable is False


class TestUUIDPrimaryKeyModel:
    def test_is_abstract(self) -> None:
        from apps.core.models import UUIDPrimaryKeyModel

        assert UUIDPrimaryKeyModel._meta.abstract is True

    def test_primary_key_is_a_uuid(self) -> None:
        """architecture.md 5.2: sequential integers in URLs leak business
        information and make enumeration trivial."""
        from apps.core.models import UUIDPrimaryKeyModel

        pk = UUIDPrimaryKeyModel._meta.get_field("id")

        assert pk.primary_key is True
        assert pk.get_internal_type() == "UUIDField"

    def test_primary_key_defaults_to_a_generated_value(self) -> None:
        from apps.core.models import UUIDPrimaryKeyModel

        pk = UUIDPrimaryKeyModel._meta.get_field("id")
        generated = pk.get_default()

        assert isinstance(generated, uuid.UUID)
        assert generated != pk.get_default(), "each default must be distinct"


class TestCoreAppIsInstalled:
    def test_core_is_registered(self) -> None:
        from django.conf import settings

        assert "apps.core" in settings.INSTALLED_APPS


class TestM1CreatesNoMigrations:
    """ADR-003. M1 ships no concrete models.

    If this fails, something in M1 grew a model. That matters because the first
    migration applied to a real database fixes AUTH_USER_MODEL, and the custom
    user model does not exist until M2.
    """

    def test_no_model_changes_are_pending(self) -> None:
        # The autodetector is driven directly rather than through
        # `makemigrations --check`, because that command verifies migration
        # history against a live database. CI has no Postgres, and a test that
        # silently required one would be a test that only ever ran locally.
        # MigrationLoader(None) reads the on-disk graph with no connection.
        loader = MigrationLoader(None, ignore_no_migrations=True)
        autodetector = MigrationAutodetector(
            loader.project_state(),
            ProjectState.from_apps(django_apps),
            NonInteractiveMigrationQuestioner(specified_apps=set(), dry_run=True),
        )

        changes = autodetector.changes(graph=loader.graph)
        ours = {label: ops for label, ops in changes.items() if label.startswith("apps.")}

        assert not ours, (
            f"A concrete model was added in {sorted(ours)}. M1 must create no "
            "migrations (ADR-003) — the custom User model must exist before the "
            "first migration is applied. Move the model to M2."
        )
