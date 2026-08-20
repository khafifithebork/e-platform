# ADR-013 — M5 media pipeline: what implementation settled

**Status:** Accepted
**Date:** 2026-08-20
**Companion to:** ADR-012 (decisions taken before code). This records what only
became a decision once the pipeline existed.

---

## 1. A presigned PUT cannot cap upload size — and the gap is real

**What we do.** The presigned URL signs the object key, the expiry and the
**content type**, so the store refuses an upload whose type does not match
what we authorised. That is proven against MinIO, which answers 403 to a
substituted type and stores nothing.

**What it cannot do.** Size. A presigned PUT has no way to express "at most N
bytes", so whoever holds the URL can send a hundred gigabytes. Only a
presigned **POST policy** (`content-length-range`) enforces size at the store.

**What we do instead, and why it is weaker.** `complete/` reads the real byte
count with a `head` and refuses anything over the limit, deleting the object.
That costs one wasted upload — bandwidth and storage we pay for before
rejecting it — where a store-side cap would have refused it outright.

**Marked for verification, not assumed.** Whether Cloudflare R2 supports
presigned POST is **not something this project has confirmed**, and §6 forbids
inventing a provider capability. Someone must check before launch. If R2 does
support it, switching is one method in `providers/storage.py` and the
after-the-fact check becomes a second line rather than the only one.

---

## 2. Verification is synchronous; processing is not

**Decision.** `complete/` does a `head` and a sixteen-byte range read before
it returns. Transcoding is a task.

**Why the split falls there.** "That file is not a video" has to reach the
person while they still have the file open. Deferring it means an instructor
learns on publication day, from an email, that an upload they believed was
fine never worked. Conversely, transcoding takes minutes and cannot be held in
a request.

The magic-byte check reads sixteen bytes by range request rather than
downloading the object, because invariant 6 forbids media passing through
Django — a check that violated the invariant it was protecting would be a poor
trade.

---

## 3. The dead-letter queue is a table, not a log

**Decision.** A bounded retry budget with exponential backoff, then a row:
`status=FAILED`, `error_message`, `retry_count`. Readable in admin, filterable,
retryable in bulk.

**Why.** §10 M5 names "no dead-letter queue, so failures vanish silently" as
the mistake for this milestone. Celery has no DLQ of its own, and a traceback
in a worker log is not a queue: nobody can list it, count it for an alert, or
act on it.

**The bug this nearly shipped as.** `complete_upload` was wrapped in
`transaction.atomic`, so the failure path wrote `FAILED` and then raised —
**and the raise rolled the record back**. Every rejected upload would have
stayed `PENDING` with no message, and the queue would have been permanently
empty while appearing to work. A failure has to survive the exception that
reports it. The same shape recurs in the task, and is tested there too.

**Retry does not re-upload.** The master is ours (invariant 7), so a provider
outage costs a click. The test asserts the object key is unchanged, because a
"retry" that silently required a fresh upload would satisfy the weaker
assertion that the status changed.

---

## 4. Two facts about testing this pipeline, learned the hard way

**Celery's eager mode runs retries inline.** A test watching for a `Retry`
exception reports "did not raise" against code that is retrying correctly. So
recovery is asserted through the outcome — a provider that fails once then
succeeds — and the backoff schedule is a named function asserted directly,
because eager mode never exposes the countdown.

**`transaction.on_commit` never fires under pytest-django**, which rolls back
rather than commits. Without `django_capture_on_commit_callbacks` an enqueue
test fails against correct code; and a test asserting the callback was merely
*registered* would pass against code that queued nothing. This is the same
invisibility as ADR-009 §5's deferred constraints, in a different disguise.

**And a third, from CI.** GitHub Actions gives `services:` containers no
command, so MinIO ran bare, printed its usage and exited. It starts with
`docker run` instead, with readiness polled against `/minio/health/live` —
verified by running the exact command rather than reasoning about it.

---

## 5. Abuse cases 10 and 11 are swept, not spot-checked

**Decision.** One test enumerates every media-touching endpoint and asserts
`provider_playback_id` appears in none of them, and that no response contains a
provider URL — against raw bytes, so a value nested anywhere still fails.

**Why a sweep.** A leak is a property of the system. Checking the endpoint you
happened to think of is how the *next* endpoint leaks — and this project has
already shipped that failure once, when a `ReadOnlyModelViewSet` in M4 exposed
every lesson body through a `list` route nobody had considered.

**With a positive twin.** The playback-token endpoint *must* return the handle,
and a test asserts it does. A sweep that found the handle nowhere would also
pass if playback had quietly stopped working.

---

## 6. What M5 did not do

- **No real video provider.** ADR-012 §1. The Mux integration is unproven; what
  is proven is that everything around it is correct and the swap is one file.
- **No transcription.** M6, with Deepgram.
- **No durable audit of token issuance.** §10 M5 asks for one; `AuditLog` is
  M10 (ADR-005 §3), so issuance is a structured log line for now. **This is a
  real gap** for anyone who needs issuance records before M10.
- **No notification on failure.** An instructor must look at the status
  endpoint; nothing tells them. Notifications are M11, so until then "visible"
  means "visible if you check".
- **No timestamp in the webhook signature.** Our scheme accepts a valid old
  signature indefinitely. Real providers include a timestamp to bound replay
  across time, and **M8's adapter must add it** — the idempotency table stops a
  duplicate being *processed* twice, but does not stop a captured payload being
  replayed months later.
