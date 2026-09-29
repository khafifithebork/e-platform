"""Account reads.

Invariant 2: queries live here, not in views or serializers.
"""

from django.utils import timezone

from apps.accounts.models import Role, User


def get_user_for_me(*, user: User) -> User:
    """Re-read the signed-in user with their profile joined.

    The join does not save a query over reading ``request.user.student_profile``
    lazily — both cost one beyond what the authentication middleware already
    did. It is here for layering (invariant 2, reads live in selectors) and
    because it stays a single query as more relations are added to this
    response, which is what stops /auth/me/ fanning out later.
    """
    return User.objects.select_related("student_profile").get(pk=user.pk)


def personal_data_export(*, user: User) -> dict:
    """Everything this service holds about one person, as JSON-ready data.

    GDPR Article 15 (access) and Article 20 (portability). Requested by the
    account page; `docs/specs/m10-admin.md` §6 deferred this deliberately and
    ADR-036 records the decisions it needed.

    **Scoped to the caller and nothing else.** Every queryset below filters on
    ``user`` — invariant 10 — and the view takes no identifier at all, so there
    is nothing to manipulate. The strongest form of "you cannot export somebody
    else's data" is having no way to name them.

    Imports are local, matching ``MeSerializer.get_access``: accounts is the
    lower layer and learning and entitlements already depend on it, so a
    module-level import would tie them together in both directions.

    ## What is deliberately absent, and why

    ``password``, and the verification and reset token hashes. A credential is
    not data about somebody in any useful sense, and a hash discloses nothing
    while being the one thing here that must never leave the database.

    ``AuditLog``. It records administrative actions, and each row carries an
    ``actor_label`` naming **another person** — the administrator who acted.
    Article 15 covers the requester's own data and explicitly does not extend to
    other people's; handing over a log of who touched an account would disclose
    staff identities to anyone who asked. If a regulator ever requires it, the
    answer is a redacted projection, not this.

    ``AccessOverride.granted_by``, for the same reason and in miniature: the
    grant, its reason and its window are the person's own data, and the name of
    the administrator who granted it is not. That section is assembled by
    ``apps.entitlements.selectors.personal_billing_data`` — invariant 3 forbids
    importing the subscription model here, and a test caught the first attempt.

    ``WebhookEvent``. Not keyed to a user at all — provider payloads with
    signatures and delivery metadata — so "this person's webhooks" is not a
    query this schema can answer. It becomes a real question at M8, and ADR-036
    says so rather than pretending the export is complete.

    Course content, sections, lessons and transcripts. That is the product, not
    personal data. Only the identifiers needed to make the rows below legible
    are included: a progress row saying ``lesson: 9f3c…`` is technically
    complete and useless to a human.

    ## Why this is synchronous

    A curated catalogue means tens of courses, one enrolment per course and one
    progress row per lesson watched. A committed learner has a few hundred rows,
    and **the query count is eight regardless** — counted, not estimated, and
    pinned by ``test_does_not_fan_out_per_row``. An asynchronous job writing to
    R2 and emailing a link is the right shape at the point where a single
    response would time out, and this is nowhere near it — building that now
    would add a Celery task, a storage object and an expiring URL to serve
    something that fits in a response body.
    """
    from apps.entitlements.selectors import personal_billing_data
    from apps.learning.models import Enrollment, LessonProgress

    enrollments = (
        Enrollment.objects.filter(user=user)
        .select_related("course", "last_lesson")
        .order_by("started_at")
    )
    # `lesson__course` as well as `lesson`: without it each row's course costs a
    # query, which is the N+1 that turns a few hundred rows into a timeout.
    progress = (
        LessonProgress.objects.filter(user=user)
        .select_related("lesson", "lesson__course")
        .order_by("lesson__course__slug", "lesson__position")
    )
    billing = personal_billing_data(user=user)

    return {
        # Named so the file explains itself when somebody opens it a year later
        # with no memory of having asked for it.
        "export": {
            "service": "Lingua",
            "generated_at": timezone.now().isoformat(),
            # States its own scope and points at nothing.
            #
            # The first draft ended "See the privacy documentation for what that
            # covers", and **there is no privacy documentation** — that page is
            # blocked on owner-supplied content, so the sentence referred a reader to
            # something that does not exist. Same fault as the support address the
            # account page nearly invented, and the same fix: say what is true and
            # stop. A test asserts the absence of any such pointer.
            "about": (
                "Everything this service holds about your account. Course content "
                "is not included, and neither are administrative records that name "
                "other people, such as which administrator changed something."
            ),
        },
        "account": {
            "id": str(user.id),
            "email": user.email,
            "role": user.role,
            "email_confirmed": user.is_email_verified,
            "active": user.is_active,
            "registered_at": user.date_joined.isoformat(),
            "last_signed_in_at": user.last_login.isoformat() if user.last_login else None,
        },
        "profile": {
            "display_name": getattr(getattr(user, "student_profile", None), "display_name", ""),
        },
        "courses_started": [
            {
                "course": enrollment.course.slug,
                "course_title": enrollment.course.title,
                "started_at": enrollment.started_at.isoformat(),
                "completed_at": (
                    enrollment.completed_at.isoformat() if enrollment.completed_at else None
                ),
                "resume_at_lesson": (
                    enrollment.last_lesson.slug if enrollment.last_lesson else None
                ),
            }
            for enrollment in enrollments
        ],
        "lesson_progress": [
            {
                "course": row.lesson.course.slug,
                "lesson": row.lesson.slug,
                "lesson_title": row.lesson.title,
                "last_position_seconds": row.last_position_seconds,
                "furthest_position_seconds": row.max_position_seconds,
                "watched_seconds": row.watched_seconds,
                "completed_at": row.completed_at.isoformat() if row.completed_at else None,
            }
            for row in progress
        ],
        # Assembled by `apps.entitlements.selectors.personal_billing_data`, not
        # here. Invariant 3: nothing outside that app imports the subscription model,
        # and a test enforces it — see that function for the story.
        **billing,
    }


def administrator_emails() -> list[str]:
    """Everyone who should hear that a course needs reviewing.

    A selector rather than a queryset built inside the notifying service, so
    "who is an administrator" stays one answer. Returns addresses rather than
    users because that is all the caller may have — handing a service a `User`
    invites it to read something else off them.
    """
    return list(
        User.objects.filter(role=Role.ADMIN, is_active=True)
        .order_by("email")
        .values_list("email", flat=True)
    )
