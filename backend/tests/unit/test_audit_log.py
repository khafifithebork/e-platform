"""The audit log, and what append-only actually means.

M10 grants a small number of people the ability to give away paid content and
move money. This table is what makes that acceptable, so it is built before any
of the capabilities that use it (ADR-018 §1).

The tests worth reading are the ones about what *cannot* be done to a row, and
one about what still can: deleting an administrator must keep working, and the
row must survive naming them.
"""

from __future__ import annotations

import pytest
from django.db import IntegrityError, transaction

from apps.core.models import AuditLog, AuditLogIsAppendOnly

PASSWORD = "a-long-enough-passphrase"

pytestmark = pytest.mark.django_db


def _admin(email: str = "admin@example.test"):
    from apps.accounts.models import Role
    from apps.accounts.services import create_account

    user = create_account(email=email, password=PASSWORD)
    user.role = Role.ADMIN
    user.save(update_fields=["role"])
    return user


def _row(**overrides) -> AuditLog:
    actor = overrides.pop("actor", None)
    fields = {
        "actor": actor,
        "actor_label": overrides.pop("actor_label", "admin@example.test"),
        "action": "ACCESS_OVERRIDE_GRANTED",
        "target_type": "user",
        "target_id": "00000000-0000-0000-0000-000000000001",
        "metadata": {"reason": "double charged"},
        "ip_address": "203.0.113.7",
    }
    fields.update(overrides)
    return AuditLog.objects.create(**fields)


class TestWhatARowRecords:
    def test_it_keeps_actor_target_reason_and_address(self) -> None:
        """§8's list, which is the whole requirement in one line."""
        actor = _admin()

        row = _row(actor=actor)

        assert row.actor == actor
        assert row.actor_label == "admin@example.test"
        assert row.action == "ACCESS_OVERRIDE_GRANTED"
        assert (row.target_type, row.target_id) == (
            "user",
            "00000000-0000-0000-0000-000000000001",
        )
        assert row.metadata["reason"] == "double charged"
        assert row.ip_address == "203.0.113.7"
        assert row.created_at is not None

    def test_an_action_without_a_request_may_have_no_address(self) -> None:
        """A management command has no IP. Recording 0.0.0.0 would be a fact we
        made up."""
        row = _row(actor=_admin(), ip_address=None)

        assert row.ip_address is None

    def test_there_is_no_updated_at(self) -> None:
        """`TimestampedModel` would have added one. A column named "when this
        last changed" on an append-only table tells the next reader that rows
        change."""
        fields = {field.name for field in AuditLog._meta.get_fields()}

        assert "updated_at" not in fields
        assert "created_at" in fields


class TestHistoryCannotBeRewritten:
    def test_a_row_cannot_be_saved_twice(self) -> None:
        row = _row(actor=_admin())
        row.action = "SOMETHING_ELSE"

        with pytest.raises(AuditLogIsAppendOnly):
            row.save()

    def test_a_row_cannot_be_deleted(self) -> None:
        row = _row(actor=_admin())

        with pytest.raises(AuditLogIsAppendOnly):
            row.delete()

    def test_a_queryset_cannot_be_updated(self) -> None:
        """The likelier accident by far. Model `save` never sees a bulk call,
        so guarding only the model would leave the wide-open door shut on the
        narrow one."""
        _row(actor=_admin())

        with pytest.raises(AuditLogIsAppendOnly):
            AuditLog.objects.all().update(action="SOMETHING_ELSE")

    def test_a_queryset_cannot_be_deleted(self) -> None:
        _row(actor=_admin())

        with pytest.raises(AuditLogIsAppendOnly):
            AuditLog.objects.all().delete()

    def test_the_row_is_still_there_afterwards(self) -> None:
        """The twin. Every test above would pass if `create` had quietly failed
        and there were nothing to update or delete in the first place."""
        _row(actor=_admin())

        for attempt in (
            lambda: AuditLog.objects.all().update(action="X"),
            lambda: AuditLog.objects.all().delete(),
        ):
            with pytest.raises(AuditLogIsAppendOnly):
                attempt()

        assert AuditLog.objects.count() == 1
        assert AuditLog.objects.get().action == "ACCESS_OVERRIDE_GRANTED"


class TestDeletingAnAdministrator:
    def test_an_audit_row_outlives_its_actor(self) -> None:
        """The reason `actor` is `SET_NULL` and the label sits beside it.

        This also proves the append-only queryset does not break user deletion:
        Django clears the foreign key through `sql.UpdateQuery` rather than
        `QuerySet.update`, which is a claim in the model's docstring and is
        worth checking rather than believing.
        """
        actor = _admin("leaving@example.test")
        _row(actor=actor, actor_label="leaving@example.test")

        actor.delete()

        row = AuditLog.objects.get()
        assert row.actor is None
        assert row.actor_label == "leaving@example.test"
        assert row.action == "ACCESS_OVERRIDE_GRANTED"


class TestTheDatabaseRefusesAnUnreadableRow:
    """Invariant 11. The service checks first; these make the check
    unavoidable for a caller that goes around it."""

    def test_a_row_naming_nobody_is_refused(self) -> None:
        with pytest.raises(IntegrityError, match="audit_names_who_acted"), transaction.atomic():
            _row(actor=_admin(), actor_label="")

    def test_a_row_naming_no_action_is_refused(self) -> None:
        with pytest.raises(IntegrityError, match="audit_names_what_happened"), transaction.atomic():
            _row(actor=_admin(), action="")

    def test_a_row_naming_no_target_is_refused(self) -> None:
        match = "audit_names_what_it_happened_to"

        with pytest.raises(IntegrityError, match=match), transaction.atomic():
            _row(actor=_admin(), target_id="")

    def test_a_row_naming_no_target_type_is_refused(self) -> None:
        match = "audit_names_what_it_happened_to"

        with pytest.raises(IntegrityError, match=match), transaction.atomic():
            _row(actor=_admin(), target_type="")

    def test_but_a_complete_row_is_accepted(self) -> None:
        """The positive twin. A constraint that refused everything would
        satisfy all four tests above."""
        assert _row(actor=_admin()).pk is not None


class TestTheIndexesExist:
    def test_the_support_ticket_question_is_indexed(self) -> None:
        """architecture.md §5.4: "what happened to this user?" — the query every
        access complaint starts as."""
        names = {index.name for index in AuditLog._meta.indexes}

        assert "audit_by_target_newest_first" in names

    def test_and_so_is_the_paginator_s_ordering(self) -> None:
        """§6.1 lists the audit log among the cursor-paginated collections, and
        cursor pagination orders by ("-created_at", "-pk"). An index that does
        not match that ordering is not used by it."""
        index = next(i for i in AuditLog._meta.indexes if i.name == "audit_paginated_feed")

        assert index.fields == ["-created_at", "-id"]
