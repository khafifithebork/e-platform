# Agent Prompt Templates

Reusable prompts for working with a local coding agent on this project. `CLAUDE.md` is loaded automatically; these are what you paste at the start of a session or task.

---

## 1. Milestone kickoff

Use once per milestone, before any code.

```
Read CLAUDE.md, docs/STATUS.md, and the section of docs/architecture.md
covering milestone <M#>.

Do not write code yet. Produce a milestone plan:

1. Objective, restated in your own words.
2. Every deliverable, broken into tasks small enough to review in one sitting.
3. Task order, with dependencies marked.
4. Which architectural invariants each task touches.
5. Database changes — models, fields, constraints, indexes, migration order.
6. API surface — endpoints, methods, status codes, permissions.
7. Tests required, with the coverage target for each area.
8. Anything ambiguous or blocked by an open decision in CLAUDE.md §11.
9. What you would deliberately NOT build in this milestone, and why.

Flag anything in the architecture doc you think is wrong or has been
overtaken by events. I would rather hear it now.
```

---

## 2. Single task

```
Task: <one sentence>
Milestone: <M#>
Relevant docs: <sections>

Follow the work protocol in CLAUDE.md §7. Plan first, then stop and wait
for my approval before writing code.
```

---

## 3. Code review

Use on your own work as well as the agent's.

```
Review the changes in <files / diff> as a senior engineer would review a
pull request on this project.

Check specifically:
- Every invariant in CLAUDE.md §4
- Business logic that leaked into views or serializers
- Querysets not scoped to the requesting user (IDOR)
- N+1 query patterns
- Missing negative-path tests (wrong user, wrong role, no subscription)
- Error handling and failure modes, not just the happy path
- Anything that would be painful to change in six months

Rank findings: blocking / should fix / consider. Be direct. Do not
soften a real problem, and do not pad the list with nitpicks to look
thorough.
```

---

## 4. Debugging

```
Symptom: <what you observe>
Expected: <what should happen>
What I have already tried: <...>

Before proposing a fix:
1. State your top three hypotheses, ranked by likelihood.
2. Say what evidence would distinguish them.
3. Gather that evidence.

Then fix the cause, not the symptom. If the fix requires weakening a
test or a security control, stop and tell me instead.
```

---

## 5. Explain (learning mode)

```
Explain <concept> as it applies specifically to this codebase.

- Why we chose this approach here
- What the alternatives were and their trade-offs
- What breaks if it's done wrong
- Where in our code it shows up

Assume I know the fundamentals but not the reasoning. Use a concrete
example from our own domain, not a generic tutorial one.
```

---

## 6. End of session

```
Update docs/STATUS.md:
- Milestone and task now in progress
- What was completed this session
- What is half-finished, and precisely where you stopped
- Blockers and open questions
- What the next session should start with

Be accurate about what is incomplete. A wrong status file is worse
than no status file.
```

---

## 7. Weekly review

```
Read docs/STATUS.md and the git log for the last week.

1. Are we on track against the milestone plan?
2. What technical debt accumulated, and is any of it worth paying down now?
3. Has anything drifted from the architecture docs?
4. Any invariant we're eroding without having decided to?
5. What is the single highest-risk thing in the codebase right now?

Be blunt. I want the problems, not a progress report.
```
