# VietLaw Conversational Rental-Deposit Demo V2 — Architecture, Contract and Implementation Plan V1

Verdict: `VIETLAW_CONVERSATIONAL_DEMO_V2_ARCHITECTURE_READY_WITH_LIMITATIONS`

Read-only architecture task. No source, test, data, package or existing report file was
modified. No stage, commit, push, merge, rebase, reset, clean, stash, PR change or deploy
was performed.

---

## 1. Base, worktree and remote preconditions

### 1.1 Remote audit (after `git fetch --prune origin`)

| Item | Value |
| --- | --- |
| `origin/main` | `d67ece4fc17c2a26218b49b7c5c57c1eb2f43175` |
| `origin/test/pr10-with-current-ui-v1` (checkpoint) | `af27483564b9dc1a978b1a23d6c21c808d628858` |
| Expected checkpoint | `af27483564b9dc1a978b1a23d6c21c808d628858` |
| Checkpoint match | yes |
| PR #10 | `#10`, state `OPEN`, head `release/demo-vertical-slice-port-on-origin-main-v1` |
| PR #10 head SHA | `8ca39b830f988445ca2919a80005c089bcb66680` |
| PR #10 head changed since audit | no |
| Commits `d67ece4..origin/main` | 0 |
| Commits `8ca39b8..origin/release/…-v1` | 0 |
| Collaborator commits after the checkpoint audit | 0 |
| Remote changes touching `backend_lite/**` | 0 |
| Remote changes touching `frontend/**` | 0 |
| Remote changes touching `data/**` | 0 |
| Remote overlap with the proposed V2 surface | 0 |

Only three remote branches carry recent activity, and the two newest are exactly the
checkpoint and the PR #10 head at their audited SHAs. Nothing was merged or rebased.

### 1.2 New worktree

```text
path   /Users/tranvanbac/Documents/AI/ai-agent/VietLaw-Chat-conversational-demo-v2
branch feature/conversational-rental-deposit-demo-v2
base   af27483564b9dc1a978b1a23d6c21c808d628858
HEAD   af27483564b9dc1a978b1a23d6c21c808d628858
index  empty (git status --porcelain produced no output)
```

All other worktrees (primary, `demo-ui-test`, `demo-origin-main-port`, and the nine
competition/release worktrees) were read only and retain their pre-existing status. The
primary worktree's dirty tree was **not** used as an implementation source; every code
path traced below was read from the clean `af27483` worktree.

---

## 2. Current failure analysis

### 2.1 Empirical reproduction

Executed against the clean checkpoint worktree, driving the real classifier, router and
extractor (`classify_demo_scenario` → `route_demo` → `extract_scenario_facts`):

| Turn | Message | Scenario | Route | LLM | Fact ops |
| --- | --- | --- | --- | --- | --- |
| 1 | `Xin chào` | `unsupported` | `social_direct` | no | — |
| 2 | `Tôi đã đặt cọc 20 triệu. Tôi không có giấy đặt cọc nhưng có sao kê chuyển khoản.` | `deposit_fact_update` | `fact_update_direct` | no | `deposit_amount=set_value`, `written_agreement_exists=negate`, `payment_evidence_exists=affirm` |
| 3 | `Tôi đã đặt cọc 20 triệu nhưng chủ nhà chưa trả lại tiền cọc. Viết giúp tôi tin nhắn yêu cầu hoàn trả tiền cọc.` | `deposit_draft_request` | `document_drafting` | yes | `deposit_amount=set_value`, `deposit_returned=negate` |
| 4 | `Tôi nên làm gì tiếp?` | `unsupported` | `policy_direct` | no | — |
| 5 | `Tôi nói nhầm, tiền cọc là 15 triệu.` | `unsupported` | `policy_direct` | no | — |

Additional probes confirming the mechanism:

| Message | Scenario |
| --- | --- |
| `Viết giúp tôi tin nhắn yêu cầu hoàn trả tiền cọc.` | `unsupported` |
| `Chủ nhà chưa trả lại tiền cọc. Viết giúp tôi tin nhắn yêu cầu hoàn trả.` | `unsupported` |
| `vậy tôi cần giấy tờ gì?` | `unsupported` |
| `tôi chưa nhận nhà` | `unsupported` |
| `Tôi đang hỏi chuyện khoản vay, không phải tiền cọc` | `unsupported` |

Turn 3 succeeds **only** because the user re-typed the deposit amount inside a phrasing
that happens to `fullmatch` an approved template. Drop the redundant prefix and the same
drafting request is rejected. This is the defining property of the current build: it is a
sentence-shape recognizer, not a conversation.

### 2.2 Root causes (traced to exact code)

**RC-1 — Classification is a complete-message `re.fullmatch` allowlist.**
[demo_deposit_extractor.py:160-174](backend_lite/app/services/demo_deposit_extractor.py#L160-L174)
runs `pattern.fullmatch(norm)` over six templates in `_TEMPLATES`
([:96-114](backend_lite/app/services/demo_deposit_extractor.py#L96-L114)). Any message
whose *entire* normalized text is not one of six shapes is `UNSUPPORTED`. This was a
deliberate V4 safety closure (documented in the module docstring at
[:8-19](backend_lite/app/services/demo_deposit_extractor.py#L8-L19)) that traded all
conversational generality for precision. It is the single largest cause of turns 4 and 5
failing.

**RC-2 — Routing consumes only the current message.**
`DemoOrchestrator.handle` ([demo_llm_generation.py:258-312](backend_lite/app/services/demo_llm_generation.py#L258-L312))
derives everything from `state.request.question` / `state.classification.*`. `route_demo`
([demo_generation_router.py:45-63](backend_lite/app/services/demo_generation_router.py#L45-L63))
takes `(normalized_text, accentless_text, scenario)` — three views of one message. No
parameter in either signature can carry prior turns.

**RC-3 — Facts are per-request and thrown away.**
`apply_operations` ([demo_llm_generation.py:89-106](backend_lite/app/services/demo_llm_generation.py#L89-L106))
builds `slots: dict[str, FactSlot]` from a **fresh empty dict** on every call, and
`AppliedFacts` is a local dataclass. Its own docstring header says "per-slot, in-memory
only; no persistence" ([:80-82](backend_lite/app/services/demo_llm_generation.py#L80-L82)).
`DEMO_EPISODE_ID = "demo-rental-deposit"` ([:61](backend_lite/app/services/demo_llm_generation.py#L61))
is a **constant string**, not a row — there is no episode identity, no episode store, no
episode lifecycle. The sophisticated A1 resolver in
[fact_conflict_resolver.py](backend_lite/app/application/fact_conflict_resolver.py) (617
lines, with supersession, contradiction and dispute handling) is invoked with
`assertions_by_slot` that never survives the request.

**RC-4 — Chat history is loaded, normalized, and then ignored by the demo path.**
`SameChatContextBuilder.build` ([context_builder.py:14-32](backend_lite/app/services/context_builder.py#L14-L32))
runs at [agent_runtime.py:135-136](backend_lite/app/runtime/agent_runtime.py#L135-L136)
and populates `state.chat.history_messages` and `state.chat.context_topic_terms`. The demo
orchestrator reads neither. It then hard-codes the contradiction into the response
metadata: `"used_current_chat_history": False`
([demo_llm_generation.py:320](backend_lite/app/services/demo_llm_generation.py#L320)).
History exists in state and is discarded — the baseline retriever uses it for query terms
only, never for state.

**RC-5 — Turn 2's response mode is acknowledgement-only by construction.**
`_fact_update_response` ([demo_llm_generation.py:358-368](backend_lite/app/services/demo_llm_generation.py#L358-L368))
emits `"Đã ghi nhận: …"` and passes `clarifying=[]` whenever any fragment was captured. A
clarifying question is produced only in the *empty-extraction* branch. There is no
missing-fact model, no question registry, and no notion of which unknown facts would
change the guidance — so a successful extraction structurally cannot ask anything.

**RC-6 — Turn 4 has no antecedent resolution and falls to a scope-refusal.**
`"Tôi nên làm gì tiếp?"` matches no template → `DemoScenario.UNSUPPORTED` → `route_demo`
falls through to `POLICY_DIRECT` ([demo_generation_router.py:63](backend_lite/app/services/demo_generation_router.py#L63))
→ `_policy_response` ([demo_llm_generation.py:336-341](backend_lite/app/services/demo_llm_generation.py#L336-L341))
tells the user the demo only supports deposit situations — immediately after having
discussed their deposit situation. The user experiences this as amnesia; the code has no
mechanism to experience it otherwise.

**RC-7 — Explicit correction is unrepresentable at the input boundary.**
`FactOpKind.CORRECT` exists in the contract
([legal_facts.py:58-66](backend_lite/app/contracts/legal_facts.py#L58-L66)) and the
resolver handles `ChangeType.CORRECTION`, but no extractor path ever emits a `CORRECT`
operation: `extract_scenario_facts` only emits `SET_VALUE`, `AFFIRM` and `NEGATE`
([demo_deposit_extractor.py:223-240](backend_lite/app/services/demo_deposit_extractor.py#L223-L240)).
Turn 5 is `UNSUPPORTED` before any operation is considered. The correction machinery is
built and unreachable.

**RC-8 — Negation is carried by fixed clause strings, adjacent to a greedy amount regex.**
`_FACT_CLAUSES` ([demo_deposit_extractor.py:117-126](backend_lite/app/services/demo_deposit_extractor.py#L117-L126))
is a substring table; polarity is a hard-coded boolean per phrase. Separately, `_AMOUNT`
([:57-60](backend_lite/app/services/demo_deposit_extractor.py#L57-L60)) takes the **first**
amount in the message unconditionally ([:218](backend_lite/app/services/demo_deposit_extractor.py#L218)).
Any phrasing outside the eight approved clauses loses its polarity silently, and any
message whose first number is not the paid deposit assigns the wrong amount. The template
gate is currently the only thing preventing both.

**RC-9 — Retrieval is bypassed on the demo path.**
The demo returns before `retrieve_sources` at
[agent_runtime.py:216-224](backend_lite/app/runtime/agent_runtime.py#L216-L224). Sources
are a hard-coded pair of IDs — `ARTICLE_328_AUTHORITY_ID` and `EVIDENCE_CHECKLIST_ID`
([demo_llm_generation.py:63-64](backend_lite/app/services/demo_llm_generation.py#L63-L64))
— attached by route, not by facts or user goal. Drafting attaches no sources at all
([:294](backend_lite/app/services/demo_llm_generation.py#L294)).

### 2.3 Where the current-message-only boundary physically is

```text
AgentRuntime.analyze
  ├─ build_same_chat_context      → state.chat.history_messages   ← populated
  ├─ normalize_input              → state.classification.*        ← current message only
  ├─ detect_unsafe_intent
  └─ demo_vertical_slice
       DemoOrchestrator.handle(state)
         classify_demo_scenario(nfc)                  ← current message only  (RC-1)
         route_demo(norm, accentless, scenario)       ← current message only  (RC-2)
         extract_scenario_facts(nfc, scenario, mid)   ← current message only  (RC-8)
         apply_operations(ops, request_id)            ← fresh dict per request (RC-3)
         ...renders and returns; history never read   (RC-4)
```

### 2.4 Safety mechanisms worth keeping

| Mechanism | Location | Keep because |
| --- | --- | --- |
| Baseline-first safety ordering | [demo_llm_generation.py:262-265](backend_lite/app/services/demo_llm_generation.py#L262-L265) | Unsafe/high-risk turns defer to the baseline pipeline *before* any classification, extraction or provider construction. |
| Bounded risk-defer predicate | [demo_generation_router.py:22-38](backend_lite/app/services/demo_generation_router.py#L22-L38) | Deliberately overblocks; fail-closed; matches on the eligibility-normalized form so `mã-tấu` → `ma tau`. |
| Backend owns every visible string | `_ACTION_TEXT`, `render_*`, `_legal_envelope` | The model returns enums only. This is the core anti-fabrication property. |
| Native Structured Outputs + Pydantic revalidation, one call, no repair | [demo_llm_generation.py:163-183](backend_lite/app/services/demo_llm_generation.py#L163-L183) | Every failure mode collapses to one deterministic fallback with a diagnostic reason code. |
| Validated `TextAnchor` provenance | [demo_deposit_extractor.py:149-157](backend_lite/app/services/demo_deposit_extractor.py#L149-L157) | Guarantees `anchor.quote == nfc_original[start:end]`; every fact is re-checkable against the user's own words. |
| Fail-closed anchoring | [:232-234](backend_lite/app/services/demo_deposit_extractor.py#L232-L234) | Drops the fact if its span cannot be located rather than asserting it unanchored. |
| A1 fact-conflict resolver | [fact_conflict_resolver.py](backend_lite/app/application/fact_conflict_resolver.py) | Supersession, contradiction, dispute and epistemic handling are already correct — they were only starved of persistent input. |
| `response_kind` invariants | [content.py:64-118](backend_lite/app/schemas/content.py#L64-L118) | Enforces that social responses carry no domain/risk/decision/sources. |
| Demo failure containment | [agent_runtime.py:165-172](backend_lite/app/runtime/agent_runtime.py#L165-L172) | A demo exception degrades to baseline; never a 500, never a raw leak. |

### 2.5 Replace versus extend

**Replace outright (do not extend):**

- `classify_demo_scenario` and `_TEMPLATES` — a six-shape `fullmatch` allowlist cannot be
  widened into a conversation router. Widening it re-opens exactly the residual-clause
  hole that V4 closed. Replace with route classification over deterministic features plus
  an episode-aware resolver.
- `_FACT_CLAUSES` / `_FACT_CLAUSE_ANCHORS` polarity tables — replace with an explicit
  cue-plus-polarity grammar producing typed operations.
- `apply_operations`'s fresh-dict projection — replace with `EpisodeStore`-backed
  application inside a transaction.
- `_fact_update_response` — replace with the decision policy plus composer.
- The `DEMO_EPISODE_ID` constant — replace with a real episode row.
- Route→sources hard-coding — replace with fact-driven retrieval.

**Extend / reuse unchanged:**

- `fact_conflict_resolver.resolve_fact_operation` — reuse as the projection kernel.
- `legal_facts` contract types (`FactSlot`, `TextAnchor`, `BoundFactOperation`,
  `FactStatus`, `Claimant`, `ChangeType`) — extend with V2 slots, do not redesign.
- `normalize_for_eligibility` — reuse verbatim as the normalization primitive.
- `should_defer_demo_for_risk` — reuse verbatim, called earlier and unchanged.
- `demo_llm_client` native Structured Outputs plumbing, `demo_llm_guards.parse_demo_plan`,
  `default_plan` — extend the plan enum surface only.
- `detect_social_intent` — reuse for the `social` route.
- `AgentRuntime` demo hook and its containment semantics — extend in place.

---

## 3. Target product boundary

V2 is a bounded **rental-deposit** vertical slice with real conversational state.

**In scope:** natural multi-turn conversation; exactly one active rental-deposit matter per
chat; facts accumulated across turns; explicit corrections; negation; useful clarification
questions; vague follow-ups (`tôi nên làm gì tiếp?`); drafting from trusted accumulated
facts; safe legal guidance; deterministic fallback; approved sources only.

**Out of scope:** multiple simultaneous legal matters; general multi-domain legal chat;
autonomous tool loops; long-term cross-chat memory; user accounts; file upload; OCR;
fine-tuning; production legal advice.

**Boundary enforcement:** the `context_switch` route (§8) recognizes an out-of-scope topic,
states the bounded scope, and — critically — performs **zero** fact operations, so an
out-of-scope turn can never contaminate the active episode.

---

## 4. Frozen owner decisions

| Key | Value |
| --- | --- |
| `ACTIVE_EPISODES_V2` | one |
| `EXPLICIT_CORRECTION` | unambiguous correction overwrites the active value; prior value and provenance retained in audit history; no confirmation turn |
| `AMBIGUOUS_CORRECTION` | ask for confirmation; do not overwrite state |
| `DRAFTING_WITH_MISSING_FACTS` | proceed when drafting intent is explicit; known facts only; never invent name, address, date, deadline, contract clause or legal claim; placeholders only when genuinely needed; optionally up to two high-value questions after the draft |
| `CLARIFICATION_LIMIT` | max three questions per turn; prefer one or two; never re-ask an answered fact unless a conflict exists |
| `DISCLAIMER` | one short persistent disclaimer under the composer; no large per-message disclaimer; social greetings omit legal scaffolding |
| `PROVIDER_BUDGET` | zero provider calls for greeting and deterministic fact updates; max one for a legal response turn; no JSON repair call |

No safety or implementation contradiction was found against any of these. They are adopted
as frozen. Four secondary decisions remain open and are listed in §22.3; none blocks
implementation start, and each has a stated working default.

---

## 5. Legal episode contract

New module: `backend_lite/app/contracts/legal_episode.py`.

### 5.1 `LegalEpisode`

| Field | Type | Notes |
| --- | --- | --- |
| `episode_id` | `str` | `ep_<uuid4hex>`; backend-generated only |
| `chat_id` | `str` | FK → `chats.chat_id` |
| `issue_type` | `IssueType` | V2: `rental_deposit` only |
| `status` | `EpisodeStatus` | `gathering` \| `advising` \| `drafting` \| `resolved` \| `abandoned` |
| `active` | `bool` | at most one `active=1` per `chat_id` (partial unique index) |
| `user_goal` | `UserGoal \| None` | `understand_rights` \| `prepare_evidence` \| `draft_message` \| `escalate` \| `unknown` |
| `facts` | `dict[FactSlotId, EpisodeFact]` | current facts only; history in `legal_episode_facts` |
| `evidence` | `list[EvidenceRef]` | typed evidence claims with provenance |
| `missing_fact_ids` | `list[FactSlotId]` | derived each turn, persisted for auditability |
| `asked_question_ids` | `list[QuestionId]` | suppression set |
| `conflict_ids` | `list[str]` | open, unresolved conflicts |
| `selected_source_ids` | `list[str]` | approved source IDs shown so far |
| `created_at` / `updated_at` | ISO-8601 UTC | |
| `version` | `int` | optimistic concurrency; incremented on every mutating turn |

### 5.2 `EpisodeFact`

| Field | Type | Notes |
| --- | --- | --- |
| `fact_id` | `str` | `fct_<uuid4hex>` |
| `slot` | `FactSlotId` | from §5.3 |
| `value` | `FactValue \| None` | typed (`MoneyAmount`, `ExistenceValue`, `PaymentEvidenceValue`, `EnumValue`, `TextValue`) |
| `state` | `known` \| `unknown` \| `disputed` \| `retracted` | |
| `source_message_id` | `str` | FK → `messages.message_id` |
| `evidence_span` | `TextAnchor` | validated against the NFC original |
| `authority` | `Claimant` | `user` \| `counterparty` \| `authority` \| `unknown` |
| `confidence` | `float` | `[0,1]` |
| `created_at` | ISO-8601 UTC | |
| `supersedes_fact_id` | `str \| None` | correction chain |
| `current` | `bool` | exactly one `current=1` per `(episode_id, slot)` |

`state` maps onto the existing `FactStatus` for resolver reuse: `known` ↔
`PRESENT`/`ABSENT`, `disputed` ↔ `DISPUTED`, `unknown` ↔ `UNSET` with
`Epistemic.USER_UNKNOWN`, `retracted` ↔ `current=0` with a `RetractFact` event.

### 5.3 Fact slots — 13 total

| # | Slot | Value type | Authority |
| --- | --- | --- | --- |
| 1 | `deposit_paid` | `ExistenceValue` | **backend-authoritative** |
| 2 | `deposit_amount` | `MoneyAmount` | **backend-authoritative** |
| 3 | `deposit_currency` | `EnumValue{VND}` | **backend-authoritative** (defaults to VND; never model-set) |
| 4 | `written_deposit_agreement` | `ExistenceValue` | **backend-authoritative** |
| 5 | `rental_contract` | `ExistenceValue` | **backend-authoritative** |
| 6 | `payment_evidence` | `PaymentEvidenceValue` | **backend-authoritative** |
| 7 | `property_handed_over` | `ExistenceValue` | **backend-authoritative** |
| 8 | `deposit_returned` | `ExistenceValue` | **backend-authoritative** |
| 9 | `landlord_refusal_reason` | `EnumValue` | **backend-authoritative** when it matches an approved enum; otherwise not recorded |
| 10 | `landlord_response` | `EnumValue{none, verbal, written, refused, promised}` | **backend-authoritative** |
| 11 | `termination_or_cancellation` | `EnumValue{none, by_user, by_landlord, mutual, unclear}` | **backend-authoritative** |
| 12 | `agreed_refund_condition` | `EnumValue{none, verbal, in_contract, unclear}` | **backend-authoritative** |
| 13 | `user_goal` | `EnumValue{UserGoal}` | **backend-authoritative** |

**Authority rule — no exceptions.** All thirteen slots are backend-authoritative facts.
Every one is written **only** by a deterministic extractor operation carrying a validated
`TextAnchor` into the user's own message. The model may never write, propose, amend or
delete a fact in any slot. The model's only permitted influence on facts is *indirect and
bounded*: it may emit `question_ids` from the frozen registry (§11), which cause the
backend to ask questions whose answers the backend then extracts deterministically.

The **model-suggestion** category is therefore empty for facts. It is non-empty only for
presentation: `tone`, ordering of `action_codes`, and `drafting_template_code` — none of
which are facts, none of which are persisted to `legal_episode_facts`.

`landlord_refusal_reason` deserves a specific note: free-text reasons are common and
tempting to store verbatim. V2 stores only an enum drawn from an approved set
(`property_damage`, `unpaid_utilities`, `early_termination`, `contract_breach_claimed`,
`no_reason_given`, `other_unclassified`). A reason that does not map is recorded as
`other_unclassified` with the anchor preserved, and is never rendered back as prose.

---

## 6. Persistence design

Additive only. Message semantics are unchanged; `chats` and `messages` are untouched.

### 6.1 Placement — a verified favorable finding

The episode tables belong in the **existing chat DB** (`settings.chat_db_path`). This is
safe: `_base_objects`
([sqlite_chat_store.py](backend_lite/app/stores/sqlite_chat_store.py)) filters
`sqlite_master` to the four names in `_BASE_OBJECTS` before comparing, so `verify_base_schema`
tolerates additional tables in the same database. Co-location gives real foreign keys to
`chats` and `messages` and a single transaction boundary per turn. Cross-DB placement
would have forfeited both.

Two consequences must be handled by V2-B:

- `bootstrap_base_schema` creates the base DDL only when **no** base object exists, so the
  episode tables need their own idempotent bootstrap/verify pair (`bootstrap_episode_schema`,
  `verify_episode_schema`) modeled on the existing one.
- `Migrator` in [migrator.py](backend_lite/app/adapters/migrator.py) governs a *different*
  database and raises `MigrationError` on `unknown future migration versions`. V2's episode
  schema must **not** be registered there; adding a version to that registry would make an
  upgraded DB unopenable by older code. See risk R-8.

### 6.2 Tables

```sql
CREATE TABLE legal_episodes (
    episode_id    TEXT PRIMARY KEY,
    chat_id       TEXT NOT NULL,
    issue_type    TEXT NOT NULL CHECK(issue_type IN ('rental_deposit')),
    status        TEXT NOT NULL CHECK(status IN ('gathering','advising','drafting','resolved','abandoned')),
    active        INTEGER NOT NULL CHECK(active IN (0,1)),
    user_goal     TEXT NULL,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL,
    version       INTEGER NOT NULL,
    FOREIGN KEY(chat_id) REFERENCES chats(chat_id)
);
CREATE UNIQUE INDEX idx_episodes_one_active ON legal_episodes(chat_id) WHERE active = 1;
CREATE INDEX idx_episodes_chat ON legal_episodes(chat_id, updated_at);

CREATE TABLE legal_episode_facts (
    fact_id            TEXT PRIMARY KEY,
    episode_id         TEXT NOT NULL,
    slot               TEXT NOT NULL,
    value_json         TEXT NULL,
    state              TEXT NOT NULL CHECK(state IN ('known','unknown','disputed','retracted')),
    source_message_id  TEXT NOT NULL,
    anchor_json        TEXT NOT NULL,
    authority          TEXT NOT NULL CHECK(authority IN ('user','counterparty','authority','unknown')),
    confidence         REAL NOT NULL,
    created_at         TEXT NOT NULL,
    supersedes_fact_id TEXT NULL,
    current            INTEGER NOT NULL CHECK(current IN (0,1)),
    FOREIGN KEY(episode_id) REFERENCES legal_episodes(episode_id),
    FOREIGN KEY(source_message_id) REFERENCES messages(message_id),
    FOREIGN KEY(supersedes_fact_id) REFERENCES legal_episode_facts(fact_id)
);
CREATE UNIQUE INDEX idx_facts_one_current ON legal_episode_facts(episode_id, slot) WHERE current = 1;
CREATE INDEX idx_facts_episode_slot ON legal_episode_facts(episode_id, slot, created_at);

CREATE TABLE legal_episode_events (
    event_id     TEXT PRIMARY KEY,
    episode_id   TEXT NOT NULL,
    request_id   TEXT NOT NULL,
    message_id   TEXT NOT NULL,
    seq          INTEGER NOT NULL,
    event_type   TEXT NOT NULL,
    route        TEXT NOT NULL,
    decision     TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at   TEXT NOT NULL,
    FOREIGN KEY(episode_id) REFERENCES legal_episodes(episode_id)
);
CREATE UNIQUE INDEX idx_events_episode_seq ON legal_episode_events(episode_id, seq);
CREATE INDEX idx_events_request ON legal_episode_events(request_id);

CREATE TABLE legal_episode_asked_questions (
    episode_id  TEXT NOT NULL,
    question_id TEXT NOT NULL,
    asked_at    TEXT NOT NULL,
    message_id  TEXT NOT NULL,
    answered_at TEXT NULL,
    PRIMARY KEY (episode_id, question_id),
    FOREIGN KEY(episode_id) REFERENCES legal_episodes(episode_id)
);
```

`asked_questions` is kept as a table rather than a JSON column so suppression is queryable
and `answered_at` is recordable without a read-modify-write of the episode row.

### 6.3 Transactions, concurrency, failure

- **One transaction per turn.** `BEGIN IMMEDIATE` covers: load episode → apply operations →
  insert facts → flip `current` → update `legal_episodes.version` → insert one event row.
  Response rendering happens **after** commit and reads only the committed projection.
- **Optimistic version.** The update is
  `UPDATE legal_episodes SET version = :v+1, … WHERE episode_id = :id AND version = :v`.
  Zero rows affected → `EpisodeVersionConflict` → the turn is retried **once** from a fresh
  load. A second conflict degrades to a read-only response (guidance from the last committed
  state, no fact writes) with `metadata.episode_write_deferred = true`.
- **Migration.** Forward-only `bootstrap_episode_schema()`, idempotent, invoked from the
  same readiness path as the base bootstrap. No data backfill: chats predating V2 simply
  have no episode and start one on their next in-scope turn.
- **Rollback.** Dropping the four tables restores the checkpoint exactly, because no
  existing table, column or constraint is altered. With `DEMO_V2_ENABLED=0` the tables are
  inert even if present.
- **Persistence failure.** Fail **closed on state, open on response**: the transaction rolls
  back, no fact is recorded, and the turn renders a deterministic acknowledgement that does
  **not** claim the fact was stored. Never a 500 (mirrors the existing containment at
  [agent_runtime.py:165-172](backend_lite/app/runtime/agent_runtime.py#L165-L172)).
- **Provider isolation.** The provider client is constructed and called in
  `plan_service`, which receives an immutable `LLMPlanRequest` and returns a
  `DemoResponsePlan`. It holds no store handle, no connection and no episode object. The
  `EpisodeStore` is not in the plan service's constructor signature — the prohibition is
  enforced by the type system, not by convention.

---

## 7. Turn understanding pipeline

Fifteen deterministic stages. Stage 12 is the only one that may touch the network, and at
most once.

| # | Stage | Notes |
| --- | --- | --- |
| 1 | Load active episode | `EpisodeStore.load_active(chat_id)`; may be `None` |
| 2 | Safety / high-risk gate | baseline flags + `should_defer_demo_for_risk`, **before** anything else |
| 3 | Normalize current message | `normalize_for_eligibility` + NFC original retained for anchors |
| 4 | Classify conversation route | deterministic features + episode state (§8) |
| 5 | Extract candidate operations | typed ops with anchors (§10) |
| 6 | Validate evidence and ownership | anchor round-trip; `episode_id` ownership; slot allowlist |
| 7 | Apply facts/corrections transactionally | via `resolve_fact_operation`, inside one tx (§6.3) |
| 8 | Detect conflicts | resolver `DISPUTED` output → `conflict_ids` |
| 9 | Evaluate missing facts | question registry eligibility (§11) |
| 10 | Choose response decision | deterministic predicates (§12) |
| 11 | Retrieve approved sources | fact-driven (§14) |
| 12 | Request one bounded LLM plan | only when §8 allows; never for social/fact_update |
| 13 | Validate the plan | native Structured Outputs + Pydantic; failure → deterministic fallback |
| 14 | Render from backend facts + templates | model contributes no prose (§15) |
| 15 | Persist response and episode event | one event row per turn |

### 7.1 `ConversationRoute` — 10 routes (frozen)

| Route | Entry conditions | Episode required | Fact ops allowed | Provider | Response mode | Fallback |
| --- | --- | --- | --- | --- | --- | --- |
| `social` | `detect_social_intent` matches full-message; no deposit cue | no | none | **0** | greeting/capability text, no legal scaffolding | n/a (deterministic) |
| `new_matter` | deposit cue present AND no active episode | creates one | Assert / SetGoal | 0 | ack + clarify | deterministic |
| `fact_update` | active episode AND ≥1 fact op AND no draft/guidance intent | yes | Assert / Negate / Confirm | **0** | ack + clarify (§15 target) | deterministic |
| `clarification_answer` | prior turn asked ≥1 question AND message answers ≥1 asked slot | yes | Assert / Negate / ConfirmFact | 0 | ack + next question or advance | deterministic |
| `legal_followup` | active episode AND guidance/vague-follow-up intent | yes | none (read-only) | ≤1 | guidance + actions + sources | deterministic guidance |
| `correction` | explicit correction cue AND targetable slot | yes | CorrectFact / RetractFact | 0 | correction ack | deterministic |
| `draft_request` | explicit drafting intent | yes | SetGoal only | ≤1 | draft block (+ ≤2 questions) | deterministic template draft |
| `context_switch` | out-of-scope topic cue, or explicit topic-change cue | no (episode untouched) | **none** | 0 | bounded-scope statement | deterministic |
| `unsafe` | baseline unsafe/high-risk OR `should_defer_demo_for_risk` | no | **none** | 0 | defer to baseline pipeline | baseline owns it |
| `unsupported` | nothing above resolves | no | **none** | 0 | bounded-scope statement | deterministic |

Provider budget check: `social`, `new_matter`, `fact_update`, `clarification_answer`,
`correction`, `context_switch`, `unsafe`, `unsupported` → **0 calls**. Only
`legal_followup` and `draft_request` may spend one. This satisfies `PROVIDER_BUDGET`
exactly, and turn 2 of the target conversation costs nothing.

---

## 8. Context resolution

Resolution runs on deterministic features. Regex `fullmatch` over the whole message is
abolished as a gate; regexes survive only as *cue detectors* feeding a feature vector.

### 8.1 Deterministic feature set

`has_deposit_cue`, `has_amount`, `amount_count`, `has_negation_cue`, `has_correction_cue`,
`has_draft_cue`, `has_vague_followup_cue`, `has_question_mark`, `has_out_of_scope_domain_cue`,
`has_intensifier_cue`, `has_repeat_cue`, `answers_asked_slot_id`, `episode_active`,
`turns_since_episode_update`, `prior_turn_asked_question_ids`, `token_count`.

### 8.2 Worked resolutions

| Utterance | Resolution | Route | Provider |
| --- | --- | --- | --- |
| `tôi nên làm gì tiếp?` | `has_vague_followup_cue` + `episode_active` → antecedent is the active episode | `legal_followup` | ≤1 |
| `vậy tôi cần giấy tờ gì?` | vague follow-up + evidence cue → goal `prepare_evidence` | `legal_followup` | ≤1 |
| `viết mạnh hơn` | `has_draft_cue`(implicit) + `has_intensifier_cue` + last response contained a draft → re-render same template at `tone=polite_firm` | `draft_request` | 0 (template swap only) |
| `gửi lại tin nhắn đó` | `has_repeat_cue` + last response contained a draft → re-render the **stored** draft verbatim | `draft_request` | 0 |
| `không phải 20 triệu, là 15 triệu` | `has_correction_cue` + two amounts, old matches current `deposit_amount` → unambiguous | `correction` | 0 |
| `tôi chưa nhận nhà` | negation cue + handover cue → `property_handed_over = absent` | `fact_update` or `clarification_answer` | 0 |
| `chủ nhà bảo tôi tự bỏ cọc` | counterparty cue → `landlord_response=refused`, `landlord_refusal_reason=contract_breach_claimed`, `authority=counterparty` | `fact_update` | 0 |
| `tôi đang hỏi chuyện khoản vay, không phải tiền cọc` | out-of-scope domain cue + explicit contrast → episode untouched | `context_switch` | 0 |

The counterparty case is the one that most often corrupts state in naive designs: the fact
is recorded with `authority=counterparty`, never as a user-asserted fact, so it can never
silently overwrite the user's own account of the same slot.

### 8.3 Bounded model assistance

The model participates in context resolution **only** on `legal_followup` and
`draft_request`, and only by choosing enum codes from frozen registries. The LLM must not:
choose the episode; invent an antecedent; write facts; override a conflict; or interpret an
ambiguous correction as authoritative. Each prohibition is structurally enforced: the plan
schema has no episode, fact, amount or free-text field, so there is nothing for the model
to say even if it tried.

### 8.4 Fallback when context cannot be resolved

Ordered, deterministic:

1. Active episode + any legal cue → `legal_followup` with `explain_next_steps`.
2. Active episode + no legal cue + short message → `acknowledge_and_clarify`, asking the
   single highest-priority eligible question.
3. No active episode → `unsupported` with the bounded-scope statement.

Ambiguity never produces a guess about facts. It produces a question.

---

## 9. Fact operation contract

New module: `backend_lite/app/contracts/fact_operations.py`. Seven typed operations.

| Operation | Purpose |
| --- | --- |
| `AssertFact` | set a slot to a known value/existence |
| `NegateFact` | set a slot to `absent` |
| `CorrectFact` | supersede the current value (explicit correction only) |
| `RetractFact` | mark the current fact `retracted`, leave no current value |
| `ConfirmFact` | reaffirm without change; refreshes `updated_at`, no new current fact |
| `SetGoal` | set `user_goal` |
| `NoFactOperation` | explicit no-op, recorded for auditability |

Every operation carries: `target_slot`, `proposed_value`, `evidence_message_id`,
`evidence_span` (validated `TextAnchor`), `authority` (`Claimant`), and
`expected_prior_fact_id` / `expected_episode_version` where applicable.

### 9.1 Last-writer rules

1. **Empty slot** → any `AssertFact`/`NegateFact` writes it.
2. **Same value re-asserted** → `ConfirmFact` semantics; no new current fact row; no
   version-visible change beyond `updated_at`.
3. **Different value, no correction cue** → **never a silent overwrite.** The slot becomes
   `disputed`, a conflict is opened, and the decision policy routes to
   `resolve_fact_conflict`. This is the rule that makes ordinary repetition safe.
4. **Different value with an unambiguous correction cue** → `CorrectFact` supersedes: the
   prior row keeps `current=0`, the new row records `supersedes_fact_id`, and both remain
   in `legal_episode_facts` as audit history. No confirmation turn (frozen decision).
5. **Ambiguous correction** (correction cue but the old value does not match the current
   value, or the target slot is not uniquely determined) → **no state change**; ask for
   confirmation.
6. **Counterparty-authority claim conflicting with a user fact** → `disputed`, never an
   overwrite (rule 3 applies regardless of cue).

### 9.2 Negation and amount integrity

Two invariants that address RC-8 directly:

- **Negation is never inferred from clause tables.** Polarity is computed from an explicit
  negation-cue scope (`không`, `chưa`, `chẳng`, `không có`, `chưa được`) resolved against
  the cue token it governs, and is carried in the operation type itself (`NegateFact` is a
  distinct type, not a boolean). A polarity that cannot be resolved fails closed: no
  operation is emitted.
- **Amounts are never taken positionally.** `deposit_amount` is written only when an amount
  token is bound to a deposit cue within a bounded window. A message with two amounts and no
  correction cue emits **no** amount operation and opens a clarification instead of guessing
  — the current "first amount wins" behavior is removed.

---

## 10. Clarification policy — 12 questions

Ordered deterministic registry, `backend_lite/app/services/question_registry.py`. Each entry
has `question_id`, `target_slot`, Vietnamese text, eligibility rule, suppression rule,
priority, sensitivity, `changes_guidance`, `required_before_drafting`.

Universal suppression: a question is suppressed once its target slot is `known`, once it
appears in `legal_episode_asked_questions` without an intervening conflict, or once its
target slot is `retracted` by explicit user retraction.

| P | ID | Target slot | Vietnamese | Changes guidance | Required before draft |
| --- | --- | --- | --- | --- | --- |
| 1 | `q_deposit_returned` | `deposit_returned` | Hiện chủ nhà đã hoàn trả tiền cọc cho bạn chưa? | yes | yes |
| 2 | `q_refusal_reason` | `landlord_refusal_reason` | Chủ nhà nói lý do gì khi chưa trả lại tiền cọc? | yes | no |
| 3 | `q_handover` | `property_handed_over` | Bạn đã được bàn giao nhà chưa? | yes | no |
| 4 | `q_termination` | `termination_or_cancellation` | Việc thuê nhà bị dừng lại do bạn, do chủ nhà, hay hai bên cùng thỏa thuận? | yes | no |
| 5 | `q_written_agreement` | `written_deposit_agreement` | Bạn có giấy đặt cọc hoặc thỏa thuận đặt cọc bằng văn bản không? | yes | no |
| 6 | `q_rental_contract` | `rental_contract` | Hai bên có ký hợp đồng thuê nhà không? | yes | no |
| 7 | `q_refund_condition` | `agreed_refund_condition` | Hai bên đã thỏa thuận điều kiện hoàn cọc như thế nào? | yes | no |
| 8 | `q_user_goal` | `user_goal` | Bạn muốn được hướng dẫn các bước xử lý, chuẩn bị chứng cứ, hay soạn tin nhắn gửi chủ nhà? | yes | no |
| 9 | `q_payment_evidence` | `payment_evidence` | Bạn có chứng từ thanh toán (sao kê, biên nhận) cho khoản đặt cọc không? | yes | yes |
| 10 | `q_deposit_amount` | `deposit_amount` | Số tiền bạn đã đặt cọc là bao nhiêu? | yes | yes |
| 11 | `q_landlord_response` | `landlord_response` | Bạn đã liên hệ yêu cầu hoàn cọc chưa, và chủ nhà phản hồi thế nào? | yes | no |
| 12 | `q_deposit_paid` | `deposit_paid` | Bạn đã thực sự chuyển khoản hoặc đưa tiền đặt cọc chưa? | yes | yes |

### 10.1 Audit of the candidate order

The task's candidate order was `handover → contract/agreement → refusal reason → refund
condition → goal`. Reordered on decision impact:

- **`deposit_returned` promoted to P1.** The candidate list omitted it entirely, yet it is
  the predicate that decides whether this is a dispute at all. Asking anything before it
  risks a full clarification round on a matter that is already resolved.
- **`landlord_refusal_reason` promoted above `handover`.** The refusal reason discriminates
  between "landlord is stalling" and "landlord asserts a forfeiture ground" — the largest
  branch in the guidance tree. Handover matters, but mostly *within* the forfeiture branch.
- **`written_agreement` and `rental_contract` demoted to P5/P6.** Their absence changes
  evidentiary strategy but rarely the immediate next step, and users volunteer them
  unprompted more often than any other slot (as they do in target turn 2).
- **`user_goal` demoted to P8, not removed.** It is frequently inferable from the turn's own
  cues; asking it when it is already inferable is the most common form of the "annoying
  chatbot" failure. It is asked only when no goal cue has ever appeared.
- **P9–P12 are safety-net entries**, eligible only when the slot is genuinely unknown; in
  practice `deposit_paid` and `deposit_amount` arrive in the opening message.

Never asked: CCCD, full address, bank account number, phone number, or any sensitive
identity detail. This is enforced as a registry-level invariant test, not a review habit:
no `question_id` may exist whose `sensitivity` is `identity` or `financial_account`.

---

## 11. Decision policy — 8 outcomes

`backend_lite/app/services/v2_decision_policy.py`, evaluated in order; first match wins.

| # | Outcome | Predicate |
| --- | --- | --- |
| 1 | `refuse_or_escalate` | `route == unsafe` OR high-risk flag |
| 2 | `unsupported_scope` | `route in {context_switch, unsupported}` |
| 3 | `resolve_fact_conflict` | `open_conflicts != []` |
| 4 | `draft_message` | `route == draft_request` AND explicit drafting intent |
| 5 | `acknowledge_and_clarify` | `route in {new_matter, fact_update, clarification_answer}` AND ≥1 eligible question with `changes_guidance` |
| 6 | `ask_clarifying_questions` | `route == clarification_answer` AND no new fact captured AND ≥1 eligible question |
| 7 | `explain_next_steps` | `route == legal_followup` AND vague follow-up AND active episode |
| 8 | `answer_with_guidance` | `route == legal_followup` otherwise; or outcome 5's predicate with no eligible question |

Explicit correction is handled inside `route == correction`: the state is updated, the
correction is acknowledged, and affected guidance is regenerated **only when the user asks
for it** — a correction turn does not silently re-issue a full analysis.

Question count per turn: `min(3, eligible_by_priority)`, preferring 1–2. The composer emits
2 when the top two both have `changes_guidance` and the top one is not independently
sufficient.

---

## 12. Structured LLM contract

`DemoResponsePlanV2`, enum-only, `additionalProperties=false`, Anthropic native Structured
Outputs, local Pydantic revalidation, exactly one call, no repair, deterministic fallback.

| Field | Type |
| --- | --- |
| `response_mode` | enum: `guidance` \| `next_steps` \| `draft` \| `clarify` |
| `issue_summary_code` | enum (extends `SummaryCode` with `deposit_handover_disputed`, `deposit_refusal_reason_given`, `deposit_termination_disputed`) |
| `reason_codes` | list[enum], ≤3 |
| `question_ids` | list[enum from §10 registry], ≤3 |
| `action_codes` | list[enum, extends `ActionCode`], ≤3 |
| `checklist_ids` | list[enum], ≤5 |
| `source_ids` | list[enum of approved IDs], ≤3 |
| `tone` | enum: `neutral` \| `polite_firm` |
| `drafting_template_code` | enum: `refund_request_v1` \| `refund_request_firm_v1` \| `evidence_request_v1` |

Model-authored content is prohibited for: facts, amounts, dates, names, addresses, article
numbers, URLs, deadlines, penalties, free-form final prose, episode IDs and state
mutations. None of these has a field in the schema — the prohibition is structural.

`source_ids` deserves care: the model selects from an enum of approved IDs, and the backend
**intersects** that selection with the retrieval result before rendering. The model can
therefore narrow but never widen the source set, and cannot surface a source that retrieval
did not already justify.

### 12.1 Is the LLM needed per route?

| Route | LLM needed | Justification |
| --- | --- | --- |
| `social` | **no** | fixed text |
| `new_matter` | **no** | ack + registry question |
| `fact_update` | **no** | ack + registry question — deterministic and better |
| `clarification_answer` | **no** | registry-driven |
| `correction` | **no** | deterministic ack |
| `context_switch` | **no** | fixed scope text |
| `unsafe` / `unsupported` | **no** | baseline / fixed text |
| `legal_followup` | **optional (≤1)** | orders and selects among approved actions/checklists; deterministic default is a complete answer |
| `draft_request` | **optional (≤1)** | selects template and tone only; deterministic default template is complete |

Ten routes, two that may call the provider, both of which produce a correct response with
zero calls. The LLM is a ranking and tone layer, never a content or state layer.

---

## 13. Retrieval and legal authority

Retrieval runs **after** episode and intent resolution (stage 11), never before.

**Input:** `issue_type`, current trusted facts (slot → state, values excluded from the query
string), `user_goal`, `decision`, the current message's normalized cue tokens, and the
approved scenario scope. Raw full history is never sent. Values are excluded from queries so
that an amount or a landlord's stated reason cannot leak into a retrieval side channel.

**Authority rules:** only owner-approved source IDs may appear publicly; the backend maps
IDs to final metadata; the model cannot create citations; the empty source set is a valid,
non-degraded outcome; uncertain facts produce cautious wording.

### 13.1 Source-pack sufficiency audit — legal-content gaps

The approved corpus (`data/legal_snippets.json`, 26 entries) contains exactly two
deposit-relevant entries: `civil_deposit_001` (Điều 328 — đặt cọc) and `civil_rental_001`
(tranh chấp thuê nhà / tiền cọc checklist), plus `civil_contract_001/002`,
`general_no_source_001` and `general_privacy_001`.

| V2 scenario | Covered | Gap |
| --- | --- | --- |
| Refund request | partial | `civil_deposit_001` states the deposit mechanism; nothing addresses demand/notice practice |
| Evidence preservation | yes | `civil_rental_001` |
| No written agreement | **no** | nothing on proving a deposit without a written agreement |
| No handover | **no** | nothing on handover obligations or their effect on forfeiture |
| Refusal to return deposit | partial | Điều 328 covers forfeiture/double-return in principle; no entry on contesting an asserted ground |
| Next-step guidance | partial | checklist is generic to rental disputes, not staged to deposit recovery |

**These are legal-content gaps, not architecture gaps.** The architecture handles them
correctly today: `general_no_source_001` plus cautious wording is the designed response to
an uncovered fact pattern, and the no-source case is explicitly valid. V2 can ship on the
current pack with cautious wording on the two uncovered patterns. Four new approved entries
(`civil_deposit_002` proving an unwritten deposit, `civil_deposit_003` handover and
forfeiture, `civil_deposit_004` contesting an asserted forfeiture ground,
`civil_deposit_005` staged deposit-recovery checklist) would close them. Authoring them is
owner legal work, tracked separately from V2-A…V2-N, and is the primary reason this report
is `READY_WITH_LIMITATIONS` rather than `READY_FOR_OWNER`.

---

## 14. Response composer

Eleven backend-owned blocks. Every string originates in a backend template.

| Block | Appears when |
| --- | --- |
| `matter_summary` | `explain_next_steps` or `answer_with_guidance`; suppressed if unchanged since the last turn that showed it |
| `fact_acknowledgement` | ≥1 fact captured or corrected this turn |
| `clarification_lead` | ≥1 clarifying question follows |
| `clarifying_questions` | 1–3 eligible questions |
| `preliminary_analysis` | `answer_with_guidance` only |
| `priority_actions` | `answer_with_guidance` or `explain_next_steps` |
| `evidence_checklist` | goal is `prepare_evidence`, or an evidence gap is material |
| `draft_message` | `draft_message` decision |
| `sources` | retrieval returned ≥1 approved source AND the block is not a repeat of the immediately preceding turn's identical set |
| `disclaimer` | **never in-message**; rendered once, persistently, under the composer |
| `uncertainty_notice` | a material fact is `unknown` or `disputed` and guidance was still given |

Badges (domain / risk / decision) are **not** rendered mechanically per turn. They appear
only on `answer_with_guidance` and `refuse_or_escalate`. Social, fact-update, correction and
clarification turns render no badges — this alone removes most of the current build's
robotic texture.

Target rendering after target turn 2 (`fact_acknowledgement` + `clarification_lead` +
`clarifying_questions`, no badges, no sources, no in-message disclaimer):

```text
Tôi hiểu bạn đã đặt cọc 20 triệu và hiện có sao kê chuyển khoản nhưng không có
giấy đặt cọc.

Để xác định hướng xử lý phù hợp, bạn cho tôi biết thêm:
1. Nhà đã được bàn giao chưa?
2. Chủ nhà nói lý do gì khi chưa trả tiền cọc?
```

---

## 15. UI contract

Presentation authority is the UI checkpoint (`af27483`). Preserved unchanged: logo,
sidebar, social-response rendering, source filtering, responsive layout, composer focus
behavior.

**V2 additions:**

- persistent short disclaimer under the composer (`Composer.tsx`, one line, always visible);
- clarification questions rendered as an ordered list visually distinct from `next_steps`;
- `fact_acknowledgement` visually distinct from `preliminary_analysis`;
- `draft_message` block with a copy action;
- optional "Thông tin đã ghi nhận" summary, **collapsed by default**;
- no debug metadata in normal UI (`demo_route`, `provider_calls`, `outcome` stay in
  `metadata` and are never rendered);
- badges and source panels suppressed on follow-ups per §14.

### 15.1 The `response_kind` mismatch — confirmed, and the recommended fix

The mismatch is real and verified. `frontend/src/api/types.ts` declares `response_kind` as a
**required discriminant** on all four response/content interfaces. The backend, at
[api.py:68-71](backend_lite/app/schemas/api.py#L68-L71), does the opposite:

```python
if "response_kind" not in self.model_fields_set:
    data.pop("response_kind", None)
```

Baseline (non-demo) responses never set the field explicitly, so it is **deleted from the
JSON**. The TypeScript discriminated union is therefore unsound against real baseline
traffic: `response.response_kind === 'social'` is `false` for a legacy payload, so every
legacy response silently falls into the `legal` branch of the union.

**Recommended solution — normalize at the API boundary (frontend).** In the fetch layer,
apply `response_kind: raw.response_kind ?? 'legal'` before the payload is typed, and change
the wire-level type to a separate `RawAnalyzeResponse` with `response_kind?: ResponseKind`.
The domain type keeps `response_kind` required, so no component changes.

Chosen over the alternatives because: making the backend always emit the field would change
the baseline wire contract that PR #10 is currently under review with, and would break the
legacy-omission invariant that
[content.py:90](backend_lite/app/schemas/content.py#L90) deliberately encodes; making the
field optional in TS would push `undefined` handling into every consumer component.
Normalizing at the boundary changes one function and zero components.

**Tests:** (a) unit test — raw payload without `response_kind` normalizes to `'legal'`;
(b) unit test — explicit `'social'` is preserved; (c) type test — `RawAnalyzeResponse` is
not assignable to `AnalyzeResponse` without normalization; (d) integration test — a stored
legacy `AnalyzeContent` rehydrates and renders without badge/source leakage.

---

## 16. Target conversation proof

Starting state: new chat, no episode. `E1` denotes the created episode.

### Turn 1 — `Xin chào`

| | |
| --- | --- |
| Route | `social` |
| Episode | none loaded, none created |
| Fact ops | — |
| Facts | ∅ |
| Missing | not evaluated |
| Asked | ∅ |
| Decision | (social; no legal decision) |
| Retrieval | none |
| Provider calls | **0** |
| Plan | none |
| Rendered | greeting only; no badges, no sources, no in-message disclaimer |
| Event | `social_turn` (no episode → event withheld; recorded in request trace only) |

### Turn 2 — `Tôi đã đặt cọc 20 triệu. Tôi không có giấy đặt cọc nhưng có sao kê chuyển khoản.`

| | |
| --- | --- |
| Route | `new_matter` (deposit cue, no active episode) |
| Episode | `E1` created, `status=gathering`, `active=1`, `version=1` |
| Fact ops | `AssertFact(deposit_paid=present)`, `AssertFact(deposit_amount=20,000,000 VND)`, `AssertFact(deposit_currency=VND)`, `NegateFact(written_deposit_agreement)`, `AssertFact(payment_evidence={bank_transfer, has_document})` |
| Facts | 5 known |
| Missing | `deposit_returned`, `landlord_refusal_reason`, `property_handed_over`, `termination_or_cancellation`, `rental_contract`, `agreed_refund_condition`, `landlord_response`, `user_goal` |
| Asked | `q_deposit_returned`, `q_refusal_reason` |
| Decision | `acknowledge_and_clarify` |
| Retrieval | none (clarification turn) |
| Provider calls | **0** |
| Plan | none |
| Rendered | the §14 target text exactly |
| Event | `facts_applied` seq 1, `version → 2` |

### Turn 3 — `Chủ nhà chưa trả lại tiền cọc. Viết giúp tôi tin nhắn yêu cầu hoàn trả.`

| | |
| --- | --- |
| Route | `draft_request` (explicit draft cue dominates the co-occurring fact) |
| Episode | `E1` loaded at `version=2` |
| Fact ops | `NegateFact(deposit_returned)` — also answers `q_deposit_returned`; `SetGoal(draft_message)` |
| Facts | 7 known |
| Missing | `landlord_refusal_reason`, `property_handed_over`, `termination_or_cancellation`, `rental_contract`, `agreed_refund_condition`, `landlord_response` |
| Asked | `q_deposit_returned` marked `answered_at`; `q_refusal_reason` remains outstanding |
| Decision | `draft_message` |
| Retrieval | `civil_deposit_001` (deposit authority, goal=draft) |
| Provider calls | **1** (template + tone selection) |
| Plan | `response_mode=draft`, `drafting_template_code=refund_request_v1`, `tone=polite_firm`, `question_ids=[q_refusal_reason]` |
| Rendered | draft block using **only** known facts (amount 20 triệu, transfer evidence); no invented name/address/date/deadline; copy action; one follow-up question |
| Event | `facts_applied` + `draft_rendered` seq 2, `version → 3` |

**No fact was repeated by the user.** The amount was never restated, and the draft still
carries it — the precise thing the current build cannot do.

### Turn 4 — `Tôi nên làm gì tiếp?`

| | |
| --- | --- |
| Route | `legal_followup` (vague follow-up + active episode) |
| Episode | `E1` at `version=3` |
| Fact ops | none (read-only) |
| Facts | 7 known, unchanged |
| Missing | unchanged |
| Asked | `q_refusal_reason` still outstanding, asked at most once more |
| Decision | `explain_next_steps` |
| Retrieval | `civil_deposit_001`, `civil_rental_001` |
| Provider calls | **1** (action ordering) |
| Plan | `response_mode=next_steps`, `action_codes=[send_written_refund_request, preserve_payment_evidence, request_written_response]` |
| Rendered | `matter_summary` (suppressed — unchanged since turn 3) + `priority_actions` + `evidence_checklist` + `sources` + `uncertainty_notice` (refusal reason unknown) |
| Event | `guidance_rendered` seq 3, `version` unchanged (read-only turn) |

### Turn 5 — `Tôi nói nhầm, tiền cọc là 15 triệu.`

| | |
| --- | --- |
| Route | `correction` (explicit correction cue; target slot unique; new value present) |
| Episode | `E1` at `version=3` |
| Fact ops | `CorrectFact(deposit_amount: 20,000,000 → 15,000,000)` |
| Facts | 7 known; old fact row `current=0`, new row `supersedes_fact_id` set; both retained |
| Missing | unchanged |
| Asked | unchanged |
| Decision | (within `correction`) acknowledge correction; **no** confirmation turn; guidance not auto-regenerated |
| Retrieval | none |
| Provider calls | **0** |
| Plan | none |
| Rendered | short correction acknowledgement naming old and new values; offer to re-issue the draft |
| Event | `fact_corrected` seq 4, `version → 4` |

Totals across five turns: **2 provider calls**, both on legal turns, none on greeting or
fact updates. Zero facts repeated by the user. Full audit chain for the corrected amount.

---

## 17. Golden trajectory suite — 40 trajectories

`backend_lite/tests/trajectories/` — YAML fixtures driven by one runner.

**Normal follow-ups (8):** T01 greeting→facts→next-steps · T02 facts→"vậy tôi cần giấy tờ gì?"
· T03 facts→guidance→"còn gì nữa không?" · T04 facts→next-steps→evidence checklist ·
T05 multi-turn incremental facts (4 turns) · T06 follow-up after a no-source answer ·
T07 follow-up with a new fact embedded · T08 follow-up after drafting.

**Clarification answers (6):** T09 answers Q1 only · T10 answers both questions in one
message · T11 answers with a negation · T12 answers "tôi không biết" → `unknown` +
`Epistemic.USER_UNKNOWN` · T13 answers a question never asked (still recorded) · T14 answers
then immediately corrects.

**Correction / negation (6):** T15 explicit amount correction (target turn 5) · T16
`không phải 20 triệu, là 15 triệu` · T17 ambiguous correction → confirmation, no state change
· T18 `tôi chưa nhận nhà` negation after a prior affirmation → `disputed` · T19 retraction
(`bỏ qua thông tin đó`) · T20 negation whose sentence contains an unrelated amount (RC-8
regression).

**Drafting (5):** T21 draft with full facts · T22 draft with missing facts, explicit intent ·
T23 `viết mạnh hơn` → `refund_request_firm_v1`, 0 provider calls · T24 `gửi lại tin nhắn đó`
→ verbatim re-render, 0 calls · T25 draft then correction then re-draft.

**Context switches (5):** T26 `tôi đang hỏi chuyện khoản vay, không phải tiền cọc` · T27
traffic-fine question mid-episode · T28 business-registration question mid-episode · T29
switch then return to the deposit matter (episode intact) · T30 out-of-scope question
carrying an amount (must not write `deposit_amount`).

**Ambiguous references (4):** T31 `cái đó thì sao?` with no antecedent · T32 `còn cái kia?`
after two facts · T33 vague follow-up with no active episode · T34 pronoun referring to the
landlord's claim rather than the user's.

**Unsafe / high-risk (3):** T35 threat cue mid-episode → defer to baseline, episode untouched
· T36 police/summons cue → `refuse_or_escalate` · T37 evidence-destruction request → refusal,
no fact write.

**Provider failures (3):** T38 timeout on `legal_followup` → deterministic guidance · T39
schema-invalid plan → deterministic fallback, no repair call · T40 provider disabled →
zero-call deterministic path for every route.

### 17.1 Release metrics

| Metric | Target |
| --- | --- |
| Target conversation (§16) pass | 100% |
| Fact value and negation integrity | 100% |
| Explicit correction integrity | 100% |
| Repeated answered questions | 0 |
| Fabricated fact / source / date / amount | 0 |
| Cross-chat contamination | 0 |
| Unexpected HTTP 500 | 0 |
| Provider calls per legal turn | ≤ 1 |
| Provider calls for greeting / deterministic fact update | 0 |
| Fallback trajectory pass | 100% |

### 17.2 Test layers

| Layer | Path | Covers |
| --- | --- | --- |
| Contract | `tests/contracts/test_legal_episode_contract.py`, `test_fact_operations.py`, `test_plan_v2_schema.py` | type invariants, `additionalProperties=false`, no free-text field |
| State transition | `tests/unit/test_fact_application.py` | §9.1 last-writer rules, supersession, dispute |
| Route | `tests/unit/test_route_classifier.py` | all 10 routes, §8.2 utterances, provider allowance |
| Persistence | `tests/integration/test_episode_store.py` | tx boundaries, partial unique indexes, version conflict, failure-closed |
| Integration | `tests/integration/test_turn_pipeline.py` | 15 stages end to end |
| API trajectory | `tests/trajectories/test_golden_trajectories.py` | all 40 |
| UI | `frontend/src/__tests__/` | `response_kind` normalization, badge suppression, draft copy, collapsed facts |

---

## 18. Implementation decomposition — 14 tasks

Dependency order: A → B → C → D → E → F → G → H → I → J → K → L → M → N.
D and E may run in parallel after C. G and H may run in parallel after F.

**Recommended implementer/reviewer:** Opus 5 implements A, C, D, F, J (contract, semantics
and integration density); Sonnet 5 implements B, E, G, I, K, L (mechanical against a frozen
spec). Opus 5 reviews every task; M and N are owner-run with Opus 5 assisting.

---

### V2-A — Contracts and episode schema

- **Scope:** typed `LegalEpisode`, `EpisodeFact`, 13 slot IDs, enums, `IssueType`,
  `EpisodeStatus`, `UserGoal`. No behavior.
- **Add:** `backend_lite/app/contracts/legal_episode.py`
- **Modify:** `backend_lite/app/contracts/legal_facts.py` (additive slot enum only)
- **Prohibited:** any `services/`, `runtime/`, `frontend/`, `data/`
- **In/Out:** none / importable frozen types
- **Tests:** `tests/contracts/test_legal_episode_contract.py`
- **Accept:** all 13 slots typed; every field in §5.1–5.2 present; round-trip
  `model_dump`/`model_validate` stable; no free-text fact field
- **Rollback:** delete one new file, revert one additive enum

### V2-B — SQLite migration and `EpisodeStore`

- **Scope:** four tables, indexes, `bootstrap_episode_schema`, `verify_episode_schema`,
  `EpisodeStore` (load/create/apply/append-event), optimistic version, tx boundaries.
- **Add:** `backend_lite/app/stores/episode_store.py`,
  `backend_lite/app/stores/episode_schema.py`
- **Modify:** `backend_lite/app/dependencies.py` (wire the store)
- **Prohibited:** `sqlite_chat_store.py` DDL, `_BASE_OBJECTS`, `_BASE_DDL`,
  `adapters/migrator.py`, `adapters/migrations/**`
- **Tests:** `tests/integration/test_episode_store.py`
- **Accept:** existing 475 backend_lite tests still pass; `verify_base_schema` passes with
  episode tables present; partial unique indexes enforced; version conflict raises;
  concurrent-turn test green; failure-closed verified
- **Rollback:** drop four tables; delete two files; revert wiring

### V2-C — Fact operations and provenance

- **Scope:** seven typed operations; deterministic extractor emitting them; anchor
  validation; §9.1 last-writer rules on top of `resolve_fact_operation`; §9.2 negation and
  amount integrity.
- **Add:** `backend_lite/app/contracts/fact_operations.py`,
  `backend_lite/app/services/v2_fact_extractor.py`
- **Prohibited:** `fact_conflict_resolver.py` (reuse unchanged),
  `demo_deposit_extractor.py` (superseded, not edited)
- **Tests:** `tests/unit/test_fact_application.py`, `tests/unit/test_v2_extractor.py`
- **Accept:** every op carries a validated anchor; ordinary repetition never overwrites; two
  amounts without a correction cue emit no amount op; negation never lost; 100% on the
  negation/amount regression set
- **Rollback:** delete two files

### V2-D — Route and context resolver

- **Scope:** 10 routes; §8.1 feature extraction; §8.2 resolutions; §8.4 fallback ladder.
  No `fullmatch` gate.
- **Add:** `backend_lite/app/services/v2_route_classifier.py`,
  `backend_lite/app/services/v2_context_features.py`
- **Reuse unchanged:** `normalize_for_eligibility`, `detect_social_intent`,
  `should_defer_demo_for_risk`
- **Prohibited:** `demo_generation_router.py`, `social_intent_detector.py`
- **Tests:** `tests/unit/test_route_classifier.py`
- **Accept:** all §8.2 utterances resolve as specified; every §16 turn routes correctly;
  provider allowance per route enforced by test; no route reachable without an episode where
  §7.1 requires one
- **Rollback:** delete two files

### V2-E — Missing-fact and question policy

- **Scope:** 12-question registry, eligibility, suppression, priority, sensitivity ban.
- **Add:** `backend_lite/app/services/question_registry.py`,
  `backend_lite/app/services/missing_facts.py`
- **Tests:** `tests/unit/test_question_registry.py`
- **Accept:** no answered question is re-asked absent a conflict; ≤3 per turn; no question
  targets identity or financial-account data (registry-level invariant test)
- **Rollback:** delete two files

### V2-F — Deterministic decision policy

- **Scope:** 8 outcomes with §11 ordered predicates.
- **Add:** `backend_lite/app/services/v2_decision_policy.py`
- **Prohibited:** `services/decision_policy.py` (baseline, untouched)
- **Tests:** `tests/unit/test_v2_decision_policy.py`
- **Accept:** predicates total and mutually exclusive in order; exhaustive route × facts ×
  conflicts matrix covered
- **Rollback:** delete one file

### V2-G — Retrieval integration

- **Scope:** fact-driven retrieval input; source-authority mapping; empty-set handling;
  values excluded from query strings.
- **Add:** `backend_lite/app/services/v2_retrieval.py`
- **Modify:** none (`rag_retriever.py` consumed as-is)
- **Prohibited:** `data/legal_snippets.json`
- **Tests:** `tests/unit/test_v2_retrieval.py`
- **Accept:** retrieval runs only after stage 10; no raw history in the query; no fact value
  in the query; unapproved IDs unreachable; empty set renders cautiously
- **Rollback:** delete one file

### V2-H — Structured LLM plan

- **Scope:** `DemoResponsePlanV2`; enum extensions; native Structured Outputs; one call; no
  repair; fallback; backend intersection of `source_ids`.
- **Add:** `backend_lite/app/contracts/demo_llm_v2.py`,
  `backend_lite/app/services/v2_plan_service.py`
- **Modify:** `backend_lite/app/services/demo_llm_guards.py` (additive parser)
- **Prohibited:** `demo_llm_client.py` transport
- **Tests:** `tests/contracts/test_plan_v2_schema.py`, `tests/unit/test_v2_plan_service.py`
- **Accept:** `additionalProperties=false`; no free-text field exists; exactly one call;
  all failure kinds → deterministic fallback; plan service constructor cannot accept an
  `EpisodeStore`
- **Rollback:** delete two files; revert additive parser

### V2-I — Response composer

- **Scope:** 11 blocks; appearance rules; badge suppression; no in-message disclaimer.
- **Add:** `backend_lite/app/services/v2_composer.py`,
  `backend_lite/app/services/v2_templates.py`
- **Prohibited:** `response_builder.py`
- **Tests:** `tests/unit/test_v2_composer.py`
- **Accept:** §14 target text reproduced byte-for-byte; no badge on social/fact-update/
  correction/clarification turns; every visible string traceable to a template constant
- **Rollback:** delete two files

### V2-J — Runtime integration

- **Scope:** wire the 15-stage pipeline behind `DEMO_V2_ENABLED`; preserve failure
  containment; keep V1 reachable when the flag is off.
- **Add:** `backend_lite/app/runtime/v2_turn_pipeline.py`
- **Modify:** `backend_lite/app/runtime/agent_runtime.py` (hook only),
  `backend_lite/app/dependencies.py`, `backend_lite/app/config.py`
- **Prohibited:** baseline phases below the demo hook
- **Tests:** `tests/integration/test_turn_pipeline.py`
- **Accept:** flag off → checkpoint behavior bit-identical; flag on → §16 proof reproduced;
  no unhandled exception escapes; existing 475 tests pass in both flag states
- **Rollback:** set `DEMO_V2_ENABLED=0`

### V2-K — UI adaptation

- **Scope:** persistent disclaimer; clarification presentation; fact-vs-analysis distinction;
  draft block with copy; collapsed known-facts; badge/source suppression; `response_kind`
  normalization (§15.1).
- **Modify:** `frontend/src/api/types.ts`, `frontend/src/api/client.ts`,
  `frontend/src/components/Composer.tsx`, `StructuredAnswer.tsx`, `MessageBubble.tsx`
- **Prohibited:** `Sidebar.tsx`, `frontend/index.html`, `globals.css` layout/logo rules,
  `src/assets/brand/**`
- **Tests:** four `response_kind` tests from §15.1 plus component tests
- **Accept:** `npm run typecheck` and `npm run build` pass; checkpoint visual identity
  preserved; no debug metadata rendered
- **Rollback:** revert five files

### V2-L — Trajectory evaluation

- **Scope:** 40 trajectories + runner + metrics report.
- **Add:** `backend_lite/tests/trajectories/**`
- **Accept:** every §17.1 metric met
- **Rollback:** delete the directory

### V2-M — Live provider smoke

- **Scope:** real Anthropic call on `legal_followup` and `draft_request`; verify ≤1 call per
  turn and 0 on deterministic routes.
- **Add:** `VIETLAW_CONVERSATIONAL_DEMO_V2_LIVE_SMOKE_V1.md`
- **Prohibited:** committing any key or raw provider payload
- **Accept:** plan validates natively; call counts confirmed from provider-side telemetry;
  fallback verified by induced failure
- **Rollback:** report-only

### V2-N — Internal demo release

- **Scope:** release branch, full verification matrix, report. No deploy without owner
  approval.
- **Add:** `VIETLAW_CONVERSATIONAL_DEMO_V2_RELEASE_V1.md`
- **Accept:** full backend + frontend suites green; §16 reproduced live; owner sign-off
- **Rollback:** delete the release branch

---

## 19. Exact file proposal

### Files to add (24)

```text
backend_lite/app/contracts/legal_episode.py
backend_lite/app/contracts/fact_operations.py
backend_lite/app/contracts/demo_llm_v2.py
backend_lite/app/stores/episode_store.py
backend_lite/app/stores/episode_schema.py
backend_lite/app/services/v2_fact_extractor.py
backend_lite/app/services/v2_route_classifier.py
backend_lite/app/services/v2_context_features.py
backend_lite/app/services/question_registry.py
backend_lite/app/services/missing_facts.py
backend_lite/app/services/v2_decision_policy.py
backend_lite/app/services/v2_retrieval.py
backend_lite/app/services/v2_plan_service.py
backend_lite/app/services/v2_composer.py
backend_lite/app/services/v2_templates.py
backend_lite/app/runtime/v2_turn_pipeline.py
backend_lite/tests/contracts/test_legal_episode_contract.py
backend_lite/tests/contracts/test_fact_operations.py
backend_lite/tests/contracts/test_plan_v2_schema.py
backend_lite/tests/unit/test_fact_application.py
backend_lite/tests/unit/test_route_classifier.py
backend_lite/tests/integration/test_episode_store.py
backend_lite/tests/integration/test_turn_pipeline.py
backend_lite/tests/trajectories/**
```

### Files to modify (9)

```text
backend_lite/app/contracts/legal_facts.py      (additive slot enum only)
backend_lite/app/services/demo_llm_guards.py   (additive V2 parser)
backend_lite/app/runtime/agent_runtime.py      (hook only)
backend_lite/app/dependencies.py               (wiring)
backend_lite/app/config.py                     (DEMO_V2_ENABLED)
frontend/src/api/types.ts
frontend/src/api/client.ts
frontend/src/components/Composer.tsx
frontend/src/components/StructuredAnswer.tsx
```

### Explicitly excluded

```text
backend_lite/app/adapters/migrator.py          (governs a different DB; see R-8)
backend_lite/app/adapters/migrations/**
backend_lite/app/stores/sqlite_chat_store.py   (DDL, _BASE_OBJECTS, _BASE_DDL)
backend_lite/app/application/fact_conflict_resolver.py   (reuse unchanged)
backend_lite/app/application/social_intent_detector.py   (reuse unchanged)
backend_lite/app/guards/**                     (safety guards unchanged)
backend_lite/app/services/decision_policy.py   (baseline)
backend_lite/app/services/response_builder.py  (baseline)
backend/**                                     (production backend, out of scope)
data/legal_snippets.json                       (owner legal content only)
frontend/src/components/Sidebar.tsx
frontend/index.html
frontend/src/assets/brand/**
```

### Migration files

None under `adapters/migrations/`. The episode schema ships as
`stores/episode_schema.py` with its own bootstrap/verify pair (§6.1).

### Proposed commit boundaries

One commit per task, V2-A … V2-N, each independently revertible. V2-K is a single frontend
commit. V2-L, V2-M, V2-N are report/test-only commits.

### Protected WIP and mixed ownership

The **primary worktree** (`/Users/tranvanbac/Documents/AI/ai-agent/VietLaw-Chat`) has 19
modified tracked files and ~30 untracked reports. Of these, seven are files V2 also touches:
`dependencies.py`, `agent_runtime.py`, `schemas/api.py`, `schemas/content.py`,
`lite_content_generator.py`, `response_builder.py`, plus five frontend files and
`data/legal_snippets.json`. **That tree is not an implementation source and must not be
merged, cherry-picked or copied into V2.** All V2 work happens in the clean
`VietLaw-Chat-conversational-demo-v2` worktree from `af27483`. The `demo-ui-test` and
`demo-origin-main-port` worktrees are read-only references.

---

## 20. Risks

| ID | Risk | Level | Mitigation | Test |
| --- | --- | --- | --- | --- |
| R-1 | Episode-state corruption | **MEDIUM** | one tx per turn; optimistic version; partial unique index on `(episode_id, slot) WHERE current=1`; fail-closed on persistence error | `test_episode_store.py::test_corruption_invariants` |
| R-2 | Ambiguous correction overwrites state | **HIGH** | frozen policy: ambiguous → confirm, never write; correction requires a uniquely determined target slot AND a matching prior value | T17, `test_fact_application.py::test_ambiguous_correction_no_write` |
| R-3 | Negation loss | **HIGH** | `NegateFact` is a distinct type, not a boolean; explicit negation-cue scope resolution; unresolvable polarity fails closed | T18, T20, `test_v2_extractor.py::test_negation_integrity` |
| R-4 | Context contamination across topics | **HIGH** | `context_switch` route performs zero fact ops; out-of-scope amounts never bind to `deposit_amount` | T26–T30 |
| R-5 | Question repetition | **MEDIUM** | `legal_episode_asked_questions` with `answered_at`; suppression on `known`; re-ask only on conflict | T09–T14, metric = 0 |
| R-6 | Retrieval on stale facts | **MEDIUM** | retrieval at stage 11, strictly after fact application and commit; input is the committed projection | `test_v2_retrieval.py::test_uses_committed_facts` |
| R-7 | Provider leakage of facts/PII | **HIGH** | plan request carries slot states and enum codes only — no values, no message text, no episode ID; plan service constructor cannot take an `EpisodeStore` | `test_v2_plan_service.py::test_request_payload_has_no_values` |
| R-8 | Schema migration breaks the analysis DB or older code | **MEDIUM** | episode tables live in the chat DB, **not** the `Migrator` registry — registering a version there would make an upgraded DB unopenable by older code (`unknown future migration versions`); `_base_objects` name-filtering verified to tolerate extra tables | `test_episode_store.py::test_base_schema_verify_with_episode_tables` + a `Migrator`-untouched assertion |
| R-9 | Concurrent request races in one chat | **MEDIUM** | `BEGIN IMMEDIATE`; version check; one retry; second conflict → read-only response with `episode_write_deferred` | `test_episode_store.py::test_concurrent_turns` |
| R-10 | Frontend/backend contract drift (`response_kind`) | **MEDIUM** | normalize at the API boundary (§15.1); wire type separated from domain type | four §15.1 tests |
| R-11 | Scope creep back into general legal chat | **MEDIUM** | `issue_type` CHECK constraint allows only `rental_deposit`; `context_switch` and `unsupported` are terminal; slot allowlist enforced at stage 6 | `test_route_classifier.py::test_no_general_legal_route` |
| R-12 | Legal-content gaps produce confidently wrong guidance | **MEDIUM** | uncovered fact patterns route to `general_no_source_001` + `uncertainty_notice` + cautious wording; empty source set is valid | `test_v2_retrieval.py::test_uncovered_pattern_is_cautious` |
| R-13 | V2 regresses the checkpoint baseline | **LOW** | `DEMO_V2_ENABLED` flag; flag-off path bit-identical; existing 475 + 186 tests run in both flag states | `test_turn_pipeline.py::test_flag_off_is_baseline` |
| R-14 | Fabricated content in drafts | **LOW** | draft renders from templates plus trusted facts only; no model prose field exists in the schema | T21–T25, metric = 0 |

No risk is classified `BLOCKED`. Three are `HIGH` (R-2, R-3, R-4, R-7 — four), each with a
structural rather than procedural mitigation and a named regression test.

---

## 21. Limitations

1. **Legal-content gaps (§13.1).** Two of six V2 scenarios — no written agreement, no
   handover — have no approved source. The architecture handles this correctly via cautious
   wording, but the demo will be visibly thinner on those paths until the owner authors four
   new approved entries. This is the reason for `READY_WITH_LIMITATIONS`.
2. **Vietnamese cue coverage is bounded by design.** V2 replaces a six-shape allowlist with
   a cue-plus-feature resolver, not a general Vietnamese grammar. Unusual phrasings will
   fall to the §8.4 fallback ladder — a question, never a guess. Coverage is an empirical
   matter to be tuned against the 40 trajectories.
3. **One active episode.** A user who genuinely has two rental-deposit matters in one chat
   is not supported; the second is treated as a correction or a conflict. This follows the
   frozen `ACTIVE_EPISODES_V2=one` decision.
4. **Provider-side call counting in V2-M** depends on owner-accessible telemetry; the
   in-process counter is authoritative for tests but not independent verification.

---

## 22. Verdict

### 22.1 Verdict

```text
VIETLAW_CONVERSATIONAL_DEMO_V2_ARCHITECTURE_READY_WITH_LIMITATIONS
```

Architecture, contracts, persistence, pipeline, policies and the 14-task decomposition are
complete and internally consistent, and the target conversation is proven end to end.
`READY_WITH_LIMITATIONS` rather than `READY_FOR_OWNER` because of the §13.1 legal-content
gaps, which require owner legal authorship outside the engineering plan.

### 22.2 Required fields

```text
CHECKPOINT_BASE_MATCH=yes
NEW_WORKTREE_CREATED=yes
OTHER_WORKTREES_UNCHANGED=yes

CURRENT_FAILURE_ROOT_CAUSES=9
TARGET_ROUTES_DEFINED=10
FACT_SLOTS_DEFINED=13
CLARIFICATION_QUESTIONS_DEFINED=12
GOLDEN_TRAJECTORIES_DEFINED=40
IMPLEMENTATION_TASKS_DEFINED=14

ONE_ACTIVE_EPISODE_V2=yes
EXPLICIT_CORRECTION_POLICY_FROZEN=yes
DRAFT_WITH_MISSING_FACTS_POLICY_FROZEN=yes
PERSISTENT_DISCLAIMER_FROZEN=yes
MAX_ONE_PROVIDER_CALL_FROZEN=yes

REMOTE_OVERLAP_BLOCKERS=0
OWNER_DECISIONS_REMAINING=4

FILES_MODIFIED_BY_TASK=0
TRACKED_FILES_STAGED=0
COMMIT_CREATED=no
PUSH_PERFORMED=no
PR_MODIFIED=no
MERGE_PERFORMED=no
DEPLOY_PERFORMED=no
```

### 22.3 Owner decisions remaining (4) — none blocking

1. **Approve four new legal source entries (§13.1)?** Working default: ship on the current
   pack with cautious wording.
2. **`landlord_refusal_reason` enum set.** Working default: the six values in §5.3.
3. **Episode reset semantics** when a user clearly starts a new deposit matter in the same
   chat. Working default: treat as a correction/conflict on the existing episode; never
   auto-create a second active episode.
4. **Draft copy-action telemetry** — record `draft_copied` as an episode event? Working
   default: no, to keep the event table state-only.

---

Hard stop.
