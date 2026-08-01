# VietLaw Conversational Demo V2 — Architecture Hardening V2

Verdict: `VIETLAW_CONVERSATIONAL_DEMO_V2_HARDENED_ARCHITECTURE_READY`

Documentation-only hardening pass over
`VIETLAW_CONVERSATIONAL_DEMO_V2_ARCHITECTURE_AND_PLAN.md` (V1). No source, test, data or
package file was modified. Nothing staged, committed, pushed, merged, rebased or deployed.

Worktree `VietLaw-Chat-conversational-demo-v2`, branch
`feature/conversational-rental-deposit-demo-v2`, HEAD `49051f2` — all verified before work
began.

---

## 1. What changed from V1, and why

V1 was written against the `backend_lite` checkpoint only. The live test ran against the
**production backend on `origin/main`**, which is a different codebase with a different
failure profile. Six product failures were reported. Diagnosing them required separating
which are production-backend failures, which are `backend_lite` failures, and which are
both — because only the second and third categories constrain V2.

I reproduced every case against real code rather than reasoning from the report.

### 1.1 Failure attribution — measured

| # | Reported failure | Production backend (`d67ece4`) | `backend_lite` checkpoint (`af27483`) | V2 impact |
| --- | --- | --- | --- | --- |
| F1 | `"xin chào?"` treated as unsupported / non-Vietnamese | **fails** — no greeting handling exists at all | passes with diacritics; **fails without** (`"xin chao?"` → `policy_direct`) | **real V2 gap** (accentless) |
| F2 | `"bạn làm được gì?"` had no capability route | **fails** — no capability handling exists at all | passes with diacritics; **fails without** (`"ban lam duoc gi?"` → `policy_direct`) | **real V2 gap** (accentless) |
| F3 | `"Vậy tôi cần chuẩn bị những bằng chứng gì?"` lost same-chat context | fails | **fails** — `policy_direct` | already RC-1/RC-2 in V1 |
| F4 | `"Tôi nên làm gì tiếp?"` could not resolve active matter | fails | **fails** — `policy_direct` | already RC-6 in V1 |
| F5 | `"Tôi nói nhầm, số tiền là 15 triệu."` could not correct state | fails | **fails** — `policy_direct` | already RC-7 in V1 |
| F6 | Unsupported responses repeated badges, source-empty boilerplate, long disclaimers | **fails** | **fails on the baseline path** | **root cause newly isolated** |

Measured evidence for the `backend_lite` column:

```text
'xin chào?'          social=GREETING          route=social_direct
'xin chao?'          social=None              route=policy_direct     <-- accentless gap
'bạn làm được gì?'   social=CAPABILITY_QUERY  route=capability_direct
'ban lam duoc gi?'   social=None              route=policy_direct     <-- accentless gap
'Vậy tôi cần chuẩn bị những bằng chứng gì?'   route=policy_direct
'Tôi nên làm gì tiếp?'                        route=policy_direct
'Tôi nói nhầm, số tiền là 15 triệu.'          route=policy_direct
```

Production-backend evidence: `grep -rn "chào" backend/app/` returns **zero hits**. There is
no greeting, social or capability path anywhere in that service, and no episode/conversation
state module. F1, F2 and F6 are therefore structural absences there, not tuning problems.

### 1.2 Two corrections to V1 that the live test forced

**Correction A — the accentless gap is real and V1 missed it.**
V1 §8 said regex `fullmatch` survives only as cue detectors, but it kept
`detect_social_intent` as "reuse unchanged". That is wrong. The module's patterns are
**accent-bearing** (`xin\s+chào`, `bạn\s+làm\s+được\s+g[ìi]`) and it is called with
`normalized_text`, which preserves accents. Vietnamese users routinely type without
diacritics; `"xin chao?"` and `"ban lam duoc gi?"` both fall through to the
scope-refusal. V1's "reuse unchanged" verdict for this module is **withdrawn** — see §3.

**Correction B — F6's mechanism is a decision/envelope mismatch, now isolated.**
In `backend_lite/app/services/decision_policy.py`:

```python
if c.detected_language != "vi":
    return "unsupported"
```

`"unsupported"` is a **legal `Decision`**, so the turn is built through the legal envelope:
domain badge, risk badge, decision badge, `SAFETY_NOTICE`, and an empty-source panel. The
frontend only suppresses that furniture when `response_kind === 'social'`
(`StructuredAnswer.tsx:269`), and the baseline path never sets it. So a greeting that trips
the language heuristic renders as a full legal card. F1 and F6 share this root cause.

V2's fix is structural: **`unsupported` and `context_switch` are non-legal response kinds**,
never routed through the legal envelope. See §7.

### 1.3 Production backend is excluded from V2

`origin/main`'s backend is a **read-only reference only**. It is removed from every V2
dependency, wave, file map and task boundary. `backend/**` is untouched by all V2 work.
Beyond the missing conversational surface, its frontend cannot even be installed on
`origin/main` (`npm ci` → `ERESOLVE`, root `vite@^8.1.4` vs `@vitejs/plugin-react@4.7.0`
peering `^4|^5|^6|^7`), which independently disqualifies it as a demo base.

`FRIEND_BACKEND_USED_AS_IMPLEMENTATION_BASE=no`, `BACKEND_LITE_V2_PRIMARY=yes`.

---

## 2. Corrected architecture overview

```text
                 ┌─────────────────────────────────────────────┐
   HTTP turn ───▶│ 1. TurnUnitOfWork.begin (idempotency claim)  │
                 └──────────────────┬──────────────────────────┘
                                    ▼
                 ┌─────────────────────────────────────────────┐
                 │ 2. Safety gate (baseline + bounded defer)    │──▶ unsafe ──▶ baseline
                 └──────────────────┬──────────────────────────┘
                                    ▼
                 ┌─────────────────────────────────────────────┐
                 │ 3. Dual normalization (accented + accentless)│
                 │ 4. Deterministic feature extraction          │
                 └──────────────────┬──────────────────────────┘
                                    ▼
                 ┌─────────────────────────────────────────────┐
                 │ 5. Route classification (11 routes)          │
                 │      confidence >= tau  ──▶ FAST PATH        │
                 │      confidence <  tau  ──▶ INTERPRET        │
                 └──────────────────┬──────────────────────────┘
                    FAST PATH        │        INTERPRET (<=1 call)
                         │           ▼
                         │   ┌───────────────────────────────┐
                         │   │ 6. Semantic interpretation     │
                         │   │    (enum-only proposal)        │
                         │   │ 7. Backend validation is        │
                         │   │    authoritative               │
                         │   └───────────────┬───────────────┘
                         └───────────────────┤
                                             ▼
                 ┌─────────────────────────────────────────────┐
                 │ 8. TX-A: apply fact ops, conflicts, episode  │  (no provider call inside)
                 │ 9. Question graph  10. Decision policy       │
                 │ 11. Retrieval (post-commit projection)       │
                 └──────────────────┬──────────────────────────┘
                                    ▼
                 ┌─────────────────────────────────────────────┐
                 │ 12. Compose API blocks (backend-owned)       │
                 │ 13. TX-B: persist response + event + commit  │
                 └─────────────────────────────────────────────┘
```

Two facts are load-bearing: **the provider is never called inside a SQLite transaction**
(§6), and **at most one provider call happens per turn in total** — the interpretation call
and the plan call are the *same budget*, resolved by the state machine in §5.

---

## 3. Social and capability detection — hardened

V1's "reuse `detect_social_intent` unchanged" is replaced by a new module,
`v2_social_capability.py`, with `social` and `capability` as **separate first-class routes**.

### 3.1 Required tolerances

| Tolerance | Design |
| --- | --- |
| Punctuation | matched against the eligibility-normalized form, where `_SEPARATORS` already maps `. , ; : ! ? " ' " " ' ' ( ) [ ] { } - _ / \` to spaces |
| Capitalization | normalization lowercases before matching |
| Whitespace | separators collapsed to single spaces; leading/trailing stripped |
| **Diacritics present** | matched on the accented normalized form |
| **Diacritics absent** | matched on the accent-stripped form — the V1 gap, now closed |
| Provider calls | **zero**, unconditionally — both routes terminate before the state machine can reach `INTERPRET` |
| Rendering | `response_kind` is `social` / `capability`; no badges, no sources, no in-message disclaimer |

**Dual-form matching rule.** Every social/capability cue is authored **once** in
accent-stripped form and matched against `normalize_for_eligibility(text)`. That function
already performs NFC → lower → strip combining marks → `đ`→`d` → separators→space → collapse.
Authoring in the stripped alphabet means `"Xin chào?"`, `"xin chao?"`, `"XIN CHÀO !!"` and
`"  xin   chao  "` all reduce to the single token sequence `xin chao`. This removes the
accented/accentless duplication that caused F1 and F2 rather than papering over it with a
second pattern table.

### 3.2 Cue registry (accent-stripped, full-message anchored)

| Route | Cues (fullmatch on stripped form, optional trailing particles) |
| --- | --- |
| `social` | `xin chao`, `chao`, `chao ban/anh/chi/em/moi nguoi`, `chao buoi sang/trua/chieu/toi`, `hi`, `hello`, `hey`, `alo`, `helo`, `e lo`, `lo` |
| `capability` | `ban lam duoc gi`, `ban giup duoc gi`, `ban ho tro duoc gi`, `ban co the lam gi`, `ban co the giup gi`, `ban lam gi duoc`, `what can you do`, `help` |
| `identity` → folded into `capability` | `ban la ai`, `ban ten gi`, `ten ban la gi`, `who are you`, `what are you` |

Optional trailing courtesy particles (`nhe`, `a`, `ạ`, `vay`, `the`) and any run of separator
characters are absorbed by the anchor.

**Full-message anchoring is retained.** A social cue mixed with actionable content
(`"Xin chào, tôi đã đặt cọc 20 triệu"`) must **not** be social — it routes to `new_matter`
or `fact_update` and the greeting is answered as a courtesy prefix inside the
`fact_acknowledgement` block. This preserves the checkpoint's precision property while
fixing its recall.

### 3.3 Regression obligation

`T41` and `T42` (§12) run each cue in four surface forms: accented, accentless, punctuated,
and mixed-case-with-padding. Zero provider calls asserted by counter, not by inspection.

---

## 4. Route table — 11 routes

`social` and `capability` are now distinct (V1 merged capability into `social`).

| # | Route | Entry condition | Episode required | Fact ops | Provider budget | `response_kind` | Blocks rendered | Fallback |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | `social` | social cue fullmatch (dual-form); no actionable residue | no | none | **0** | `social` | `social_reply` | n/a |
| 2 | `capability` | capability/identity cue fullmatch (dual-form) | no | none | **0** | `capability` | `capability_reply` | n/a |
| 3 | `new_matter` | deposit cue AND no active episode | creates | Assert, SetGoal | **0** | `legal` | ack + clarify | deterministic |
| 4 | `fact_update` | active episode AND ≥1 fact op AND no draft/guidance intent | yes | Assert, Negate, Confirm | **0** | `legal` | ack + clarify | deterministic |
| 5 | `clarification_answer` | prior turn asked ≥1 question AND message answers ≥1 asked slot | yes | Assert, Negate, Confirm | **0** | `legal` | ack + next question | deterministic |
| 6 | `legal_followup` | active episode AND guidance/vague-follow-up intent | yes | none (read-only) | **≤1** | `legal` | analysis / next steps / checklist | deterministic guidance |
| 7 | `correction` | explicit correction cue AND uniquely targetable slot | yes | Correct, Retract | **0** | `legal` | correction ack | deterministic |
| 8 | `draft_request` | explicit drafting intent | yes | SetGoal only | **≤1** | `legal` | draft (+ ≤2 questions) | deterministic template |
| 9 | `context_switch` | out-of-scope domain cue or explicit topic-change contrast | no — episode untouched | **none** | **0** | `scope` | scope statement | deterministic |
| 10 | `unsafe` | baseline unsafe/high-risk OR bounded risk defer | no | **none** | **0** | `legal` (baseline-owned) | safety response | baseline owns |
| 11 | `unsupported` | nothing above resolves | no | **none** | **0** | `scope` | scope statement | deterministic |

**F6 fix, stated as an invariant:** routes 1, 2, 9 and 11 have `response_kind` in
`{social, capability, scope}` and are **structurally incapable** of emitting
`domain`, `risk_level`, `decision`, `confidence`, `sources` or `safety_notice` — the
composer has no code path that attaches those blocks to a non-`legal` kind, and the schema
validator rejects it. Badges and empty-source panels can no longer appear on a greeting,
a capability answer, or a scope refusal.

Nine of eleven routes cost **zero** provider calls. Only `legal_followup` and
`draft_request` may spend one, and both produce a complete correct answer with zero.

---

## 5. Hybrid turn understanding and the provider-call state machine

### 5.1 Principle

Deterministic features decide the route whenever they are confident. The model is consulted
**only** when Vietnamese phrasing is genuinely ambiguous, it may only **propose** an
interpretation from frozen enums, and backend validation is always authoritative.

### 5.2 States

```text
      ┌──────────┐
      │  START   │
      └────┬─────┘
           ▼
   ┌───────────────────┐
   │ DETERMINISTIC     │  extract features, score routes
   └────┬─────────┬────┘
        │         │
 conf>=τ│         │conf<τ  AND route ∈ INTERPRETABLE
        │         ▼
        │  ┌──────────────────┐
        │  │ INTERPRET        │  provider call #1 (budget consumed)
        │  │ enum proposal    │  ── failure/timeout/invalid ──┐
        │  └────────┬─────────┘                               │
        │           ▼                                          │
        │  ┌──────────────────┐                                │
        │  │ VALIDATE         │ backend authoritative;         │
        │  │ reject → fallback│ rejects unsupported proposals  │
        │  └────────┬─────────┘                                │
        │           │                                          │
        ▼           ▼                                          ▼
   ┌────────────────────────────────────────────────────────────┐
   │ RESOLVED (route fixed, budget_used ∈ {0,1})                 │
   └────────────────────┬───────────────────────────────────────┘
                        ▼
              ┌───────────────────┐
              │ APPLY (TX-A)      │  no provider call may occur here
              └─────────┬─────────┘
                        ▼
        ┌───────────────────────────────┐
        │ PLAN?                          │
        │  budget_used==0 AND route ∈    │
        │  {legal_followup,draft_request}│──yes──▶ provider call #1
        │                                │
        │  budget_used==1  ──────────────┼──no───▶ DETERMINISTIC_PLAN
        └───────────────┬────────────────┘
                        ▼
                  ┌───────────┐
                  │ COMPOSE   │
                  └───────────┘
```

### 5.3 The one-call invariant

A single counter `budget_used ∈ {0,1}` is carried on the turn context. `INTERPRET` and
`PLAN` **draw from the same budget**. Therefore:

- a turn that needed interpretation gets a **deterministic** plan;
- a turn that was deterministically confident may spend its one call on the plan;
- **no turn ever makes two provider calls**, and there is no repair call.

`ONE_TOTAL_PROVIDER_CALL_DEFINED=yes`. This is enforced by a runtime assertion in
`TurnUnitOfWork.commit()` (`budget_used <= 1`) and by a trajectory-suite metric, not by
convention.

`INTERPRETABLE` routes are `{legal_followup, correction, draft_request, fact_update,
clarification_answer, context_switch}`. `social`, `capability`, `unsafe` and `unsupported`
are **never** interpretable — they cannot reach `INTERPRET`, guaranteeing the zero-call
requirement for greetings and capability queries.

### 5.4 Interpretation contract

`SemanticInterpretation` — enum-only, `additionalProperties=false`, native Structured
Outputs, local Pydantic revalidation, no repair.

| Field | Type |
| --- | --- |
| `proposed_route` | enum of the 11 routes |
| `antecedent_kind` | enum: `active_episode` \| `last_draft` \| `last_question` \| `none` |
| `referenced_slot_ids` | list[enum FactSlotId], ≤3 |
| `correction_target_slot` | enum FactSlotId \| `none` |
| `correction_confidence` | enum: `unambiguous` \| `ambiguous` |
| `out_of_scope_domain` | enum: `loan` \| `traffic` \| `business` \| `consumer` \| `other` \| `none` |

The model **may not**: choose the episode, write facts, supply values/amounts/dates, override
a conflict, or declare an ambiguous correction authoritative. None of these has a field.

### 5.5 Backend validation is authoritative

Every proposal passes five checks; any failure discards the proposal and falls back to the
deterministic ladder (V1 §8.4):

1. **Route legality** — proposed route's entry conditions must hold in deterministic features
   (e.g. `correction` requires a correction cue actually present in the text).
2. **Antecedent existence** — `active_episode` requires a loaded active episode;
   `last_draft` requires a previous draft event.
3. **Slot ownership** — every `referenced_slot_id` must belong to the active episode's
   `issue_type`.
4. **Correction safety** — the backend independently re-derives ambiguity. A model claim of
   `unambiguous` is **advisory only**; if the backend finds the old value does not match the
   current fact, or the target slot is not uniquely determined, the correction is treated as
   ambiguous and no state is written.
5. **Budget** — validation cannot itself trigger another call.

`HYBRID_INTERPRETATION_DEFINED=yes`.

---

## 6. Persistence, TurnUnitOfWork and idempotency

### 6.1 The rule that shapes everything

**No SQLite transaction may be open across a provider call.** Provider latency is unbounded;
holding `BEGIN IMMEDIATE` across it would serialize the whole database on network I/O and
convert a provider timeout into a write-lock outage. The turn is therefore split into two
transactions with the provider call strictly between them.

### 6.2 Two-phase turn

| Phase | Contents | Provider |
| --- | --- | --- |
| **TX-A** | claim idempotency row; load episode at `version=v`; apply fact operations; detect conflicts; bump to `v+1`; write `pending` turn row | never |
| *(gap)* | interpretation and/or plan call | ≤1 call here |
| **TX-B** | re-check `version == v+1`; persist response blocks; append episode event; mark turn `committed` | never |

Read-only routes (`legal_followup`) skip the mutation part of TX-A but still claim the
idempotency row, so replay protection is uniform.

### 6.3 Additional table

```sql
CREATE TABLE legal_turns (
    turn_id           TEXT PRIMARY KEY,
    chat_id           TEXT NOT NULL,
    episode_id        TEXT NULL,
    request_id        TEXT NOT NULL,
    idempotency_key   TEXT NOT NULL,
    user_message_id   TEXT NOT NULL,
    status            TEXT NOT NULL CHECK(status IN ('pending','committed','abandoned')),
    route             TEXT NULL,
    budget_used       INTEGER NOT NULL DEFAULT 0 CHECK(budget_used BETWEEN 0 AND 1),
    ops_applied       INTEGER NOT NULL DEFAULT 0 CHECK(ops_applied IN (0,1)),
    response_json     TEXT NULL,
    episode_version_before INTEGER NULL,
    episode_version_after  INTEGER NULL,
    created_at        TEXT NOT NULL,
    committed_at      TEXT NULL,
    FOREIGN KEY(chat_id) REFERENCES chats(chat_id),
    FOREIGN KEY(episode_id) REFERENCES legal_episodes(episode_id)
);
CREATE UNIQUE INDEX idx_turns_idempotency ON legal_turns(chat_id, idempotency_key);
CREATE INDEX idx_turns_pending ON legal_turns(chat_id, status) WHERE status = 'pending';
```

This joins the four V1 tables (`legal_episodes`, `legal_episode_facts`,
`legal_episode_events`, `legal_episode_asked_questions`) in the **chat DB**, which V1 §6.1
verified is safe: `_base_objects` name-filters `sqlite_master` before comparing, so
`verify_base_schema` tolerates additional tables. `adapters/migrator.py` remains untouched
(V1 risk R-8).

### 6.4 Guarantees

| Guarantee | Mechanism |
| --- | --- |
| **Fact ops applied exactly once** | `ops_applied` flag set inside TX-A in the same transaction as the fact rows. A replay finds it already `1` and skips application entirely. |
| **Duplicate request replay** | `idempotency_key = SHA-256(chat_id ‖ user_message_text ‖ client_turn_nonce)`. `UNIQUE(chat_id, idempotency_key)`: a duplicate insert fails, the existing row is read, and if `status='committed'` the stored `response_json` is returned verbatim — **no** provider call, **no** re-application. |
| **Pending-turn recovery** | A row left `pending` (crash between TX-A and TX-B) is detected on the next turn in that chat. Facts were already committed in TX-A, so recovery does **not** re-apply them; it marks the row `abandoned`, appends a `turn_abandoned` event, and proceeds. Bounded to the most recent N pending rows per chat, mirroring the existing bounded SQLite request recovery. |
| **No transaction during provider call** | Structural: the client is only reachable from the gap phase; `TurnUnitOfWork` asserts `not connection.in_transaction` before invoking it. |
| **Version safety** | TX-B re-checks the episode version; a mismatch (concurrent turn) discards the plan and re-renders deterministically from the committed projection rather than writing stale guidance. |

`TURN_IDEMPOTENCY_DEFINED=yes`.

### 6.5 Frozen LegalEpisode state and correction provenance

V1 §5 is carried forward unchanged and **frozen**: `LegalEpisode` (14 fields),
`EpisodeFact` (11 fields), 13 fact slots, one active episode per chat enforced by
`CREATE UNIQUE INDEX … ON legal_episodes(chat_id) WHERE active = 1`, and one current fact per
slot via `… ON legal_episode_facts(episode_id, slot) WHERE current = 1`.

`LEGAL_EPISODE_DEFINED=yes`.

**Provenance categories (corrected).** V1 used `Claimant` (`user` / `counterparty` /
`authority` / `unknown`). V2 replaces the `authority`/`unknown` members with an explicit
four-value provenance enum that distinguishes *who said it* from *who derived it*:

| Provenance | Meaning | May be written by | Rendered as fact to the user |
| --- | --- | --- | --- |
| `user_asserted` | the user stated it, with a validated anchor into their own message | deterministic extractor only | yes |
| `counterparty_reported` | the user reports what the landlord said | deterministic extractor only | yes, attributed ("chủ nhà cho biết…") |
| `system_inferred` | backend derived it from other known facts | backend rules only | only in `known_facts`, marked inferred |
| `system_default` | a policy default (e.g. `deposit_currency = VND`) | backend only | never rendered as a user fact |

Rules: a `system_inferred` or `system_default` fact can **never** overwrite or dispute a
`user_asserted` one; `counterparty_reported` conflicting with `user_asserted` yields
`disputed`, never an overwrite (V1 §9.1 rule 6); the model can write **none** of the four.

**Correction provenance chain.** An explicit correction writes a new
`legal_episode_facts` row with `supersedes_fact_id` pointing at the superseded row, the old
row keeps `current=0`, and both retain their anchors and provenance. The full chain is
reconstructible by walking `supersedes_fact_id`, and a `fact_corrected` event records
`(slot, old_fact_id, new_fact_id, provenance, correction_confidence, request_id)`.

`CORRECTION_PROVENANCE_DEFINED=yes`.

### 6.6 One active episode with safe sequential reset

Exactly one `active=1` episode per chat. Reset is **sequential and explicit**, never
concurrent:

1. Trigger: the user unambiguously starts a different rental-deposit matter, or explicitly
   asks to start over. Never triggered by `context_switch` (which leaves the episode alone)
   and never by the model.
2. Inside a single TX-A: `UPDATE … SET active=0, status='abandoned'` on the current episode,
   then `INSERT` the new episode with `active=1`.
3. The partial unique index makes any interleaving that would produce two active episodes
   fail at the database level rather than in application logic.
4. A `episode_reset` event links `old_episode_id → new_episode_id`; no fact is copied
   across, so the new matter starts clean and the old one stays fully auditable.

---

## 7. V2 API block contract

The response is an ordered list of typed blocks. The backend owns every visible string.
Twelve block types; `response_kind` gates which may appear.

| Block | Payload | Allowed `response_kind` |
| --- | --- | --- |
| `social_reply` | `text` | `social` |
| `capability_reply` | `text`, `supported_topics[]` | `capability` |
| `fact_acknowledgement` | `fragments[]` (slot, rendered text, provenance) | `legal` |
| `clarifying_questions` | `lead_text`, `questions[]` (question_id, text) | `legal` |
| `analysis` | `text`, `reason_codes[]` | `legal` |
| `next_steps` | `steps[]` (action_code, text) | `legal` |
| `checklist` | `items[]` (checklist_id, text) | `legal` |
| `draft` | `title`, `body`, `template_code`, `copyable: true` | `legal` |
| `known_facts` | `facts[]` (slot, label, value_text, provenance, state), `collapsed: true` | `legal` |
| `uncertainty` | `text`, `unknown_slots[]` | `legal` |
| `sources` | `sources[]` (approved SourceObject) | `legal` |
| `metadata` | diagnostic only, **never rendered** | all |

### 7.1 Structural invariants (the F6 fix)

```text
response_kind = social      → blocks ⊆ {social_reply, metadata}
response_kind = capability  → blocks ⊆ {capability_reply, metadata}
response_kind = scope       → blocks ⊆ {analysis(scope text), metadata}
response_kind = legal       → any block; badges permitted only when
                              decision ∈ {answer_with_guidance, refuse_or_escalate}
```

- `domain`, `risk_level`, `decision`, `confidence`, `safety_notice` are **absent** (not
  null-valued) for `social`, `capability` and `scope`.
- A `sources` block with zero sources is **never emitted** — the empty-source boilerplate is
  eliminated at the contract level, not hidden in CSS.
- The disclaimer is **not** a block. It is a single persistent line under the composer,
  rendered once by the shell, independent of message content.

### 7.2 Wire-compatibility

`response_kind` is currently **omitted** by the baseline serializer when unset
(`schemas/api.py`: `data.pop("response_kind", None)`), which makes the frontend's
discriminated union unsound for legacy payloads. V2 keeps V1 §15.1's decision: normalize at
the API boundary (`raw.response_kind ?? 'legal'`), with a separate `RawAnalyzeResponse` wire
type. `scope` and `capability` are **new** members, so the normalizer must map unknown kinds
to `legal` defensively and the union must be exhaustive-checked at compile time.

`API_BLOCK_CONTRACT_DEFINED=yes`.

---

## 8. Conditional question graph

V1's static priority list is replaced by a **directed acyclic graph** whose edges are guarded
by predicates over episode state. Static priority could not express "don't ask about the
refusal reason if the deposit was already returned" and would have re-asked irrelevant
questions after a correction.

### 8.1 Node schema

```text
QuestionNode:
  question_id, target_slot, text_vi
  preconditions[]        -- all must hold for eligibility
  suppressed_when[]      -- any holding suppresses
  unlocks[]              -- nodes eligible once this is answered
  priority_within_tier
  sensitivity            -- must not be identity | financial_account
  changes_guidance: bool
  required_before_draft: bool
```

### 8.2 Graph

```text
                        ┌──────────────────────────┐
                        │ ROOT: deposit_paid known? │
                        └───────────┬──────────────┘
                              no    │    yes
                   ┌────────────────┘
                   ▼
            q_deposit_paid ──unlocks──▶ q_deposit_amount
                                              │
                                              ▼
                                    ┌────────────────────┐
                                    │ TIER 1 — disposition│
                                    └─────────┬──────────┘
                                              ▼
                                    q_deposit_returned
                             ┌────────────────┴────────────────┐
                    returned=yes                        returned=no
                             │                                 │
                             ▼                                 ▼
                   [matter likely resolved]         ┌────────────────────┐
                   suppress refusal/handover/       │ TIER 2 — dispute    │
                   termination questions            └─────────┬──────────┘
                                                              ▼
                                                    q_refusal_reason
                                          ┌───────────────────┴──────────────────┐
                          reason ∈ {forfeiture-type}                 reason = no_reason_given
                                          │                                      │
                                          ▼                                      ▼
                                   q_handover                            q_landlord_response
                                          │                                      │
                                          ▼                                      │
                                  q_termination                                  │
                                          │                                      │
                                          └──────────────┬───────────────────────┘
                                                         ▼
                                               ┌────────────────────┐
                                               │ TIER 3 — evidence   │
                                               └─────────┬──────────┘
                                                         ▼
                                    q_payment_evidence ─▶ q_written_agreement ─▶ q_rental_contract
                                                         │
                                                         ▼
                                                 q_refund_condition
                                                         │
                                                         ▼
                                               ┌────────────────────┐
                                               │ TIER 4 — direction  │
                                               └─────────┬──────────┘
                                                         ▼
                                                    q_user_goal
                                        (suppressed if any goal cue ever observed)
```

### 8.3 Guard examples

| Node | Preconditions | Suppressed when |
| --- | --- | --- |
| `q_refusal_reason` | `deposit_returned = absent` | `deposit_returned = present`; `landlord_refusal_reason` known |
| `q_handover` | `deposit_returned = absent` AND `landlord_refusal_reason ∈ forfeiture-type` | handover known; matter resolved |
| `q_termination` | `property_handed_over` known | `termination_or_cancellation` known |
| `q_user_goal` | no goal cue observed in any turn | goal known or inferable from the current turn |
| any | — | slot `known`; already asked without an intervening conflict; slot `retracted` by the user |

### 8.4 Selection

Walk the graph from the lowest unsatisfied tier; collect eligible nodes; order by
`(tier, priority_within_tier)`; emit `min(3, eligible)` preferring 1–2, and prefer nodes with
`changes_guidance = true`. Universal suppression from V1 §10 is retained, so an answered
question is never re-asked absent a conflict.

**Re-eligibility after correction.** If a correction changes a slot that gated a suppressed
branch, that branch becomes eligible again — this is exactly the case a static list could not
represent.

`CONDITIONAL_QUESTION_GRAPH_DEFINED=yes`.

---

## 9. Revised implementation waves

Waves replace V1's linear A→N chain, allowing parallelism where contracts permit.
**`backend/**` appears in no wave.**

| Wave | Tasks | Depends on | Theme |
| --- | --- | --- | --- |
| **W1 — Contracts** | H-A contracts & episode schema · H-B block contract & `response_kind` extension | — | freeze all types before any behavior |
| **W2 — Persistence** | H-C episode schema + `EpisodeStore` · H-D `TurnUnitOfWork`, idempotency, recovery | W1 | durable state, two-phase turn |
| **W3 — Understanding** | H-E dual-form social/capability · H-F feature extraction & route classifier · H-G fact operations & provenance | W1 (H-G also W2) | deterministic comprehension |
| **W4 — Policy** | H-H conditional question graph · H-I decision policy · H-J retrieval | W3 | what to say |
| **W5 — Provider** | H-K state machine, interpretation & plan services | W3, W4 | bounded, single-call model use |
| **W6 — Presentation** | H-L block composer & templates · H-M runtime integration | W4, W5 | render and wire |
| **W7 — Frontend** | H-N API normalization & block renderer · H-O frontend test tooling | W1, W6 | UI contract |
| **W8 — Verification** | H-P trajectory suite (45) · H-Q browser E2E · H-R live provider smoke | W6, W7 | prove it |

Parallelism: H-A ∥ H-B; H-E ∥ H-F ∥ H-G; H-H ∥ H-I ∥ H-J; H-L ∥ H-N; H-P ∥ H-Q.

### 9.1 Opus 5 task boundaries

Opus 5 **implements** the tasks where a wrong call is expensive and non-local:

| Task | Why Opus 5 |
| --- | --- |
| H-A, H-B | contracts constrain every later wave; a wrong field is a cross-wave rewrite |
| H-D | two-phase turn, idempotency, recovery — concurrency reasoning, hardest to test into correctness |
| H-F | route classification is the product's comprehension surface |
| H-G | provenance and last-writer rules; silent overwrites are the worst failure mode |
| H-I | decision predicates must be total and ordered |
| H-K | the one-call invariant spans interpretation and planning |
| H-M | runtime integration; must preserve baseline containment and flag-off identity |

Sonnet 5 implements against a frozen spec: H-C, H-E, H-H, H-J, H-L, H-N, H-O, H-P, H-Q.
Opus 5 reviews **every** task. H-R is owner-run with Opus 5 assisting.

Hard boundaries for every Opus 5 task: no edits to `backend/**`, `adapters/migrator.py`,
`adapters/migrations/**`, `sqlite_chat_store.py` DDL, `application/fact_conflict_resolver.py`,
`guards/**`, or `data/legal_snippets.json`.

### 9.2 Codex review gates

Each gate is blocking; a failed gate returns the wave to its implementer.

| Gate | After | Codex must independently verify |
| --- | --- | --- |
| **G1 — Contract freeze** | W1 | every type in §5–§7 present; `additionalProperties=false`; **no free-text field on any model-facing model**; block/`response_kind` matrix enforced by validator, not comment |
| **G2 — Persistence integrity** | W2 | both partial unique indexes enforced by the DB; `verify_base_schema` still passes with the five new tables; `migrator.py` untouched; no transaction can span a provider call; replay returns stored response with 0 calls |
| **G3 — Comprehension** | W3 | all four surface forms of every social/capability cue route correctly with 0 calls; mixed social+legal turns are **not** social; negation and amount integrity regressions pass |
| **G4 — Policy determinism** | W4 | decision predicates total and mutually exclusive in order; question graph is acyclic; no answered question re-asked; no identity/financial-account question exists |
| **G5 — Provider budget** | W5 | `budget_used ≤ 1` on every path; `social`/`capability`/`unsafe`/`unsupported` unreachable from `INTERPRET`; every failure mode → deterministic fallback; no repair call; interpretation cannot write facts |
| **G6 — Presentation** | W6/W7 | no badge/source/disclaimer on `social`, `capability`, `scope`; zero-source `sources` block never emitted; §11 target text byte-exact; flag-off identical to checkpoint |
| **G7 — Release** | W8 | all 45 trajectories pass; every §13 metric met; browser E2E green; 475 + 186 baselines still green |

---

## 10. Revised exact file map

### Add — backend (20)

```text
backend_lite/app/contracts/legal_episode.py
backend_lite/app/contracts/fact_operations.py
backend_lite/app/contracts/provenance.py
backend_lite/app/contracts/response_blocks.py
backend_lite/app/contracts/semantic_interpretation.py
backend_lite/app/contracts/demo_llm_v2.py
backend_lite/app/stores/episode_schema.py
backend_lite/app/stores/episode_store.py
backend_lite/app/stores/turn_store.py
backend_lite/app/runtime/turn_unit_of_work.py
backend_lite/app/runtime/v2_turn_pipeline.py
backend_lite/app/services/v2_social_capability.py
backend_lite/app/services/v2_context_features.py
backend_lite/app/services/v2_route_classifier.py
backend_lite/app/services/v2_fact_extractor.py
backend_lite/app/services/question_graph.py
backend_lite/app/services/v2_decision_policy.py
backend_lite/app/services/v2_retrieval.py
backend_lite/app/services/v2_interpretation_service.py
backend_lite/app/services/v2_plan_service.py
backend_lite/app/services/v2_composer.py
backend_lite/app/services/v2_templates.py
```

### Add — tests (12 + fixtures)

```text
backend_lite/tests/contracts/test_legal_episode_contract.py
backend_lite/tests/contracts/test_fact_operations.py
backend_lite/tests/contracts/test_response_blocks.py
backend_lite/tests/contracts/test_interpretation_schema.py
backend_lite/tests/unit/test_social_capability_forms.py
backend_lite/tests/unit/test_route_classifier.py
backend_lite/tests/unit/test_fact_application.py
backend_lite/tests/unit/test_question_graph.py
backend_lite/tests/unit/test_v2_decision_policy.py
backend_lite/tests/unit/test_provider_budget.py
backend_lite/tests/integration/test_episode_store.py
backend_lite/tests/integration/test_turn_idempotency.py
backend_lite/tests/integration/test_turn_pipeline.py
backend_lite/tests/trajectories/**            (45 fixtures + runner)
```

### Add — frontend (7)

```text
frontend/src/api/normalize.ts
frontend/src/components/blocks/BlockRenderer.tsx
frontend/src/components/blocks/DraftBlock.tsx
frontend/src/components/blocks/KnownFactsBlock.tsx
frontend/src/components/blocks/ClarifyingQuestionsBlock.tsx
frontend/src/components/PersistentDisclaimer.tsx
frontend/e2e/**                               (Playwright specs)
```

### Modify (10)

```text
backend_lite/app/contracts/legal_facts.py        additive slot enum only
backend_lite/app/services/demo_llm_guards.py     additive V2 parser
backend_lite/app/runtime/agent_runtime.py        hook only
backend_lite/app/dependencies.py                 wiring
backend_lite/app/config.py                       DEMO_V2_ENABLED, interpretation threshold
frontend/src/api/types.ts                        Raw vs domain types; scope/capability kinds
frontend/src/api/client.ts                       boundary normalization
frontend/src/components/StructuredAnswer.tsx     delegate to BlockRenderer
frontend/src/components/Composer.tsx             persistent disclaimer
frontend/package.json                            add vitest + Playwright (W7 only)
```

### Excluded — unchanged (12)

```text
backend/**                                       production backend: read-only reference
backend_lite/app/adapters/migrator.py
backend_lite/app/adapters/migrations/**
backend_lite/app/stores/sqlite_chat_store.py     DDL, _BASE_OBJECTS, _BASE_DDL
backend_lite/app/application/fact_conflict_resolver.py
backend_lite/app/application/social_intent_detector.py   superseded, not edited
backend_lite/app/services/demo_deposit_extractor.py      superseded, not edited
backend_lite/app/services/demo_generation_router.py      superseded, not edited
backend_lite/app/guards/**
backend_lite/app/services/decision_policy.py     baseline
backend_lite/app/services/response_builder.py    baseline
data/legal_snippets.json                         owner legal content only
frontend/src/components/Sidebar.tsx
frontend/index.html
frontend/src/assets/brand/**
```

`frontend/package.json` is the one package change in the whole programme, confined to W7,
because **no frontend test framework currently exists** — `package.json` has no vitest, no
Playwright, no testing-library, and `"lint": "echo 'lint not configured'"`. V1 listed UI
tests without noting that the tooling was absent; that omission is corrected here.

---

## 11. Target rendering after the first fact update

```text
Tôi hiểu bạn đã đặt cọc 20 triệu và hiện có sao kê chuyển khoản nhưng không có
giấy đặt cọc.

Để xác định hướng xử lý phù hợp, bạn cho tôi biết thêm:
1. Nhà đã được bàn giao chưa?
2. Chủ nhà nói lý do gì khi chưa trả tiền cọc?
```

Blocks: `fact_acknowledgement` + `clarifying_questions`. No badges, no sources, no in-message
disclaimer, zero provider calls.

---

## 12. Updated trajectory suite — 45

V1's 40 are retained. Five mandatory trajectories are added, each derived from a measured
live failure.

| ID | Input | Expected | Asserted |
| --- | --- | --- | --- |
| **T41** | `"xin chào?"` — plus `"Xin chào"`, `"xin chao?"`, `"  XIN CHÀO !!  "` | `route=social`, `response_kind=social` | **provider_calls == 0**; no `domain`/`risk_level`/`decision`/`confidence`; **no `sources` block**; no in-message disclaimer; no episode created |
| **T42** | `"bạn làm được gì?"` — plus `"Bạn làm được gì?"`, `"ban lam duoc gi?"`, `"bạn giúp được gì?"` | `route=capability`, `response_kind=capability` | **provider_calls == 0**; `capability_reply` names the rental-deposit scope; no badges, no sources |
| **T43** | deposit matter established, then `"Vậy tôi cần chuẩn bị những bằng chứng gì?"` | `route=legal_followup`, same `episode_id` | episode unchanged from prior turn; `checklist` block present and relevant to known facts; no fact re-asked; provider_calls ≤ 1 |
| **T44** | deposit matter established, then `"Tôi nên làm gì tiếp?"` | `route=legal_followup`, `decision=explain_next_steps` | resolves to the active episode; `next_steps` reflects actual missing facts; provider_calls ≤ 1; **never** a scope refusal |
| **T45** | `deposit_amount = 20,000,000`, then `"Tôi nói nhầm, số tiền là 15 triệu."` | `route=correction` | new current fact `15,000,000`; old row `current=0` with `supersedes_fact_id` chain intact; provenance `user_asserted`; `fact_corrected` event written; **no confirmation turn**; provider_calls == 0 |

T41 and T42 each run four surface forms, so the accentless gap that produced F1/F2 cannot
regress silently.

### 12.1 Browser-level E2E

Playwright against the built frontend plus a live `backend_lite` instance with
`DEMO_V2_ENABLED=1` and the provider stubbed deterministically. Chromium at desktop
(1440×900) and mobile (390×844) viewports.

| Spec | Asserts |
| --- | --- |
| `e2e/social.spec.ts` | typing `xin chào?` renders one short reply; **zero** badge, source-panel or in-message-disclaimer elements in the DOM; persistent disclaimer visible under the composer exactly once |
| `e2e/capability.spec.ts` | `bạn làm được gì?` renders the capability reply, no legal furniture |
| `e2e/deposit_flow.spec.ts` | full target conversation (5 turns); facts never re-typed; correction updates the visible amount |
| `e2e/draft_copy.spec.ts` | draft block renders; copy action writes the exact draft body to the clipboard |
| `e2e/known_facts.spec.ts` | known-facts summary is collapsed by default and expands on click |
| `e2e/no_debug.spec.ts` | no `metadata` value (`demo_route`, `provider_calls`, `budget_used`) appears anywhere in rendered text |
| `e2e/responsive.spec.ts` | no horizontal body scroll at either viewport; sidebar and logo intact |

`BROWSER_E2E_DEFINED=yes`.

---

## 13. Updated release metrics

| Metric | Target |
| --- | --- |
| Target conversation pass | 100% |
| T41–T45 pass | **100%** |
| Social/capability provider calls | **exactly 0**, all four surface forms |
| Provider calls per turn (any route) | **≤ 1 total**, interpretation + plan combined |
| Badges/sources/disclaimer on `social`/`capability`/`scope` | **0 occurrences** |
| Zero-source `sources` block emitted | **0** |
| Fact value and negation integrity | 100% |
| Explicit correction integrity (value + provenance + chain) | 100% |
| Repeated answered questions | 0 |
| Fabricated fact / source / date / amount | 0 |
| Duplicate-request replay: extra provider calls | **0** |
| Duplicate-request replay: duplicate fact applications | **0** |
| Pending-turn recovery leaving inconsistent state | **0** |
| Transactions open across a provider call | **0** |
| Cross-chat contamination | 0 |
| Unexpected HTTP 500 | 0 |
| Fallback trajectory pass | 100% |
| Browser E2E pass | 100% |
| Baseline regression (flag off) | 475 + 186 green, byte-identical behavior |

---

## 14. Updated risk matrix

| ID | Risk | Level | Mitigation | Test |
| --- | --- | --- | --- | --- |
| R-1 | Episode-state corruption | MEDIUM | two-phase turn; partial unique indexes; version re-check in TX-B | `test_episode_store.py` |
| R-2 | Ambiguous correction overwrites state | **HIGH** | backend re-derives ambiguity; model's `unambiguous` claim is advisory only | T17, T45 |
| R-3 | Negation loss | **HIGH** | `NegateFact` is a distinct type; explicit cue-scope resolution; unresolvable polarity fails closed | T18, T20 |
| R-4 | Context contamination | **HIGH** | `context_switch` performs zero fact ops; out-of-scope amounts never bind | T26–T30 |
| R-5 | Question repetition | MEDIUM | graph suppression + `answered_at`; re-eligibility only via conflict/correction | T09–T14 |
| R-6 | Retrieval on stale facts | MEDIUM | retrieval reads the post-TX-A committed projection | `test_v2_retrieval.py` |
| R-7 | Provider leakage of facts/PII | **HIGH** | interpretation and plan requests carry enum codes and slot **states** only — no values, no message text, no episode ID; services cannot accept a store handle | `test_provider_budget.py` |
| R-8 | Migration breaks analysis DB or older code | MEDIUM | episode/turn tables in chat DB, **not** the `Migrator` registry | `test_episode_store.py` |
| R-9 | Concurrent turns in one chat | MEDIUM | idempotency claim; version re-check; deterministic re-render on mismatch | `test_turn_idempotency.py` |
| **R-15** | **Provider call inside a transaction → DB lock outage** | **HIGH** | structural two-phase split; `TurnUnitOfWork` asserts `not in_transaction` before the call | `test_turn_idempotency.py::test_no_tx_during_provider` |
| **R-16** | **Double-charged provider call on client retry** | MEDIUM | idempotency key; committed replay returns stored response with 0 calls | `test_turn_idempotency.py::test_replay_zero_calls` |
| **R-17** | **Accentless Vietnamese falls to scope refusal (F1/F2 regression)** | **HIGH** | cues authored once in the accent-stripped alphabet; four-form matrix in T41/T42 | `test_social_capability_forms.py` |
| **R-18** | **Legal furniture leaks onto social/scope turns (F6 regression)** | **HIGH** | block/`response_kind` matrix enforced by the schema validator; zero-source block never emitted | `test_response_blocks.py`, `e2e/social.spec.ts` |
| **R-19** | **Interpretation call becomes a second call** | MEDIUM | shared `budget_used` counter; runtime assertion in `commit()` | `test_provider_budget.py` |
| **R-20** | **Episode reset races producing two active episodes** | MEDIUM | sequential reset in one transaction; partial unique index makes it impossible | `test_episode_store.py::test_reset_sequential` |
| R-11 | Scope creep to general legal chat | MEDIUM | `issue_type` CHECK; `context_switch`/`unsupported` terminal | `test_route_classifier.py` |
| R-12 | Legal-content gaps → confident wrong guidance | MEDIUM | uncovered patterns → cautious wording + `uncertainty` block | `test_v2_retrieval.py` |
| R-13 | V2 regresses the checkpoint | LOW | `DEMO_V2_ENABLED` flag; both flag states tested | `test_turn_pipeline.py` |
| R-14 | Fabricated draft content | LOW | templates + trusted facts only; no prose field exists | T21–T25 |

Six risks are HIGH (R-2, R-3, R-4, R-7, R-15, R-17, R-18 — seven), each with a structural
mitigation and a named test. None is BLOCKED.

---

## 15. Limitations carried forward

1. **Legal-content gaps.** Two of six scenarios (no written agreement, no handover) still
   have no approved source. Handled by cautious wording + `uncertainty`; closing them is
   owner legal authorship, unchanged from V1 §13.1.
2. **Cue coverage is bounded.** Dual-form matching fixes the diacritic axis, not the
   vocabulary axis. Unusual phrasings fall to the deterministic ladder — a question, never a
   guess — or to one bounded interpretation call.
3. **One active episode.** Two simultaneous deposit matters in one chat remain unsupported;
   the second triggers correction/conflict or an explicit sequential reset.
4. **E2E provider is stubbed.** Browser E2E asserts UI and call-count behavior, not live
   model quality; that is H-R's job.

---

## 16. Verdict

```text
VIETLAW_CONVERSATIONAL_DEMO_V2_HARDENED_ARCHITECTURE_READY
```

Every required correction is specified against measured behavior, and the four owner
decisions still open from V1 §22.3 each retain a stated working default, so none blocks
implementation.

```text
FRIEND_BACKEND_USED_AS_IMPLEMENTATION_BASE=no
BACKEND_LITE_V2_PRIMARY=yes

SOCIAL_ROUTE_DEFINED=yes
CAPABILITY_ROUTE_DEFINED=yes
PUNCTUATED_GREETING_SUPPORTED=yes
HYBRID_INTERPRETATION_DEFINED=yes
ONE_TOTAL_PROVIDER_CALL_DEFINED=yes
LEGAL_EPISODE_DEFINED=yes
CORRECTION_PROVENANCE_DEFINED=yes
TURN_IDEMPOTENCY_DEFINED=yes
API_BLOCK_CONTRACT_DEFINED=yes
CONDITIONAL_QUESTION_GRAPH_DEFINED=yes
BROWSER_E2E_DEFINED=yes

T41_DEFINED=yes
T42_DEFINED=yes
T43_DEFINED=yes
T44_DEFINED=yes
T45_DEFINED=yes

FILES_MODIFIED_BY_TASK=0
TRACKED_FILES_STAGED=0
COMMIT_CREATED=no
PUSH_PERFORMED=no
PR_MODIFIED=no
MERGE_PERFORMED=no
DEPLOY_PERFORMED=no
```

---

Hard stop.
