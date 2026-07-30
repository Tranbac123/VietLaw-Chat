# VietLaw Fast Demo V2 — MODE_2B Malformed JSON Root-Cause and Correction Report V1

Date: 2026-07-30 (Asia/Ho_Chi_Minh)
Revision: V1 rev-4 (accepted by owner)
Implementer: `CLAUDE_CODE_SONNET`

## CURRENT VERDICT

`VIETLAW_MODE_2B_ACCEPTED_BY_OWNER`

Both independent reviews (initial root-cause verification and the LOW-01
through LOW-04 correction round) returned pass verdicts, and the owner has
accepted the result. No production code was ever changed across MODE_2B;
the only artifact is the permanent regression suite, already committed as
`bbd9832f67b23148c159ed88be6c2bd3b3c23613` (`test(api): lock strict JSON
transport behavior`).

```text
VIETLAW_MODE_2B_ACCEPTED_BY_OWNER

ROOT_CAUSE_CONFIRMED=test_operator_shell_capture
ROOT_CAUSE_MECHANISM=zsh_echo_builtin_backslash_interpretation
APPLICATION_CODE_DEFECT_FOUND=no
TEST_COMMIT=bbd9832f67b23148c159ed88be6c2bd3b3c23613

INITIAL_INDEPENDENT_VERDICT=VIETLAW_MODE_2B_MALFORMED_JSON_INDEPENDENT_VERIFICATION_PASS_WITH_NONBLOCKING_FINDINGS
CORRECTION_INDEPENDENT_VERDICT=VIETLAW_MODE_2B_CORRECTION_VERIFICATION_PASS_WITH_NONBLOCKING_FINDINGS

LOW01_CLOSED=yes
LOW02_CLOSED=yes
LOW03_CLOSED=yes
LOW04_CLOSED=yes
HIGH_FINDINGS_OPEN=0
MEDIUM_FINDINGS_OPEN=0
LOW_FINDINGS_OPEN=0

HTTP_BODY_STRICT_JSON=yes
MALFORMED_PROVIDER_OUTPUT_FAILS_CLOSED=yes
DUPLICATE_TURN_SERVER_DEFECT=no
PRODUCTION_CODE_CHANGED=no
MODE_2B_ACCEPTED=yes
```

**Precise claim (corrected from rev-1's overbroad wording, stands unchanged
through acceptance):** command substitution preserved this compact FastAPI
response sufficiently, but is not a general binary-safe transport and
removes trailing newlines. The current reviewed application path produces
strict valid JSON, and the MODE_2A corruption signature is independently
explained by zsh `echo`.

```text
ROOT_CAUSE_CONFIRMED=yes
ROOT_CAUSE_LOCATION=test_operator_shell_capture
ROOT_CAUSE_MECHANISM=echo_builtin_backslash_interpretation
APPLICATION_CODE_DEFECT_FOUND=no
APPLICATION_CODE_CHANGED=no
HTTP_200_BODY_STRICT_JSON=yes
RAW_MODEL_TEXT_CANNOT_BREAK_TRANSPORT_JSON=yes
PARAGRAPH_BREAKS_PRESERVED=yes
ANALYZE_RESPONSE_SCHEMA_UNCHANGED=yes

LOW01_CLOSED=yes
LOW02_CLOSED=yes
LOW03_CLOSED=yes
LOW04_CLOSED=yes
LOW_FINDINGS_OPEN=0
FOCUSED_JSON_TRANSPORT_TESTS=5 passed
BACKEND_LITE_TESTS=915 passed
```

## 1. Failure-boundary investigation

Per instruction, "the model returned bad JSON" was not accepted without raw
evidence that the application passes model text directly into the HTTP body.
Each candidate boundary was tested directly, in order:

| # | Candidate boundary | Test | Result |
|---|---|---|---|
| 1 | Anthropic raw output | N/A -- MODE_2A's actual failing response had `"decision":"answer_with_guidance"`, i.e. the **success** path, not the fallback. If the model's own text had been invalid JSON, `_request_plan`'s `json.loads(raw)` would have failed and returned `None`, forcing the deterministic fallback (`_FALLBACK_SUMMARY`/similar). It did not. | **Rejected**: the model's own JSON text was valid; the app's `json.loads` on it must have succeeded. |
| 2 | Provider-response parsing (`AnthropicLLMClient.complete`) | Fed a `FakeLLMClient` a plan whose JSON text contained a genuine unescaped raw newline (simulating truly malformed model output) and drove it through the real orchestrator via `TestClient`. | **Rejected as MODE_2A's cause**: this path correctly fails closed to the deterministic fallback (`category=provider_invalid_json`), which is itself now a permanent regression test (§6, test 2) -- but it does not reproduce a *malformed transport response*, since the fallback text is always clean, schema-conformant JSON. |
| 3 | Extraction of structured fields (`json.loads(raw)` / `FastDemoPlan.model_validate`) | Same test as #2 -- extraction either succeeds cleanly or fails closed; no code path in between manually re-encodes or splices text. | **Rejected**: no defect found. |
| 4 | `AnalyzeResponse` construction (`_build_success` in `fast_demo_orchestrator.py`) | Fed a `FakeLLMClient` a **well-formed** plan whose `analysis` field legitimately contains a properly JSON-escaped newline (`\n\n`, four wire characters), quotes, a backslash, and Vietnamese diacritics, through the real orchestrator via `TestClient`. | **Rejected**: `response.content` (raw bytes) parsed with `json.loads` cleanly; the paragraph break, quote, backslash and Unicode text all round-tripped exactly. |
| 5 | Pydantic serialization (`AnalyzeResponse.model_dump`/custom `@model_serializer`) | Same test as #4, inspecting the raw wire bytes directly for the two/four-character JSON escapes (`\\n\\n`) instead of a bare `0x0A` byte. | **Rejected**: escapes were present and correct; zero bare control bytes in the wire bytes. |
| 6 | FastAPI/Starlette response rendering, over a **real TCP socket** (not just in-process `TestClient`) | Ran the exact production `fast_demo_orchestrator` → `AnalyzeResponse` pipeline under a real `uvicorn` process (port 8098) with the same `FakeLLMClient` plan as #4, then hit it with `curl -o file` (direct byte write, no shell variable). | **Rejected**: `json.loads` on the resulting file succeeded. Real-socket HTTP/1.1 transport does not introduce the corruption. |
| 7 | Middleware (`CORSMiddleware`, error handlers) | Same real-TCP run as #6 -- CORS middleware only adds headers, and the 200 success path never touches `error_handlers.py`. No content-mutating middleware exists on this path (confirmed by reading `main.py` and `error_handlers.py` in full). | **Rejected**: no middleware in this app mutates response bodies. |
| 8 | **Shell/curl capture or post-processing (the operator's own harness)** | Hit the **same real-TCP uvicorn process from #6** twice: once via `RESP=$(curl -s ...); echo "$RESP" > file` (the exact method used throughout the MODE_2A checkpoint), once via `curl -s ... -o file` (direct byte write). | **CONFIRMED as the true root cause** (full byte-level evidence in §2). |

## 2. Deterministic reproduction (byte-level evidence)

### Minimal isolation (throwaway probe app, not part of the product)

A minimal `FastAPI` route returning `{"analysis": "dong 1\n\ndong 2 voi \"trich dan\" va \\ backslash va tieng Viet: đặt cọc, Điều 328"}` was run under real `uvicorn` on a scratch port. Captured two ways:

```text
$ RESP=$(curl -s http://127.0.0.1:8099/probe); echo "$RESP" > bashcap.json
$ curl -s http://127.0.0.1:8099/probe -o direct.json
```

```text
bashcap.json : json.loads FAILED: Invalid control character at: line 1 column 40 (char 39)
direct.json  : json.loads OK
```

Byte-level diff (`repr()` of the raw file contents):

```text
bashcap.json (corrupted):
  ...ana lysis":"dong 1\n\ndong 2 voi \"trich dan\" va \ backslash...
                        ^^ ^^ real 0x0A bytes here          ^ single real backslash byte

direct.json (clean, correct wire bytes):
  ...analysis":"dong 1\\n\\ndong 2 voi \\"trich dan\\" va \\\\ backslash...
                        ^^^^ ^^^^ four-char JSON escape       ^^^^ four-char escape (2 backslashes)
```

`echo "$RESP"` in this shell (zsh, per the environment) interprets `\n` as a
newline and `\\` as a single backslash -- exactly the standard `echo`
backslash-interpretation behavior, applied *after* `curl` had already
received a perfectly valid HTTP response.

**Corrected (round 1, LOW-01):** command substitution preserved this compact
FastAPI response sufficiently, but `RESP=$(curl ...)` is **not** a
general binary-safe transport -- it strips trailing newline bytes as a
documented shell behavior, independent of this specific bug. The claim that
it captures bytes "losslessly" was overbroad and is retracted; the precise,
evidence-backed claim is that it preserved *this* compact body sufficiently
for the `echo` step's corruption to be cleanly observable, not that command
substitution is safe in general.

### Confirmation against the real production pipeline (not a toy probe)

The identical experiment was repeated running the actual
`backend_lite.app.main:app` (with `create_app()`, the real `dependencies.py`
wiring, and the real `FastDemoOrchestrator`/`AnalyzeResponse` path) under a
real `uvicorn` process, with only the LLM client swapped for a
`FakeLLMClient` seeded with **one** multiline/quote/backslash/Vietnamese plan
(matching §1 test 4) and two requests issued against it -- one captured via
`$(curl)+echo`, one via `curl -o` direct file write:

```text
real_pipeline_bashcap.json (via $(curl)+echo) : FAILED: Invalid control character at: line 1 column 1686 (char 1685)
real_pipeline_direct.json  (via curl -o)       : OK
```

**Corrected (round 1, LOW-03):** these two files are **not** captures of the
same underlying response, and the original wording claiming so was
inaccurate. `FakeLLMClient` was seeded with exactly one queued plan; the
first request (captured via `$(curl)+echo`) consumed it and produced the
rich multiline content, corrupted only in transit by `echo`. The second
request (captured via `curl -o`) found the fake response list already
empty, hit `LLMClientError(PROVIDER_ERROR, "fake exhausted")`, and returned
the deterministic fallback response (`analysis: null`, `fast_demo_mode:
fallback`) -- a different response body entirely, not a clean capture of the
same multiline content. **That retained pair alone is not valid
same-response evidence** for "the direct-write method preserves this exact
body correctly" -- it only shows that *a* valid fallback response transports
correctly, which was never in question.

The missing same-response comparison -- the same multiline body, captured
both ways, over the same real TCP socket -- was supplied independently in
the Codex review (`VIETLAW_FAST_DEMO_V2_CODEX_MODE_2B_MALFORMED_JSON_
VERIFICATION_V1.md`, §3): an idempotent real-TCP replay of the identical
response via direct capture and via `RESP=$(curl ...); printf '%s' "$RESP"`
produced byte-identical output (matching SHA-256 hashes), while capturing
that same replay through `echo` reproduced the literal-newline/reduced-
backslash corruption and failed strict parsing. That independent
reproduction is the valid same-response proof; this report's own retained
`real_pipeline_*` artifact pair is corroborating context only, not
same-response evidence, and is kept unmodified below rather than rewritten
to look more conclusive than it is.

The minimal-probe artifacts from §2's first experiment (`bashcap.json` /
`direct.json`, a single-field toy payload, not the full `AnalyzeResponse`
schema) remain valid same-response evidence on their own terms, since that
probe's route had no provider-call/fake-response-exhaustion concern at
all -- it returns a fixed dict on every request.

```text
DEFECT_REPRODUCED_IN_APPLICATION_CODE=no
DEFECT_REPRODUCED_IN_TEST_HARNESS=yes
DEFECT_REPRODUCED_OVER_REAL_TCP=yes
DEFECT_REPRODUCED_IN_PROCESS_TESTCLIENT=no
```

(`TestClient` uses an in-process ASGI transport with no shell in the loop at
all, which is exactly why the original MODE_2A defect never showed up in any
of this repository's existing automated tests -- those tests never pipe
through a shell.)

## 3. Structured-output-disabled path, inspected directly

```text
VIETLAW_FAST_DEMO_STRUCTURED_OUTPUT=0
MODEL=claude-sonnet-4-6
```

With this configuration, `_structured_output_supported()` in
`dependencies.py` returns `False` (explicit env override), so
`AnthropicLLMClient.complete()` omits `output_config` entirely
(`demo_llm_client.py:149-154`) and the model is asked, via
`fast_demo_prompt.py`'s `SYSTEM_PROMPT`/`build_user_prompt`, to produce JSON
as its plain response text, relying on local `FastDemoPlan` Pydantic
validation for conformance (exactly as the module's own docstring states).

Confirmed directly against this exact path:

* **Does the adapter strip Markdown fences?** No. `AnthropicLLMClient.complete`
  returns `first_block.get("text")` verbatim (`demo_llm_client.py:208-211`);
  no fence-stripping, trimming beyond the provider's own text, or
  preprocessing exists anywhere between the HTTP call and
  `_request_plan`'s `json.loads(raw)`.
* **Does it perform manual string concatenation?** No. Every field on
  `AnalyzeResponse` in `_build_success` is assigned directly from a
  `FastDemoPlan` attribute (already a validated Python `str`/`list`), never
  built via f-string/`%`/`.format()` concatenation of raw provider text.
* **Does it parse JSON leniently?** No. `json.loads(raw)` is the standard
  library's default strict decoder -- no `strict=False`, no custom decoder,
  no regex-based repair.
* **Does it inject raw provider strings into a prebuilt HTTP payload?** No.
  The only "payload" construction is the *outbound* Anthropic request body
  (`demo_llm_client.py:140-156`), which contains the *prompt*, not any prior
  response; the *inbound* response is returned through FastAPI's normal
  `response_model=AnalyzeResponse` mechanism, which always re-serializes via
  Pydantic + Starlette's default JSON encoder.
* **Does fallback parsing preserve invalid control characters?** No --
  fallback parsing is "give up and use a fixed deterministic fallback
  response" (`_fallback_response`), never "salvage what we can from the
  invalid text."

```text
MARKDOWN_FENCE_STRIPPING=no
MANUAL_STRING_CONCATENATION=no
LENIENT_JSON_PARSING=no
RAW_PROVIDER_STRING_INJECTED_INTO_PREBUILT_PAYLOAD=no
FALLBACK_PRESERVES_INVALID_CONTROL_CHARS=no
```

**Conclusion: this exact code path is already safe.** There is no file or
function reference to give for "the root cause in application code" because
none exists; the investigation in §1 is the complete, exhaustive answer.

## 4. Correction

**No production code correction was required or made**, since no
application-code failure boundary was found. The task's own required
contract was verified to already hold:

```text
HTTP_200_BODY_STRICT_JSON=yes
RAW_MODEL_TEXT_CANNOT_BREAK_TRANSPORT_JSON=yes
PARAGRAPH_BREAKS_PRESERVED=yes
ANALYZE_RESPONSE_SCHEMA_UNCHANGED=yes
```

A permanent regression suite (§6) was added instead, so this guarantee is
now continuously checked rather than resting on the reasoning in §1-§3 alone.
Per instruction ("do not hide malformed upstream output by silently
fabricating legal content... never manually splice untrusted model text into
JSON bytes"): the existing code already satisfies this -- genuinely malformed
upstream model text fails closed to the controlled fallback contract
(§6, test 2), and no splicing exists anywhere in the reviewed path.

## 5. Retry and duplicate-turn assessment

MODE_2A's Call 8 used a **new** `client_request_id` for what the operator
believed was a necessary retry, resulting in two persisted user/assistant
turn pairs in that chat (documented in the MODE_2A report). With the root
cause now known -- the original response was valid all along -- that retry
was unnecessary, and the duplication was a direct consequence of treating a
non-failure as a failure and resubmitting under a fresh idempotency key.

**Does the existing `client_request_id` contract already prevent this when
used correctly?** Tested directly: two calls with the **same**
`client_request_id` against the same chat produce exactly one persisted
user/assistant pair and exactly one provider call (`fake.calls == 1`), with
both HTTP responses returning the identical `assistant_message_id` (a true
replay). This exact scenario is also already covered by the existing,
unmodified `test_existing_chat_replay_is_persistence_idempotent` in
`backend_lite/tests/integration/test_phase_b1_idempotency.py`.

```text
DUPLICATE_TURN_ROOT_CAUSE=operator_used_new_client_request_id_for_a_non_failure
EXISTING_IDEMPOTENCY_CONTRACT_ALREADY_SUFFICIENT=yes
NARROW_PATCH_PROPOSED=no
IDEMPOTENCY_CODE_CHANGED=no
```

No separate proposed patch is included: the contract is already correct when
used as designed, and no defect was found in it. Per instruction, this is
documented rather than "fixed," since there is nothing to fix.

## 6. Tests added

`backend_lite/tests/integration/test_analyze_response_json_transport.py`
(new, **5 tests** after round-1 correction, zero live provider calls,
`FakeLLMClient` + `TestClient`):

| # | Test | Proves |
|---|---|---|
| 1 | `test_multiline_quotes_backslash_and_unicode_survive_strict_json_transport` | A well-formed plan's `analysis` field (real paragraph break, quotes, backslash, Vietnamese diacritics) round-trips exactly through `json.loads(response.content)`; the wire bytes for that specific field contain the escaped `\n\n` and no bare control newline; exactly one provider call |
| 2 | `test_malformed_provider_json_falls_back_and_transport_stays_valid` | A model response containing a genuinely invalid raw newline in its own JSON text is rejected by `_request_plan`'s `json.loads`, and the resulting HTTP body is still strict, valid JSON via the controlled fallback contract -- never a crash, never the raw invalid text echoed back |
| 3 | `test_normal_legal_response_still_carries_the_official_source` | Unchanged: the migrated Công báo URL is still present |
| 4 | `test_sourceless_response_still_has_no_sources` | Unchanged: a plan selecting no sources still yields `sources: []` |
| 5 | `test_deterministic_route_unaffected_and_still_valid_json` | A deterministic route (`hello` → `social`) is unaffected, zero provider calls, still strict JSON |

**Corrected (round 1, LOW-02):** rev-1 also included a sixth test,
`test_raw_wire_bytes_never_contain_a_bare_control_character_inside_the_string`,
which asserted no `0x0A` byte exists **anywhere** in the response body. That
assertion was imprecise and redundant: a bare newline outside a JSON string
is legal insignificant whitespace, so the test's implicit claim was broader
than its own name/purpose warranted, and it duplicated test 1's coverage
against the same fixture. It has been **removed**; test 1 now locates the
`"analysis":"..."` field specifically (via its JSON key boundaries) and
asserts the escaped `\n\n` sequence and the absence of a bare control
newline **within that field's own bytes**, which is the precise claim the
regression needs. Five focused tests, none redundant, is the corrected
scope.

Mapped to the ten required assertions in the task: 1↔(1,3), 2↔(1), 3↔(1),
4↔(1), 5↔(1,2,3,4,5 -- every test asserts `json.loads` on raw bytes), 6↔(2),
7↔(3), 8↔(4), 9↔(every test asserts `fake.calls`), 10↔(5).

## 7. Live confirmation (post-test-pass)

```text
MAX_LIVE_PROVIDER_CALLS=3
MAX_RETRIES=0
ACTUAL_LIVE_PROVIDER_CALLS=3
ACTUAL_RETRIES=0
```

The same fresh legal request (`Tôi đã đặt cọc 20 triệu để thuê nhà nhưng chủ
nhà không giao nhà và cũng chưa trả lại tiền.`) was sent three independent
times against the still-running real backend from the MODE_2A checkpoint
(port 8010, real Anthropic provider, real model), each in a fresh session,
each captured with `curl -o file` (direct byte write -- the corrected
capture method, not `$(...)`+`echo`):

| Call | HTTP status | Content-Type | `json.loads` | Official source present | Latency |
|---|---|---|---|---|---|
| 1 | 200 | application/json | OK | yes (`congbao.chinhphu.vn`) | 15,630 ms |
| 2 | 200 | application/json | OK | yes (`congbao.chinhphu.vn`) | 15,038 ms |
| 3 | 200 | application/json | OK | yes (`congbao.chinhphu.vn`) | 14,965 ms |

All three succeeded on the first attempt; no retry was needed or performed,
consistent with the root-cause finding that the application itself was
never at fault.

```text
LIVE_CONFIRMATION_ALL_VALID_JSON=yes
LIVE_CONFIRMATION_OFFICIAL_SOURCE_PRESENT=3_of_3
LIVE_CONFIRMATION_FAILURES=0
```

## 8. Exact changed paths

```text
A backend_lite/tests/integration/test_analyze_response_json_transport.py
```

```text
PRODUCTION_CODE_FILES_CHANGED=0
TEST_FILES_ADDED=1
LEGAL_DATA_MODIFIED=0
PROMPTS_MODIFIED=no
ROUTING_MODIFIED=no
MEMORY_MODIFIED=no
RETRIEVAL_MODIFIED=no
CURATED_SOURCES_MODIFIED=no
FRONTEND_REVEAL_MODIFIED=no
PROVIDER_MODEL_CONFIG_MODIFIED=no
NAME_RECALL_WORK_PERFORMED=no
TRAFFIC_ROUTING_OPTIMIZATION_PERFORMED=no
```

## 9. Regression

| Check | Result |
|---|---|
| Focused new tests | **5 passed** (round 1: removed 1 redundant test, rewrote 1) |
| Complete Backend Lite suite | **915 passed** (910 + 5 new) |
| Complete evaluation suite | **214 passed** |
| Complete frontend suite | **146 passed** (unchanged) |
| Frontend typecheck | passed |
| Frontend production build | passed -- 167.52 kB JS |
| `compileall backend_lite/app evaluation scripts` | passed |
| `git diff --check` | clean |

```text
AUTOMATED_PROVIDER_CALLS=0
LIVE_PROVIDER_CALLS_USED=3
```

Confirmed via `git status --porcelain --untracked-files=no`: the only
modified tracked files are two pre-existing, unrelated report files (Phase C
and the official-source migration report), both already mid-edit from prior
tasks; the only path this task touched is the one new test file above.

## 10. Remaining findings (from MODE_2A, reassessed)

| Finding | MODE_2A characterization | This task's finding |
|---|---|---|
| Malformed JSON on live Call 8 | Medium severity, root cause not confirmed | **Closed.** Root cause was the test operator's own shell capture method, not the application. No application defect exists. |
| Traffic-law topic switch cost a live call | Low, cost/latency note | Unchanged -- out of scope for this task per instruction ("do not... optimize traffic routing"). |
| Name-recall phrasing gap | Low, by design | Unchanged -- out of scope for this task per instruction ("do not work on name recall"). |
| Session B duplicated turn | Cosmetic | **Explained** (§5): a direct consequence of the now-understood non-failure being treated as a failure; the underlying idempotency contract was never at fault and needs no patch. |

No new defect was discovered in this task beyond re-explaining the prior
finding's true origin.

## 11. Correction rounds — Codex LOW findings

| ID | Finding | Correction |
|---|---|---|
| LOW-01 | "Losslessly" and "never produced malformed JSON" were overbroad claims not fully supported by retained evidence | Reworded throughout (§2, top verdict) to the precise claim: command substitution preserved this compact response sufficiently but is not a general binary-safe transport; the current reviewed application path produces strict valid JSON, and the MODE_2A signature is independently explained by zsh `echo` |
| LOW-02 | The global bare-newline-scan test was imprecise (a bare newline outside a string is legal JSON whitespace) and redundant with test 1 | Removed; test 1 rewritten to locate the `"analysis":"..."` field specifically and assert the escaped `\n\n` / absence of a bare control newline within that field's own bytes only |
| LOW-03 | `real_pipeline_bashcap.json` and `real_pipeline_direct.json` were claimed to be two captures of the same multiline response; they are not (the direct-write file is a `provider_error` fallback caused by the one-shot `FakeLLMClient` being exhausted by the first request) | Corrected in §2: documented the actual cause, stated plainly that this retained pair is not valid same-response evidence, and pointed to the Codex review's independent idempotent real-TCP replay as the actual same-response proof. Neither artifact file was deleted or rewritten. |
| LOW-04 | Two stale `§6, test 6` references remained after LOW-02 removed a test and renumbered the surviving five (the malformed-provider-fallback test is now test 2, not test 6) | Both references (§1 boundary-8 discussion, §4 conclusion) corrected to `§6, test 2`. Confirmed no other stale reference to "test 6" or "six tests"/"six focused tests" remains anywhere in the report. |

```text
LOW01_CLOSED=yes
LOW02_CLOSED=yes
LOW03_CLOSED=yes
LOW04_CLOSED=yes
LOW_FINDINGS_OPEN=0
```

## 12. Owner acceptance

Documentation-only. No production code, test file, legal data, dependency,
or `.env` file changed in this section or its commit.

Both independent reviewer verdicts are closed with zero open findings of any
severity:

* `INITIAL_INDEPENDENT_VERDICT=VIETLAW_MODE_2B_MALFORMED_JSON_INDEPENDENT_
  VERIFICATION_PASS_WITH_NONBLOCKING_FINDINGS` -- root cause confirmed as
  the test operator's shell capture (zsh `echo` builtin backslash
  interpretation), not an application defect; the four resulting LOW
  findings (report/test wording only) were all closed across two correction
  rounds (§11).
* `CORRECTION_INDEPENDENT_VERDICT=VIETLAW_MODE_2B_CORRECTION_VERIFICATION_
  PASS_WITH_NONBLOCKING_FINDINGS` -- the corrections themselves were
  independently re-verified and returned a clean pass.

```text
VIETLAW_MODE_2B_ACCEPTED_BY_OWNER

ROOT_CAUSE_CONFIRMED=test_operator_shell_capture
ROOT_CAUSE_MECHANISM=zsh_echo_builtin_backslash_interpretation
APPLICATION_CODE_DEFECT_FOUND=no
TEST_COMMIT=bbd9832f67b23148c159ed88be6c2bd3b3c23613

INITIAL_INDEPENDENT_VERDICT=VIETLAW_MODE_2B_MALFORMED_JSON_INDEPENDENT_VERIFICATION_PASS_WITH_NONBLOCKING_FINDINGS
CORRECTION_INDEPENDENT_VERDICT=VIETLAW_MODE_2B_CORRECTION_VERIFICATION_PASS_WITH_NONBLOCKING_FINDINGS

LOW01_CLOSED=yes
LOW02_CLOSED=yes
LOW03_CLOSED=yes
LOW04_CLOSED=yes
HIGH_FINDINGS_OPEN=0
MEDIUM_FINDINGS_OPEN=0
LOW_FINDINGS_OPEN=0

HTTP_BODY_STRICT_JSON=yes
MALFORMED_PROVIDER_OUTPUT_FAILS_CLOSED=yes
DUPLICATE_TURN_SERVER_DEFECT=no
PRODUCTION_CODE_CHANGED=no
MODE_2B_ACCEPTED=yes
```

## Files changed (owner-acceptance commit only)

```text
M VIETLAW_FAST_DEMO_V2_MODE_2B_MALFORMED_JSON_CORRECTION_REPORT_V1.md
```

No production code, test file, legal data, Markdown authoring file,
dependency, or `.env` file was touched. The pre-existing unstaged
modifications to the Phase C report and the official-source migration
report (from prior, unrelated tasks) and every untracked Codex verification
report were left exactly as they were -- neither staged nor committed here.

```text
IMPLEMENTATION_FILES_CHANGED=0
TEST_FILES_CHANGED=0
PHASE_C_REPORT_STAGED=no
OFFICIAL_SOURCE_MIGRATION_REPORT_STAGED=no
CODEX_REPORTS_STAGED=no
```

## 13. Machine-readable verdict

This is the **only** authoritative machine-readable block in this document.
The top verdict block above and §12's block both already state
`VIETLAW_MODE_2B_ACCEPTED_BY_OWNER`; this final block is the fullest,
most complete record and takes precedence over both for any field they
share.

```text
VIETLAW_MODE_2B_ACCEPTED_BY_OWNER

STARTING_HEAD=994965b86c92594e709b01c53c95ef3a6fd1cce3
TEST_COMMIT=bbd9832f67b23148c159ed88be6c2bd3b3c23613
ACCEPTANCE_COMMIT=pending

ROOT_CAUSE_CONFIRMED=test_operator_shell_capture
ROOT_CAUSE_MECHANISM=zsh_echo_builtin_backslash_interpretation
APPLICATION_CODE_DEFECT_FOUND=no

REJECTED_HYPOTHESES=anthropic_raw_output,provider_response_parsing,structured_field_extraction,analyze_response_construction,pydantic_serialization,fastapi_starlette_rendering,middleware

HTTP_BODY_STRICT_JSON=yes
RAW_MODEL_TEXT_CANNOT_BREAK_TRANSPORT_JSON=yes
PARAGRAPH_BREAKS_PRESERVED=yes
ANALYZE_RESPONSE_SCHEMA_UNCHANGED=yes
MALFORMED_PROVIDER_OUTPUT_FAILS_CLOSED=yes

DUPLICATE_TURN_ROOT_CAUSE=operator_used_new_client_request_id_for_a_non_failure
EXISTING_IDEMPOTENCY_CONTRACT_ALREADY_SUFFICIENT=yes
DUPLICATE_TURN_SERVER_DEFECT=no
NARROW_PATCH_PROPOSED=no

INITIAL_INDEPENDENT_VERDICT=VIETLAW_MODE_2B_MALFORMED_JSON_INDEPENDENT_VERIFICATION_PASS_WITH_NONBLOCKING_FINDINGS
CORRECTION_INDEPENDENT_VERDICT=VIETLAW_MODE_2B_CORRECTION_VERIFICATION_PASS_WITH_NONBLOCKING_FINDINGS

LOW01_CLOSED=yes
LOW02_CLOSED=yes
LOW03_CLOSED=yes
LOW04_CLOSED=yes
HIGH_FINDINGS_OPEN=0
MEDIUM_FINDINGS_OPEN=0
LOW_FINDINGS_OPEN=0

FOCUSED_JSON_TRANSPORT_TESTS=5 passed
BACKEND_LITE_TESTS=915 passed
EVALUATION_TESTS=214 passed
FRONTEND_TESTS=146 passed
FRONTEND_TYPECHECK=passed
FRONTEND_BUILD=passed
COMPILEALL=passed
GIT_DIFF_CHECK=clean

MAX_LIVE_PROVIDER_CALLS=3
ACTUAL_LIVE_PROVIDER_CALLS=0
MAX_RETRIES=0
ACTUAL_RETRIES=0

PRODUCTION_CODE_FILES_CHANGED=0
PRODUCTION_CODE_CHANGED=no
TEST_FILES_ADDED=1
NAME_RECALL_WORK_PERFORMED=no
TRAFFIC_ROUTING_OPTIMIZATION_PERFORMED=no

TRACKED_WORKTREE_CLEAN=no (unrelated pre-existing dirty files: VIETLAW_FAST_DEMO_V2_PHASE_C_RESPONSE_REVEAL_REPORT_V1.md, VIETLAW_FAST_DEMO_V2_OFFICIAL_SOURCE_MIGRATION_REPORT_V1.md -- from prior tasks, not touched here)
COMMITS_CREATED_THIS_TASK=pending
REPORT_STAGED=no
MODE_2B_ACCEPTED=yes

PUSH_PERFORMED=no
MERGE_PERFORMED=no
DEPLOY_PERFORMED=no
PHASE_D_STARTED=no
```
