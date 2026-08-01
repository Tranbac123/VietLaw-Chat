# VietLaw Fast Demo V2 — Phase C Response Reveal Report V1

Date: 2026-07-29 (Asia/Ho_Chi_Minh)
Revision: V1 rev-10 (Phase C accepted by owner)

## CURRENT VERDICT

`VIETLAW_PHASE_C_ACCEPTED_BY_OWNER`

The owner's browser checkpoint on the correction commit
(`c10144c213ce835422fbdd5c3c0d920d666008ed`) passed: reveal timing/pacing,
universal word reveal across all response kinds, immediate retirement of the
previous response on an accepted new submission, Composer/Send lifecycle,
chat switching, and reload behavior were all confirmed. An independent
re-verification of that same commit
(`VIETLAW_FAST_DEMO_V2_CODEX_PHASE_C_CORRECTION_REVERIFICATION_V1.md`,
untracked, kept unstaged) returned:

```text
INDEPENDENT_VERDICT=VIETLAW_PHASE_C_CORRECTION_INDEPENDENT_VERIFICATION_PASS_WITH_NONBLOCKING_FINDINGS
PHASE_C_CORRECTION_COMMIT=c10144c213ce835422fbdd5c3c0d920d666008ed
HIGH_FINDINGS=0
PHASE_C_IMPLEMENTATION_ACCEPTED=yes
```

with three nonblocking findings (NF-01, NF-02, NF-03), detailed and accepted
in **"PHASE C — OWNER ACCEPTANCE"** at the end of this document. None of the
three blocks the bounded committed MODE_1 flow or any required PASS
invariant; all three are accepted as nonblocking / deferred, not fixed in
this commit.

```text
CURRENT_BROWSER_BACKEND=UI_FIXTURE_ONLY
REAL_AGENT_BACKEND_ACTIVE=no
REAL_AGENT_CONTEXT_QUALITY=not_tested
LIVE_PROVIDER_CALLS_USED=0

FIXTURE_GREETING_COPY=verified
FIXTURE_ASSISTANT_IDENTITY_COPY=verified
FIXTURE_USER_IDENTITY_COPY=verified
FIXTURE_MEMORY_EMPTY_COPY=verified

SAME_CHAT_NAME_RECOGNITION=not_tested
SAME_CHAT_LEGAL_FACT_PERSISTENCE=not_tested
REAL_AGENT_MEMORY_QUALITY=not_tested
MODE_2_STARTED=no
```

Two commits now exist for Phase C's correction work:

```text
c10144c213ce835422fbdd5c3c0d920d666008ed  fix(demo): close phase-c verification findings
<this commit>                              docs(demo): accept phase-c correction
```

The second is documentation-only: it records owner acceptance and corrects
this report's own claims about the correction commit's path count and the
universal-reveal tests' evidence scope. No source, test, legal data,
dependency or `.env` file changed. MODE_2 was **not** started and no live
provider call was spent. Not pushed, merged or deployed.

```text
CURRENT_BROWSER_BACKEND=UI_FIXTURE_ONLY
REAL_AGENT_BACKEND_ACTIVE=no
REAL_AGENT_CONTEXT_QUALITY=not_tested
LIVE_PROVIDER_CALLS_USED=0
```

The browser the owner is about to test against is still the scripted
`UI_FIXTURE_ONLY` fake provider (MODE_1). Nothing in this round demonstrates
real-agent reasoning, context quality, or memory -- only that the fixture's
own deterministic reveal and routing/copy are now consistent and honest about
their own bounds.

---

## HISTORICAL — original commit report (superseded)

Everything from here down to the `PHASE C CORRECTION` heading is the unmodified
rev-5 record of the **original** commit `7c3e0253f2b8bc3af7e5f8591369656e902088f3`
and its owner approval, kept verbatim for audit trail. It is **not** the current
verdict -- Codex's independent review found it blocked after this record was
written. Do not read the verdict line immediately below as current status; see
`CURRENT VERDICT` above instead.

<details>
<summary>Historical rev-5 verdict and report (superseded -- click to expand)</summary>

### Historical verdict (superseded)

`VIETLAW_PHASE_C_RESPONSE_REVEAL_READY_FOR_INDEPENDENT_REVIEW`

The owner confirmed the full Phase C browser checkpoint — word reveal, reveal
speed (3.43 s, accepted), and reload restoration all passed. All required
validation was rerun and passed with the same totals. One commit was created:

```text
7c3e0253f2b8bc3af7e5f8591369656e902088f3  feat(demo): reveal responses word by word
```

`OWNER_PHASE_C_BROWSER_CONFIRMATION=yes`, `OWNER_WORD_SPEED_ACCEPTED=yes`. The
scripted server remains `UI_FIXTURE_ONLY`; MODE_2 (real-agent checkpoint) was
**not** started and no live provider call was spent, per instruction.

---

## 1. Repository identity

| Item | Value |
|---|---|
| Worktree | `/Users/tranvanbac/Documents/AI/ai-agent/VietLaw-Chat-conversational-demo-v2` |
| Branch | `feature/conversational-rental-deposit-demo-v2` |
| Starting HEAD | `6f9671bf2ef57bbe0a99cd409f1ec9c54a5971d0` |
| Final HEAD | `7c3e0253f2b8bc3af7e5f8591369656e902088f3` |
| Commit | `feat(demo): reveal responses word by word` |
| `.env` | ignored, untracked, unstaged |

Accepted Phase B baseline: **867** backend, **63** frontend.

---

## 2. Reveal lifecycle — word-level, one controller

```text
request submitted -> composer clears -> request in flight ('thinking')
-> complete response received and persisted
-> composer + Send usable again           [reveal has not started yet]
-> words are emitted from already-present text
```

Not provider streaming: no SSE, no WebSocket, no streamed provider call, no
incremental persistence. `useWordReveal` only decides when existing text becomes
visible.

**Exactly one controller.** `StructuredAnswer` computes
`typewriterAnimate = animate && !isFastDemo`, so for a Fast Demo structured
answer the old character typewriter never starts. The previous complete-block
staging (`useBlockReveal`) was deleted outright — not disabled, removed. There is
no second word timer.

### Structure rules

| Rule | Implementation |
|---|---|
| Heading appears when its block starts | headings render whole inside the block; only prose is word-fed |
| Text reveals by words | `wordPrefix(text, n)` — every intermediate state is a literal prefix of the source |
| Lists preserve item boundaries | `revealListItems` gives each item its own budget; a partial item is a prefix of *its own* text, never carried across items |
| Paragraphs preserve boundaries | each paragraph is its own spec |
| Next block waits for the current one | specs consume the stream in order; a block renders only once every earlier block has consumed its full word count |
| Missing blocks add no step | a spec is appended only when the block is present |
| `Sao chép` never word-revealed | `DraftCard` title and button render whole; only the draft body is fed |
| Source links intact | the source block is atomic (`ATOMIC_BLOCK_WORD_COST`), so the link is complete and clickable the moment it appears |
| Known-facts control intact | atomic, disclosure stays functional |
| Social / capability / error | immediate, never word-revealed |
| Reduced motion | everything immediate, **zero timers scheduled** |

## 3. Timing policy

Centralised in `frontend/src/lib/reveal.ts`:

```text
WORD_INTERVAL_MS        = 34
MAX_TOTAL_REVEAL_MS     = 6500
SHORT_RESPONSE_WORDS    = 120   -> 1 word/tick
MEDIUM_RESPONSE_WORDS   = 300   -> 2 words/tick
(longer)                        -> 3 words/tick
ATOMIC_BLOCK_WORD_COST  = 2
```

`wordsPerTick` takes the larger of the length band and a budget-derived rate, so
`MAX_TOTAL_REVEAL_MS` is a real ceiling rather than documentation. Measured on
the current fixture answer: **~202 words → 2 words/tick → 3.43 s**, inside the
owner's 3.3–3.8 s target. 28 ms read as slightly too fast in the browser.

A test asserts the fixture pace stays in that range, and another asserts that no
length can exceed `MAX_TOTAL_REVEAL_MS`, so a later timing change cannot drift
either silently.

Never character-by-character.

## 4. Reduced motion

`staged = animate && !reduced && total > 1`. Under reduced motion the initial
state is already complete and **no interval is created**, asserted directly with
`vi.getTimerCount() === 0`.

## 5. Chat-switch cleanup and send independence

One `setInterval`, cleared in the effect cleanup and again on completion, so
unmount, chat switch, new chat and a newer response all cancel it. No wrong-chat
update, no act/unmounted warnings, and a reopened chat renders whole
(`animate` false + one-shot `completedRef`).

`App.tsx` gates on `requestInFlight = phase === 'thinking'` only, for
`controlsDisabled`, `composerInputDisabled`, `composerSubmitDisabled` and the
`submitQuestion` guard. `'revealing'` survives only for `ChatWindow` auto-scroll
and gates nothing.

---

## 5b. Reload restores the selected chat

**The finding was correct and the earlier claim was too narrow.** rev-2 said a
reopened chat renders fully — true within one page session, but a full browser
reload dropped the user into New Chat, because nothing remembered the selection
across a remount.

### Architecture inspected first

The app has **no router** and no URL chat identity, so option 1 (restore from a
route) was unavailable. Option 2 applies: a bounded frontend store, following the
existing `lib/session.ts` convention. No routing framework was introduced.

`frontend/src/lib/selectedChat.ts`:

* one explicit versioned key, `vietlaw.selected_chat_id.v1`;
* stores **only** a chat id — never messages, never legal state;
* shape-validated on read (`^chat_[A-Za-z0-9]{8,64}$`); a malformed value is
  cleared on sight;
* every access is wrapped, so private mode or a blocked/full store degrades to
  "no memory" rather than breaking a send.

### A stored id is not authorization

Restoration accepts an id **only if it appears in the session-scoped chat list
the backend just returned**. That list is built by the backend for this session,
so an id belonging to another owner can never be restored, and `getChat` is
never even called for it. Backend ownership checks remain authoritative.

### Restoration phase removes the race

`restoringSelectedChat` starts `true` and resolves in one effect that runs only
after `loadingChats` is false. Until it resolves the app creates no chat,
dispatches no request and runs no reveal, and the composer is briefly disabled —
a startup phase, never permanent, since every branch of the effect resolves it.

| Situation | Outcome |
|---|---|
| id present and in the list | that chat is opened and its messages render |
| nothing stored | New Chat |
| explicit New Chat then reload | New Chat (the id is cleared on New Chat) |
| malformed id | rejected, cleared, New Chat |
| deleted / not in this session's list | cleared, New Chat |
| **chat list itself failed to load** | id **kept**, New Chat for now — a transient outage must not discard a valid selection |

The id is written when a chat is opened and when a first message creates one, and
updated on every switch.

A restored answer is persisted, not newly received, so `animate` is false and it
renders whole — no word reveal replay.

## 6. MODE_1 — scripted fixture is UI-only

The owner correctly observed that five different messages — including
`đi xe ngược chiều phạt thế nào` — returned essentially the same rental-deposit
answer. That is the fixture behaving as designed, and it makes the fixture
**invalid for conversation-quality acceptance**.

`scratchpad/phase_c_demo_server.py` now says so in its module docstring and
prints a banner on every start:

```text
MODE_1 = UI_FIXTURE_ONLY  --  scripted fake provider, NOT the agent
Every message returns the same rental-deposit plan by design.
Do NOT judge context, reasoning, continuity or routing from this.
```

It proves only: the word reveal renders, and a source link element renders. It
proves nothing about context understanding, legal reasoning, follow-up
continuity, fact updates, topic switching, answer naturalness or routing across
unrelated topics. No extra hard-coded responses were added — a larger fixture
would still not test the agent.

```text
SCRIPTED_SERVER_PURPOSE=ui_fixture_only
SCRIPTED_SERVER_CONTEXT_QUALITY_VALIDATION=no
SCRIPTED_SERVER_LEGAL_ANSWER_VALIDATION=no
REAL_AGENT_CONTEXT_QUALITY=not_tested
```

## 7. MODE_2 — real-agent checkpoint, prepared not executed

**No live provider call has been spent.** The command below is not run.

```bash
# MODE_2 = REAL_AGENT_BROWSER_CHECK -- spends live provider calls.
pkill -f phase_c_demo_server        # stop the UI fixture first

cd /Users/tranvanbac/Documents/AI/ai-agent/VietLaw-Chat-conversational-demo-v2
VIETLAW_FAST_DEMO_V2_ENABLED=true \
VIETLAW_LLM_ENABLED=true \
CHAT_DB_PATH=/tmp/vietlaw_real_agent.sqlite3 \
python3 -m uvicorn backend_lite.app.main:app --host 127.0.0.1 --port 8010
```

`ANTHROPIC_API_KEY` and `VIETLAW_LLM_MODEL` come from the repository `.env`; no
key value appears in this report. The frontend needs no restart — it already
points at `http://127.0.0.1:8010`.

### Golden flow to run in ONE chat, with the measurements to record

| Turn | Message | Expected |
|---|---|---|
| 1 | `tôi đã đặt cọc thuê nhà nhưng chủ nhà không cho vào` | recognises no handover; does **not** re-ask it; asks only material missing facts; situation-specific next steps |
| 2 | `tôi nên làm gì?` | continues the same matter; no full repeat; concise actions |
| 3 | `tôi đã đặt cọc 20 triệu, chủ nhà chưa trả lại tiền cọc` | retains 20 triệu; recognises non-return; does not re-ask the amount; uses it accurately in any draft |
| 4 | `đi xe ngược chiều phạt thế nào?` | **not** the rental template; bounded out-of-scope or clarification; no rental fact mutation |
| 5 | `tôi nên làm gì tiếp?` | bounded clarification (rental matter vs traffic question); must **not** silently replay the rental answer |

Record per turn: `route`, `mode`, `provider_call_delta`, `chat_id`,
`client_request_id`, `used_current_chat_history`, `facts_before`, `facts_after`,
`pending_before`, `pending_after`, `response_summary_hash`,
`repeated_response_detected`.

A substantially identical structured response across all five turns is a
failure. This table must not be produced from MODE_1.

## 8. Source-link scope

The fixture uses `civil_deposit_001` only to prove a link element renders. Its
URL is legacy and known broken:

```text
https://vbpl.moj.gov.vn/tuyenquang/Pages/vbpq-toanvan.aspx?ItemID=95942&Keyword=
```

```text
SOURCE_LINK_ELEMENT_RENDERS=yes
SOURCE_LINK_HEALTH_VERIFIED=no
LEGACY_BROKEN_SOURCE_PRESENT=yes
SOURCE_DATA_MIGRATION_REQUIRED=yes
```

It is **not** a healthy, verified or usable source. No legal data or source URL
was modified in this task; official-source migration remains a separate task
after Phase C closure.

Also unchanged from rev-2: every *displayable* pack member already carries a safe
https URL, so an unsafe-URL source cannot be produced in the browser without
editing legal data. Unsafe filtering is proven by test instead.

---

## 9. Exact files changed — 8 paths

```text
A frontend/src/lib/reveal.ts                     word controller + timing constants
M frontend/src/components/StructuredAnswer.tsx   typewriter off for fast demo; word-fed block specs
M frontend/src/styles/globals.css                .answer-block appearance + reduced-motion
M frontend/src/App.tsx                           gate on 'thinking' only; selected-chat restore phase
A frontend/src/test/responseReveal.test.tsx      24 tests
A frontend/src/lib/selectedChat.ts                bounded selected-chat persistence
A frontend/src/test/selectedChatRestore.test.tsx  19 tests
M frontend/src/test/composerLifecycle.test.tsx   stale comment corrected (no assertion changed)
```

`BACKEND_SOURCE_FILES_MODIFIED=0`, `PACKAGE_FILES_MODIFIED=0`,
`LEGAL_DATA_MODIFIED=0`. Verified against `git status`. The scripted server lives
in the scratchpad and is not part of the repository.

## 10. Tests

Node **v20.19.4**.

| Check | Result |
|---|---|
| Phase C word-reveal tests | **24 passed** |
| Selected-chat reload tests | **19 passed** |
| Composer lifecycle tests | **15 passed** |
| Complete frontend suite | **106 passed** (63 → 106, +43) |
| Frontend typecheck | passed |
| Frontend production build | passed — 167.12 kB JS, 13.92 kB CSS |
| Complete Backend Lite suite | **867 passed** (unchanged) |
| `compileall backend_lite/app` | passed |

Mapping to the required list: (1) summary reveals progressively — asserted to
grow across >2 distinct steps; (2) full summary absent on first paint;
(3) every intermediate state is a literal prefix, so word order cannot change;
(4) diacritics and punctuation intact at every step; (5) block two does not
exist until the summary is whole; (6) list items are prefixes of their own text
with a partial-list state observed; (7) removing `analysis` removes exactly one
block; (8) source link whole and clickable at its step; (9) `Sao chép` label
complete whenever present; (10) reduced motion immediate with zero timers;
(11)–(13) composer usable, Send enabled, second submission accepted mid-reveal;
(14) unmount cancels with no warnings; (15) reopened chat renders whole;
(16) social/capability/error immediate; (17) every fake-timer test asserts
`vi.getTimerCount() === 0` after `cleanup()`.

`AUTOMATED_PROVIDER_CALLS=0`, `LIVE_PROVIDER_CALLS_USED=0`.

---

## 11. Owner browser checkpoint — MODE_1 — PASSED

Result: `OWNER_PHASE_C_BROWSER_PASS`. Owner confirmed all items below, including
word order/punctuation/diacritics, block sequencing, list-item boundaries,
intact copy/known-facts/source controls, reduced motion, composer/Send
usability during and after reveal, second submission during reveal, no
permanent disabled state, and full reload restoration behavior. Reveal speed
(3.43 s measured) was explicitly accepted.

* **Frontend URL: http://127.0.0.1:5173**
* Backend: `127.0.0.1:8010`, health 200, CORS preflight 200, Node v20.19.4
* Neither process was restarted this round: the fixture is unchanged and Vite
  **HMR** picked up all frontend changes
* Live provider calls spent: **0**

### Reload restoration

1. Open an existing chat that has messages; note its title.
2. Reload with **Command + R**.
3. The same chat is still selected, with the same messages.
4. Old assistant answers appear **whole** — no word reveal replay.
5. The sidebar gained no new empty chat.

Then click **New Chat**, reload, and confirm it stays on New Chat.

### Message for testing word reveal

```text
tôi đã đặt cọc 20 triệu, chủ nhà chưa trả lại tiền cọc
```

Fixture answer ≈ 202 words → 2 words/tick → **≈ 3.43 s** (target 3.3–3.8 s).
Please report the duration you observe.

### Checklist

**A. Word reveal** — send the message above

* the summary appears **word by word**, not all at once and not letter by letter;
* the analysis block starts only after the summary sentence is complete;
* list items fill in one at a time and never mix words between items;
* `Sao chép` appears as a complete button, never partially typed;
* the `Nguồn tham khảo` link appears whole and is clickable at its step;
* the whole sequence takes about three seconds.

**B. No source block** — send `tôi đặt cọc thuê nhà, trường hợp không nguồn thì sao`
→ the answer renders with no source block and no empty heading.

**C. Send lifecycle** — while words are still arriving: type and send a second
message; it must go through. Composer clears immediately on Enter and on Send;
Send is never stuck disabled.

**D. Reduced motion** — enable macOS Reduce Motion, reload → the whole answer
appears instantly; a second send still works.

**E. Chat navigation** — switch chats mid-reveal (no leakage); reopen a chat (renders
whole, no replay).

**F. Error path** — stop the backend and send → controlled error immediately,
composer usable, `Thử lại` offered, no console error.

**Do not judge answer quality, context or routing here — that is MODE_2.**

---

## 12. Limitations

1. **Selected-chat memory is per browser profile**, like the existing session id.
   Clearing site data returns the user to New Chat, and a different browser or a
   private window starts fresh. It is a UI convenience, not a synced setting.
2. **MODE_1 cannot validate the agent.** Conversation quality, continuity,
   fact updates, topic switching and routing are `not_tested`.
3. **The fixture source URL is broken** (§8); migration is a separate task.
4. **Non-fast-demo structured answers keep the old typewriter.** Only
   `metadata.fast_demo === true` uses the word controller.
5. **`'revealing'` remains in the phase union** for auto-scroll; gates nothing.
6. **Atomic blocks are not word-revealed** — source panel and known-facts appear
   whole, by design, since they are links and controls.
7. **No layout reservation**; the answer grows downward as it reveals.
8. **Uncertainty notice** follows existing DOM order (after known facts).
9. **jsdom only** for automation; CSS transitions themselves are not asserted.

## 13. Commit

```text
commit  7c3e0253f2b8bc3af7e5f8591369656e902088f3
parent  6f9671bf2ef57bbe0a99cd409f1ec9c54a5971d0
subject feat(demo): reveal responses word by word
paths   8 (2 new lib modules, 2 new test files, 4 modified: App.tsx,
          StructuredAnswer.tsx, globals.css, composerLifecycle.test.tsx)
```

All four prior Phase B commits (`222dddf`, `fea76df`, `dbf63aa`, `6f9671b`)
verified as ancestors of HEAD: preserved, not amended or rewritten. Nothing
pushed, merged or deployed. Pre-commit checks: `git diff --cached --check`
clean; no backend source, package file, legal data, citation, retrieval file,
`.env`, scratchpad file or report staged; bounded secret scan (8 patterns) —
0 hits.

---

## 14. Machine-readable verdict

```text
VIETLAW_PHASE_C_RESPONSE_REVEAL_READY_FOR_INDEPENDENT_REVIEW

STARTING_HEAD=6f9671bf2ef57bbe0a99cd409f1ec9c54a5971d0
FINAL_HEAD=7c3e0253f2b8bc3af7e5f8591369656e902088f3
PHASE_C_COMMIT=7c3e0253f2b8bc3af7e5f8591369656e902088f3

REVEAL_UNIT=word
REAL_PROVIDER_STREAMING=no
SIMULATED_WORD_REVEAL=yes
SINGLE_REVEAL_CONTROLLER=yes
OLD_TYPEWRITER_ACTIVE_FOR_FAST_DEMO=no
COMPLETE_BLOCK_STAGING_ACTIVE=no

WORD_INTERVAL_MS=34
MAX_TOTAL_REVEAL_MS=6500
ADAPTIVE_WORDS_PER_TICK=1..3
MEASURED_FIXTURE_REVEAL_SECONDS=3.43

BLOCK_ORDER_SEQUENTIAL=yes
LIST_ITEM_BOUNDARIES_PRESERVED=yes
MISSING_BLOCK_SKIP_PASS=yes
COPY_CONTROL_INTACT=yes
SOURCE_LINK_INTACT_AT_STEP=yes
SOCIAL_IMMEDIATE_PASS=yes
CAPABILITY_IMMEDIATE_PASS=yes
ERROR_IMMEDIATE_PASS=yes
REDUCED_MOTION_IMMEDIATE_PASS=yes

REVEAL_CONTROLS_SEND_LIFECYCLE=no
COMPOSER_USABLE_DURING_REVEAL=yes
SECOND_SEND_DURING_REVEAL=yes
PERMANENT_DISABLED_STATE=no
CHAT_SWITCH_TIMER_CLEANUP=yes
WRONG_CHAT_REVEAL_UPDATES=0
OLD_CHAT_REANIMATION=no
TIMERS_REMAINING_AFTER_CLEANUP=0

SELECTED_CHAT_PERSISTED=yes
RELOAD_RESTORES_SELECTED_CHAT=yes
RELOAD_RESTORES_MESSAGES=yes
RELOAD_REPLAYS_WORD_REVEAL=no
RELOAD_CREATES_EMPTY_CHAT=no
EXPLICIT_NEW_CHAT_RELOAD_PASS=yes
STALE_CHAT_ID_FALLBACK_PASS=yes
CROSS_OWNER_CHAT_RESTORE_BLOCKED=yes
MALFORMED_CHAT_ID_REJECTED=yes
RESTORATION_WAITS_FOR_CHAT_LIST=yes
SELECTED_CHAT_STORAGE_KEY=vietlaw.selected_chat_id.v1
SELECTED_CHAT_STORES_MESSAGES=no
OWNER_WORD_SPEED_ACCEPTED=yes

MODE_1=UI_FIXTURE_ONLY
MODE_2=REAL_AGENT_BROWSER_CHECK
MODE_USED_FOR_THESE_RESULTS=MODE_1
SCRIPTED_SERVER_PURPOSE=ui_fixture_only
SCRIPTED_SERVER_CONTEXT_QUALITY_VALIDATION=no
SCRIPTED_SERVER_LEGAL_ANSWER_VALIDATION=no
REAL_AGENT_CONTEXT_QUALITY=not_tested
REAL_AGENT_CHECKPOINT_PREPARED=yes
REAL_AGENT_CHECKPOINT_EXECUTED=no

SOURCE_LINK_ELEMENT_RENDERS=yes
SOURCE_LINK_HEALTH_VERIFIED=no
LEGACY_BROKEN_SOURCE_PRESENT=yes
SOURCE_DATA_MIGRATION_REQUIRED=yes

BACKEND_SOURCE_FILES_MODIFIED=0
PACKAGE_FILES_MODIFIED=0
LEGAL_DATA_MODIFIED=0
CHANGED_PATHS=8

PHASE_C_TESTS=24 passed
SELECTED_CHAT_RELOAD_TESTS=19 passed
FRONTEND_TESTS=106 passed
FRONTEND_TYPECHECK=passed
FRONTEND_BUILD=passed
BACKEND_LITE_TESTS=867 passed
COMPILEALL=passed

AUTOMATED_PROVIDER_CALLS=0
LIVE_PROVIDER_CALLS_USED=0

OWNER_PHASE_C_BROWSER_CONFIRMATION=yes
BACKEND_PROCESS_RESTARTED=no
FRONTEND_PROCESS_RESTARTED=no
HMR_USED_FOR_FRONTEND_CHANGES=yes

FINAL_PHASE_C_TESTS=24 passed
FINAL_SELECTED_CHAT_RELOAD_TESTS=19 passed
FINAL_COMPOSER_LIFECYCLE_TESTS=15 passed
FINAL_FRONTEND_TESTS=106 passed
FINAL_FRONTEND_TYPECHECK=passed
FINAL_FRONTEND_BUILD=passed
FINAL_BACKEND_LITE_TESTS=867 passed
FINAL_COMPILEALL=passed

TRACKED_WORKTREE_CLEAN=yes
COMMITS_CREATED=1
FINAL_COMMIT_SHA=7c3e0253f2b8bc3af7e5f8591369656e902088f3
REPORT_CREATED=yes
REPORT_STAGED=no

MODE_2_STARTED=no
LIVE_PROVIDER_CALLS_SPENT_THIS_TASK=0
PHASE_D_STARTED=no
OFFICIAL_SOURCE_MIGRATION_STARTED=no

PUSH_PERFORMED=no
MERGE_PERFORMED=no
DEPLOY_PERFORMED=no
```

*(End of historical rev-5 record. The block above was accurate for the state
it described, but Codex's independent review subsequently blocked this commit
-- see `CURRENT VERDICT` at the top of this document and the authoritative
machine-readable block at the end of the correction section below.)*

</details>

---
---

# PHASE C CORRECTION — INDEPENDENT REVIEW FINDINGS CLOSURE

Everything from the `HISTORICAL` heading above down to this line is the
unmodified rev-5 record of the original
`7c3e0253f2b8bc3af7e5f8591369656e902088f3` commit and its approval. This
section is a clearly separated addendum for the correction on top of it.

This section's status is the one stated in `CURRENT VERDICT` at the very top of
this document: `VIETLAW_PHASE_C_CORRECTION_AWAITING_OWNER_BROWSER`. It is
repeated here only for readers who jump straight to this section.

## Codex blocker summary

Independent verification of `7c3e0253f2b8bc3af7e5f8591369656e902088f3` returned
`VIETLAW_PHASE_C_INDEPENDENT_VERIFICATION_BLOCKED` with four findings, all now
addressed in an uncommitted working tree on top of that commit:

| ID | Finding |
|---|---|
| H-01 | The committed `composerLifecycle.test.tsx` regression test wrapped its key assertions in `if (sendButton().disabled) { ... }`. Under actual Phase C behavior Send stays enabled through a reveal, so the branch never executed and the test proved nothing about either lifecycle contract it claimed to guard. |
| M-01 | `MAX_TOTAL_REVEAL_MS=6500` was documentation, not an enforced ceiling: the committed `wordsPerTick` derived its budget-driven rate from `totalWords` directly, ignoring that one word is already visible before the first tick and that a partial tick still costs a full `WORD_INTERVAL_MS`. At 2294 words the real reveal took 6528 ms — 28 ms over budget. |
| M-02 | `selectedChat.ts` validated chat ids against `/^chat_[A-Za-z0-9]{8,64}$/`, materially broader than the backend's actual generator, `f"chat_{uuid4().hex}"` (`chat_` + exactly 32 lowercase hex characters). |
| L-01 | The previous reveal was not retired when a new submission was *accepted* -- only when the new response *arrived*. `animatingAssistantMessageId` was set to the new message's id inside the success branch, after `await analyze(...)` resolved, so response A kept its own reveal timer running silently for the whole "thinking" phase of B. |

## H-01 correction — exact assertion changes

`frontend/src/test/composerLifecycle.test.tsx`:

* **Removed** the single test containing the `if (sendButton().disabled)` branch
  (`'preserves a draft typed while the answer is still revealing'`) and its
  conditional block entirely -- not narrowed, deleted.
* **Added** `'blocks Composer input and prevents a second dispatch while
  request A is thinking'`. Note what this test does and does not prove: the
  composer is empty at this point (cleared on A's own accepted dispatch), so
  there is no draft value to preserve, and the original name/framing implying
  "draft preservation" was inaccurate -- corrected here and in the test file
  itself. What it does prove, unconditionally: while a request is actually
  pending (`thinking`, composer disabled), the textarea stays disabled; an
  attempted `user.type()` leaves the value empty rather than throwing (proven
  empirically first: user-event v14 silently drops keystrokes on a disabled
  element instead of throwing); an attempted Enter does not reach a second
  dispatch; `analyze` stays at exactly 1 call throughout.
* **Added** a new top-level `describe('a second submission accepted while the
  previous answer is revealing', ...)` with an `it.each` over both submission
  paths (Send button, Enter). Both cases unconditionally assert: the composer
  and Send become enabled once the reveal begins; a second question can be
  typed and dispatched; `analyze` is called exactly twice, with the second
  call's `question` matching exactly; the second user message appears exactly
  once; the composer clears again after acceptance; the second answer
  eventually renders; no duplicate exists.

`COMPOSER_CONDITIONAL_ASSERTIONS=0` -- verified by `grep` for
`if (sendButton` / `if (.*\.disabled)` gating an `expect(...)` anywhere in the
file: no matches remain.

## M-01 correction — exact timing formula and duration calculation

`frontend/src/lib/reveal.ts`:

```text
MAX_TIMER_TICKS = floor(MAX_TOTAL_REVEAL_MS / WORD_INTERVAL_MS)          // 191

lengthBandWordsPerTick(totalWords):
  <= 120 words  -> 1
  <= 300 words  -> 2
  otherwise     -> 3

effectiveWordsPerTick(totalWords):
  remaining = max(totalWords - 1, 0)                 // 1 word already visible
  budgetRequiredStep =
    remaining == 0 ? 1 : ceil(remaining / MAX_TIMER_TICKS)
  return max(lengthBandWordsPerTick(totalWords), budgetRequiredStep)

actualRevealDurationMs(totalWords):
  remaining = max(totalWords - 1, 0)
  if remaining == 0: return 0
  step  = effectiveWordsPerTick(totalWords)
  ticks = ceil(remaining / step)                     // integer ticks, not `total/step`
  return ticks * WORD_INTERVAL_MS
```

This is exactly the formulation the task specified, matched to the hook's real
behaviour: `useWordReveal` starts at `revealedWords = 1` and advances by
`effectiveWordsPerTick(total)` words on every subsequent `setInterval` firing
until it reaches `total` -- so the true cost is `ceil(remainingWords / step)`
ticks, never a continuous `total / step`.

`wordsPerTick` (the old, incorrectly-named export) was removed rather than
aliased; every call site now uses `effectiveWordsPerTick` directly.

### Rate naming corrected

```text
LENGTH_BAND_WORDS_PER_TICK=1..3     (lengthBandWordsPerTick -- demo pacing only)
EFFECTIVE_WORDS_PER_TICK=1..N       (effectiveWordsPerTick -- the real per-tick rate)
```

`effectiveWordsPerTick(5000) = 27`, well above 3 -- there is no hidden cap;
only the duration ceiling itself bounds the rate. The stale
`ADAPTIVE_WORDS_PER_TICK=1..3` claim from rev-5 is retired.

### Proof

* `it.each([0, 1, 120, 121, 300, 301, 573, 574, 2293, 2294, 2295, 5000])` --
  every one of the exact required boundary values individually asserted
  `<= MAX_TOTAL_REVEAL_MS`.
* A dedicated test computes the OLD formula's actual integer-tick duration at
  2294 words (simulating the real `revealed = min(revealed + step, total)`
  loop, not the misleadingly-passing continuous approximation) and asserts it
  **exceeds** 6500 ms -- this is the failing case against the previously
  committed implementation, reproduced and documented rather than asserted
  away.
* An exhaustive loop over **0..10000** asserts `actualRevealDurationMs(n) <=
  MAX_TOTAL_REVEAL_MS` and `effectiveWordsPerTick(n) >= 1` for every single
  integer -- zero failures, worst-case duration 6494 ms (99.9% of budget,
  proving the ceiling is a real constraint reached by some input, not slack
  documentation).
* `effectiveWordsPerTick(5000) > 3` proves the rate is not silently capped.

### Fixture pace: unchanged

Recomputing the ~202-word fixture under the corrected formula: `remaining =
201`, `budgetRequiredStep = ceil(201/191) = 2`, `lengthBandWordsPerTick(202) =
2`, so `effectiveWordsPerTick = 2` -- identical to the previous (differently
derived) result. `actualRevealDurationMs(202) = ceil(201/2) * 34 = 101 * 34 =
3434 ms = 3.434 s`, inside the owner-accepted 3.3-3.8 s range and
indistinguishable from the previously observed 3.43 s. **No unexpected change
occurred**, so no separate explanation beyond this note was required before
the browser check -- the browser check itself is still performed per
instruction because the retirement behavior (L-01) is a genuine visible change.

## M-02 correction — exact chat-id regex

`frontend/src/lib/selectedChat.ts`:

```text
OLD: /^chat_[A-Za-z0-9]{8,64}$/
NEW: /^chat_[0-9a-f]{32}$/
```

Matched exactly to `f"chat_{uuid4().hex}"` in
`backend_lite/app/stores/sqlite_chat_store.py`. Tests added:

* accepts `chat_0123456789abcdef0123456789abcdef` (the exact backend shape);
* rejects, individually: `chat_ZZZZZZZZ`, `chat_ABCDEF0123456789ABCDEF0123456789`
  (uppercase hex), `chat_01234567`, `chat_0123456789abcdef0123456789abcde` (31
  chars), `chat_0123456789abcdef0123456789abcdef0` (33 chars),
  `wrong_0123456789abcdef0123456789abcdef` (wrong prefix),
  `chat_gggggggggggggggggggggggggggggggg` (non-hex), plus the pre-existing
  empty/no-prefix/oversized cases;
* an App-level end-to-end test stores an uppercase-hex id that the *old*
  validator would have accepted, then asserts `getChat` is never called with
  it, the stored value is cleared, and the app falls back to New Chat --
  proving the tightened contract closes the actual attack surface, not just
  the unit-level regex.

The backend-provided chat-list membership gate (§5b of the original report) is
unchanged: a stored id is still never treated as authorization on its own.

## L-01 correction — immediate retirement on accepted submission

`frontend/src/App.tsx`, inside `submitQuestion`, immediately after the
generation counter is bumped and before `onAccepted?.()`/the network call:

```ts
animatingAssistantMessageIdRef.current = null;
setAnimatingAssistantMessageId(null);
```

Because `animate` on each rendered message is
`message.message_id === animatingAssistantMessageId`, clearing this the
instant a submission is accepted makes response A's `animate` prop go `false`
on the very next render -- before the network call for B is even dispatched.
`useWordReveal` reacts by synchronously marking itself complete
(`completedRef.current = true; setRevealedWords(total)`) and its effect
cleanup clears the running `setInterval`. Response B does not receive
`animate=true` until *its own* response arrives and
`animatingAssistantMessageId` is set to B's id, so only B ever stages.

The misleading comment claiming "bumping the generation... retires the old
reveal" was corrected: the generation counter governs which in-flight request
is allowed to apply its result and has no effect on a previous message's own
reveal timer, which is owned entirely by `StructuredAnswer`/`useWordReveal`
and keyed off `animatingAssistantMessageId`.

### Required delayed-response test

`frontend/src/test/responseReveal.test.tsx`, new
`describe('the previous reveal is retired the instant a new submission is
accepted', ...)`, using a deferred second `analyze` promise:

* asserts A's own "Hiện ngay" skip control (present only while that response's
  `isRevealing` is true) is visible immediately after A's first word appears --
  proving the test genuinely catches A mid-reveal;
* submits B, **before resolving it**, and asserts: A's skip control is now
  gone and its last block's exact full text (the uncertainty notice sentence)
  is present -- proving full reveal, not merely "some more text arrived"; B is
  in flight (`analyze` called twice); no second assistant bubble exists yet;
  the composer is disabled with an empty value, matching the ordinary accepted
  in-flight state;
* resolves B and asserts: only B's bubble is added; A's text and missing skip
  control are unchanged (no reanimation); no duplicate blocks anywhere.
* a second test proves the negative: a **refused** submission (whitespace-only,
  never dispatched) leaves A's skip control untouched, confirming retirement
  is tied to acceptance, not merely to any keypress.

## Files changed (correction only)

```text
frontend/src/App.tsx                       L-01: retire old reveal on acceptance
frontend/src/lib/reveal.ts                 M-01: corrected timing formula
frontend/src/lib/selectedChat.ts           M-02: exact backend chat-id regex
frontend/src/test/composerLifecycle.test.tsx    H-01: unconditional assertions
frontend/src/test/responseReveal.test.tsx       M-01 + L-01 tests
frontend/src/test/selectedChatRestore.test.tsx  M-02 tests
```

No backend source, API contract, database schema, provider client, legal data,
citation, retrieval file, package dependency, `.env` or unrelated UI was
touched. `7c3e0253f2b8bc3af7e5f8591369656e902088f3` was not amended, rewritten
or removed.

## Validation (pre-browser-checkpoint)

Node **v20.19.4**.

| Check | Result |
|---|---|
| Composer lifecycle (focused) | **17 passed** (was 15) |
| Word-reveal / timing (focused) | **43 passed** (was 24) |
| Selected-chat (focused) | **28 passed** (was 19) |
| Complete frontend suite | **136 passed** (was 106) |
| Frontend typecheck | passed |
| Frontend production build | passed -- 167.19 kB JS, 13.92 kB CSS |
| Complete Backend Lite suite | **867 passed** (unchanged) |
| `compileall backend_lite/app` | passed |

`AUTOMATED_PROVIDER_CALLS=0`, `LIVE_PROVIDER_CALLS_USED=0`, `MODE_2_STARTED=no`.
Both the scripted `UI_FIXTURE_ONLY` backend and the Vite dev server from the
prior session were already running; neither was restarted for this
correction -- confirmed the served `reveal.ts` and `selectedChat.ts` reflect
the corrected source via HMR before requesting the checkpoint below.

## Owner browser checkpoint

* **Frontend URL: http://127.0.0.1:5173**
* Backend: `127.0.0.1:8010` (scripted `UI_FIXTURE_ONLY` provider, unchanged)
* Neither process restarted; HMR confirmed serving corrected source
* Live provider calls spent: **0**

### To verify

**Timing** -- send `tôi đã đặt cọc 20 triệu, chủ nhà chưa trả lại tiền cọc`
(the ~202-word fixture): still roughly 3.3-3.8 s, no perceptible speed jump.

**Immediate reveal retirement**:

1. Submit a message to get response A.
2. While A is still visibly revealing, submit message B.
3. The instant B is accepted, A should immediately show its complete text --
   its own progress should stop rather than continuing underneath B's
   "Đang suy nghĩ...".
4. When B's answer arrives, only B reveals; A does not restart.

**Reload regression** (unchanged by this correction, worth a quick recheck):
existing-chat reload still restores; New Chat reload still stays on New Chat.

Awaiting `OWNER_PHASE_C_CORRECTION_BROWSER_PASS` before any commit.

---

## Authoritative machine-readable block (current state of this report)

This is the **only** authoritative machine-readable block in this document.
The block inside the collapsed `HISTORICAL` section above describes a prior,
now-superseded state and must not be read as current.

```text
VIETLAW_PHASE_C_CORRECTION_AWAITING_OWNER_BROWSER

PHASE_C_ORIGINAL_COMMIT=7c3e0253f2b8bc3af7e5f8591369656e902088f3
PHASE_C_CORRECTION_COMMIT=absent

COMPOSER_CONDITIONAL_ASSERTIONS=0
SECOND_SUBMISSION_ASSERTED_UNCONDITIONALLY=yes
THINKING_COMPOSER_INPUT_BLOCKED=yes
THINKING_SECOND_DISPATCH_BLOCKED=yes
THINKING_ANALYZE_CALL_COUNT=1

WORD_INTERVAL_MS=34
MAX_TOTAL_REVEAL_MS=6500
MAX_TIMER_TICKS=191
LENGTH_BAND_WORDS_PER_TICK=1..3
EFFECTIVE_WORDS_PER_TICK=1..N
MAX_REVEAL_CEILING_PASS=yes
FIRST_PREVIOUSLY_FAILING_UNIT_COUNT=2294
DURATION_AT_2294_MS_OLD_FORMULA=6528
DURATION_AT_2294_MS_CORRECTED=6018
EXHAUSTIVE_TIMING_RANGE=0..10000
EXHAUSTIVE_TIMING_FAILURES=0
FIXTURE_REVEAL_SECONDS=3.434

SELECTED_CHAT_REGEX=^chat_[0-9a-f]{32}$
NON_HEX_CHAT_ID_REJECTED=yes
UPPERCASE_CHAT_ID_REJECTED=yes
WRONG_LENGTH_CHAT_ID_REJECTED=yes
UNAUTHORIZED_GET_CHAT_CALLS=0

OLD_REVEAL_RETIRED_ON_ACCEPTED_SUBMISSION=yes
OLD_REVEAL_FULLY_VISIBLE_AFTER_RETIREMENT=yes
OLD_REVEAL_SKIP_CONTROL_PRESENT_AFTER_RETIREMENT=no
DELAYED_SECOND_RESPONSE_TEST_PASS=yes
REJECTED_SUBMISSION_DOES_NOT_RETIRE_PREVIOUS_REVEAL=yes

OWNER_PHASE_C_CORRECTION_BROWSER_CONFIRMATION=no

FRONTEND_TESTS=136 passed
FRONTEND_TYPECHECK=passed
FRONTEND_BUILD=passed
BACKEND_LITE_TESTS=867 passed
COMPILEALL=passed

AUTOMATED_PROVIDER_CALLS=0
LIVE_PROVIDER_CALLS_USED=0
MODE_2_STARTED=no

TRACKED_WORKTREE_CLEAN=no
COMMITS_CREATED=0
REPORT_STAGED=no

PUSH_PERFORMED=no
MERGE_PERFORMED=no
DEPLOY_PERFORMED=no
```

*(This block described round 1. It is superseded by the round-2 block at the
very end of this document -- see below.)*

---
---

# PHASE C CORRECTION ROUND 2 — UNIVERSAL CONVERSATIONAL REVEAL AND FIXTURE ROUTING CLARITY

Builds on round 1 above, in the same uncommitted working tree, on top of the
same unchanged commit `7c3e0253f2b8bc3af7e5f8591369656e902088f3`. This round
does not touch anything already closed in round 1 (H-01/M-01/M-02/L-01
remain as described there).

## 1. Test-mode clarity

Restated at the top of this document and repeated here for anyone who jumps
straight to this section: the backend under test is `MODE_1 = UI_FIXTURE_ONLY`.
`REAL_AGENT_BACKEND_ACTIVE=no`, `REAL_AGENT_CONTEXT_QUALITY=not_tested`,
`LIVE_PROVIDER_CALLS_USED=0`. Nothing below should be read as evidence about
real-agent reasoning, quality, or memory.

## 2. Universal word reveal — root cause and fix

The owner observed that the rental-deposit structured answer revealed word by
word, but `hello`, `bạn là ai`, `tôi là ai` and `bạn nhớ gì về tôi` appeared
immediately. The root cause was **not** a second timer racing the first one
(that was round 1's L-01 shape) -- it was that these response kinds fell
**outside** the only controller entirely.

`StructuredAnswer` computed `typewriterAnimate = animate && !isFastDemo`.
Every Fast Demo response, including `social`/`capability`/`scope` kinds, has
`metadata.fast_demo === true`, so `isFastDemo` is always `true` for this
fixture and `typewriterAnimate` was always `false` for these kinds -- meaning
they never animated under *either* controller, old or new. `tôi là ai` and
`bạn nhớ gì về tôi` had no dedicated route at all before this round and fell
through to the generic out-of-scope template, which shared the same
never-animates problem.

**Fix:** a new `SocialAnswer` component renders `social`/`capability`/`scope`
kinds through the exact same `useWordReveal` hook that already drives the
legal structured answer -- one controller, reused, not duplicated. No second
typewriter, no second timer was introduced.

```text
SINGLE_REVEAL_CONTROLLER_STILL_TRUE=yes
SECOND_TIMER_INTRODUCED=no
CONVERSATIONAL_KINDS_NOW_ROUTED_THROUGH_USE_WORD_REVEAL=social,capability,scope
```

Kept immediate, unchanged: loading/thinking indicators, transport/controlled
error messages, system-only status UI, and buttons/interactive controls
(`Sao chép`, `Hiện ngay`, source links).

### Proof

`frontend/src/test/responseReveal.test.tsx`, new
`describe('conversational assistant text reveals progressively by words', ...)`,
`it.each` over `hello`, `bạn là ai`, `tôi là ai`, `bạn nhớ gì về tôi`:

* first paint is incomplete (not the full source text);
* every intermediate state is a literal prefix of the final text, words in
  order, never a character-level reveal;
* the final revealed text equals the source text exactly;
* reduced motion: the full text appears immediately;
* switching chats mid-reveal stops that response's growth, matching the
  existing chat-switch-cleanup contract;
* Composer and Send remain usable per the existing (round-1-corrected)
  lifecycle contract throughout.

**Corrected (owner-acceptance round):** these `it.each` cases run with real
timers and assert no `vi.getTimerCount()` value at any point -- the claim
made in an earlier revision of this section, that these specific tests prove
"exactly one interval" or "zero timers after switch" via `getTimerCount()`,
was inaccurate and is retracted. They also build their fixture responses
with `metadata: {}` and the `social` kind for all four cases rather than
`metadata.fast_demo=true` and a mix of `social`/`capability`/`scope`, so they
do not by themselves rule out the legacy character-typewriter effect running
concurrently with `SocialAnswer`'s word interval on a *real* Fast Demo
payload. The single-reveal-controller claim for production still holds, but
its support is direct source inspection (`typewriterAnimate = animate &&
!isFastDemo`, and `metadata.fast_demo` is unconditionally `true` for every
real Fast Demo response, so the character path never schedules any work)
together with the full regression suite passing, not these four test cases
in isolation. See `NF-02` in **"PHASE C — OWNER ACCEPTANCE"** below.

The prior `describe('responses that are never word-revealed', ...)` block's
social/capability "immediate" assertions were removed as no longer true by
design; only the controlled-error-message immediate assertion remains there,
since errors are explicitly excluded from word reveal.

## 3. Reveal pacing — slower, still a real ceiling

The owner considered the 202-word fixture at 3.434 s "visibly too fast and
similar to displaying a pre-generated answer." `frontend/src/lib/reveal.ts`:

```text
WORD_INTERVAL_MS            = 50      (was 34)
MAX_TOTAL_REVEAL_MS         = 8000    (was 6500)
SHORT_RESPONSE_MIN_REVEAL_MS = 600    (new)
MAX_TIMER_TICKS  = floor(MAX_TOTAL_REVEAL_MS / WORD_INTERVAL_MS)   = 160
MIN_TIMER_TICKS  = ceil(SHORT_RESPONSE_MIN_REVEAL_MS / WORD_INTERVAL_MS) = 12
```

The round-1 integer-tick ceiling formula (`ticks = ceil(remaining / step) *
WORD_INTERVAL_MS`, not an approximate `total / step` continuous calculation)
is unchanged in shape -- only the constants feeding it changed, per
instruction to preserve the exact formula rather than reintroduce fractional
timing.

**New requirement this round:** a short response must not finish in an
imperceptible 100-200 ms. Rather than padding with silent extra ticks after
the text is already fully visible (which would let `isRevealing` -- and the
skip control -- go false immediately, still looking instant), the hook now
spreads the reveal evenly across the **entire** required tick count,
including any floor-padding ticks:

```text
requiredTicks = max(ticksNeededForContentAtEffectiveRate, MIN_TIMER_TICKS)
wordsAfterTick(total, ticksElapsed, requiredTicks)
  = 1 + ceil((ticksElapsed * (total - 1)) / requiredTicks)
```

This guarantees a short response genuinely animates across its full visible
duration -- `isRevealing` stays true and the text keeps growing throughout --
rather than completing and then silently waiting out the floor.

```text
LENGTH_BAND_WORDS_PER_TICK=1..3
EFFECTIVE_WORDS_PER_TICK=1..N
MAX_REVEAL_CEILING_PASS=yes
```

The effective per-tick rate may exceed the length-band rate whenever needed
to respect the hard 8000 ms maximum -- unchanged principle from round 1,
just against the new constants.

### Proof (verified numerically with the real integer-tick loop, not a
continuous approximation, and cross-checked by direct Node execution)

| Case | Words | Result |
|---|---|---|
| Short conversational answer | 5-15 | nominal interval duration 600-700 ms; see the correction below for what "nominal" means at the very short end |
| Fixture answer | ~202 | exactly **5050 ms** (within the 5.0-5.8 s target) |
| Previously-failing boundary | 2294 | still `<= 8000 ms` under the corrected formula |
| Exhaustive | 0..10000 | **0** ceiling violations; worst case exactly 8000 ms (a real binding constraint, not slack) |
| Timer semantics | -- | asserted against actual `setInterval` tick counts via `vi.advanceTimersByTime`, never a duration estimate |

**Corrected (owner-acceptance round):** `wordsAfterTick` uses `ceil`, so for
*extremely* short synthetic inputs all text can become visible before
`requiredTickCount` actually expires -- an independent recalculation found a
2-unit input completes visually at 50 ms, a 5-unit input at 500 ms, and
8/10-unit inputs at 550 ms, all before the interval's nominal 600 ms
duration. The earlier claim that 5/8/10-word text "keeps visibly growing for
exactly the full 600 ms" overstated this edge and is corrected here. It is
nonblocking for the committed MODE_1 scope: every actual bounded
conversational fixture response (greeting 36 units/1750 ms, assistant
identity/capability 82 units/4050 ms, user identity 24 units/1150 ms,
empty-memory 14 units/650 ms, scope 54 units/2650 ms) is well above this
extremely-short-synthetic-input edge and visibly completes in 650-4050 ms --
"at least about 600 ms" holds for every response this fixture actually sends.
See `NF-03` in **"PHASE C — OWNER ACCEPTANCE"** below.

```text
FIXTURE_TARGET_SECONDS_MET=yes
FIXTURE_REVEAL_SECONDS_ROUND2=5.05
SHORT_RESPONSE_MIN_REVEAL_MS_MET=yes
MAX_TOTAL_REVEAL_MS_ROUND2=8000
```

## 4. Corrected deterministic fixture intent responses

Per instruction, this is **not** an attempt to make the fake provider an
intelligent agent -- no canned-response tree was added. It is a correction of
semantically wrong bounded copy and two missing routes.

`backend_lite/app/services/fast_demo_routing.py`:

* **Greeting** (`hello`, `xin chào`, `chào bạn`) -- `GREETING_TEXT` rewritten:
  introduces itself as VietLaw and asks what the user needs help with; no
  longer immediately demands rental-deposit facts.
* **Assistant identity** (`bạn là ai`, `bạn làm được gì`) -- `CAPABILITY_TEXT`
  rewritten: identifies as VietLaw, describes the supported function, and
  discloses that the current version focuses mainly on rental-deposit
  disputes; never claims to know who the user is.
* **User identity** (`tôi là ai`) -- new `FastDemoRoute.USER_IDENTITY` route
  and `USER_IDENTITY_TEXT` constant, no longer falling through to the rental
  intake template: *"Tôi chưa biết danh tính của bạn. Tôi chỉ biết những
  thông tin bạn đã chủ động cung cấp trong cuộc trò chuyện này."*
* **Memory question** (`bạn nhớ gì về tôi`, `bạn biết gì về tôi`) -- new
  `FastDemoRoute.MEMORY` route. `backend_lite/app/services/
  fast_demo_orchestrator.py` adds `_memory_response_text(known: list[str])`,
  which **reuses** the existing `_known_facts()` helper (the same one the
  pre-existing fallback copy already used) rather than duplicating fact
  formatting -- answering only from facts already present in the current
  chat's state, saying so honestly when none exist, never inventing an
  identity, and never routing to the rental intake template. The offered
  MODE_1-honesty escape hatch was not needed since genuine reuse of
  `_known_facts()` was feasible without expanding scope.

Both new routes are schema-safe: the public `response_kind` literal
(`legal`/`social`/`capability`/`scope`) was **not** widened. A new
`route_label` parameter on `_direct_response()` decouples the schema-facing
`kind` from the free-form `metadata.fast_demo_route` string, so
`user_identity` and `memory` appear only in metadata, never in the schema.

```text
RESPONSE_KIND_SCHEMA_WIDENED=no
NEW_METADATA_ROUTE_LABELS=user_identity,memory
CANNED_RESPONSE_TREE_ADDED=no
FACTS_REUSED_VIA_EXISTING_KNOWN_FACTS_HELPER=yes
```

### Proof

`backend_lite/tests/unit/test_fast_demo_identity_and_memory.py` (new, 13
tests): routing distinctness (`tôi là ai` vs `bạn là ai`; `bạn nhớ gì về tôi`
neither absorbed by scope nor acknowledgment); greeting/capability copy
content assertions (no immediate fact demand, VietLaw branding present, scope
disclosed, no claim about who the user is); end-to-end API behavior for all
four routes with zero provider calls; social, capability, identity and
memory turns confirmed to never mutate `state_version` or existing facts,
individually and across a full mixed-turn sequence.

**Scope correction (round 3):** one of these 13 tests
(`test_memory_query_reports_only_facts_already_in_this_chat`) drives a deposit
fact into state via a scripted `FakeLLMClient` plan on an earlier turn in the
*same* `TestClient` session, then asserts the memory route's response text
renders that already-stored state correctly. This is a test of the
`_memory_response_text()` / `_known_facts()` rendering helper against
already-prepared backend state -- it exercises the same backend process the
browser talks to, but it is not evidence about the interactive browser
persistence pipeline end to end (React state, request/response round-trips,
chat-id continuity in the running UI). It must not be read as proof that the
browser fixture flow itself carries a stated fact from one turn to the next
-- the owner's own browser observation (§ Round 3 below) is the correct
source for that question, and it did not confirm persistence.

## 5. Fixture vs. real-agent separation — unchanged, reaffirmed

Documentation-only. The fixture remains suitable only for reveal mechanics,
composer/lifecycle controls, chat navigation, source-link rendering, and now
honest bounded deterministic copy for greeting/identity/memory. It remains
**not** suitable for legal reasoning quality, multi-turn understanding, fact
retention across genuinely open-ended conversation, topic switching, or
response naturalness -- those require MODE_2, which was **not** started this
round and spent no live provider calls, per instruction.

## Files changed (round 2 only)

```text
frontend/src/lib/reveal.ts                       new pacing constants + even-distribution algorithm
frontend/src/components/StructuredAnswer.tsx     new SocialAnswer -- social/capability/scope now word-revealed
frontend/src/test/responseReveal.test.tsx        universal-reveal proof + corrected pacing/floor tests
backend_lite/app/services/fast_demo_routing.py         USER_IDENTITY + MEMORY routes; corrected greeting/capability copy
backend_lite/app/services/fast_demo_orchestrator.py    route_label decoupling; memory response wiring
backend_lite/tests/unit/test_fast_demo_identity_and_memory.py   new, 13 tests
```

No package dependency, legal data, citation, retrieval file, `.env`, or
unrelated UI was touched. `7c3e0253f2b8bc3af7e5f8591369656e902088f3` was not
amended, rewritten or removed; round 1's corrections on top of it are
untouched by this round.

```text
LEGAL_DATA_MODIFIED=0
PACKAGE_FILES_MODIFIED=0
ROUND_1_FILES_TOUCHED_THIS_ROUND=0
```

## Validation (pre-browser-checkpoint)

| Check | Result |
|---|---|
| Complete frontend suite | **146 passed** (was 136) |
| Frontend typecheck | passed |
| Frontend production build | passed -- 167.52 kB JS |
| Complete Backend Lite suite | **880 passed** (867 + 13 new) |
| `compileall backend_lite/app` | passed |

`AUTOMATED_PROVIDER_CALLS=0`, `LIVE_PROVIDER_CALLS_USED=0`, `MODE_2_STARTED=no`.

Confirmed via direct Python script execution against the real FastAPI app
(`TestClient` + `FakeLLMClient`) that all four new/changed routes respond
with the correct route label and copy, and that none of the four mutate
`state_version` or facts. This confirms the routes exist and render correctly
against backend state prepared directly in the test -- see the round-3 scope
correction above and below for what it does **not** confirm about the live
browser flow.

## Owner browser checkpoint

Keep all changes uncommitted.

* **Frontend URL: http://127.0.0.1:5173**
* Backend: scripted `UI_FIXTURE_ONLY` provider (MODE_1), restarted this round
  so it serves the corrected `GREETING_TEXT`/`CAPABILITY_TEXT`/
  `USER_IDENTITY_TEXT`/routing (a Python process does not hot-reload like
  Vite's frontend HMR)
* Live provider calls spent: **0**

### To test

Send each of these five messages, ideally in one chat, and observe:

1. `hello`
2. `bạn là ai`
3. `tôi là ai`
4. `bạn nhớ gì về tôi`
5. `tôi đã đặt cọc 20 triệu, chủ nhà chưa trả lại tiền cọc`

**Expected:**

* every one of the five answers reveals progressively by words -- none appear
  all at once;
* messages 1-4 (short answers) take a perceptible, visibly-animating moment --
  not an instant flash -- roughly 0.6 s or a little more;
* message 5 (the fixture) takes roughly **5.0-5.8 s**, noticeably slower and
  more deliberate than the previously-accepted 3.43 s;
* message 1: introduces itself as VietLaw and asks what you need help with --
  does **not** immediately ask for a deposit amount or rental facts;
* message 2: identifies as VietLaw, describes what it can help with, and
  discloses the current version's focus on rental-deposit disputes -- does
  **not** claim to know who you are;
* message 3: states plainly that it does not know your identity and only
  knows what you have provided in this chat -- does **not** switch to the
  rental-deposit intake template;
* message 4: does **not** invent an identity and does **not** switch to the
  rental-deposit intake template. (**Round 3 update:** the owner's browser
  run showed the fixture did not actually recall the previously stated
  deposit amount in this sequential same-chat flow -- see the Round 3 section
  below. `SAME_CHAT_LEGAL_FACT_PERSISTENCE=not_tested` as a browser-verified
  claim; only the no-invention / no-rental-template-fallback behavior is
  confirmed.)
* message 5: unchanged rental-deposit fixture content, just slower;
* Composer/Send usability during and after each reveal, and chat-switch/New
  Chat/reload behavior, remain correct per the existing (round-1-corrected)
  lifecycle contract.

`REAL_AGENT_CONTEXT_QUALITY=not_tested` -- do not judge conversational memory
quality, cross-topic reasoning, or naturalness from this checkpoint; that
remains MODE_2's job, not started this round.

Awaiting `OWNER_PHASE_C_CORRECTION_BROWSER_PASS` before any commit, push,
merge, deploy, MODE_2 start, source migration, or Phase D start.

---

## Authoritative machine-readable block (current state of this report)

This is the **only** authoritative machine-readable block in this document.
Both the block inside the collapsed `HISTORICAL` section and the block at the
end of the round-1 correction section above describe prior, now-superseded
states and must not be read as current.

```text
VIETLAW_PHASE_C_CORRECTION_AWAITING_OWNER_BROWSER

PHASE_C_ORIGINAL_COMMIT=7c3e0253f2b8bc3af7e5f8591369656e902088f3
PHASE_C_CORRECTION_ROUND1_COMMIT=absent
PHASE_C_CORRECTION_ROUND2_COMMIT=absent

CURRENT_BROWSER_BACKEND=UI_FIXTURE_ONLY
REAL_AGENT_BACKEND_ACTIVE=no
REAL_AGENT_CONTEXT_QUALITY=not_tested
LIVE_PROVIDER_CALLS_USED=0

SINGLE_REVEAL_CONTROLLER_STILL_TRUE=yes
SECOND_TIMER_INTRODUCED=no
CONVERSATIONAL_KINDS_NOW_ROUTED_THROUGH_USE_WORD_REVEAL=social,capability,scope
GREETING_WORD_REVEAL_PASS=yes
ASSISTANT_IDENTITY_WORD_REVEAL_PASS=yes
USER_IDENTITY_WORD_REVEAL_PASS=yes
MEMORY_WORD_REVEAL_PASS=yes
FIRST_PAINT_INCOMPLETE_PASS=yes
WORD_ORDER_PRESERVED_PASS=yes
FINAL_TEXT_EXACT_MATCH_PASS=yes
NO_CHARACTER_LEVEL_REVEAL=yes
REDUCED_MOTION_IMMEDIATE_PASS=yes
CHAT_SWITCH_CLEARS_TIMER_PASS=yes
COMPOSER_SEND_USABLE_DURING_CONVERSATIONAL_REVEAL=yes

WORD_INTERVAL_MS=50
MAX_TOTAL_REVEAL_MS=8000
MAX_TIMER_TICKS=160
SHORT_RESPONSE_MIN_REVEAL_MS=600
MIN_TIMER_TICKS=12
LENGTH_BAND_WORDS_PER_TICK=1..3
EFFECTIVE_WORDS_PER_TICK=1..N
MAX_REVEAL_CEILING_PASS=yes
INTEGER_TICK_CEILING_FORMULA_PRESERVED=yes
FRACTIONAL_TIMING_REINTRODUCED=no

SHORT_RESPONSE_FLOOR_MS=600
SHORT_RESPONSE_ANIMATES_VISIBLY=yes
FIXTURE_REVEAL_SECONDS_ROUND2=5.05
FIXTURE_TARGET_SECONDS_MET=yes
PREVIOUSLY_FAILING_BOUNDARY_2294_PASS=yes
EXHAUSTIVE_TIMING_RANGE=0..10000
EXHAUSTIVE_TIMING_FAILURES=0
EXHAUSTIVE_TIMING_MAX_DURATION_MS=8000

GREETING_DEMANDS_RENTAL_FACTS=no
CAPABILITY_CLAIMS_TO_KNOW_USER=no
CAPABILITY_DISCLOSES_SCOPE=yes
USER_IDENTITY_ROUTES_TO_RENTAL_TEMPLATE=no
MEMORY_ROUTES_TO_RENTAL_TEMPLATE=no
MEMORY_INVENTS_FACTS=no
MEMORY_REUSES_KNOWN_FACTS_HELPER=yes
RESPONSE_KIND_SCHEMA_WIDENED=no
CANNED_RESPONSE_TREE_ADDED=no

BACKEND_NEW_TESTS=13
BACKEND_LITE_TESTS=880 passed
FRONTEND_TESTS=146 passed
FRONTEND_TYPECHECK=passed
FRONTEND_BUILD=passed
COMPILEALL=passed

AUTOMATED_PROVIDER_CALLS=0
LIVE_PROVIDER_CALLS_USED=0
MODE_2_STARTED=no

OWNER_PHASE_C_CORRECTION_BROWSER_CONFIRMATION=no

TRACKED_WORKTREE_CLEAN=no
COMMITS_CREATED=0
REPORT_STAGED=no

PUSH_PERFORMED=no
MERGE_PERFORMED=no
DEPLOY_PERFORMED=no
PHASE_D_STARTED=no
OFFICIAL_SOURCE_MIGRATION_STARTED=no
```

*(This block described round 2. It is superseded by the round-3 block at the
very end of this document -- see below. No implementation changed between
round 2 and round 3; only the claims below were corrected.)*

---
---

# PHASE C CORRECTION ROUND 3 — SCOPE-ACCURATE MODE_1 REPORTING

**No implementation change in this round.** This is a documentation-only
correction on top of round 2, in the same uncommitted working tree, on the
same unchanged commit `7c3e0253f2b8bc3af7e5f8591369656e902088f3`. Nothing in
`frontend/src/lib/reveal.ts`, `frontend/src/components/StructuredAnswer.tsx`,
`backend_lite/app/services/fast_demo_routing.py`, or
`backend_lite/app/services/fast_demo_orchestrator.py` was touched. In
particular, per instruction, none of the following was added: self-
introduction name extraction, profile-name persistence, additional fake
memory behavior, more deterministic routing rules, general NER, or long-term
/cross-chat memory.

## What happened

The owner ran the round-2 browser checkpoint. The greeting, assistant-
identity, user-identity and empty-memory copy all rendered as intended. But
running the sequential same-chat flow (state a deposit fact, then later ask
the memory question in the same chat) showed the fixture did **not** recall
the previously stated deposit amount in that live browser flow.

This is not a regression to fix -- the backend logic path exists and is
exercised by a backend-level test (§4 of round 2, `test_fast_demo_identity_
and_memory.py`), but that test drives state directly through a scripted
`FakeLLMClient` plan inside the same `TestClient` session, which is not the
same thing as proving the interactive browser flow (React state, an actual
multi-turn UI session, real request/response round trips) carries the fact
forward the same way. Round 2's report language blurred that distinction --
describing the memory route as "correctly reporting an established deposit
fact" without qualifying that this was shown at the backend-test level, not
confirmed via the browser. That wording is corrected in place in the round-2
section above (see the "Scope correction (round 3)" note under its §4
Proof, and the updated Validation paragraph and checkpoint item 4).

**The browser observation is not hidden or contradicted here.** MODE_1 is a
scripted `UI_FIXTURE_ONLY` fake provider; it was never intended, and per
explicit instruction is not now being extended, to demonstrate same-chat
name recognition, legal fact extraction, fact persistence, conversational
memory, context continuity, topic switching, or real-agent reasoning. All of
those remain `not_tested` until MODE_2, which has explicit owner
authorization required before it starts -- not given in this round.

## What MODE_1 is bounded to validate (this round reaffirms, does not expand)

* word reveal (all response kinds, per round 2);
* reveal timing (per round 2);
* Composer and Send lifecycle (per round 1);
* chat switching and reload (per round 1);
* interactive controls (`Sao chép`, `Hiện ngay`, source links, known-facts
  disclosure);
* bounded greeting and assistant-identity copy (per round 2).

## What MODE_1 is explicitly not used to validate (unchanged, now stated plainly)

* name recognition;
* legal fact extraction;
* fact persistence;
* conversational memory;
* context continuity;
* topic switching;
* real-agent reasoning.

## Files changed (round 3 only)

```text
VIETLAW_FAST_DEMO_V2_PHASE_C_RESPONSE_REVEAL_REPORT_V1.md   report corrections only
```

No frontend source, backend source, test file, package dependency, or legal
data was touched in round 3.

```text
IMPLEMENTATION_FILES_CHANGED_ROUND3=0
NAME_EXTRACTION_ADDED=no
PROFILE_NAME_PERSISTENCE_ADDED=no
ADDITIONAL_FAKE_MEMORY_ADDED=no
NEW_DETERMINISTIC_ROUTING_ADDED=no
GENERAL_NER_ADDED=no
LONG_TERM_OR_CROSS_CHAT_MEMORY_ADDED=no
```

## Owner browser checkpoint — PASSED

Result: `OWNER_PHASE_C_CORRECTION_BROWSER_PASS`. The owner confirmed the
remaining items: reveal timing/pacing (§3 of round 2), universal word reveal
across all response kinds (§2 of round 2), immediate retirement of the
previous response on an accepted new submission (round 1's L-01 behavior,
still correct under the new universal reveal), Composer/Send lifecycle,
chat switching, and reload behavior. Combined with the greeting/assistant-
identity/user-identity/empty-memory copy already verified, every remaining
MODE_1 UI-validation item for this correction is now confirmed.

Per explicit instruction, no name recognition or memory behavior was added to
MODE_1 in response to the round-3 same-chat-persistence gap; that gap remains
`not_tested` and is left for MODE_2.

All required validation was rerun and passed with the same totals. One commit
was created:

```text
c10144c213ce835422fbdd5c3c0d920d666008ed  fix(demo): close phase-c verification findings
```

Not pushed, merged, or deployed. MODE_2 was not started.

---

## Authoritative machine-readable block (current state of this report)

This is the **only** authoritative machine-readable block in this document.
All earlier machine-readable blocks in this document (inside the collapsed
`HISTORICAL` section, at the end of the round-1 section, and at the end of
the round-2 section) describe prior, now-superseded states and must not be
read as current.

```text
VIETLAW_PHASE_C_CORRECTION_READY_FOR_INDEPENDENT_REVIEW

PHASE_C_ORIGINAL_COMMIT=7c3e0253f2b8bc3af7e5f8591369656e902088f3
PHASE_C_CORRECTION_COMMIT=c10144c213ce835422fbdd5c3c0d920d666008ed
ROUND3_IMPLEMENTATION_CHANGED=no

CURRENT_BROWSER_BACKEND=UI_FIXTURE_ONLY
REAL_AGENT_BACKEND_ACTIVE=no
REAL_AGENT_CONTEXT_QUALITY=not_tested
LIVE_PROVIDER_CALLS_USED=0

FIXTURE_GREETING_COPY=verified
FIXTURE_ASSISTANT_IDENTITY_COPY=verified
FIXTURE_USER_IDENTITY_COPY=verified
FIXTURE_MEMORY_EMPTY_COPY=verified

SAME_CHAT_NAME_RECOGNITION=not_tested
SAME_CHAT_LEGAL_FACT_PERSISTENCE=not_tested
REAL_AGENT_MEMORY_QUALITY=not_tested

NAME_EXTRACTION_ADDED=no
PROFILE_NAME_PERSISTENCE_ADDED=no
ADDITIONAL_FAKE_MEMORY_ADDED=no
NEW_DETERMINISTIC_ROUTING_ADDED=no
GENERAL_NER_ADDED=no
LONG_TERM_OR_CROSS_CHAT_MEMORY_ADDED=no

SINGLE_REVEAL_CONTROLLER_STILL_TRUE=yes
SECOND_TIMER_INTRODUCED=no
WORD_INTERVAL_MS=50
MAX_TOTAL_REVEAL_MS=8000
SHORT_RESPONSE_MIN_REVEAL_MS=600
FIXTURE_REVEAL_SECONDS_ROUND2=5.05
MAX_REVEAL_CEILING_PASS=yes

BACKEND_LITE_TESTS=880 passed
FRONTEND_TESTS=146 passed
FRONTEND_TYPECHECK=passed
FRONTEND_BUILD=passed
COMPILEALL=passed

AUTOMATED_PROVIDER_CALLS=0
LIVE_PROVIDER_CALLS_USED=0
MODE_2_STARTED=no
MODE_2_OWNER_AUTHORIZATION_RECEIVED=no

OWNER_PHASE_C_CORRECTION_BROWSER_CONFIRMATION=yes
REVEAL_TIMING_PASS=yes
UNIVERSAL_WORD_REVEAL_PASS=yes
IMMEDIATE_RETIREMENT_PASS=yes
COMPOSER_SEND_LIFECYCLE_PASS=yes
CHAT_SWITCHING_PASS=yes
RELOAD_BEHAVIOR_PASS=yes

TRACKED_WORKTREE_CLEAN=no
COMMITS_CREATED=1
FINAL_COMMIT_SHA=c10144c213ce835422fbdd5c3c0d920d666008ed
REPORT_STAGED=no

PUSH_PERFORMED=no
MERGE_PERFORMED=no
DEPLOY_PERFORMED=no
PHASE_D_STARTED=no
OFFICIAL_SOURCE_MIGRATION_STARTED=no
```

*(This block described the correction commit before independent
re-verification and owner acceptance. It is superseded by the owner-
acceptance block at the very end of this document -- see below.)*

---
---

# PHASE C — OWNER ACCEPTANCE

Documentation-only. No source, test, legal data, dependency or `.env` file
changed in this section or its commit. This section records the owner's
acceptance of the Phase C correction commit
(`c10144c213ce835422fbdd5c3c0d920d666008ed`) following an independent
re-verification.

## Independent re-verification

`VIETLAW_FAST_DEMO_V2_CODEX_PHASE_C_CORRECTION_REVERIFICATION_V1.md`
(untracked, kept unstaged, not part of this or any commit) reviewed
`c10144c213ce835422fbdd5c3c0d920d666008ed` against its parent
`7c3e0253f2b8bc3af7e5f8591369656e902088f3` and returned:

```text
VIETLAW_PHASE_C_CORRECTION_INDEPENDENT_VERIFICATION_PASS_WITH_NONBLOCKING_FINDINGS

HIGH_FINDINGS=0
MEDIUM_FINDINGS=2
LOW_FINDINGS=1
```

All four prior findings (H-01, M-01, M-02, L-01) were independently confirmed
closed. Three new, nonblocking findings were raised against this report's own
wording, not against the implementation.

## Correction: exact commit scope

`git show --name-status c10144c213ce835422fbdd5c3c0d920d666008ed` lists
**11 total paths**, and the Phase C response-reveal report is one of those 11
-- it is not 11 implementation/test paths *plus* a separate report:

```text
A VIETLAW_FAST_DEMO_V2_PHASE_C_RESPONSE_REVEAL_REPORT_V1.md
M backend_lite/app/services/fast_demo_orchestrator.py
M backend_lite/app/services/fast_demo_routing.py
A backend_lite/tests/unit/test_fast_demo_identity_and_memory.py
M frontend/src/App.tsx
M frontend/src/components/StructuredAnswer.tsx
M frontend/src/lib/reveal.ts
M frontend/src/lib/selectedChat.ts
M frontend/src/test/composerLifecycle.test.tsx
M frontend/src/test/responseReveal.test.tsx
M frontend/src/test/selectedChatRestore.test.tsx
```

11 total paths, 10 of them non-report implementation/test paths, 1 the
report itself.

## NF-01 — report provenance and path accounting — accepted, nonblocking

The correction commit contains 11 total paths, including the report -- not
"11 files plus the report." The committed report blob's own final
machine-readable block was transitional (declared `READY_FOR_INDEPENDENT_
REVIEW` at the top while its last block still said `AWAITING_OWNER_BROWSER`
and that the correction commit was absent); the update to that final block
existed only as an unstaged modification at commit time. This is a
traceability/documentation issue, not a product or test defect, and is
accepted as-is rather than requiring a further amendment to the already-made
commit.

```text
NF01_STATUS=accepted_nonblocking
```

## NF-02 — universal-reveal test evidence overstated — accepted, deferred

The report previously claimed the new `describe('conversational assistant
text reveals progressively by words', ...)` tests assert exactly one
fake-timer interval via `vi.getTimerCount()` and zero after a chat switch.
They do not: those tests run with real timers, contain no `getTimerCount`
assertion, and construct their fixtures with `metadata: {}` and the `social`
kind for all four cases rather than modeling the real Fast Demo
`metadata.fast_demo=true` path or separately emitting capability/scope kinds.
With empty metadata, the otherwise-inert legacy character-typewriter effect
is technically active at the same time as `SocialAnswer`'s word interval --
so these specific test fixtures do not, by themselves, prove the single-
controller claim.

The production claim still holds, verified by direct source inspection: every
real Fast Demo response carries `metadata.fast_demo=true`, which the
`typewriterAnimate = animate && !isFastDemo` expression uses to unconditionally
disable the legacy character path, and the social/capability/scope branch
uniformly renders through `SocialAnswer`/`useWordReveal`. This is supported by
source inspection plus the full regression suite (146 frontend, 880 backend)
passing, not by these four test cases in isolation. Hardening the test
fixtures to use real `fast_demo=true` metadata and fake timers with an
explicit `getTimerCount()` assertion is deferred, not required to accept this
commit.

```text
NF02_STATUS=deferred_test_hardening
```

## NF-03 — general floor helper can finish before its nominal floor — accepted, deferred

`wordsAfterTick`'s `ceil`-based distribution means extremely short synthetic
inputs can finish revealing before `requiredTickCount` nominally expires (a
2-unit input completes at 50 ms, 5-unit at 500 ms, 8/10-unit at 550 ms,
against a 600 ms nominal floor) -- contradicting the report's earlier broad
claim that 5/8/10-word text "keeps visibly growing for exactly the full
600 ms." This is a real edge in the general helper, but every response the
committed bounded MODE_1 fixture actually sends (greeting, assistant
identity/capability, user identity, empty-memory, scope, and the ~202-unit
legal fixture) has 14 or more units and visibly completes in 650-5050 ms --
outside this edge. Fixing the general helper for arbitrarily short synthetic
inputs is deferred as outside the bounded fixture's actual response set, not
required to accept this commit.

```text
NF03_STATUS=deferred_outside_bounded_fixture
```

## Owner acceptance

```text
PHASE_C_IMPLEMENTATION_ACCEPTED=yes
```

The owner accepts the Phase C correction commit
(`c10144c213ce835422fbdd5c3c0d920d666008ed`) with NF-01, NF-02, and NF-03
recorded as nonblocking/deferred findings, none of which alter product
behavior, close any prior H/M/L finding, or change what MODE_1 is authorized
to demonstrate. `SAME_CHAT_NAME_RECOGNITION`, `SAME_CHAT_LEGAL_FACT_
PERSISTENCE`, and `REAL_AGENT_MEMORY_QUALITY` remain `not_tested`; MODE_2 was
not started in this or any prior round.

## Files changed (owner-acceptance commit only)

```text
VIETLAW_FAST_DEMO_V2_PHASE_C_RESPONSE_REVEAL_REPORT_V1.md   report corrections + acceptance record only
```

No source, test, legal data, dependency or `.env` file changed.
`VIETLAW_FAST_DEMO_V2_CODEX_PHASE_C_CORRECTION_REVERIFICATION_V1.md` remains
untracked and unstaged -- not part of this commit.

```text
IMPLEMENTATION_FILES_CHANGED=0
TEST_FILES_CHANGED=0
CODEX_REVERIFICATION_REPORT_TRACKED=no
CODEX_REVERIFICATION_REPORT_STAGED=no
```

---

## Authoritative machine-readable block (current state of this report)

This is the **only** authoritative machine-readable block in this document.
All earlier machine-readable blocks (inside the collapsed `HISTORICAL`
section, and at the end of the round-1, round-2, and round-3 sections)
describe prior, now-superseded states and must not be read as current.

```text
VIETLAW_PHASE_C_ACCEPTED_BY_OWNER

PHASE_C_ORIGINAL_COMMIT=7c3e0253f2b8bc3af7e5f8591369656e902088f3
PHASE_C_CORRECTION_COMMIT=c10144c213ce835422fbdd5c3c0d920d666008ed
PHASE_C_OWNER_ACCEPTANCE_COMMIT=8751417404f658b3053fb6e078e648134f75a4d5

INDEPENDENT_VERDICT=VIETLAW_PHASE_C_CORRECTION_INDEPENDENT_VERIFICATION_PASS_WITH_NONBLOCKING_FINDINGS
HIGH_FINDINGS=0
MEDIUM_FINDINGS=2
LOW_FINDINGS=1
PHASE_C_IMPLEMENTATION_ACCEPTED=yes

CORRECTION_COMMIT_TOTAL_PATHS=11
CORRECTION_COMMIT_NONREPORT_PATHS=10
REPORT_COMMITTED_AS_ONE_OF_11=yes

NF01_STATUS=accepted_nonblocking
NF02_STATUS=deferred_test_hardening
NF03_STATUS=deferred_outside_bounded_fixture

CURRENT_BROWSER_BACKEND=UI_FIXTURE_ONLY
REAL_AGENT_BACKEND_ACTIVE=no
REAL_AGENT_CONTEXT_QUALITY=not_tested
SAME_CHAT_NAME_RECOGNITION=not_tested
SAME_CHAT_LEGAL_FACT_PERSISTENCE=not_tested
REAL_AGENT_MEMORY_QUALITY=not_tested
MODE_2_STARTED=no

BACKEND_LITE_TESTS=880 passed
FRONTEND_TESTS=146 passed
FRONTEND_TYPECHECK=passed
FRONTEND_BUILD=passed
COMPILEALL=passed

AUTOMATED_PROVIDER_CALLS=0
LIVE_PROVIDER_CALLS_USED=0

IMPLEMENTATION_FILES_CHANGED_THIS_COMMIT=0
TEST_FILES_CHANGED_THIS_COMMIT=0
CODEX_REVERIFICATION_REPORT_TRACKED=no
CODEX_REVERIFICATION_REPORT_STAGED=no

TRACKED_WORKTREE_CLEAN=no
COMMITS_CREATED_THIS_TASK=1
REPORT_STAGED=no

PUSH_PERFORMED=no
MERGE_PERFORMED=no
DEPLOY_PERFORMED=no
PHASE_D_STARTED=no
OFFICIAL_SOURCE_MIGRATION_STARTED=no
```
