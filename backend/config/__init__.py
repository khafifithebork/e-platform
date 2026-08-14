"""Project package.

Importing the Celery application here is what makes ``@shared_task`` work.
Without it, decorated tasks never attach to an app, and they fail to route at
runtime with no error at import — the single most common Django + Celery
misconfiguration.
"""

from config.celery import app as celery_app

__all__ = ("celery_app",)
