# ADR-029 — Shared frontend visual refresh

**Status:** Accepted for the first implementation stage by the owner
**Date:** 2026-09-25

The owner requested a full frontend redesign, selected the most positively
received relevant reference, and approved starting with the shared shell.
Linglee by Aga Ciurysek for 10Clouds is the primary visual reference:
https://dribbble.com/shots/7052720-Linglee-Languages-learning-platform
Its approximately 7.7k likes led the relevant results inspected; likes are
not evidence of usability or permission to reuse its assets.

Use original implementation and existing Lucide icons, cool surfaces, indigo
actions, and a restrained coral brand detail. Keep semantic light/dark tokens,
local system fonts, and the existing shared public/learner shell. Replace the
ASCII navigation tree with padded icon rows and a clear current-page state.
Retain the mobile drawer with keyboard focus containment, focus restoration,
and scroll locking that releases when the desktop rail appears.

This stage changes presentation, not authentication, entitlement decisions,
API contracts, or static generation. No dependencies or services are added.
Page-specific composition and course imagery belong to subsequent stages;
this decision does not mark the full redesign or deployment complete.
