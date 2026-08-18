"""Shared test fixtures."""

import pytest
from django.core.cache import cache


@pytest.fixture(autouse=True)
def _clear_throttle_state():
    """Reset the cache between tests.

    DRF throttling counts requests in the default cache, which lives for the
    whole test process. Without this the counters accumulate across unrelated
    tests until the shared `anon` bucket is exhausted, and the failures land on
    whichever test happened to run once the limit was reached — a test that
    passes alone and fails in the suite, which is the worst kind.

    Autouse rather than opt-in: a test that needs this and does not know it is
    exactly the case that goes unnoticed.
    """
    cache.clear()
    yield
    cache.clear()
