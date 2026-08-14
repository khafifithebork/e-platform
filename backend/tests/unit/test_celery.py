"""Contracts for the Celery application.

M0 defines no tasks. What these tests protect is the wiring and, more
importantly, the two things ADR-001 section 2.2 deliberately defers.
"""

from __future__ import annotations


class TestCeleryApplication:
    def test_app_is_exported_from_the_config_package(self) -> None:
        """Without this export, @shared_task decorators never attach to an app
        and tasks silently fail to route. It is the single most common
        Django + Celery misconfiguration, so it gets a test."""
        from config import celery_app

        assert celery_app is not None

    def test_broker_is_read_from_django_settings(self) -> None:
        """The broker URL must come from settings, never be hardcoded here."""
        from django.conf import settings

        from config import celery_app

        assert celery_app.conf.broker_url == settings.CELERY_BROKER_URL

    def test_celery_namespace_is_wired_to_django_settings(self) -> None:
        """Proves config_from_object with the CELERY_ namespace actually
        applies. task_acks_late is set in base settings as CELERY_TASK_ACKS_LATE;
        if the namespace were wrong this would silently stay at its default."""
        from config import celery_app

        assert celery_app.conf.task_acks_late is True


class TestBeatIsDeferred:
    """ADR-001 section 2.2 settles that Beat runs inside the worker at a single
    replica — but the implementation waits for the first periodic task.

    Celery's default scheduler persists its schedule to a local file, which
    invariant 5 forbids. django-celery-beat stores it in Postgres instead, and
    brings models and migrations with it. M0 applies no migrations, so both
    land together later.
    """

    def test_no_periodic_schedule_is_configured(self) -> None:
        from config import celery_app

        assert not celery_app.conf.beat_schedule

    def test_django_celery_beat_is_not_installed(self) -> None:
        from django.conf import settings

        assert "django_celery_beat" not in settings.INSTALLED_APPS

    def test_no_tasks_are_registered_yet(self) -> None:
        """M0 ships no tasks. Celery registers a handful of its own built-ins,
        which all live under the celery. prefix."""
        from config import celery_app

        project_tasks = [name for name in celery_app.tasks if not name.startswith("celery.")]

        assert project_tasks == []
