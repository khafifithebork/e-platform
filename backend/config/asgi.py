"""ASGI entrypoint.

Invariant 12 and ADR-001 section 2.4: this project runs under ASGI only. There
is deliberately no companion ``wsgi.py``, so reverting to WSGI requires a
decision rather than an import.

The settings default here is ``production``, unlike ``manage.py`` which
defaults to ``local``. That asymmetry is intentional: ``manage.py`` is a
developer tool, whereas this module is the entrypoint a container runs. If the
environment fails to specify a settings module, the safe outcome is to demand
full production configuration and fail fast, not to quietly serve traffic with
development settings.
"""

import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")

from django.core.asgi import get_asgi_application

application = get_asgi_application()
