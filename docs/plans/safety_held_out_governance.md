# Safety Held-Out Governance

**Applies to:** Gate A3a2a1 and subsequent deterministic safety corrections

**Repository rule:** held-out sentences are not stored or committed on the
implementation branch.

## Purpose

Visible tests prove known requirements and regressions. They do not constitute
an independent acceptance set. A fresh held-out set is owned by an independent
reviewer and is used to detect family-level overfitting after implementation.

## Separation of knowledge

1. The implementation agent sees only owner-approved visible development cases.
2. The independent reviewer creates held-out cases after implementation or keeps
   the fixture outside the implementation repository/worktree.
3. The reviewer does not disclose each failing sentence to the implementation
   agent.
4. The reviewer reports only the failing family and aggregate count.
5. The implementation agent corrects the whole bounded rule family.
6. The reviewer reruns the complete held-out set, including previously passing
   families.
7. No single-sentence exception or hidden-sentence literal may be added.
8. After acceptance, selected cases may become visible regressions, but a fresh
   subset remains outside the implementation branch.

## Failure-family protocol

Reviewer feedback uses only these stable families unless governance is amended:

- `DIRECT_HARM_PARAPHRASE_FAILED`
- `SAFE_REPORTING_SCOPE_FAILED`
- `CLAUSE_LINKING_FAILED`
- `APPLICATION_ANAPHORA_FAILED`
- `NEGATION_TARGET_FAILED`
- `POLICE_UNSAFE_PRECEDENCE_FAILED`
- `AMBIGUOUS_PROMPT_FAILED`

A report includes the family, number executed, number failed, severity, and
whether failure is a false refusal, false non-refusal, wrong harm family, wrong
risk escalation, nondeterminism, or contract violation. It excludes the raw
sentence and nearby uniquely identifying fragments.

## Target composition

The target set contains 24–30 cases:

- 8 direct harmful paraphrases across all owner-approved harm families;
- 6 victim/reporting/prevention cases;
- 4 ambiguous minimal prompts;
- 4 police-contact or mixed police/unsafe cases;
- 4–8 no-diacritics, clause-order, polite-framing, punctuation, and harmless-noise
  variants distributed across the preceding families.

The reviewer balances false-positive and false-negative risk. At least one case
in each applicable family must vary clause order, and no family is represented
only by a literal phrase already in visible tests.

## Construction constraints

- Cases stay within the owner-approved evasion, forgery, evidence destruction,
  coercion/threat/property coercion, and obstruction scope.
- No general Vietnamese semantic understanding is expected.
- Immediate anaphora may refer only to the immediately preceding clause.
- A case requiring general coreference, a dependency parser, external knowledge,
  or multi-domain policy is classified out of scope rather than tuned into the
  implementation.
- Concept-free direct cues must not be labelled with an invented harm family.
- Generic police mentions remain distinct from personal police contact.
- The reviewer records the exact expected structured `SafetyAssessment`, final
  decision, source boundary, and plan shape before execution.

## Storage and access

Held-out raw cases remain outside the implementation worktree/repository or are
created only after the implementation snapshot is frozen. They must not appear in
implementation prompts, source comments, checked-in tests, audit reports, logs,
or commit messages before acceptance.

Only the independent reviewer has access to the raw set during a recheck. Test
outputs shared with implementers must redact raw input and report aggregate
family results.

## Acceptance and rotation

Acceptance requires all required held-out families to pass with deterministic
full-state output and no architecture/scope regression. A green visible suite is
not acceptance.

After acceptance:

- selected non-sensitive cases may be promoted to visible regression tests;
- the promoted cases are removed from held-out scoring;
- a new fresh subset is created before the next safety-policy change;
- aggregate historical results may be retained, but raw retired cases are not
  used as implementation-tuning exceptions.

Gate A3a2a1 is accepted only by an independent held-out recheck. Its
implementation self-report is evidence for review, not acceptance authority.

