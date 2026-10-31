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

from django import forms
from django.contrib import admin, messages
from django.shortcuts import render
from django.utils import timezone

from apps.accounts.models import BetaInvitation, InstructorProfile, Role, User
from apps.accounts.services import (
    InvitationAlreadyConsumed,
    InvitationIssueConflict,
    InvitationNotFound,
    NotPermitted,
    RoleUnchanged,
    change_role,
    issue_invitation,
    revoke_invitation,
)


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


class BetaInvitationForm(forms.ModelForm):
    """The add form, carrying the reason the service demands.

    `reason` is not a model field, and should not be. It belongs to the *act* of
    issuing rather than to the invitation: re-opening a revoked row happens for a
    different reason than the original issue did, and `BetaInvitation` holds
    current state while the audit log holds the history.

    Required on the form as well as in the service, so the question is answered in
    the browser instead of as a 500 after submitting.
    """

    reason = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 4, "cols": 70}),
        help_text=(
            "Why is this person being admitted? Recorded in the audit log; "
            "nobody outside the project sees it."
        ),
    )

    class Meta:
        model = BetaInvitation
        fields: ClassVar[list[str]] = ["email"]


@admin.register(BetaInvitation)
class BetaInvitationAdmin(admin.ModelAdmin):
    """Admitting people to the private beta.

    **Issuing is the only way in, and that is deliberate.** `UserAdmin` refuses to
    add accounts because one made there would have no usable password and no
    verification email. Admission runs the other way round: an operator issues an
    invitation and the person registers normally. `docs/runbooks/beta-admission.md`
    says so explicitly, because "just create the account yourself" is the obvious
    wrong move.

    **Everything a service owns is read-only here.** `expires_at` comes from
    `INVITATION_LIFETIME`; `revoked_at`, `consumed_at` and `consumed_by` are
    written by services inside a transaction that also writes an audit row.
    Hand-editing them would bypass that *and* the check constraint pairing
    consumption's two columns — the row would change with nothing recording who
    changed it.
    """

    form = BetaInvitationForm
    list_display: ClassVar[list[str]] = [
        "email",
        "state",
        "expires_at",
        "consumed_by",
        "created_at",
    ]
    list_filter: ClassVar[list[str]] = ["revoked_at", "consumed_at"]
    search_fields: ClassVar[list[str]] = ["email"]
    actions: ClassVar[list[str]] = ["revoke_selected"]

    @admin.display(description="State")
    def state(self, obj: BetaInvitation) -> str:
        """One column instead of three timestamps read against each other.

        An operator asking "can this person still register?" should not have to
        compare `expires_at` to now while checking two nullable columns.
        """
        if obj.consumed_at is not None:
            return "Used"
        if obj.revoked_at is not None:
            return "Revoked"
        if obj.expires_at <= timezone.now():
            return "Expired"
        return "Open"

    def has_change_permission(self, request, obj=None) -> bool:
        """Nothing here is editable after issuing.

        The only legitimate changes come from services — revoke through the action
        below, consume through registration. A change form that saved would have to
        decide what a hand-edited `expires_at` means, and the honest answer is that
        it means nothing anybody audited. Re-issuing is the operation that extends
        an invitation.
        """
        return False

    def save_model(self, request, obj, form, change) -> None:
        """Route through the service, so the admission is audited.

        Not `super().save_model`, which would write the row and record nothing —
        the same reasoning as `UserAdmin.save_model`. `issue_invitation` creates or
        re-opens the row itself, so this must not save it as well.
        """
        try:
            issue_invitation(
                actor=request.user,
                email=obj.email,
                reason=form.cleaned_data["reason"],
                request=request,
            )
        except NotPermitted:
            self.message_user(request, "You are not an active administrator.", level=messages.ERROR)
        except InvitationAlreadyConsumed:
            self.message_user(
                request,
                f"{obj.email} has already registered. Look the account up instead.",
                level=messages.WARNING,
            )
        except InvitationIssueConflict:
            self.message_user(
                request,
                f"{obj.email} was issued by somebody else at the same moment. Reload.",
                level=messages.WARNING,
            )

    @admin.action(description="Revoke selected invitations")
    def revoke_selected(self, request, queryset):
        """Withdraw admissions, collecting a reason on the way.

        An intermediate page, because a bulk action has nowhere to type one. That
        is the same problem `CourseAdmin._with_notes` solves and the same shape of
        answer.

        Per invitation rather than in bulk: a selection routinely mixes states —
        somebody ticked six rows and two have since registered — and one that
        cannot be revoked must not silently cancel the four that can.
        """
        if "reason" not in request.POST:
            return render(
                request,
                "admin/accounts/revoke_reason.html",
                {
                    **self.admin_site.each_context(request),
                    "title": "Revoke invitations",
                    "action": "revoke_selected",
                    "invitations": queryset,
                    "opts": self.model._meta,
                },
            )

        revoked = 0
        for invitation in queryset:
            try:
                revoke_invitation(
                    actor=request.user,
                    email=invitation.email,
                    reason=request.POST["reason"],
                    request=request,
                )
            except NotPermitted:
                self.message_user(
                    request, "You are not an active administrator.", level=messages.ERROR
                )
            except InvitationAlreadyConsumed:
                self.message_user(
                    request,
                    f"{invitation.email} has already registered; revoking would not "
                    "remove their access. Deactivate the account instead.",
                    level=messages.WARNING,
                )
            except InvitationNotFound:
                self.message_user(
                    request,
                    f"{invitation.email} no longer exists.",
                    level=messages.WARNING,
                )
            else:
                revoked += 1

        if revoked:
            self.message_user(request, f"{revoked} invitation(s) revoked.", level=messages.SUCCESS)
        return None
