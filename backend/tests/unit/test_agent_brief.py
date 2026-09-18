"""`CLAUDE.md` and `AGENTS.md` must not drift apart.

`CLAUDE.md` §1 calls itself the constitution and tells you to copy it to
`AGENTS.md` for tools that read that filename. That instruction creates a
hazard it does not address: **two files with the same authority and nothing
keeping them equal.** A rule tightened in one and not the other gives two agents
two different constitutions, and neither is marked stale.

It had already begun. The copy arrived untracked, and a find-and-replace of
`CLAUDE` → `AGENTS` had caught a **quotation**: ADR-001 line 86 says
"`CLAUDE.md` §11 should be updated to strike decisions 2, 3 and 4", and the copy
rendered it as "`AGENTS.md` §11 should…". One of the two constitutions misquoted
its own source.

So the rule is the strictest one that can hold: **byte-identical except the
title line.** Anything looser needs a judgement about which differences are
acceptable, and that judgement is what drifts.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
CLAUDE = REPO_ROOT / "CLAUDE.md"
AGENTS = REPO_ROOT / "AGENTS.md"


def _lines(path: Path) -> list[str]:
    """Content, with line endings normalised away.

    `.gitattributes` forces LF in the working tree, but a Windows checkout can
    still present CRLF — and a guard that failed on every Windows machine would
    be one somebody deletes rather than fixes.
    """
    return path.read_text(encoding="utf-8").replace("\r\n", "\n").split("\n")


class TestTheTwoBriefsAreOneDocument:
    def test_both_exist(self) -> None:
        """`AGENTS.md` is not optional decoration — §1 instructs the copy, and
        a missing one silently means some tools read no brief at all."""
        assert CLAUDE.is_file()
        assert AGENTS.is_file()

    def test_they_differ_only_in_their_title(self) -> None:
        claude, agents = _lines(CLAUDE), _lines(AGENTS)

        assert len(claude) == len(agents), "the two briefs have different lengths"
        assert claude[0] == "# CLAUDE.md — Agent Operating Brief"
        assert agents[0] == "# AGENTS.md — Agent Operating Brief"
        assert claude[1:] == agents[1:]

    def test_the_adr_quotation_survived_the_rename(self) -> None:
        """The specific thing that went wrong, pinned by name.

        A quotation is not a reference to be updated — it is a record of what
        another document said. `CLAUDE.md` quotes ADR-001 telling it to strike
        three rows from §11, and both copies must quote it as ADR-001 wrote it,
        including in the file whose own name is not the one quoted."""
        adr = REPO_ROOT / "docs" / "adr" / "001-architecture.md"
        quoted = "`CLAUDE.md` §11 should be updated to strike"

        assert quoted in adr.read_text(encoding="utf-8"), (
            "ADR-001 no longer contains the sentence this guard pins. If the ADR "
            "was legitimately reworded, update the quotation in both briefs."
        )
        for brief in (CLAUDE, AGENTS):
            assert "CLAUDE.md §11 should" in brief.read_text(encoding="utf-8"), brief.name

    def test_neither_is_empty(self) -> None:
        """The twin. Two empty files are byte-identical."""
        assert len(_lines(CLAUDE)) > 100
