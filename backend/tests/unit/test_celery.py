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

    def test_the_first_task_is_discovered_without_wiring(self) -> None:
        """Replaces a guard asserting M0 had *no* tasks, written to fail once
        the first one arrived — which is what it just did.

        The point it was protecting still holds and is what this now checks:
        ``autodiscover_tasks`` was called in M0 precisely so the first
        ``tasks.py`` needed no change to ``config/celery.py``, and it did not.
        """
        from config import celery_app

        # Autodiscovery is lazy — the registry is empty until a worker starts
        # or something forces it. Forcing it here is the actual assertion:
        # Celery finds apps/media_assets/tasks.py from INSTALLED_APPS alone.
        celery_app.loader.import_default_modules()
        project_tasks = [name for name in celery_app.tasks if not name.startswith("celery.")]

        assert "apps.media_assets.tasks.process_media_asset" in project_tasks

    def test_beat_is_still_not_running(self) -> None:
        """A task is not a *periodic* task. ADR-001 §2.2 defers Beat until the
        first scheduled job, and processing is enqueued by a request rather
        than a clock — so nothing here brings Beat forward."""
        from config import celery_app

        assert not celery_app.conf.beat_schedule
