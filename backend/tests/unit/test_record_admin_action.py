"""`record_admin_action`, and the one-writer guard.

The tests that matter are the refusals. A row written with a blank reason or a
mistyped action is permanent, looks like coverage, and answers nothing — so the
service refuses rather than degrades, and each refusal has a positive twin
proving it is not refusing everything.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from django.db import transaction

from apps.core.audit import AdminAction, NotAuditable, client_ip, record_admin_action
from apps.core.models import AuditLog

PASSWORD = "a-long-enough-passphrase"

pytestmark = pytest.mark.django_db


def _admin(email: str = "admin@example.test"):
    from apps.accounts.models import Role
    from apps.accounts.services import create_account

    user = create_account(email=email, password=PASSWORD)
    user.role = Role.ADMIN
    user.save(update_fields=["role"])
    return user


def _learner(email: str = "learner@example.test"):
    from apps.accounts.services import create_account

    return create_account(email=email, password=PASSWORD)


class TestWhatItWrites:
    def test_it_records_actor_target_reason_and_action(self) -> None:
        actor, target = _admin(), _learner()

        row = record_admin_action(
            actor=actor,
            action=AdminAction.ACCESS_OVERRIDE_GRANTED,
            target=target,
            reason="Double charged in July",
        )

        assert row.actor == actor
        assert row.actor_label == "admin@example.test"
        assert row.action == AdminAction.ACCESS_OVERRIDE_GRANTED
        assert (row.target_type, row.target_id) == ("user", str(target.pk))
        assert row.metadata["reason"] == "Double charged in July"

    def test_the_target_type_comes_from_the_instance(self) -> None:
        """A type/id pair supplied by the caller can disagree with itself. An
        instance cannot, and it also cannot name something that does not
        exist."""
        from apps.catalog.models import Language

        language = Language.objects.create(code="es", name="Spanish", native_name="Espanol")

        row = record_admin_action(
            actor=_admin(),
            action=AdminAction.ROLE_CHANGED,
            target=language,
            reason="Testing the target shape",
        )

        assert row.target_type == "language"
        assert row.target_id == str(language.pk)

    def test_extra_details_land_beside_the_reason(self) -> None:
        row = record_admin_action(
            actor=_admin(),
            action=AdminAction.ACCESS_OVERRIDE_GRANTED,
            target=_learner(),
            reason="Support ticket 41",
            days=14,
            ticket="SUP-41",
        )

        assert row.metadata == {"reason": "Support ticket 41", "days": 14, "ticket": "SUP-41"}

    def test_the_reason_is_stripped(self) -> None:
        row = record_admin_action(
            actor=_admin(),
            action=AdminAction.REFUND_ISSUED,
            target=_learner(),
            reason="  padded  ",
        )

        assert row.metadata["reason"] == "padded"


class TestWhatItRefuses:
    def test_an_action_with_no_actor(self) -> None:
        with pytest.raises(NotAuditable, match="who took it"):
            record_admin_action(
                actor=None,
                action=AdminAction.REFUND_ISSUED,
                target=_learner(),
                reason="whatever",
            )

    def test_an_unknown_action(self) -> None:
        """A typo produces a permanent row nobody will ever find, because
        nobody searches for the spelling that was not intended."""
        with pytest.raises(NotAuditable, match="not a known administrative action"):
            record_admin_action(
                actor=_admin(),
                action="ACCESS_OVERRIDE_GRANT",
                target=_learner(),
                reason="A near miss",
            )

    @pytest.mark.parametrize("reason", ["", "   "])
    def test_an_action_with_no_reason(self, reason: str) -> None:
        with pytest.raises(NotAuditable, match="record why"):
            record_admin_action(
                actor=_admin(),
                action=AdminAction.REFUND_ISSUED,
                target=_learner(),
                reason=reason,
            )

    def test_an_action_with_no_target(self) -> None:
        with pytest.raises(NotAuditable, match="acted on"):
            record_admin_action(
                actor=_admin(),
                action=AdminAction.REFUND_ISSUED,
                target=None,
                reason="whatever",
            )

    def test_an_unsaved_target(self) -> None:
        """An instance with no primary key names nothing."""
        from apps.catalog.models import Language

        with pytest.raises(NotAuditable, match="acted on"):
            record_admin_action(
                actor=_admin(),
                action=AdminAction.ROLE_CHANGED,
                target=Language(code="xx", name="X", native_name="X"),
                reason="whatever",
            )

    def test_and_nothing_is_written_when_it_refuses(self) -> None:
        """The twin that matters. A refusal that wrote a partial row first
        would be worse than no refusal at all."""
        target = _learner()

        for call in (
            lambda: record_admin_action(
                actor=None, action=AdminAction.REFUND_ISSUED, target=target, reason="x"
            ),
            lambda: record_admin_action(
                actor=_admin("a@example.test"), action="NONSENSE", target=target, reason="x"
            ),
        ):
            with pytest.raises(NotAuditable):
                call()

        assert not AuditLog.objects.exists()

    def test_but_a_complete_action_is_accepted(self) -> None:
        """The positive twin for the whole class."""
        assert (
            record_admin_action(
                actor=_admin(),
                action=AdminAction.REFUND_ISSUED,
                target=_learner(),
                reason="Refunded on request",
            ).pk
            is not None
        )


class TestItSharesTheCallersTransaction:
    def test_a_rolled_back_action_leaves_no_row(self) -> None:
        """The reason this is called from the service and not the view.

        An audit row describing a write that did not happen is a false record,
        and it is the shape you get from auditing at the edge — the view knows
        what it asked for, not what survived.
        """
        actor, target = _admin(), _learner()

        with pytest.raises(RuntimeError), transaction.atomic():
            record_admin_action(
                actor=actor,
                action=AdminAction.ACCESS_OVERRIDE_GRANTED,
                target=target,
                reason="This transaction is about to fail",
            )
            raise RuntimeError("the write failed")

        assert not AuditLog.objects.exists()

    def test_and_a_committed_one_leaves_exactly_one(self) -> None:
        actor, target = _admin(), _learner()

        with transaction.atomic():
            record_admin_action(
                actor=actor,
                action=AdminAction.ACCESS_OVERRIDE_GRANTED,
                target=target,
                reason="This one succeeds",
            )

        assert AuditLog.objects.count() == 1


class TestTheAddress:
    def test_it_is_recorded_when_there_is_a_request(self, rf) -> None:
        request = rf.post("/admin-api/whatever/", REMOTE_ADDR="203.0.113.9")

        row = record_admin_action(
            actor=_admin(),
            action=AdminAction.REFUND_ISSUED,
            target=_learner(),
            reason="From a request",
            request=request,
        )

        assert row.ip_address == "203.0.113.9"

    def test_a_forwarded_header_is_not_believed(self, rf) -> None:
        """`X-Forwarded-For` is set by the client. Reading it without knowing
        how many proxies to strip records an attacker-supplied string as fact,
        which in an audit log is worse than recording nothing.
        """
        request = rf.post(
            "/admin-api/whatever/",
            REMOTE_ADDR="203.0.113.9",
            HTTP_X_FORWARDED_FOR="198.51.100.1",
        )

        assert client_ip(request) == "203.0.113.9"

    def test_there_is_none_without_a_request(self) -> None:
        """A management command has no address, and inventing one would be a
        fabricated fact in the one table that exists to hold facts."""
        row = record_admin_action(
            actor=_admin(),
            action=AdminAction.REFUND_ISSUED,
            target=_learner(),
            reason="From a management command",
        )

        assert row.ip_address is None


class TestOneWriter:
    """`record_admin_action` is the only thing that creates an audit row.

    Not style. A trail assembled by several callers with slightly different
    ideas of what `target_id` holds is a table nobody can query, and the
    validation above is only worth having if it cannot be walked around.
    """

    @staticmethod
    def _creates_audit_rows(tree: ast.AST) -> list[int]:
        found = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if node.func.attr != "create":
                continue
            value = node.func.value
            if isinstance(value, ast.Attribute) and value.attr == "objects":
                model = value.value
                if isinstance(model, ast.Name) and model.id == "AuditLog":
                    found.append(node.lineno)
        return found

    def test_nothing_else_in_the_codebase_creates_one(self) -> None:
        apps_root = Path(__file__).resolve().parents[2] / "apps"
        allowed = apps_root / "core" / "audit.py"
        offenders = []

        for path in apps_root.rglob("*.py"):
            if "migrations" in path.parts or path == allowed:
                continue
            for line in self._creates_audit_rows(ast.parse(path.read_text(encoding="utf-8"))):
                offenders.append(f"{path.relative_to(apps_root)}:{line}")

        assert not offenders, (
            f"Audit rows are written by record_admin_action and nowhere else. {offenders}"
        )

    def test_the_guard_recognises_what_it_looks_for(self) -> None:
        """ADR-006: a guard nobody has watched fire is not a guard."""
        offending = ast.parse("AuditLog.objects.create(action='X')\n")

        assert self._creates_audit_rows(offending) == [1]

    def test_and_the_one_permitted_writer_really_does_write_one(self) -> None:
        """The twin. If `audit.py` stopped calling `create`, the guard above
        would pass over an empty codebase and prove nothing."""
        audit = Path(__file__).resolve().parents[2] / "apps" / "core" / "audit.py"

        assert self._creates_audit_rows(ast.parse(audit.read_text(encoding="utf-8")))
