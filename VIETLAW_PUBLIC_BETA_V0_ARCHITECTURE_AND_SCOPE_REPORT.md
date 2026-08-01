# VietLaw Public Beta Expansion V0 — Architecture & Scope Report

Date: 2026-07-31 (Asia/Ho_Chi_Minh)
Implementer: `CLAUDE_CODE_SONNET`
Starting HEAD: `5079454d90730ac9f7fb23d18fe6b8a5578229a4`
Branch: `feature/conversational-rental-deposit-demo-v2`

## 1. Existing route order (today, before this task)

`AgentRuntime._analyze_turn` (`backend_lite/app/runtime/agent_runtime.py`) runs, in order:

1. `validate_request` (non-empty question).
2. `resolve_or_create_chat`, `store_user_message`.
3. `build_same_chat_context`, `normalize_input`, `detect_language`.
4. `detect_unsafe_intent` — the **baseline** unsafe detector (`PatternUnsafeDetector`), independent of FAST DEMO V2's own safety route.
5. **FAST DEMO V2 hook** (`fast_demo_orchestrator`, gated by `VIETLAW_FAST_DEMO_V2_ENABLED`): if wired, `FastDemoOrchestrator.handle(state)` is called. Internally it runs `fast_demo_routing.classify_route(...)` with this precedence: safety → pending-answer-token → social → capability → user_identity → memory → acknowledgment → out-of-scope+contrast → deposit cues → out-of-scope alone → active-matter follow-up → default `scope_or_unsupported`. **It always returns a response for every route** (never `None`) — including `scope_or_unsupported`, which returns the canned `SCOPE_TEXT` ("Tôi tập trung hỗ trợ các tình huống liên quan đến tiền cọc thuê nhà...") with **zero provider calls and zero state mutation**. This is the exact point the task's §1 defect describes: an out-of-scope-but-legal question dead-ends here today, before any official-source or general-guidance path is ever tried.
6. DEMO VERTICAL SLICE V1 hook (`demo_orchestrator`, gated by `VIETLAW_DEMO_VERTICAL_SLICE_ENABLED`, legacy, off by default) — same shape.
7. Baseline pipeline (domain/risk/decision classification, keyword RAG retrieval, `LiteContentGenerator`, `LiteCitationGuard`, `LiteSafetyGuard`, `LiteResponseBuilder`) — runs only if both hooks above deferred (returned `None`) or are unwired.
8. `store_assistant_message`, `return_response`.

Both hooks already follow the same shape: `try/except Exception → None → defer`, so a failure can never surface as a 500 and can never fall through to a *later* stage incorrectly.

## 2. Integration point for this task

`FastDemoOrchestrator._direct_response(state, "scope", SCOPE_TEXT, recent=recent)` sets `response_kind="scope"` and `metadata = {"fast_demo_route": "scope", "fast_demo_mode": None, "unsafe": False, ...}`. The **unsafe** route uses the *same* `response_kind="scope"` but `metadata["unsafe"] = True`. This gives an exact, structural, already-existing signal to distinguish "the deposit flow declined because this is out of its scope" from "the deposit flow refused because this is unsafe" — **without parsing any prose and without re-implementing any safety check**:

```python
is_scope_fallback = (
    response.metadata.get("fast_demo_route") == "scope"
    and not response.metadata.get("unsafe")
)
```

Plan: add one new optional hook, **`legal_fallback_orchestrator`**, as a new `AgentRuntime` constructor argument (default `None`, so every existing call site — including every test that constructs `AgentRuntime` directly — is unaffected). In `_analyze_turn`, immediately after the existing FAST DEMO V2 block currently does `if fast_response is not None: ... return state.final_response`, insert one narrow branch: **only when** `fast_response` is the `is_scope_fallback` shape above **and** `self.legal_fallback_orchestrator is not None`, give the new orchestrator one chance to produce a better answer (`traffic → official-search → general-guidance`), and substitute its response for `fast_response` if it returns one; otherwise `fast_response` (the original `SCOPE_TEXT`) is used exactly as today. **When the new orchestrator is not wired (flag off, or a hard repo contradiction), this substitution never triggers and `agent_runtime.py`'s behavior for every route — deposit-shaped, social, capability, identity, memory, acknowledgment, unsafe, and even genuinely out-of-scope with the new orchestrator absent — is byte-identical to the current committed HEAD.**

This satisfies every non-negotiable invariant in §2 of the task by construction:
- Deposit-shaped messages never reach `scope_or_unsupported`, so they never see the new hook at all — `existing deposit route precedence` is untouched.
- `resolve_deposit_applicable_clause` is in `fast_demo_source_pack.py`, which this task does not touch — it keeps unconditionally returning `None`.
- The genuinely-unsafe route is excluded structurally (`metadata["unsafe"]` check), not by re-deriving a safety judgement — "Unsafe requests must never be rescued by the legal fallback" holds even if the new orchestrator has a bug, because it is never invoked for that route.
- "Non-legal questions must not trigger legal web search": handled **inside** the new orchestrator itself (see §3), which must independently decide `is_legal_or_rights_related` and return `None` (defer to the original `SCOPE_TEXT`) for genuinely non-legal input — the runtime hook alone cannot make this distinction, since `scope_or_unsupported` is the fallback for both "unclassified legal question" and "unrelated chit-chat/random text" alike today.

## 3. New contracts

- `backend_lite/app/contracts/legal_trust.py` — `TrustLevel` enum (`curated_verified`, `official_source_search`, `general_guidance`), Vietnamese label/explanation maps, `EvidenceOutcome` enum (`sufficient`, `insufficient`, `conflicting`, `unavailable`).
- `backend_lite/app/contracts/traffic.py` — `VehicleType`, `TrafficViolationType`, `LicenseStatus`, `ModificationType` literals; `TrafficFacts` (Pydantic, `extra="forbid"`, all fields optional/`"unknown"`-defaulted, mirroring `FastDemoFacts`'s shape but a **separate model**, since `FastDemoFacts` is frozen and deposit-shaped); `TrafficFactUpdate` (bounded operation/slot/value, mirroring `FactUpdateProposal`'s shape without touching it).
- `backend_lite/app/contracts/official_search.py` — `LegalSearchQuery`, `OfficialLegalSearchCandidate` (title/official_url/official_domain/document_name/document_number/article_number/clause_number/published_date/effective_date/retrieved_at/relevant_excerpt/retrieval_confidence), `OfficialLegalSearchResult` (outcome + candidates + conflict/insufficiency reason).

`FastDemoFacts`/`FastDemoPlan`/`FastDemoState`/`fast_demo.py` are **not modified** — every new fact/plan/state shape for this vertical lives in its own module.

## 4. Files to modify (existing, minimal, additive)

| File | Change |
|---|---|
| `backend_lite/app/schemas/api.py` | Add `trust_level`, `trust_label`, `trust_explanation`, `source_checked_at` to `AnalyzeResponse` — optional, defaulted `None`, added to the existing `model_serializer`'s omit-when-unset field list (same pattern as `analysis`/`draft`/`known_facts`). |
| `backend_lite/app/schemas/content.py` | Mirror the same 4 fields on `AnalyzeContent`; add optional `retrieved_at: str \| None = None` to `SourceObject`. |
| `backend_lite/app/runtime/agent_runtime.py` | New optional constructor param `legal_fallback_orchestrator=None`; one new narrow branch as described in §2. |
| `backend_lite/app/dependencies.py` | New `_traffic_pack_enabled()` / `_official_legal_search_enabled()` flag readers (env-var pattern, matching `_demo_flag_enabled`/`fast_demo_enabled`); new `_build_legal_fallback_orchestrator(settings, snippet_store)`; wire it into `AgentRuntime(...)`. |

No other existing file changes. `fast_demo_fact_validation.py`, `fast_demo_source_pack.py`, `fast_demo_orchestrator.py`, `fast_demo_prompt.py`, `fast_demo_routing.py`, `contracts/fast_demo.py`, `scripts/build_snippets.py`, and `data/legal_snippets.json` are **not touched**.

## 5. New services

- `services/traffic_classifier.py` — bounded deterministic Vietnamese cue matching (same allowlist style as `fast_demo_routing.py`/`fast_demo_fact_validation.py`, not a general NLP parser): detects a traffic topic, extracts `TrafficFacts`, and identifies the single highest-priority missing blocking fact (if any) so at most one clarification is asked.
- `services/legal_intent_classifier.py` — the `IS_LEGAL_OR_RIGHTS_RELATED?` gate: a bounded combination of (a) existing routing signals already computed by `fast_demo_routing` (out-of-scope-domain cues are explicitly *not* proof of "non-legal" — traffic is legal but was previously in `_OUT_OF_SCOPE_CUES`'s spirit only via `"vi pham giao thong"`, which this task does not touch), (b) a small legal-intent phrase set (rights/obligation/dispute/penalty/document/procedure question forms), (c) a positive traffic-classifier hit. No LLM call authorizes this decision by itself.
- `services/official_domain_allowlist.py` — new, separate frozenset + `is_trusted_legal_search_host(url)`, same exact-hostname/https-only/no-credentials/no-port validation logic as `official_source_hosts.py`, plus redirect-target re-validation and private/loopback-address rejection (via `ipaddress` on the resolved host string, rejecting `localhost`/`127.*`/`10.*`/`172.16–31.*`/`192.168.*`/`::1`/link-local). `official_source_hosts.py` itself is not modified.
- `services/official_legal_search.py` — `OfficialLegalSearchService` `Protocol` (one method: `async search(query) -> OfficialLegalSearchResult`), a deterministic `FakeOfficialLegalSearchService` test double, and a structurally-complete `HttpOfficialLegalSearchService` (bounded timeout, no retry loop, allowlist-gated, redirect-chain re-validated at every hop, byte-cap on fetched content, never logs full page/user content) — **gated off by default** and not wired to any real search vendor in this task (see §"Known limitations" in the final report): no search-provider credentials or API contract were specified, so shipping a live integration would mean guessing one, which the task's own "do not fabricate" principle rules out. The class is written so a future task can plug in a real provider by implementing the same `Protocol`.
- `services/official_source_validator.py` — the deterministic evidence-sufficiency gate (§6.4 of the task): pure function over one or more `OfficialLegalSearchCandidate`s → `EvidenceOutcome`.
- `services/general_legal_guidance.py` — deterministic (no LLM call) template generator for the 6-part `GENERAL_GUIDANCE` structure. No LLM call means no risk of an invented article/penalty/deadline in this mode, which is the strongest possible guarantee for the task's `GENERAL_GUIDANCE_INVENTED_ARTICLES=0` / `GENERAL_GUIDANCE_INVENTED_PENALTIES=0` acceptance criteria.
- `services/traffic_source_pack.py` — loads `data/traffic_rules.json`, validates each row via a new `TrafficRuleRecord` Pydantic model, resolves `(topic, TrafficFacts)` → a matched rule or `None` (fail closed, never guesses).
- `services/legal_fallback_orchestrator.py` — the sibling orchestrator itself: `handle(state) -> AnalyzeResponse | None`, implementing `IS_LEGAL_OR_RIGHTS_RELATED? → curated traffic? → official-search (if flagged on and evidence sufficient) → general guidance`.
- `stores/legal_fallback_state_store.py` — new CAS-style SQLite store (own table `legal_fallback_states`), same short-load/short-commit shape as `fast_demo_state_store.py`, holding **typed, separated** fields per §8 of the task: `traffic_facts` (user-reported), `last_retrieved_evidence` (retrieved legal proposition + retrieval timestamp + query + evidence-sufficiency outcome, never conflated with a "fact"), and its own state-version CAS field.

## 6. Feature flags

| Flag | Default | Effect when off |
|---|---|---|
| `VIETLAW_TRAFFIC_PACK_ENABLED` | **on** (curated static data only, same risk class as the existing deposit pack) | Traffic vertical is skipped; `scope_or_unsupported` falls through to official-search/general-guidance exactly as if no traffic rule matched. |
| `VIETLAW_OFFICIAL_LEGAL_SEARCH_ENABLED` | **off** | `official-search` step is skipped entirely — no network attempt of any kind — and unmatched legal questions go straight to `GENERAL_GUIDANCE`. |

Both follow the exact `_flag(name)` env-var convention already used for `VIETLAW_FAST_DEMO_V2_ENABLED`/`VIETLAW_DEMO_VERTICAL_SLICE_ENABLED` — no new `Settings` field, matching the existing convention documented in §1.

## 7. Risks

1. **Curated traffic data must be genuinely verifiable, not fabricated.** Mitigation: `WebSearch`/`WebFetch` against Vietnamese government sources before writing any rule entry; any topic that cannot be verified this way is *omitted*, per the task's explicit instruction, and documented as such in the final report. This tool environment cannot render/execute a real browser session against `chinhphu.vn`/`vbpl.vn` at deploy time, so "last_verified_at" in the curated pack records **research-time verification during this task**, not a live production re-check pipeline (that would be a separate, later, ops concern).
2. **No real official-search provider is specified.** Mitigation: ship the complete, tested evidence-gate/allowlist/citation-validation pipeline behind a default-off flag, with a structurally-real HTTP client class ready for a future provider, and say so plainly rather than claiming a working live integration exists.
3. **`agent_runtime.py` is shared, high-consequence code.** Mitigation: the new branch is additive and defaults to inert (see §2); regression covers every existing route unchanged.
4. **Wire-contract drift.** Mitigation: new response/source fields follow the exact additive-optional-omit-when-unset pattern MODE_2D already established, verified by re-running the full existing test suite unmodified.

## 8. Test plan

Per §13 of the task: focused unit tests per new module (classifier, source pack, allowlist, evidence gate, general guidance), an integration test for the new orchestrator's full decision tree (curated → search-sufficient → search-insufficient/conflicting/unavailable → general-guidance, using only fakes), trust-level tests, frontend tests (badge, source metadata, no-empty-card, landing page), and adversarial/prompt-injection tests treating retrieved page content as untrusted data. Existing suites (`test_article_level_citation.py`, full Backend Lite, evaluation, frontend) must remain byte-for-byte unchanged and pass with identical totals to the documented baseline (256 / 1171 / 214 / 154).

## 9. Proceeding

No hard repository contradiction was found. Continuing directly into Phase B implementation.
