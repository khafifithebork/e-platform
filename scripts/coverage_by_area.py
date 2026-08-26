"""Report branch coverage grouped the way architecture.md §8.1 talks about it.

§8.1 opens with "test coverage percentage is a vanity metric — test by blast
radius", and then gives a target per *area*. A single total for the whole
backend answers a question nobody asked: 97% overall is compatible with an
untested permission class, because the permission classes are a hundred lines
out of three thousand.

So this groups modules into the areas §8.1 names and reports each one. It is
deliberately a **report**, not a gate. ADR-022 §2: a percentage target is a
judgement about shape rather than a threshold, and coverage moves when code is
deleted or a branch is simplified — neither of which is a regression. The one
area §8.1 calls 100% is gated separately in CI, where failing is correct.

Run it after a coverage run:

    python -m pytest --cov=apps --cov-branch
    python -m coverage json -o coverage.json
    python ../scripts/coverage_by_area.py coverage.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Each area is (label, target as written in §8.1, predicate over the module
# path). Order matters: the first match wins, so the narrow areas come first.
#
# `resolver` is listed although CI already gates it, because a report that
# silently omitted the one area with a hard target would be the more confusing
# document.
AREAS: list[tuple[str, str, object]] = [
    (
        "Entitlement resolver",
        "100% branch",
        lambda p: p.endswith("entitlements/resolver.py"),
    ),
    (
        "Billing webhooks",
        "100% branch",
        lambda p: "webhook" in p and ("billing" in p or "entitlements" in p),
    ),
    (
        "Permissions / object scoping",
        "~95%",
        lambda p: p.endswith(("permissions.py", "selectors.py")),
    ),
    (
        "Services layer",
        "~85%",
        lambda p: p.endswith(("services.py", "audit.py")),
    ),
    (
        "Media / transcription pipeline",
        "happy path + every failure mode",
        lambda p: "media_assets/" in p or "transcripts/" in p,
    ),
    (
        "Serializers, views",
        "~70%",
        lambda p: p.endswith(("serializers.py", "views.py")),
    ),
]


def _normalise(path: str) -> str:
    return path.replace("\\", "/")


def main(report_path: str) -> int:
    data = json.loads(Path(report_path).read_text(encoding="utf-8"))
    files = {_normalise(name): entry for name, entry in data["files"].items()}

    print(f"{'Area':<38}{'Target':<36}{'Measured':>10}{'Files':>7}")
    print("-" * 91)

    claimed: set[str] = set()
    for label, target, matches in AREAS:
        covered = missing = 0
        count = 0
        for name, entry in files.items():
            if name in claimed or not matches(name):
                continue
            claimed.add(name)
            count += 1
            summary = entry["summary"]
            # Statements and branches together, which is what "100% branch"
            # means in §8.1 — a module with every line hit and one branch
            # unexplored is not covered.
            covered += summary["covered_lines"] + summary["covered_branches"]
            missing += summary["missing_lines"] + summary["missing_branches"]

        total = covered + missing
        measured = f"{100 * covered / total:.1f}%" if total else "n/a"
        print(f"{label:<38}{target:<36}{measured:>10}{count:>7}")

    remaining = {name: entry for name, entry in files.items() if name not in claimed}
    covered = sum(
        entry["summary"]["covered_lines"] + entry["summary"]["covered_branches"]
        for entry in remaining.values()
    )
    missing = sum(
        entry["summary"]["missing_lines"] + entry["summary"]["missing_branches"]
        for entry in remaining.values()
    )
    total = covered + missing
    measured = f"{100 * covered / total:.1f}%" if total else "n/a"
    print(f"{'Everything else':<38}{'not directly':<36}{measured:>10}{len(remaining):>7}")

    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        raise SystemExit(2)
    raise SystemExit(main(sys.argv[1]))
