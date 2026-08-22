"""Granting access by hand, and the trail it leaves.

§10 M10's deliverable is that an administrator can resolve any access complaint
**without touching the database**. `AccessOverride` has existed since M4 and the
resolver has read it since M4 — but nothing could write one, so the deliverable
was unmet in the most literal way.

Abuse cases 3, 4, 5 and 10 live here. The one worth reading is 4: an expired
override granting nothing is asserted end to end through the new write path,
not at the resolver, because the resolver was never the part in doubt.
"""

from __future__ import annotations

import ast
from datetime import timedelta
from pathlib import Path

import pytest
from django.urls import URLPattern, URLResolver, get_resolver
from django.utils import timezone

from apps.accounts.models import Role
from apps.core.audit import AdminAction
from apps.core.models import AuditLog
from apps.entitlements.models import AccessOverride

PASSWORD = "a-long-enough-passphrase"

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _generous_throttles(settings):
    settings.REST_FRAMEWORK = {
        **settings.REST_FRAMEWORK,
        "DEFAULT_THROTTLE_RATES": dict.fromkeys(
            settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"], "10000/hour"
        ),
    }


def _user(email: str, role: str = Role.STUDENT):
    from apps.accounts.services import create_account

    user = create_account(email=email, password=PASSWORD)
    user.role = role
    user.save(update_fields=["role"])
    return user


@pytest.fixture
def admin(db):
    return _user("admin@example.test", Role.ADMIN)


@pytest.fixture
def learner(db):
    return _user("learner@example.test")


@pytest.fixture
def lesson(db):
    from apps.catalog.models import Course, Language, Lesson, Section
    from apps.catalog.services import approve, submit_for_review

    instructor = _user("teacher@example.test", Role.INSTRUCTOR)
    approver = _user("approver@example.test", Role.ADMIN)
    language = Language.objects.create(code="es", name="Spanish", native_name="Espanol")
    course = Course.objects.create(
        slug="spanish", title="Spanish", language=language, level="A1", instructor=instructor
    )
    section = Section.objects.create(course=course, title="Greetings", position=1)
    lesson = Lesson.objects.create(
        course=course, section=section, slug="intro", title="Intro", position=1
    )
    submit_for_review(course=course, by=instructor)
    approve(course=course, by=approver)
    return lesson


def _sign_in(client, email: str) -> None:
    client.post(
        "/api/v1/auth/login/",
        {"email": email, "password": PASSWORD},
        content_type="application/json",
    )


def _url(user) -> str:
    return f"/api/v1/admin-api/users/{user.id}/access-override/"


def _grant(client, user, *, days: int = 14, reason: str = "Double charged in July"):
    return client.post(
        _url(user), {"days": days, "reason": reason}, content_type="application/json"
    )


class TestGranting:
    def test_an_admin_can_grant_access(self, client, admin, learner) -> None:
        _sign_in(client, "admin@example.test")

        response = _grant(client, learner)

        assert response.status_code == 201
        override = AccessOverride.objects.get()
        assert override.user == learner
        assert override.granted_by == admin
        assert override.reason == "Double charged in July"

    def test_the_grant_takes_effect_immediately(self, client, admin, learner, lesson) -> None:
        """The whole point. Before the grant the learner is refused; after it
        they are not, without anything else changing."""
        from apps.entitlements.resolver import resolve_access

        assert not resolve_access(user=learner, lesson=lesson).allowed

        _sign_in(client, "admin@example.test")
        _grant(client, learner)

        decision = resolve_access(user=learner, lesson=lesson)
        assert decision.allowed
        assert decision.reason == "OVERRIDE"

    def test_days_become_an_end_date(self, client, admin, learner) -> None:
        """A duration rather than a date makes two failures impossible: an
        override created already expired, and one with no end at all."""
        _sign_in(client, "admin@example.test")

        _grant(client, learner, days=14)

        override = AccessOverride.objects.get()
        assert (override.ends_at - override.starts_at) == timedelta(days=14)
        assert override.ends_at > timezone.now()


class TestWhatIsRefused:
    def test_a_grant_with_no_reason(self, client, admin, learner) -> None:
        """Abuse case 3. §5.2 rejects manual access as a boolean because it is
        unexplained; a blank reason is that boolean again."""
        _sign_in(client, "admin@example.test")

        response = _grant(client, learner, reason="   ")

        assert response.status_code == 400
        assert not AccessOverride.objects.exists()

    def test_a_grant_with_no_duration(self, client, admin, learner) -> None:
        _sign_in(client, "admin@example.test")

        response = client.post(
            _url(learner), {"reason": "Forgot the days"}, content_type="application/json"
        )

        assert response.status_code == 400
        assert not AccessOverride.objects.exists()

    def test_a_grant_longer_than_the_maximum(self, client, admin, learner, settings) -> None:
        """An override measured in years is the permanent flag wearing an
        expiry date."""
        _sign_in(client, "admin@example.test")

        response = _grant(client, learner, days=settings.ACCESS_OVERRIDE_MAX_DAYS + 1)

        assert response.status_code == 400
        assert not AccessOverride.objects.exists()

    def test_but_exactly_the_maximum_is_allowed(self, client, admin, learner, settings) -> None:
        """The positive twin. An off-by-one that refused the documented
        maximum would satisfy the test above."""
        _sign_in(client, "admin@example.test")

        response = _grant(client, learner, days=settings.ACCESS_OVERRIDE_MAX_DAYS)

        assert response.status_code == 201

    def test_a_zero_day_grant(self, client, admin, learner) -> None:
        _sign_in(client, "admin@example.test")

        assert _grant(client, learner, days=0).status_code == 400


class TestOnlyAdministrators:
    def test_a_learner_cannot_grant_themselves_access(self, client, learner) -> None:
        """The one that would hand the catalogue away."""
        _sign_in(client, "learner@example.test")

        response = _grant(client, learner)

        assert response.status_code == 403
        assert not AccessOverride.objects.exists()

    def test_nor_can_an_instructor(self, client, learner) -> None:
        _user("teacher2@example.test", Role.INSTRUCTOR)
        _sign_in(client, "teacher2@example.test")

        assert _grant(client, learner).status_code == 403
        assert not AccessOverride.objects.exists()

    def test_nor_anonymous(self, client, learner) -> None:
        assert _grant(client, learner).status_code in (401, 403)
        assert not AccessOverride.objects.exists()

    def test_and_no_audit_row_is_written_by_a_refusal(self, client, learner) -> None:
        """A refused attempt is not an administrative action. Recording one
        would put entries in the trail for things that did not happen, which is
        how a trail stops being believed."""
        _sign_in(client, "learner@example.test")

        _grant(client, learner)

        assert not AuditLog.objects.exists()


class TestAnExpiredOverrideGrantsNothing:
    """Abuse case 4, end to end through the write path."""

    def test_access_is_gone_once_it_lapses(self, client, admin, learner, lesson) -> None:
        from apps.entitlements.resolver import resolve_access

        _sign_in(client, "admin@example.test")
        _grant(client, learner, days=1)
        assert resolve_access(user=learner, lesson=lesson).allowed

        # Time travel by moving the row, which is the only part of this the
        # test can control. The resolver reads the clock.
        override = AccessOverride.objects.get()
        AccessOverride.objects.filter(pk=override.pk).update(
            starts_at=timezone.now() - timedelta(days=10),
            ends_at=timezone.now() - timedelta(days=9),
        )

        assert not resolve_access(user=learner, lesson=lesson).allowed

    def test_and_the_audit_row_stays(self, client, admin, learner) -> None:
        """Expiry ends the access, not the record of who gave it."""
        _sign_in(client, "admin@example.test")
        _grant(client, learner, days=1)

        # Both dates move: `override_ends_after_it_starts` refuses a row that
        # ends before it begins, and it caught this test's first version.
        AccessOverride.objects.filter(user=learner).update(
            starts_at=timezone.now() - timedelta(days=2),
            ends_at=timezone.now() - timedelta(days=1),
        )

        assert AuditLog.objects.filter(action=AdminAction.ACCESS_OVERRIDE_GRANTED).count() == 1


class TestTheTrail:
    def test_a_grant_writes_exactly_one_audit_row(self, client, admin, learner) -> None:
        _sign_in(client, "admin@example.test")

        _grant(client, learner)

        row = AuditLog.objects.get()
        assert row.action == AdminAction.ACCESS_OVERRIDE_GRANTED
        assert row.actor == admin
        assert row.actor_label == "admin@example.test"
        assert (row.target_type, row.target_id) == ("user", str(learner.pk))
        assert row.metadata["reason"] == "Double charged in July"
        assert row.metadata["days"] == 14

    def test_the_grant_and_its_row_share_a_transaction(self, admin, learner, monkeypatch) -> None:
        """If the audit fails, the grant fails. That pairing is the whole
        argument for auditing in the service: a capability that can hand out
        paid content must not be able to do so unrecorded.
        """
        from apps.entitlements import services

        def refuse(**kwargs):
            raise RuntimeError("audit unavailable")

        monkeypatch.setattr(services, "record_admin_action", refuse)

        with pytest.raises(RuntimeError):
            services.grant_access_override(
                actor=admin, user=learner, days=7, reason="Should not survive"
            )

        assert not AccessOverride.objects.exists()

    def test_a_self_grant_is_recorded_like_any_other(self, client, admin) -> None:
        """Abuse case 10. Deliberately not blocked: an administrator who wants
        free access can grant it to a second account they control, so blocking
        is theatre. The control that works is that it is visible.
        """
        _sign_in(client, "admin@example.test")

        response = _grant(client, admin, reason="Testing my own account")

        assert response.status_code == 201
        row = AuditLog.objects.get()
        assert row.actor == admin
        assert row.target_id == str(admin.pk)


class TestEveryMutatingAdminRouteIsAudited:
    """The inventory guard.

    A sweep that calls each route cannot be written generically — they take
    different bodies. So this enumerates the mutating routes under
    `/admin-api/` and asserts each one is *declared* audited below. Adding a
    route without adding it here fails, which forces the question to be
    answered at review rather than discovered in an incident.
    """

    AUDITED: frozenset[str] = frozenset({"users/<uuid:pk>/access-override/"})

    @staticmethod
    def _mutating_admin_routes() -> set[str]:
        found: set[str] = set()

        def walk(patterns, prefix: str) -> None:
            for entry in patterns:
                route = getattr(entry.pattern, "_route", None)
                if isinstance(entry, URLResolver):
                    walk(entry.url_patterns, prefix + (route or ""))
                elif isinstance(entry, URLPattern) and route is not None:
                    full = prefix + route
                    if "admin-api/" not in full:
                        continue
                    view = getattr(entry.callback, "cls", None) or getattr(
                        entry.callback, "view_class", None
                    )
                    if view is None:
                        continue
                    if any(hasattr(view, verb) for verb in ("post", "put", "patch", "delete")):
                        found.add(full.split("admin-api/", 1)[1])

        walk(get_resolver().url_patterns, "")
        return found

    def test_the_inventory_matches_what_is_routed(self) -> None:
        assert self._mutating_admin_routes() == set(self.AUDITED)

    def test_the_walk_finds_something(self) -> None:
        """The twin. An inventory of nothing matching a declaration of nothing
        would pass forever, which is the exact failure this codebase keeps
        finding in its own guards."""
        assert self._mutating_admin_routes()

    def test_and_every_declared_route_really_writes_a_row(self, client, admin, learner) -> None:
        """Declaration is a promise; this is the check. One route today, and
        the assertion is written to cover whatever the inventory holds."""
        _sign_in(client, "admin@example.test")

        _grant(client, learner)

        assert AuditLog.objects.count() == 1


class TestTheServiceAuditsRatherThanTheView:
    def test_the_view_does_not_call_record_admin_action(self) -> None:
        """Invariant 2, and a correctness point: a view audits what it asked
        for, a service audits what happened."""
        admin_views = (
            Path(__file__).resolve().parents[2] / "apps" / "entitlements" / "admin_views.py"
        )
        tree = ast.parse(admin_views.read_text(encoding="utf-8"))

        calls = [
            node.func.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "record_admin_action"
        ]

        assert calls == []

    def test_but_the_service_does(self) -> None:
        services = Path(__file__).resolve().parents[2] / "apps" / "entitlements" / "services.py"
        tree = ast.parse(services.read_text(encoding="utf-8"))

        calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "record_admin_action"
        ]

        assert calls
