"""The pagination contract.

architecture.md 6.1: cursor pagination for anything time-ordered or large,
page-number only for small admin lists. Cursor avoids the offset drift and the
O(n) scan that page-number pagination causes at depth.

Most of this is configuration, and configuration assertions are usually a weak
test. They earn their place here because every one of these values becomes part
of the API contract the moment a client depends on it — parameter names, page
sizes, ordering. Changing one later is a breaking change, so each is chosen
deliberately rather than inherited.

The page-size cap is the exception: it is real behaviour, and it is a denial-of
-service control, so it is tested as behaviour.
"""

from __future__ import annotations

from rest_framework.test import APIRequestFactory

factory = APIRequestFactory()


class TestCursorPaginationIsTheDefault:
    def test_configured_as_the_project_default(self) -> None:
        from django.conf import settings

        assert settings.REST_FRAMEWORK["DEFAULT_PAGINATION_CLASS"] == (
            "apps.core.pagination.CursorPagination"
        )

    def test_ordering_is_deterministic(self) -> None:
        """Ordering by a timestamp alone is not stable: two rows created in the
        same millisecond can swap between requests, so a client paging through
        sees one twice and another never. The primary key breaks the tie."""
        from apps.core.pagination import CursorPagination

        assert CursorPagination.ordering == ("-created_at", "-pk")

    def test_newest_first(self) -> None:
        """Every cursor-paginated collection in this product — progress,
        catalogue, audit log — is read newest first."""
        from apps.core.pagination import CursorPagination

        assert CursorPagination.ordering[0].startswith("-")


class TestPageNumberPaginationForAdminLists:
    def test_exposes_a_total_count(self) -> None:
        """The reason it exists. A cursor cannot report a total without the
        O(n) scan it is there to avoid, and an admin list wants "142 users"."""
        from rest_framework.pagination import PageNumberPagination as DRFPageNumber

        from apps.core.pagination import PageNumberPagination

        assert issubclass(PageNumberPagination, DRFPageNumber)


class TestQueryParameterNames:
    """Hyrum's Law: these are contract as soon as one client sends them.

    snake_case follows architecture.md 6.2, which already documents
    `?has_preview=` on the catalogue endpoint.
    """

    def test_cursor_page_size_parameter(self) -> None:
        from apps.core.pagination import CursorPagination

        assert CursorPagination.page_size_query_param == "page_size"

    def test_page_number_parameters(self) -> None:
        from apps.core.pagination import PageNumberPagination

        assert PageNumberPagination.page_query_param == "page"
        assert PageNumberPagination.page_size_query_param == "page_size"


class TestPageSizeCap:
    """Behaviour, not configuration.

    An uncapped client-controlled page size is a denial-of-service vector: one
    request for a million rows is all it takes.
    """

    def test_default_page_size_is_used_when_unspecified(self) -> None:
        from apps.core.pagination import CursorPagination

        paginator = CursorPagination()
        request = _drf_request("/items/")

        assert paginator.get_page_size(request) == 20

    def test_a_client_may_request_a_smaller_page(self) -> None:
        from apps.core.pagination import CursorPagination

        paginator = CursorPagination()
        request = _drf_request("/items/?page_size=5")

        assert paginator.get_page_size(request) == 5

    def test_an_oversized_request_is_capped_not_rejected(self) -> None:
        """Capped rather than a 400: the client still gets data, and a
        legitimate caller with an optimistic default is not broken."""
        from apps.core.pagination import CursorPagination

        paginator = CursorPagination()
        request = _drf_request("/items/?page_size=1000000")

        assert paginator.get_page_size(request) == 100

    def test_the_admin_paginator_is_capped_too(self) -> None:
        from apps.core.pagination import PageNumberPagination

        paginator = PageNumberPagination()
        request = _drf_request("/items/?page_size=1000000")

        assert paginator.get_page_size(request) == 100

    def test_a_nonsense_page_size_falls_back_to_the_default(self) -> None:
        from apps.core.pagination import CursorPagination

        paginator = CursorPagination()

        assert paginator.get_page_size(_drf_request("/items/?page_size=abc")) == 20
        assert paginator.get_page_size(_drf_request("/items/?page_size=-1")) == 20
        assert paginator.get_page_size(_drf_request("/items/?page_size=0")) == 20


def _drf_request(path: str):
    """DRF paginators read `request.query_params`, which is a DRF Request."""
    from rest_framework.request import Request

    return Request(factory.get(path))
