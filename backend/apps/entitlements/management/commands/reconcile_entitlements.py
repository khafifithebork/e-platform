"""Report where stored subscription state has drifted from what it should be.

ADR-002 §4 lists nightly entitlement reconciliation among the controls that
cost nothing, and rates it above redundancy: *"An hour spent on the
reconciliation job buys more real reliability than $100/month of redundancy."*
It was never written. This is the seventh instance of the pattern ADR-023 §1
names — a documented control that nothing implements — and it is the one that
ADR called highest-value.

**This command reports. It does not repair, and that is not an omission.**
Invariant 3 has exactly one place that decides access and `services.py` is the
one place that writes subscription state. A job that quietly corrected rows
would be a second writer whose failure mode is the worst available: everything
looks fine, forever, because the evidence keeps being cleaned up.

Exit codes, because this is meant to be run by a scheduler and read by a
machine before it is read by a person:

    0   nothing drifted
    1   drift found that is granting access it should not
    2   drift found, none of it granting access

Splitting 1 from 2 is the whole point. One of these categories is a
subscription still serving paid content after it stopped being paid for; the
rest are stale rows the resolver already refuses. A single non-zero exit would
page somebody for both.
"""

from __future__ import annotations

import json

from django.core.management.base import BaseCommand

from apps.entitlements.selectors import reconciliation_findings

EXIT_CLEAN = 0
EXIT_GRANTING = 1
EXIT_STALE = 2


class Command(BaseCommand):
    help = "Report subscription rows whose stored state has drifted. Reports only; never writes."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--json",
            action="store_true",
            help="Emit findings as JSON on stdout, for a scheduler or an alert to parse.",
        )

    def handle(self, *args, **options) -> None:
        findings = reconciliation_findings()

        if options["json"]:
            self.stdout.write(
                json.dumps(
                    [
                        {
                            "code": f.code,
                            "description": f.description,
                            "grants_access": f.grants_access,
                            "count": f.count,
                            "examples": list(f.examples),
                        }
                        for f in findings
                    ],
                    indent=2,
                )
            )
        else:
            self._render(findings)

        granting = [f for f in findings if f.grants_access]
        if granting:
            # SystemExit rather than CommandError: this is a finding about the
            # data, not a failure of the command. A CommandError would print a
            # traceback-flavoured message and imply the job itself broke.
            raise SystemExit(EXIT_GRANTING)
        if findings:
            raise SystemExit(EXIT_STALE)

    def _render(self, findings) -> None:
        if not findings:
            self.stdout.write(self.style.SUCCESS("No entitlement drift found."))
            return

        for finding in findings:
            # Ids, not email addresses. §6 case 6: this output is destined for
            # an alert, and an alert is a mailbox nobody audits.
            examples = ", ".join(finding.examples)
            headline = f"{finding.code}: {finding.count}"
            if finding.grants_access:
                self.stdout.write(self.style.ERROR(f"{headline}  [GRANTING ACCESS]"))
            else:
                self.stdout.write(self.style.WARNING(headline))
            self.stdout.write(f"    {finding.description}")
            self.stdout.write(f"    e.g. {examples}")
