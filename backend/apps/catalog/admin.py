"""Django Admin for the catalogue — the review queue and its decisions.

**These registrations are deliberately not reachable.** ``config/urls.py``
does not route ``admin/``, and M10 is where it gets an obscure path, staff-only
access, 2FA and audit logging. Registering the classes now means the review
workflow is built and tested against real admin machinery; routing it is a
separate decision with a separate hardening checklist. The suite reaches these
views through a test-only urlconf.

Every action delegates to ``services.py``. Nothing here decides whether a
transition is allowed, and nothing here writes a ``CourseReviewEvent``
directly — an admin action that duplicated the state machine is exactly the
drift the services module docstring warns about, and it would drift in the one
place with the most authority.
"""

from typing import ClassVar

from django.contrib import admin, messages
from django.db.models import Max, Q
from django.shortcuts import render
from django.template.response import TemplateResponse

from apps.catalog.models import Course, CourseReviewEvent, Lesson, Section
from apps.catalog.services import (
    InvalidTransition,
    NotPermitted,
    approve,
    reject,
    request_changes,
)


class SectionInline(admin.TabularInline):
    model = Section
    extra = 0
    ordering: ClassVar[list[str]] = ["position"]


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    """The review queue.

    Ordered by submission time, oldest first, so the queue is a queue. That
    ordering is why submissions are recorded as events: ``updated_at`` would
    reorder the list every time an instructor fixed a typo, letting the
    impatient jump ahead of the patient.
    """

    list_display: ClassVar[list[str]] = [
        "title",
        "instructor",
        "language",
        "level",
        "status",
        "submitted_at",
    ]
    list_filter: ClassVar[list[str]] = ["status", "language", "level"]
    search_fields: ClassVar[list[str]] = ["title", "slug"]
    inlines: ClassVar[list] = [SectionInline]
    actions: ClassVar[list[str]] = [
        "approve_selected",
        "reject_selected",
        "request_changes_selected",
    ]
    # Writable only through the state machine. A status dropdown here would be
    # a second route to PUBLISHED that records no reviewer and no reason,
    # which is the whole thing ADR-007 §2 exists to prevent.
    readonly_fields: ClassVar[list[str]] = ["status", "published_at"]

    def get_queryset(self, request):
        """Annotate first, then order.

        Not ``super().get_queryset()``: ModelAdmin applies ``get_ordering()``
        to the queryset before returning it, so ordering on ``submitted_at``
        would be applied to a queryset that does not have the annotation yet.
        """
        queryset = (
            self.model._default_manager.get_queryset()
            .select_related("instructor", "language")
            .annotate(
                submitted_at=Max(
                    "review_events__created_at",
                    filter=Q(review_events__action=CourseReviewEvent.Action.SUBMITTED),
                )
            )
        )
        return queryset.order_by(*self.get_ordering(request))

    def get_ordering(self, request):
        """Oldest submission first.

        Not the ``ordering`` attribute: that is validated against concrete
        model fields at import, and ``submitted_at`` is annotated. Courses
        never submitted sort last, since PostgreSQL puts NULLs last ascending
        — drafts belong below the queue, not above it.
        """
        return ["submitted_at"]

    @admin.display(description="Submitted", ordering="submitted_at")
    def submitted_at(self, obj: Course):
        return obj.submitted_at

    def _apply(self, request, queryset, transition, *, notes: str = "") -> None:
        """Run one transition over a selection, reporting each refusal.

        Per course, not in bulk. A selection routinely mixes states — the
        admin ticked six rows and two were already handled by a colleague —
        and one course that cannot move must not silently cancel the five that
        can, nor be quietly dropped from the count.
        """
        moved = 0
        for course in queryset:
            try:
                # `request` is forwarded so the audit row can record the
                # address the decision came from (§8). The service does the
                # recording; this only supplies what only a view knows.
                transition(course=course, by=request.user, notes=notes, request=request)
            except NotPermitted:
                self.message_user(
                    request,
                    f"{course.title}: you are not an administrator.",
                    level=messages.ERROR,
                )
            except InvalidTransition:
                self.message_user(
                    request,
                    f"{course.title}: cannot do that from {course.status}.",
                    level=messages.WARNING,
                )
            else:
                moved += 1

        if moved:
            self.message_user(request, f"{moved} course(s) updated.", level=messages.SUCCESS)

    def _with_notes(self, request, queryset, transition, *, title: str, action: str):
        """Collect notes on an intermediate page, then apply.

        Rejection without a reason tells the instructor nothing to fix, and
        ``notes`` is the field they read (see ``CourseReviewEvent``). A bulk
        action has nowhere to type one, so this interposes a form.
        """
        if "notes" in request.POST:
            self._apply(request, queryset, transition, notes=request.POST["notes"])
            return None

        return render(
            request,
            "admin/catalog/review_notes.html",
            {
                **self.admin_site.each_context(request),
                "title": title,
                "action": action,
                "courses": queryset,
                "opts": self.model._meta,
            },
        )

    @admin.action(description="Approve and publish")
    def approve_selected(self, request, queryset) -> None:
        self._apply(request, queryset, approve)

    @admin.action(description="Reject (return to draft)")
    def reject_selected(self, request, queryset) -> TemplateResponse | None:
        return self._with_notes(
            request, queryset, reject, title="Reject courses", action="reject_selected"
        )

    @admin.action(description="Request changes (return to draft)")
    def request_changes_selected(self, request, queryset) -> TemplateResponse | None:
        return self._with_notes(
            request,
            queryset,
            request_changes,
            title="Request changes",
            action="request_changes_selected",
        )


@admin.register(CourseReviewEvent)
class CourseReviewEventAdmin(admin.ModelAdmin):
    """The trail, readable and nothing else.

    Append-only is a property of the model, so the admin must not offer a way
    to break it. An editable trail is worse than no trail: it looks like
    evidence while being whatever the last person with access decided it
    should say.
    """

    list_display: ClassVar[list[str]] = ["course", "action", "actor", "created_at"]
    list_filter: ClassVar[list[str]] = ["action"]
    search_fields: ClassVar[list[str]] = ["course__title"]

    def has_add_permission(self, request) -> bool:
        # Events are written by services.py as a side effect of a transition.
        # One added here would name a decision nobody made.
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False


@admin.register(Lesson)
class LessonAdmin(admin.ModelAdmin):
    list_display: ClassVar[list[str]] = ["title", "course", "section", "lesson_type", "position"]
    list_filter: ClassVar[list[str]] = ["lesson_type", "is_preview"]
    search_fields: ClassVar[list[str]] = ["title", "slug"]
    list_select_related: ClassVar[list[str]] = ["course", "section"]


@admin.register(Section)
class SectionAdmin(admin.ModelAdmin):
    list_display: ClassVar[list[str]] = ["title", "course", "position"]
    search_fields: ClassVar[list[str]] = ["title"]
    list_select_related: ClassVar[list[str]] = ["course"]
