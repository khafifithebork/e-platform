"""The abuse cases M4's spec §6 lists that nothing else covers.

Cases 1 to 6 and 9 are proven by `test_gated_lesson.py` and `test_resolve_access.py`.
The three here are the ones with no natural home:

- **7** — no endpoint leaks another person's subscription or override.
- **8** — an instructor cannot grant themselves a preview.
- **10** — nothing outside `entitlements/` re-derives access.

Case 8 was a live bypass when this file was written, not a hypothetical. Case
10 is the only structural test in the suite: it guards invariant 3 against a
second implementation appearing anywhere, which no behavioural test can see.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import ClassVar

import pytest

from apps.accounts.models import Role

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


def _sign_in(client, email: str) -> None:
    client.post(
        "/api/v1/auth/login/",
        {"email": email, "password": PASSWORD},
        content_type="application/json",
    )


@pytest.fixture
def instructor(db):
    return _user("teacher@example.test", Role.INSTRUCTOR)


@pytest.fixture
def lesson(db, instructor):
    """A published, gated lesson."""
    from apps.catalog.models import Course, Language, Lesson, Section
    from apps.catalog.services import approve, submit_for_review

    admin = _user("approver@example.test", Role.ADMIN)
    language = Language.objects.create(code="es", name="Spanish", native_name="Español")
    course = Course.objects.create(
        slug="spanish", title="Spanish", language=language, level="A1", instructor=instructor
    )
    section = Section.objects.create(course=course, title="Greetings", position=1)
    lesson = Lesson.objects.create(
        course=course, section=section, slug="intro", title="Intro", body="Paid.", position=1
    )
    submit_for_review(course=course, by=instructor)
    approve(course=course, by=admin)
    return lesson


class TestAnInstructorCannotGrantThemselvesAPreview:
    """Abuse case 8, and it was real.

    `is_preview` was writable on the instructor lesson API from M3 T5. The
    field was inert then — nothing read it — so nothing looked wrong. M4 made
    it the resolver's first branch, allowed before the caller is even
    identified, which turned a harmless flag into a switch that makes a course
    free to the entire internet. The subscription that pays for it is shared
    across the catalogue, so this is not an instructor giving away only their
    own work.
    """

    def _url(self, lesson) -> str:
        return f"/api/v1/instructor/courses/{lesson.course_id}/lessons/{lesson.id}/"

    def test_patching_is_preview_is_ignored(self, client, lesson, instructor) -> None:
        _sign_in(client, "teacher@example.test")

        response = client.patch(
            self._url(lesson), {"is_preview": True}, content_type="application/json"
        )

        assert response.status_code == 200
        lesson.refresh_from_db()
        assert lesson.is_preview is False

    def test_creating_a_lesson_as_a_preview_is_ignored(self, client, lesson, instructor) -> None:
        """The create path is a separate code path and would otherwise be the
        way round the check above."""
        from apps.catalog.models import Lesson

        _sign_in(client, "teacher@example.test")

        client.post(
            f"/api/v1/instructor/courses/{lesson.course_id}/lessons/",
            {
                "section": str(lesson.section_id),
                "slug": "sneaky",
                "title": "Sneaky",
                "position": 2,
                "is_preview": True,
            },
            content_type="application/json",
        )

        assert Lesson.objects.get(slug="sneaky").is_preview is False

    def test_the_lesson_stays_gated_afterwards(self, client, lesson, instructor) -> None:
        """The assertion that matters. A flag that stayed False while the
        content became readable would be the same bug wearing a disguise."""
        _sign_in(client, "teacher@example.test")
        client.patch(self._url(lesson), {"is_preview": True}, content_type="application/json")
        client.post("/api/v1/auth/logout/")

        response = client.get(f"/api/v1/lessons/{lesson.id}/")

        assert response.status_code == 403
        assert b"Paid." not in response.content

    def test_an_admin_can_still_set_it(self, client, lesson) -> None:
        """Previews are a real product feature — chosen in review, by an admin,
        like publication (ADR-007 §2). Without this the fix above would have
        removed the capability rather than moved it."""
        from apps.catalog.admin import LessonAdmin
        from apps.catalog.models import Lesson

        assert "is_preview" not in getattr(LessonAdmin, "readonly_fields", [])

        Lesson.objects.filter(pk=lesson.pk).update(is_preview=True)
        assert client.get(f"/api/v1/lessons/{lesson.id}/").status_code == 200


class TestNoEndpointLeaksSomeoneElsesBilling:
    """Abuse case 7."""

    @pytest.fixture
    def subscriber(self, db):
        from apps.entitlements.providers.fake import FakeBillingProvider
        from apps.entitlements.services import start_subscription

        user = _user("payer@example.test")
        start_subscription(user=user, provider=FakeBillingProvider())
        return user

    def test_me_reports_only_your_own_entitlement(self, client, subscriber) -> None:
        """/auth/me/ takes no identifier at all, so there is nothing to
        tamper with — a stronger guarantee than filtering a parameter out."""
        _user("nosy@example.test")
        _sign_in(client, "nosy@example.test")

        access = client.get("/api/v1/auth/me/").json()["access"]

        assert access["reason"] == "NO_SUBSCRIPTION"

    def test_a_user_id_in_the_query_string_changes_nothing(self, client, subscriber) -> None:
        _user("nosy@example.test")
        _sign_in(client, "nosy@example.test")

        body = client.get(f"/api/v1/auth/me/?user={subscriber.pk}&id={subscriber.pk}").json()

        assert body["email"] == "nosy@example.test"
        assert body["access"]["reason"] == "NO_SUBSCRIPTION"

    def test_diagnostics_is_refused_to_the_subject_themselves(self, client, subscriber) -> None:
        _sign_in(client, "payer@example.test")

        assert (
            client.get(f"/api/v1/admin-api/users/{subscriber.pk}/diagnostics/").status_code == 403
        )

    def test_no_provider_identifier_reaches_a_subscriber(self, client, subscriber) -> None:
        """The provider's subscription id is a support handle. It appears in
        the admin diagnosis and must appear nowhere a subscriber can read."""
        _sign_in(client, "payer@example.test")

        assert b"fake_" not in client.get("/api/v1/auth/me/").content


class TestNothingElseRederivesAccess:
    """Abuse case 10 — invariant 3, enforced structurally.

    No behavioural test can see a second implementation of the entitlement
    rules; it only shows up as a disagreement, later, in production. So this
    reads the source: outside `apps/entitlements/`, nothing may compare a
    subscription status or import the status enum.

    Deliberately narrow. It is not a general ban on the word "subscription" —
    it targets the specific shape a duplicate takes, which is somebody writing
    `if subscription.status == "ACTIVE"` in a view because calling the resolver
    felt like overkill.
    """

    STATUS_LITERALS: ClassVar[set[str]] = {
        "TRIALING",
        "ACTIVE",
        "PAST_DUE",
        "CANCELED",
        "EXPIRED",
    }

    def _product_modules(self):
        apps_root = Path(__file__).resolve().parents[2] / "apps"
        for path in apps_root.rglob("*.py"):
            parts = path.parts
            if "entitlements" in parts or "migrations" in parts:
                continue
            yield path

    def test_no_module_outside_entitlements_imports_the_status_enum(self) -> None:
        offenders = []
        for path in self._product_modules():
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.ImportFrom)
                    and node.module
                    and ("entitlements.models" in node.module)
                ):
                    names = {alias.name for alias in node.names}
                    if names & {"Subscription", "SubscriptionStatus", "LIVE_STATUSES"}:
                        offenders.append(f"{path.name}: {sorted(names)}")

        assert not offenders, (
            "Access must be decided by resolve_access, not by reading subscription "
            f"state directly (invariant 3): {offenders}"
        )

    def test_no_module_outside_entitlements_compares_a_subscription_status(self) -> None:
        """Catches the literal form, which needs no import to write."""
        offenders = []
        for path in self._product_modules():
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source)
            for node in ast.walk(tree):
                if not isinstance(node, ast.Compare):
                    continue
                for operand in [node.left, *node.comparators]:
                    if (
                        isinstance(operand, ast.Constant)
                        and operand.value in self.STATUS_LITERALS
                        and "status" in ast.dump(node).lower()
                    ):
                        offenders.append(f"{path.name}:{node.lineno}")

        assert not offenders, (
            "A subscription status compared outside entitlements/ is a second "
            f"entitlement rule (invariant 3): {offenders}"
        )

    def test_the_guard_would_catch_a_real_duplicate(self, tmp_path) -> None:
        """ADR-006: a structural guard nobody has seen fail is not a guard.
        The offending shape is parsed directly rather than written into the
        tree, since planting a real file would fail the suite for everyone
        until it was removed."""
        offending = ast.parse('if subscription.status == "ACTIVE":\n    allow()\n')

        found = [
            node
            for node in ast.walk(offending)
            if isinstance(node, ast.Compare)
            and any(
                isinstance(operand, ast.Constant) and operand.value in self.STATUS_LITERALS
                for operand in [node.left, *node.comparators]
            )
            and "status" in ast.dump(node).lower()
        ]

        assert found, "the detector no longer recognises the pattern it exists to find"
