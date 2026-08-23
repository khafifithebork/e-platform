from django.apps import AppConfig


class CoreConfig(AppConfig):
    name = "apps.core"
    label = "core"
    verbose_name = "Core"

    def ready(self) -> None:
        # Importing registers the checks. Nothing else in this module runs at
        # startup — invariant 5 forbids in-process schedulers, and `ready` is
        # where those get added by accident.
        from apps.core import checks  # noqa: F401
