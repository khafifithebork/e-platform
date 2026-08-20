"""Rendering segments into WebVTT.

Invariant 13: the rows are the source, this is a projection. Nothing here
writes anything, and a VTT file is never stored — §5.2's whole argument is
that a caption file is these rows with the structure thrown away.

A pure function over segments, deliberately. It has no database access, no
request and no cache, so the escaping below can be tested against hostile
input directly rather than through four layers of HTTP.
"""

from __future__ import annotations

from collections.abc import Iterable

# WebVTT reserves these three. A cue is parsed by a browser, so unescaped
# markup in a transcript is markup in a document — the same class of problem
# as `dangerouslySetInnerHTML`, which CLAUDE.md §6 forbids outright, arriving
# through a file instead of a component.
_ESCAPES = (
    ("&", "&amp;"),  # first, or it would double-escape the others
    ("<", "&lt;"),
    (">", "&gt;"),
)

# The cue separator. A line containing it inside cue *text* ends the cue early
# and turns the rest of the line into a malformed timing — a transcript
# containing "-->" is ordinary in a lesson about arrows or code, so this is a
# content problem rather than an attack.
CUE_SEPARATOR = "-->"


def escape_cue_text(text: str) -> str:
    """Make one segment safe to put in a VTT file.

    Escaping the three reserved characters is not enough on its own: the
    separator has to be neutralised too, and it survives escaping because
    neither `-` nor `>` alone is reserved. `>` becoming `&gt;` is what breaks
    it up, so the order here matters — the separator is handled *by* the
    escaping rather than beside it.
    """
    for character, replacement in _ESCAPES:
        text = text.replace(character, replacement)
    return text


def format_timestamp(milliseconds: int) -> str:
    """WebVTT wants ``HH:MM:SS.mmm``.

    Hours are always present. They are optional in the format, but a lesson
    that crosses an hour would otherwise change shape halfway through the
    file, and players have historically been uneven about the short form.
    """
    if milliseconds < 0:
        raise ValueError("A cue cannot start before the media does.")

    seconds, remainder = divmod(milliseconds, 1000)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)

    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{remainder:03d}"


def render_vtt(segments: Iterable) -> str:
    """Build a WebVTT file from segments in order.

    Cue identifiers are the segment position rather than the primary key. A
    UUID would leak a database identifier into a file the browser can read and
    a learner can save, and the position is what an interactive transcript
    wants to scroll to anyway.
    """
    lines = ["WEBVTT", ""]

    for segment in segments:
        lines.append(str(segment.position))
        lines.append(
            f"{format_timestamp(segment.start_ms)} "
            f"{CUE_SEPARATOR} "
            f"{format_timestamp(segment.end_ms)}"
        )
        lines.append(escape_cue_text(segment.text))
        lines.append("")

    # Trailing newline: the format is line-oriented and some parsers treat a
    # file ending mid-line as truncated.
    return "\n".join(lines)
