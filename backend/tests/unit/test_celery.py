"""Contracts for the Celery application.

Written at M0, when there were no tasks and no schedule, to protect the wiring
and the two things ADR-001 §2.2 deliberately deferred. Both deferrals have now
ended — the first task at M5, Beat at M14 T4 — and each guard was converted
rather than deleted, into an assertion about the constraint the deferral was
protecting. Every docstring below says what it replaced.
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


class TestBeatHasArrived:
    """ADR-001 §2.2 settled that Beat runs inside the worker at a single
    replica, with its schedule in Postgres, and deferred the implementation
    until the first periodic task. M14 T4 is that task, and the dependency was
    approved under CLAUDE.md §5 on 2026-08-27.

    These three replace guards that asserted the deferral was still in force —
    written to fail once Beat arrived, which is exactly what they did. What
    they were protecting was never "no Beat"; it was invariant 5, and that is
    what they assert now.
    """

    def test_a_periodic_schedule_is_configured(self) -> None:
        """Replaces `test_no_periodic_schedule_is_configured`.

        The schedule lives in settings and `DatabaseScheduler` syncs it into
        Postgres on startup, so this dict is the source of truth and the
        database is its projection. Defining it only through Admin would mean a
        schedule that exists in production, was never code-reviewed, and is not
        in any backup anybody thought to test.
        """
        from config import celery_app

        assert celery_app.conf.beat_schedule

    def test_django_celery_beat_is_installed(self) -> None:
        """Replaces `test_django_celery_beat_is_not_installed`.

        It has to be in INSTALLED_APPS for its models — and therefore its
        tables — to exist. `CELERY_BEAT_SCHEDULER` naming a class in an
        uninstalled app fails at worker startup, in a container nobody is
        watching at 06:00.
        """
        from django.conf import settings

        assert "django_celery_beat" in settings.INSTALLED_APPS

    def test_the_schedule_is_not_kept_on_local_disk(self) -> None:
        """Replaces `test_beat_is_still_not_running`, and carries the reason
        that test existed for.

        The deferral was never about Beat being unwelcome. It was that Celery's
        default `PersistentScheduler` writes `celerybeat-schedule` to the local
        filesystem, which invariant 5 forbids on a stateless app tier — a
        container that loses that file loses its record of when each job last
        ran, and re-runs or skips accordingly. That is the thing to keep
        guarding now that Beat is here.
        """
        from django.conf import settings

        assert settings.CELERY_BEAT_SCHEDULER == "django_celery_beat.schedulers:DatabaseScheduler"


class TestTheFirstTaskNeededNoWiring:
    def test_the_first_task_is_discovered_without_wiring(self) -> None:
        """Replaces a guard asserting M0 had *no* tasks, written to fail once
        the first one arrived — which is what it did.

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

    def test_and_so_did_the_first_periodic_one(self) -> None:
        """The same property, nine milestones later. `apps/entitlements/tasks.py`
        is new in M14 T4 and `config/celery.py` was not touched to find it."""
        from config import celery_app

        celery_app.loader.import_default_modules()

        assert "apps.entitlements.tasks.alert_on_entitlement_drift" in celery_app.tasks
