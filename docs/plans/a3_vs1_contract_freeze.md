# A3-VS1 Semantic Contract Freeze

**Status:** frozen specification only

**Implementation:** not present in Gate A3a2a1

**Freeze date:** 2026-07-17

## Purpose and boundary

This document freezes the semantic seam between the pure deterministic analysis
kernel and a future A3-VS1 application orchestrator. It does not authorize or
implement `AnalyzeService`, retrieval, a deterministic finalizer, HTTP wiring,
startup composition, persistence changes, or public contract changes.

There remains one policy engine. Future orchestration must call the canonical
kernel stages and must not reproduce safety, domain, evidence, decision,
AnswerPlan, confidence, or validation rules.

## Frozen future API

```python
def prepare_analysis(
    analysis_input: AnalysisInput,
) -> PreparedAnalysis: ...

def create_retrieval_request(
    prepared: PreparedAnalysis,
) -> RetrievalRequest | None: ...

def complete_analysis(
    prepared: PreparedAnalysis,
    candidates: tuple[EvidenceCandidate, ...],
) -> AnalysisState: ...

def run_deterministic_analysis(
    analysis_input: AnalysisInput,
) -> AnalysisState: ...
```

Compatibility is frozen as:

```text
run_deterministic_analysis(analysis_input)
  = prepare_analysis(analysis_input)
  -> complete_analysis(
       prepared,
       candidates=analysis_input.evidence_candidates,
     )
```

The wrapper must preserve the present canonical value semantics, final-state
congruence, stage order, deterministic output, and external authoritative-input
boundary. It may not select a second policy path based on whether a retriever was
used.

## PreparedAnalysis semantics

`PreparedAnalysis` is a frozen internal value and contains exactly the semantic
outputs available before evidence admission:

- authoritative canonical `AnalysisInput`;
- normalized current question;
- resolved bounded context;
- canonical domain result or bounded domain hints;
- canonical `SafetyAssessment`;
- fact completeness;
- canonical `EvidenceRequirementPlan`/current `EvidencePlan` equivalent;
- immutable version snapshot;
- exact ordered prepare-stage markers.

It does not contain:

- admitted or rejected evidence;
- final `ResponseDecision`/`DecisionRecord`;
- `AnswerPlan`;
- confidence;
- generated wording or a public response.

The authoritative `AnalysisInput` remains the validator authority. A caller may
not replace the question, context, candidates, identity references, language, or
versions by forging a `PreparedAnalysis`.

## RetrievalRequest semantics

`RetrievalRequest` is a frozen internal request carrying:

- normalized query;
- bounded retrieval context only when current policy permits it;
- domain hint or ordered domain candidates;
- allowed evidence categories;
- `sources_allowed`;
- `evidence_required`;
- bounded `max_sources`;
- corpus/source-policy version.

When `sources_allowed` is false,
`create_retrieval_request(prepared)` must return `None`. A future
`AnalyzeService` must then make zero retriever calls. Refusal and unsupported
paths must not manufacture a retrieval request.

The request is a candidate-acquisition contract only. A retriever result is not
admitted evidence and cannot set safety, decision, sources, AnswerPlan, or
confidence.

## Completion semantics

`complete_analysis()` executes this fixed semantic order:

```text
retrieved candidates
-> canonical EvidenceGuard
-> final ResponseDecisionPolicy
-> canonical AnswerPlan
-> deterministic confidence
-> final canonical validation
```

It validates candidates against the prepared authoritative input and version
boundary, and it reuses the sole canonical policy functions. Guidance that
requires evidence cannot survive zero canonical admissions. Refusal and
unsupported results remain source-free.

No generated text, HTTP DTO, durable request state, retriever implementation, or
adapter value participates in this pure completion contract.

## Stage and compatibility rules

- Prepare-stage markers are one immutable prefix of the existing canonical stage
  order; completion appends the remaining markers exactly once.
- The public `run_deterministic_analysis()` outcome stays value-compatible with
  the current one-shot function for candidates already present in
  `AnalysisInput`.
- Runner and validator must share one canonical derivation; validation must not
  copy policy tables.
- SafetyPolicy remains the sole safety authority.
- Domain classification remains owned by the existing domain policy. This freeze
  does not change multi-domain behavior.
- Evidence candidates remain caller/retriever candidates until EvidenceGuard
  admits them.
- Confidence is deterministic diagnostic output and never changes the decision.
- No kernel stage performs I/O, retrieval, persistence, clock, randomness, model
  invocation, or framework work.

## File ownership freeze

| Area | A3a2a1 owner | Future A3-VS1 owner | Rule |
|---|---|---|---|
| `application/safety_policy.py` | Yes | No | A3a2a1 owns clause-aware safety semantics. |
| `application/safety_intent.py` if introduced | Yes | No | Pure bounded safety helper only. |
| Safety-specific typed values | Yes | Shared read-only consumer | A3a2a1 defines; future work consumes frozen contract. |
| Safety focused/architecture tests | Yes | Regression consumer | Future work may add integration coverage, not weaken policy tests. |
| `application/analyze_service.py` | No | Yes | Not created in A3a2a1. |
| Application errors | No | Yes | No HTTP/error semantics invented here. |
| Retriever port/adapter | No | Yes | Existing port remains untouched by A3a2a1. |
| Deterministic finalizer | No | Yes | Not created in A3a2a1. |
| Integration composition/tests | No | Yes | No runtime/startup/API wiring in A3a2a1. |
| Canonical application state | Safety fields only | Shared interface | One coding owner changes it at a time. |
| Deterministic pipeline seam | Canonical safety integration only | Future split implementation | Contract must be rechecked before edits. |

Shared state/kernel interfaces must never be changed independently on parallel
branches. The required sequence for one coding agent is:

```text
contract freeze
-> A3a2a1 implementation
-> visible regression
-> independent held-out audit
-> A3-VS1 implementation
```

If shared-contract drift is discovered before A3-VS1 begins, the freeze must be
reviewed again; neither branch may silently adapt the contract.

## Explicit non-implementation statement

Gate A3a2a1 creates no `PreparedAnalysis` or `RetrievalRequest` runtime type and
no `prepare_analysis`, `create_retrieval_request`, or `complete_analysis`
function. It does not activate `AnalyzeService`, retrieval, finalization,
persistence, API routes, startup wiring, or public HTTP idempotency.

