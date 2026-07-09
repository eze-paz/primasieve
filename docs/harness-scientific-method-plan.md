# Harness plan: checklist-enforced hypothesis→evidence loop

**Goal:** make the model converge reliably on hard debugging by treating the todo
list as a *proof obligation* — a prediction committed before the work, a cited
piece of observed output to close it — enforced mechanically, with no hardcoded
domain lessons.

## Foundations — must come first

### F1 · Citable tool-result IDs
Every tool result gets a short per-conversation ordinal `#N`, shown in the result
the model sees; the harness keeps `#N → {tc.id, name, ts, exit/summary}`.
- *Why:* evidence citation + mechanical contradiction inspection ride on this;
  the provider `tool_call_id` is too opaque for the model to cite reliably.
- *Touches:* tool-result emit/append path in `sandpie-worker.js` + rendering. Small–medium.

### F2 · Todo integrity — the "free change" fix
Today `write_todos` full-replaces the list, so the model can rewrite a prediction
after seeing the result, delete an inconvenient failed item, or edit a completed
one — which makes any discipline theater. Fix: stable per-item IDs + reconcile-by-ID
with enforced transition rules:
- **hypothesis locks** the moment an item goes `in_progress` (prediction precedes evidence — no retrofitting);
- **completed items freeze** (content/hypothesis/evidence immutable);
- **no silent deletion** — removing requires explicit `status:"dropped"` (kept, marked), not omission from the resend;
- constrained status transitions (reopening allowed but recorded).
- *Approach:* keep "resend whole list" but reconcile by ID and reject illegal
  mutations with a clear error (less disruptive than add/start/complete ops). Medium.

## Enforcement — rides on F1+F2

- **E1 · Hypothesis required on `in_progress`** — can't start an item without a non-empty prediction/expected-outcome.
- **E2 · Evidence-by-citation on `completed`** — completing requires `evidence` = one or more result IDs (`#N`). Harness validates **exists + within that item's `in_progress` span**; rejects nonexistent/out-of-span. Narrow, *visible* escape (`evidence:"user-confirmed"`) for genuine non-tool evidence, kept auditable.
- **E3 · Mechanical contradiction checks (soft, `>>> drift`-toggleable)**
  - On completion, inspect the cited result(s): failure markers (`exit≠0`/`FAILED`) while claiming done → flag.
  - Independent free tier: prose claims success ("fixed/works/passes") and the **next** result is `exit≠0`/`FAILED` → flag. Zero-cost, high-precision.

## Optional — only if the loop still stalls

- **O1 · Reflection trigger** — generic stall signals (near-duplicate tool calls; an `in_progress` item unchanged for N rounds) inject an evidence-anchored self-critique: *"cheapest experiment to confirm or kill your current hypothesis?"* Model derives the lesson. Largely subsumed by E1/E2; build only if needed.
- **O2 · Semantic evidence judge** — tiny judge compares one item's hypothesis vs its cited result to catch "real but insufficient" evidence. Cheap (tiny explicit inputs). Luxury.

## Honest ceiling & risk
- Mechanical checks catch *missing/failed* evidence, not *real-but-insufficient* — that residual needs judgment (spot-check or O2), but it's a cheap check of one pointed-to result.
- Compliance: adds ceremony; enforce only on the *active* item and on completion, one line per field. Freeze/lock rules + failed-exit backstop bound gaming.

## Related open items (separate threads)
- **Cross-session continuity:** global, self-labeling, recency-surfaced todos/memory at session start (no project-ID key — see below). F2 IDs + timestamps feed it.
- **`read_file`/`edit_file` WSL friction:** redirect OPFS-miss on absolute paths to `shell`.
- From the original RISC-V analysis, still unbuilt: **high-salience steering (#1)**, **sticky-facts-across-compaction (#2)**, **tool-output dedup (#4)**.

## Dependency spine & build order
```
F1 (result IDs) ─┐
F2 (todo integrity) ─┼─► E1 (hypothesis)  ─► E3 (contradiction)
                     └─► E2 (cited evidence) ┘        O1 / O2 (later)
```
1. **F1 + F2 together** (foundations)
2. **E1 + E2** (core discipline)
3. **E3** (cheap, high-value)
4. O1/O2 only if it still stalls.

## Design decisions already settled (context)
- **Project identity:** do NOT key memory/todos by a project id (cwd is unreliable
  under `shell()`). Go global + self-labeling + recency-surfaced, like Claude Code
  memory. "Phase 2 (getProjectId fix)" is deleted, not solved.
- **Reflection is model-generated, not hardcoded:** harness supplies the *trigger*
  (generic stall/loop/contradiction), the model supplies the lesson.
- **Contradiction detection reliability:** semantic cases need a conservative,
  quote-or-silent LLM judge over a short window anchored to the stated hypothesis;
  the "claimed-done-but-exit≠0" case is free/mechanical — do that tier first.

## Eval set (prompts that stress the design)
- **A (checklist clearly helps — falsifiable):** C.J PC-update bug; prefill regression hunt; make decode faster without quality loss.
- **B (helps, evidence-quality ceiling):** behavior-preserving refactor; conditional sync-orphan bug.
- **C (weak/fails — negative/unfalsifiable):** flaky-test fix; security audit; "correct across all shapes?" — cited-evidence gives false comfort for absence/coverage claims. Decide: accept, special-case (demand repro/coverage artifact), or warn on completion of unfalsifiable items.
- **D (long-horizon drift):** boot Alpine to a shell — exercises F2 freeze/no-silent-delete + cross-session continuity together.
