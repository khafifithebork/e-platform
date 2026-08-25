"""User administration. architecture.md §6.10 — "user lookup, instructor approval".

Deliberately narrow. This is the widest surface in the system: the account
table decides who is an administrator, and a `ModelAdmin` with the defaults on
would let anyone with admin access grant themselves `is_superuser` through a
checkbox.

So the form exposes exactly two fields, `role` and `is_active`, and everything
that grants privilege inside Django itself — `is_staff`, `is_superuser`,
`groups`, `user_permissions` — is deliberately absent. `is_staff` in particular
is the admin site's own gate and a wider capability than any role
(accounts.models draws that line); it is granted at the command line, on
purpose, where the act is visible.
"""

import contextlib
from typing import ClassVar

from django.contrib import admin

from apps.accounts.models import InstructorProfile, Role, User
from apps.accounts.services import RoleUnchanged, change_role


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display: ClassVar[list[str]] = [
        "email",
        "role",
        "is_active",
        "is_staff",
        "is_email_verified",
        "date_joined",
    ]
    list_filter: ClassVar[list[str]] = ["role", "is_active", "is_staff", "is_email_verified"]
    search_fields: ClassVar[list[str]] = ["email"]
    ordering: ClassVar[list[str]] = ["-date_joined"]

    fields: ClassVar[list[str]] = ["email", "role", "is_active", "is_staff", "date_joined"]
    readonly_fields: ClassVar[list[str]] = ["email", "is_staff", "date_joined"]

    def has_add_permission(self, request) -> bool:
        """Accounts arrive through registration, which sets a password and
        sends a verification email. One created here would have neither."""
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        """Deleting a learner destroys their progress and their history, and
        erasure is its own piece of work with its own obligations (M10 spec §6).
        Deactivate instead — the field is right there."""
        return False

    def save_model(self, request, obj, form, change) -> None:
        """Route a role change through the service, so it is audited.

        Not `super().save_model`, which would write the row and record nothing.
        `is_active` is saved the ordinary way — it is not in §8's list, and a
        deactivation is visible in the row itself.
        """
        if "role" in form.changed_data:
            # `suppress`, because a no-op is unreachable through this form —
            # it only gets here when the role is in `changed_data`. Guarded
            # anyway so a future caller cannot turn a refused no-op into a 500.
            with contextlib.suppress(RoleUnchanged):
                change_role(
                    actor=request.user,
                    user=obj,
                    role=obj.role,
                    reason=f"Changed via the admin site from {form.initial['role']}.",
                    request=request,
                )

        if "is_active" in form.changed_data:
            obj.save(update_fields=["is_active"])

    def get_readonly_fields(self, request, obj=None):
        """Nobody edits their own role here.

        An administrator who wants a different role for themselves can ask
        another one, and the audit row will name them. Self-service privilege
        change is the shape most worth making awkward.
        """
        readonly = list(super().get_readonly_fields(request, obj))
        if obj is not None and obj.pk == request.user.pk:
            readonly.append("role")
        return readonly

    def get_queryset(self, request):
        return super().get_queryset(request).filter(role__in=Role.values)


@admin.register(InstructorProfile)
class InstructorProfileAdmin(admin.ModelAdmin):
    """Where an instructor's public name is set.

    The catalogue renders `display_name` and nothing else can write it: there
    is no instructor-facing profile API, and adding one would be an endpoint
    with no caller while the frontend is auth pages and a lesson page. Django
    Admin is the interface for this, the same call M10 §2.5 made.

    Deliberately narrow, for the reason `UserAdmin` above is: `approved_at` and
    `approved_by` are the instructor approval trail and must not be editable
    from a form — approval is an act with a record, not a checkbox. `user` is
    read-only because moving a profile between accounts is not an edit, it is
    two operations pretending to be one.
    """

    list_display: ClassVar[list[str]] = ["user", "display_name", "is_active", "approved_at"]
    list_filter: ClassVar[list[str]] = ["is_active"]
    search_fields: ClassVar[list[str]] = ["user__email", "display_name"]
    fields: ClassVar[list[str]] = ["user", "display_name", "headline", "bio", "is_active"]
    readonly_fields: ClassVar[list[str]] = ["user"]

    def has_add_permission(self, request) -> bool:
        # A profile belongs to an account and is created with one. Adding a
        # bare profile here would produce a row pointing at nobody.
        return False
