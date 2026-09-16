"""One file chooses a provider, and nothing else may import a concrete one.

**This is the guard two docstrings already claimed existed.**
`providers/video.py` says swapping a provider is "one file", and the factories
in `fake_video.py` and `fake.py` each said they were "the one place that
chooses between them — the claim rests on nothing else importing a concrete
provider directly".

Nothing asserted it, and it was false: each factory lived *inside* the concrete
provider's own module, so every call site imported the fake by name. ADR-023 §1
names this exact shape — a control a document describes and nothing enforces —
and it has now been found six times in this repository.

**What the false version would have cost.** A real provider arrives, three
import lines change, one is missed. That path keeps constructing the fake, so
it mints playback tokens that verify against our own key and nothing else.
Every entitlement check still passes. Nothing raises. It surfaces when a
learner presses play.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from django.core.exceptions import ImproperlyConfigured

from apps.media_assets.providers import PROVIDERS as VIDEO_PROVIDERS
from apps.media_assets.providers import video_provider
from apps.media_assets.providers.video import VideoProvider
from apps.transcripts.providers import PROVIDERS as TRANSCRIPTION_PROVIDERS
from apps.transcripts.providers import transcription_provider
from apps.transcripts.providers.base import TranscriptionProvider

APPS_ROOT = Path(__file__).resolve().parents[2] / "apps"

# The modules permitted to name a concrete implementation: the package that
# chooses, and the implementation itself.
SEAMS = {
    ("media_assets", "__init__.py"),
    ("media_assets", "fake_video.py"),
    ("transcripts", "__init__.py"),
    ("transcripts", "fake.py"),
}

# **Full dotted paths, not last segments.** Matching on the last segment alone
# conflates three different modules named `fake` — video's, transcription's and
# M4's billing provider — and the first version of this guard duly reported
# `entitlements/management/commands/billing.py` as a transcription violation.
CONCRETE_VIDEO_MODULES = {"apps.media_assets.providers.fake_video"}
CONCRETE_TRANSCRIPTION_MODULES = {"apps.transcripts.providers.fake"}

# **Billing is deliberately absent.** `apps.entitlements.providers` has no
# factory at all — one management command imports `FakeBillingProvider`
# directly — so there is no seam here to enforce yet. Building one is M8's, and
# §5 names working ahead into a later milestone as needing approval. Recorded
# in `docs/spikes/video-provider.md` §2 so M8 finds it rather than rediscovers
# it.


class TestTheFactoryChooses:
    def test_the_default_is_the_fake(self) -> None:
        """No provider has been chosen or paid for — ADR-012 §1. The default
        must be the one that costs nothing and reaches no vendor."""
        assert isinstance(video_provider(), VideoProvider)
        assert video_provider().name == "fake"

    def test_it_reads_the_setting_when_called(self, settings) -> None:
        """A module-level instance would freeze the choice at import and make
        this untestable. The original factory's docstring named this property;
        it is kept."""
        settings.VIDEO_PROVIDER = "fake"

        assert video_provider() is not video_provider()

    def test_an_unknown_name_raises_rather_than_falling_back(self, settings) -> None:
        """**The failure this function exists to have.** A silent fallback
        would mean one typo in one environment variable quietly minting fake
        playback tokens against a real catalogue — every entitlement check
        passing, every token worthless, nothing raising until somebody pressed
        play."""
        settings.VIDEO_PROVIDER = "mux"

        with pytest.raises(ImproperlyConfigured, match="not a video provider"):
            video_provider()

    def test_the_refusal_says_what_would_have_worked(self, settings) -> None:
        """An error naming the bad value and not the valid ones sends the
        reader to the source to find out."""
        settings.VIDEO_PROVIDER = "typo"

        with pytest.raises(ImproperlyConfigured, match="fake"):
            video_provider()

    def test_every_registered_provider_satisfies_the_protocol(self) -> None:
        """The registry is what a future provider is added to, so it is the
        place to check the contract rather than trusting the author."""
        for name, implementation in VIDEO_PROVIDERS.items():
            assert isinstance(implementation(), VideoProvider), name


class TestNothingElseImportsAConcreteProvider:
    """The claim, finally asserted.

    Parsed from the syntax tree rather than grepped, because every structural
    check in this repository has at least once matched its own explanatory
    comment, and a syntax tree holds none.
    """

    @staticmethod
    def _modules() -> list[Path]:
        return [path for path in APPS_ROOT.rglob("*.py") if "migrations" not in path.parts]

    @classmethod
    def _importers_of(cls, modules: set[str]) -> list[str]:
        offenders = []
        for path in cls._modules():
            if (path.parent.parent.name, path.name) in SEAMS and path.parent.name == "providers":
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module and node.module in modules:
                    offenders.append(f"{path.relative_to(APPS_ROOT).as_posix()}")
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name in modules:
                            offenders.append(f"{path.relative_to(APPS_ROOT).as_posix()}")
        return sorted(set(offenders))

    def test_no_module_outside_the_seam_imports_the_fake_video_provider(self) -> None:
        offenders = self._importers_of(CONCRETE_VIDEO_MODULES)

        assert offenders == [], (
            "Import `video_provider` from `apps.media_assets.providers` instead. "
            "Naming a concrete provider directly is what makes a swap more than "
            f"one file. {offenders}"
        )

    def test_the_guard_visited_the_modules_it_claims_to(self) -> None:
        """A path that matched nothing would make the test above pass by
        finding zero importers of anything."""
        assert len(self._modules()) > 50

    def test_the_guard_would_catch_a_real_importer(self) -> None:
        """The twin, checked against the pattern rather than by planting a file
        — planting one would fail the suite for everyone until it was removed."""
        planted = ast.parse(
            "from apps.media_assets.providers.fake_video import FakeVideoProvider\n"
        )
        found = [
            node
            for node in ast.walk(planted)
            if isinstance(node, ast.ImportFrom)
            and node.module
            and node.module in CONCRETE_VIDEO_MODULES
        ]

        assert found


class TestTranscriptionHasTheSameSeam:
    """The twin app, and the quieter failure of the two.

    A path left on the fake video provider breaks when somebody presses play.
    A path left on the fake *transcription* provider produces realistic
    segments — deliberately, so M6 could test its review workflow against
    something worth reviewing — which a human then approves. It would publish
    invented subtitles under a reviewer's name.
    """

    def test_the_default_is_the_fake(self) -> None:
        assert isinstance(transcription_provider(), TranscriptionProvider)

    def test_an_unknown_name_raises_rather_than_falling_back(self, settings) -> None:
        settings.TRANSCRIPTION_PROVIDER = "deepgram"

        with pytest.raises(ImproperlyConfigured, match="not a transcription provider"):
            transcription_provider()

    def test_every_registered_provider_satisfies_the_protocol(self) -> None:
        for name, implementation in TRANSCRIPTION_PROVIDERS.items():
            assert isinstance(implementation(), TranscriptionProvider), name

    def test_no_module_outside_the_seam_imports_the_fake(self) -> None:
        offenders = TestNothingElseImportsAConcreteProvider._importers_of(
            CONCRETE_TRANSCRIPTION_MODULES
        )

        assert offenders == [], (
            "Import `transcription_provider` from `apps.transcripts.providers` "
            f"instead. {offenders}"
        )
