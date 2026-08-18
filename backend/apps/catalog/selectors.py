"""Catalogue reads."""

from apps.accounts.models import User
from apps.catalog.models import Course


def courses_for_instructor(*, user: User):
    """Every course this instructor owns, and nothing else.

    The scope filter is the whole security control for the instructor API.
    ``architecture.md`` §10 names its absence as the mistake for this milestone,
    and §4.4 calls fetching by primary key without one the most common IDOR in
    DRF codebases.

    Because the filter is applied to the queryset the detail, update and delete
    views all resolve through, a course belonging to someone else is not
    forbidden — it is *not found*, which is what §6.3 requires. A 403 would
    confirm it exists.

    Joined on language and instructor: a list of courses renders both, and
    without the join that is two extra queries per row.
    """
    return (
        Course.objects.filter(instructor=user)
        .select_related("language", "instructor")
        .order_by("-created_at")
    )
