"""Pagination.

architecture.md 6.1: cursor pagination for anything time-ordered or large —
progress, catalogue, audit log — and page-number only for small admin lists.

The reason is not style. Page-number pagination resolves ``?page=500`` by
scanning and discarding every preceding row, so cost grows with depth; and
because the offset is positional, a row inserted while a client is paging
shifts everything after it, so the client sees one record twice and misses
another. A cursor encodes *where it was*, not *how far in*, and has neither
problem.

What page-number buys in exchange is a total count, which a cursor cannot
provide without the scan it exists to avoid. An admin list wants "142 users";
a learner scrolling their progress does not.

Every value in this module is API contract. Parameter names, page sizes and
ordering are all observable, and changing one after a client depends on it is
a breaking change — so each is chosen deliberately rather than left to a
framework default.
"""

from rest_framework import pagination

# Large enough that a catalogue page or a progress list is one request, small
# enough that a slow query stays slow-but-survivable.
DEFAULT_PAGE_SIZE = 20

# The cap exists for denial of service, not tidiness: without it a single
# `?page_size=1000000` is all it takes to ask the database for everything.
MAX_PAGE_SIZE = 100


class CursorPagination(pagination.CursorPagination):
    """The default for every list endpoint."""

    page_size = DEFAULT_PAGE_SIZE
    page_size_query_param = "page_size"
    max_page_size = MAX_PAGE_SIZE

    # Ordering by timestamp alone is not stable. Two rows created in the same
    # millisecond can swap between requests, and a client paging through then
    # sees one of them twice and the other never. The primary key breaks the
    # tie and makes the order total.
    #
    # `created_at` comes from core.models.TimestampedModel, so any model using
    # that base paginates without further configuration.
    ordering = ("-created_at", "-pk")


class PageNumberPagination(pagination.PageNumberPagination):
    """For small admin lists that need a total count.

    Not a default. Reach for it only where the collection is bounded and the
    count is genuinely useful — a review queue, a user lookup — never for
    anything that grows with usage.
    """

    page_size = DEFAULT_PAGE_SIZE
    page_query_param = "page"
    page_size_query_param = "page_size"
    max_page_size = MAX_PAGE_SIZE
