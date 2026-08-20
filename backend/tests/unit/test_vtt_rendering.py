"""Rendering segments into WebVTT.

A pure function, so the hostile input goes straight in rather than through
four layers of HTTP.

Abuse case 9 is the one that matters: **a transcript is user-supplied content
rendered into a file a browser parses.** Escaping it is the same obligation as
escaping anything into a template, and CLAUDE.md §6's ban on
`dangerouslySetInnerHTML` is the same rule arriving through a component
instead of a file.

The second-order case is the cue separator. A lesson about arrows, or about
code, contains `-->` legitimately — so this is a content problem before it is
an attack, and it survives naive escaping because neither `-` nor `>` alone is
reserved.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from apps.transcripts.rendering import (
    CUE_SEPARATOR,
    escape_cue_text,
    format_timestamp,
    render_vtt,
)


@dataclass
class Cue:
    """Just enough of a segment to render one."""

    position: int
    start_ms: int
    end_ms: int
    text: str


class TestTimestamps:
    def test_the_start_of_the_media(self) -> None:
        assert format_timestamp(0) == "00:00:00.000"

    def test_milliseconds_are_kept(self) -> None:
        """Cue boundaries are what a player seeks to; rounding to seconds
        would put every subtitle up to half a second out."""
        assert format_timestamp(1234) == "00:00:01.234"

    def test_minutes_and_hours_carry(self) -> None:
        assert format_timestamp(3_723_456) == "01:02:03.456"

    def test_hours_are_always_present(self) -> None:
        """Optional in the format, but a lesson crossing an hour would change
        shape halfway through the file, and players have been uneven about
        the short form."""
        assert format_timestamp(500).startswith("00:")

    def test_a_negative_start_is_refused(self) -> None:
        """Unreachable through the API — the database refuses it — so this is
        about the renderer failing loudly if it is ever called directly."""
        with pytest.raises(ValueError, match="before the media"):
            format_timestamp(-1)


class TestEscaping:
    """Abuse case 9."""

    def test_markup_cannot_survive_into_the_file(self) -> None:
        """A transcript is content a browser parses. Unescaped markup here is
        markup in a document."""
        assert escape_cue_text("<b>hola</b>") == "&lt;b&gt;hola&lt;/b&gt;"

    def test_a_script_tag_is_neutralised(self) -> None:
        escaped = escape_cue_text("<script>alert(1)</script>")

        assert "<script>" not in escaped
        assert "&lt;script&gt;" in escaped

    def test_ampersands_are_escaped_first(self) -> None:
        """Order matters: escaping `<` before `&` would turn `&lt;` into
        `&amp;lt;` and render the escape itself to the learner."""
        assert escape_cue_text("&lt;") == "&amp;lt;"

    def test_the_cue_separator_cannot_appear_in_text(self) -> None:
        """A lesson about arrows contains this legitimately. Left alone, it
        ends the cue early and turns the rest of the line into a malformed
        timing — the file breaks at that point and every later subtitle is
        lost."""
        escaped = escape_cue_text(f"the arrow {CUE_SEPARATOR} points right")

        assert CUE_SEPARATOR not in escaped

    def test_ordinary_accented_text_is_untouched(self) -> None:
        """The positive twin. An escaper that mangled everything would satisfy
        every test above and make Spanish unreadable."""
        assert escape_cue_text("¿Cómo estás?") == "¿Cómo estás?"


class TestTheFile:
    def _cues(self) -> list[Cue]:
        return [
            Cue(1, 0, 1500, "Buenos días."),
            Cue(2, 2000, 3800, "¿Cómo estás?"),
        ]

    def test_it_starts_with_the_magic_line(self) -> None:
        """A file without it is not a VTT file, and a browser rejects the
        whole thing rather than the first cue."""
        assert render_vtt(self._cues()).startswith("WEBVTT\n")

    def test_every_cue_is_rendered(self) -> None:
        output = render_vtt(self._cues())

        assert "Buenos días." in output
        assert "¿Cómo estás?" in output

    def test_timings_read_as_a_cue(self) -> None:
        assert "00:00:00.000 --> 00:00:01.500" in render_vtt(self._cues())

    def test_cue_ids_are_positions_not_database_ids(self) -> None:
        """A UUID would leak an internal identifier into a file the learner
        can save, and the position is what an interactive transcript scrolls
        to anyway."""
        output = render_vtt(self._cues())

        assert "\n1\n00:00:00.000" in output

    def test_an_empty_transcript_is_still_a_valid_file(self) -> None:
        """Unreachable through approval, which refuses an empty transcript,
        but the renderer must not produce something malformed if it happens."""
        assert render_vtt([]).strip() == "WEBVTT"

    def test_the_file_ends_with_a_newline(self) -> None:
        """Line-oriented format: some parsers treat a file ending mid-line as
        truncated."""
        assert render_vtt(self._cues()).endswith("\n")

    def test_hostile_text_does_not_break_the_structure(self) -> None:
        """The two escaping concerns together, in the shape they would
        actually arrive: a cue whose text tries to end its own cue and open
        markup."""
        output = render_vtt([Cue(1, 0, 1000, f"<script>x</script> {CUE_SEPARATOR} 99:99:99.999")])

        # Exactly one separator: the cue's own timing line.
        assert output.count(CUE_SEPARATOR) == 1
        assert "<script>" not in output
