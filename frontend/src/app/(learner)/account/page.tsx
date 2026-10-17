import type { Metadata } from "next";

import { AccountDetails } from "@/components/account/AccountDetails";
import { ChangePassword } from "@/components/account/ChangePassword";
import { DataExport } from "@/components/account/DataExport";
import { PageTitle } from "@/components/ui/PageTitle";

/**
 * The account page, which the product did not have.
 *
 * In `(learner)` rather than `(marketing)`: it is per-user and can never be
 * prerendered, and the static-marketing check would fail if it sat in the other
 * group. Nothing is fetched here — `AccountDetails` and `ChangePassword` are client
 * components and `DataExport` is a plain link, so no Server Component reaches Django
 * and CLAUDE.md §11 #5 stays moot under B-lite.
 *
 * No `<main>` of its own: `SiteShell` owns that landmark, and two on one page is
 * what the document-structure check catches.
 *
 * **No canonical URL and no `publicMetadata`.** This route is `Disallow`ed in
 * `robots.txt` and a canonical here would contradict that by inviting indexing —
 * ADR-035 §4, and `seo.test.ts` asserts no route in this group grows one.
 */
export const metadata: Metadata = {
  title: "Account",
};

export default function AccountPage() {
  return (
    <div className="mx-auto flex w-full max-w-3xl flex-col gap-10 px-6 py-10 sm:gap-12 sm:py-16 [overflow-wrap:anywhere]">
      <PageTitle>Account</PageTitle>
      <AccountDetails />
      <ChangePassword />
      <DataExport />
    </div>
  );
}
