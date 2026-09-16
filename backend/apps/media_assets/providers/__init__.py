"""Choosing a video provider. The one file a swap should touch.

`video.py` says swapping a provider is "one file" and `fake_video.video_provider`
said it was "the one place that chooses between them". **Neither was true**, and
the reason is that the factory lived inside the concrete provider's own module:
every call site read

    from apps.media_assets.providers.fake_video import video_provider

which imports the fake by name. Adding a real provider meant editing every one
of those imports, and the failure of missing one is the worst available — some
paths minting real playback tokens and others minting fake ones, with nothing
raising. Moving the choice here is what makes the claim true; the guard in
`tests/unit/test_provider_selection.py` is what keeps it true.

**A function, not a module-level instance**, so settings are read when it is
called rather than at import. That is what lets a test override the setting,
and it is the property the original docstring named and kept.
"""

from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from apps.media_assets.providers.fake_video import FakeVideoProvider
from apps.media_assets.providers.video import VideoProvider

# Every implementation, by the name `VIDEO_PROVIDER` selects.
#
# A registry rather than a chain of `if`s: adding a provider is one entry and
# one import, and the set of valid names is readable in one place — which is
# also what lets an unknown name say what it should have been.
PROVIDERS: dict[str, type] = {
    "fake": FakeVideoProvider,
}


def video_provider() -> VideoProvider:
    """The provider this process should use.

    **An unknown name raises rather than falling back to the fake**, and that
    is the whole reason this function has a failure path. A silent fallback
    would mean a production deployment with a typo in one environment variable
    quietly minting fake playback tokens against a real catalogue: every
    entitlement check would pass, every token would be worthless, and nothing
    would raise until a learner pressed play.

    `ImproperlyConfigured` rather than a plain error because Django surfaces it
    at startup with the setting named, which is where a misconfiguration should
    be discovered.
    """
    name = settings.VIDEO_PROVIDER

    try:
        implementation = PROVIDERS[name]
    except KeyError:
        raise ImproperlyConfigured(
            f"VIDEO_PROVIDER is {name!r}, which is not a video provider. "
            f"Known providers: {', '.join(sorted(PROVIDERS))}."
        ) from None

    return implementation()
