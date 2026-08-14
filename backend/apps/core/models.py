"""Abstract base models shared across the project.

Everything here is abstract. ADR-003 settles that M1 creates no concrete models
and therefore no migrations, because the custom ``User`` model must exist
before the first migration is ever applied and it does not arrive until M2.
"""

import uuid

from django.db import models


class TimestampedModel(models.Model):
    """Records when a row was created and last changed.

    Both fields are non-editable on purpose. They describe what happened, not
    what someone would prefer had happened, and leaving them editable puts them
    into ModelForms and the admin where they can be quietly rewritten.
    """

    created_at = models.DateTimeField(auto_now_add=True, editable=False)
    updated_at = models.DateTimeField(auto_now=True, editable=False)

    class Meta:
        abstract = True


class UUIDPrimaryKeyModel(models.Model):
    """A UUID primary key, for anything whose identifier appears in a URL.

    architecture.md 5.2: sequential integers leak business information —
    ``/courses/47`` tells a competitor how many courses exist — and make
    enumeration attacks trivial.

    That section suggests UUIDv7, which is time-ordered and so keeps index
    locality. It is not available here: ``uuidv7()`` landed in PostgreSQL 18
    and the target is 16, and the standard library offers no generator, so
    adopting it would mean a third-party dependency for no benefit today.
    Revisit if the PostgreSQL version moves.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True
