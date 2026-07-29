import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import type { AnalyzeContent } from '../api/types';
import {
  getAdaptiveTypewriterTiming,
  LIST_ITEM_REVEAL_MS,
  segmentGraphemes,
} from '../lib/animation';
import { formatDomain } from '../lib/format';
import { stripRedundantOrdinal } from '../lib/listText';
import {
  ATOMIC_BLOCK_WORD_COST,
  countWords,
  useWordReveal,
  wordPrefix,
} from '../lib/reveal';
import { selectSafeSources } from '../lib/sourceUrl';
import { DecisionBadge } from './DecisionBadge';
import { RiskBadge } from './RiskBadge';
import { SourcePanel } from './SourcePanel';

interface StructuredAnswerProps {
  content: AnalyzeContent;
  animate?: boolean;
  onAnimationComplete?: () => void;
  onAnimationProgress?: () => void;
}

interface RevealState {
  summaryLength: number;
  clarifyingCount: number;
  checklistCount: number;
  nextStepsCount: number;
  showSources: boolean;
  showSafetyNotice: boolean;
}

function fullRevealState(content: AnalyzeContent, summaryLength = segmentGraphemes(content.summary).length): RevealState {
  return {
    summaryLength,
    clarifyingCount: content.clarifying_questions.length,
    checklistCount: content.checklist.length,
    nextStepsCount: content.next_steps.length,
    showSources: true,
    showSafetyNotice: true,
  };
}

function initialRevealState(content: AnalyzeContent, animate: boolean, summaryLength?: number): RevealState {
  return animate
    ? {
      summaryLength: 0,
      clarifyingCount: 0,
      checklistCount: 0,
      nextStepsCount: 0,
      showSources: false,
      showSafetyNotice: false,
    }
    : fullRevealState(content, summaryLength);
}

function prefersReducedMotion(): boolean {
  return typeof window !== 'undefined'
    && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
}

interface AnswerListProps {
  title: string;
  items: string[];
  visibleCount: number;
  animateItems: boolean;
}

function AnswerList({ title, items, visibleCount, animateItems }: AnswerListProps) {
  const visibleItems = items.slice(0, visibleCount);
  if (visibleItems.length === 0) return null;

  return (
    <section className="answer-section">
      <h3>{title}</h3>
      <ul>
        {visibleItems.map((item, index) => (
          <li className={animateItems ? 'answer-list-item--revealed' : undefined} key={`${title}-${index}`}>
            {item}
          </li>
        ))}
      </ul>
    </section>
  );
}

function ClarifyingQuestions({ items, visibleCount, animateItems }: Omit<AnswerListProps, 'title'>) {
  const visibleItems = items.slice(0, visibleCount);
  if (visibleItems.length === 0) return null;

  return (
    <section className="answer-section clarification-section">
      <p className="clarification-lead">Để tôi đánh giá chính xác hơn, bạn có thể cho biết thêm:</p>
      <ul>
        {visibleItems.map((item, index) => (
          <li className={animateItems ? 'answer-list-item--revealed' : undefined} key={`clarification-${index}`}>
            {item}
          </li>
        ))}
      </ul>
    </section>
  );
}

export function StructuredAnswer({
  content,
  animate = false,
  onAnimationComplete,
  onAnimationProgress,
}: StructuredAnswerProps) {
  const summaryGraphemes = useMemo(() => segmentGraphemes(content.summary), [content.summary]);
  const typewriterTiming = useMemo(
    () => getAdaptiveTypewriterTiming(summaryGraphemes.length),
    [summaryGraphemes.length],
  );
  const isFollowUp = content.metadata.used_current_chat_history === true;
  const visibleChecklist = useMemo(
    () => (isFollowUp || content.decision === 'unsupported' ? [] : content.checklist),
    [content.checklist, content.decision, isFollowUp],
  );
  const visibleSources = useMemo(
    () => (isFollowUp ? [] : content.sources.filter((source) => (
      source.source_type !== 'curated_note'
      && source.source_type !== 'safety_policy'
      && source.source_type !== 'demo_only'
    ))),
    [content.sources, isFollowUp],
  );
  const reducedMotion = prefersReducedMotion();
  // Structured fast-demo answers are revealed word by word (see
  // `FastDemoAnswer` / `useWordReveal`). That is the ONE reveal controller for
  // this response kind: the character typewriter below never runs for it, and
  // there is no separate block-staging timer. Running more than one produced a
  // reveal that read as arriving all at once.
  const isFastDemo = content.metadata?.fast_demo === true;
  const typewriterAnimate = animate && !isFastDemo;
  const [revealState, setRevealState] = useState(() => (
    initialRevealState(content, typewriterAnimate && !reducedMotion, summaryGraphemes.length)
  ));
  const [isRevealing, setIsRevealing] = useState(typewriterAnimate && !reducedMotion);
  const completeNowRef = useRef<(() => void) | null>(null);
  const onAnimationCompleteRef = useRef(onAnimationComplete);
  const onAnimationProgressRef = useRef(onAnimationProgress);

  onAnimationCompleteRef.current = onAnimationComplete;
  onAnimationProgressRef.current = onAnimationProgress;

  useEffect(() => {
    let cancelled = false;
    let didComplete = false;
    let animationFrameId: number | null = null;
    let listTimeoutId: number | null = null;

    const cancelScheduledWork = () => {
      if (animationFrameId !== null) window.cancelAnimationFrame(animationFrameId);
      if (listTimeoutId !== null) window.clearTimeout(listTimeoutId);
      animationFrameId = null;
      listTimeoutId = null;
    };

    const revealAll = (notifyCompletion: boolean) => {
      if (cancelled || didComplete) return;
      didComplete = true;
      cancelScheduledWork();
      setRevealState(fullRevealState(content, summaryGraphemes.length));
      setIsRevealing(false);
      if (notifyCompletion) onAnimationCompleteRef.current?.();
    };

    completeNowRef.current = () => revealAll(true);

    if (!typewriterAnimate) {
      setRevealState(fullRevealState(content, summaryGraphemes.length));
      setIsRevealing(false);
      completeNowRef.current = null;
      return () => {
        cancelled = true;
        cancelScheduledWork();
      };
    }

    if (prefersReducedMotion()) {
      revealAll(true);
      return () => {
        cancelled = true;
        cancelScheduledWork();
      };
    }

    setRevealState(initialRevealState(content, true, summaryGraphemes.length));
    setIsRevealing(true);

    const revealLists = () => {
      if (cancelled || didComplete) return;

      const revealSteps: Array<() => void> = [
        ...visibleChecklist.map((_, index) => () => {
          setRevealState((current) => ({ ...current, checklistCount: index + 1 }));
        }),
        ...content.next_steps.map((_, index) => () => {
          setRevealState((current) => ({ ...current, nextStepsCount: index + 1 }));
        }),
        ...content.clarifying_questions.map((_, index) => () => {
          setRevealState((current) => ({ ...current, clarifyingCount: index + 1 }));
        }),
      ];

      const revealNext = (stepIndex: number) => {
        if (cancelled || didComplete) return;
        if (stepIndex >= revealSteps.length) {
          setRevealState((current) => ({ ...current, showSources: true, showSafetyNotice: true }));
          onAnimationProgressRef.current?.();
          revealAll(true);
          return;
        }

        revealSteps[stepIndex]();
        onAnimationProgressRef.current?.();
        listTimeoutId = window.setTimeout(() => revealNext(stepIndex + 1), LIST_ITEM_REVEAL_MS);
      };

      revealNext(0);
    };

    if (summaryGraphemes.length === 0) {
      revealLists();
    } else {
      let startedAt: number | null = null;
      let lastVisibleLength = 0;
      let lastProgressAt = 0;

      const revealSummary = (timestamp: number) => {
        if (cancelled || didComplete) return;
        if (startedAt === null) startedAt = timestamp;

        const elapsedMs = timestamp - startedAt;
        const nextVisibleLength = Math.min(
          summaryGraphemes.length,
          Math.floor((elapsedMs * typewriterTiming.charsPerSecond) / 1000),
        );

        if (nextVisibleLength !== lastVisibleLength) {
          lastVisibleLength = nextVisibleLength;
          setRevealState((current) => ({ ...current, summaryLength: nextVisibleLength }));
        }

        if (timestamp - lastProgressAt >= 160) {
          lastProgressAt = timestamp;
          onAnimationProgressRef.current?.();
        }

        if (nextVisibleLength < summaryGraphemes.length) {
          animationFrameId = window.requestAnimationFrame(revealSummary);
          return;
        }

        onAnimationProgressRef.current?.();
        revealLists();
      };

      animationFrameId = window.requestAnimationFrame(revealSummary);
    }

    return () => {
      cancelled = true;
      cancelScheduledWork();
      if (completeNowRef.current) completeNowRef.current = null;
    };
  }, [typewriterAnimate, content, summaryGraphemes.length, typewriterTiming.charsPerSecond, visibleChecklist]);

  const visibleSummary = summaryGraphemes.slice(0, revealState.summaryLength).join('');
  const animateItems = isRevealing && !prefersReducedMotion();

  // Social turns (greeting/identity/user-identity/memory/capability/out-of-scope)
  // are a direct conversational reply, not a legal analysis: no domain/risk/
  // decision badges, no clarification/checklist/next-step sections, no source
  // panel, no legal safety disclaimer -- just the assistant text. It uses the
  // SAME word-reveal controller as a structured Fast Demo legal answer
  // (`useWordReveal`, via `SocialAnswer` below), not the character typewriter:
  // these responses used to fall through to the typewriter-driven render
  // below, but `typewriterAnimate` is unconditionally false whenever
  // `content.metadata.fast_demo` is true (every Fast Demo response, social
  // included) -- so a greeting or identity answer from this backend never
  // animated at all despite `animate` being true. Routing it through the same
  // controller other assistant text uses fixes that and keeps the
  // "exactly one reveal controller" invariant. Anything that is not literally
  // response_kind === 'social'/'capability'/'scope' (including older persisted
  // messages without the field) falls through to the existing full legal
  // rendering below.
  if (
    content.response_kind === 'social'
    || content.response_kind === 'capability'
    || content.response_kind === 'scope'
  ) {
    return (
      <SocialAnswer
        content={content}
        animate={animate}
        onRevealComplete={() => onAnimationCompleteRef.current?.()}
        onRevealStep={() => onAnimationProgressRef.current?.()}
      />
    );
  }

  // FAST DEMO V2 legal rendering. The fast-demo backend owns block selection,
  // so the baseline follow-up suppression (which hides checklist/sources on any
  // turn that used chat history) must not apply here.
  if (isFastDemo) {
    return (
      <FastDemoAnswer
        content={content}
        animate={animate}
        onRevealComplete={() => onAnimationCompleteRef.current?.()}
        onRevealStep={() => onAnimationProgressRef.current?.()}
      />
    );
  }

  return (
    <div className="structured-answer">
      <div className="answer-badges" aria-label="Phân loại phản hồi">
        {content.domain !== 'high_risk' && (
          <span className={`badge domain-badge domain-${content.domain}`}>{formatDomain(content.domain)}</span>
        )}
        <RiskBadge level={content.risk_level} />
        <DecisionBadge decision={content.decision} />
      </div>

      {isRevealing && (
        <button
          className="answer-reveal-skip"
          type="button"
          onClick={() => completeNowRef.current?.()}
          aria-label="Hiển thị toàn bộ phản hồi ngay"
        >
          Hiện ngay
        </button>
      )}

      <p className="answer-summary">
        {visibleSummary}
        {isRevealing && revealState.summaryLength < summaryGraphemes.length && (
          <span className="typewriter-cursor" aria-hidden="true">▍</span>
        )}
      </p>

      <AnswerList
        title="Bạn nên chuẩn bị"
        items={visibleChecklist}
        visibleCount={revealState.checklistCount}
        animateItems={animateItems}
      />
      <AnswerList
        title="Bạn có thể làm ngay"
        items={content.next_steps}
        visibleCount={revealState.nextStepsCount}
        animateItems={animateItems}
      />
      <ClarifyingQuestions
        items={content.clarifying_questions}
        visibleCount={revealState.clarifyingCount}
        animateItems={animateItems}
      />
      {/* Visibility is decided by the validated collection inside SourcePanel,
          not by the raw array length: a response whose URLs are all unsafe
          must render no source UI at all. */}
      {revealState.showSources && <SourcePanel sources={visibleSources} />}
    </div>
  );
}


interface SocialAnswerProps {
  content: AnalyzeContent;
  /** True only for a newly received response; persisted answers render whole. */
  animate: boolean;
  onRevealComplete: () => void;
  onRevealStep: () => void;
}

/**
 * Social / capability / scope answers: a single paragraph, word-revealed by
 * the same `useWordReveal` controller `FastDemoAnswer` uses. There is nothing
 * else to stage -- no blocks, no lists, no controls -- so this is the whole
 * component.
 */
function SocialAnswer({ content, animate, onRevealComplete, onRevealStep }: SocialAnswerProps) {
  const totalWords = countWords(content.summary);
  const { revealedWords, isRevealing, revealAll } = useWordReveal(totalWords, animate, {
    onStep: onRevealStep,
    onComplete: onRevealComplete,
  });

  return (
    <div className="structured-answer structured-answer--social">
      {isRevealing && (
        <button
          className="answer-reveal-skip"
          type="button"
          onClick={revealAll}
          aria-label="Hiển thị toàn bộ phản hồi ngay"
        >
          Hiện ngay
        </button>
      )}
      <p className="message-text">{wordPrefix(content.summary, revealedWords)}</p>
    </div>
  );
}

interface FastDemoAnswerProps {
  content: AnalyzeContent;
  /** True only for a newly received response; persisted answers render whole. */
  animate: boolean;
  onRevealComplete: () => void;
  onRevealStep: () => void;
}

function DraftCard({ title, body }: { title: string; body: string }) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    try {
      await navigator.clipboard.writeText(body);
    } catch {
      return;
    }
    setCopied(true);
    window.setTimeout(() => setCopied(false), 2000);
  }

  return (
    <section className="answer-section draft-card">
      <div className="draft-card-head">
        <h3>{title}</h3>
        <button className="draft-copy-button" type="button" onClick={() => void copy()}>
          {copied ? 'Đã sao chép' : 'Sao chép'}
        </button>
      </div>
      <p className="draft-body">{body}</p>
    </section>
  );
}

function KnownFacts({ items }: { items: string[] }) {
  const [open, setOpen] = useState(false);
  if (items.length === 0) return null;

  return (
    <section className="answer-section known-facts">
      <button
        className="known-facts-toggle"
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
      >
        {open ? '▾' : '▸'} Thông tin đã ghi nhận ({items.length})
      </button>
      {open && (
        <ul className="known-facts-list">
          {items.map((item, index) => <li key={`fact-${index}`}>{item}</li>)}
        </ul>
      )}
    </section>
  );
}

/**
 * One block of the answer. A block is rendered only once the word stream has
 * reached it, so an unrevealed block occupies no layout and contributes no
 * empty container.
 */
function RevealBlock({ children }: { children: ReactNode }) {
  return <div className="answer-block answer-block--revealed">{children}</div>;
}

/** Progressive words of a paragraph. */
function RevealParagraph({ text, visible, className }: { text: string; visible: number; className?: string }) {
  return <p className={className}>{wordPrefix(text, visible)}</p>;
}

/**
 * Distribute a block's visible word budget across list items.
 *
 * Item boundaries are preserved: an item appears only when the stream reaches
 * it, and fills word by word. A partially filled item is always a literal
 * prefix of its own text -- words are never moved between items.
 */
function revealListItems(items: string[], visible: number): string[] {
  const out: string[] = [];
  let remaining = visible;
  for (const item of items) {
    if (remaining <= 0) break;
    const size = countWords(item);
    out.push(wordPrefix(item, Math.min(remaining, size)));
    remaining -= size;
  }
  return out;
}

interface BlockSpec {
  key: string;
  /** Words this block consumes from the response-wide stream. */
  words: number;
  /** `visible` is the word budget already delivered to THIS block. */
  render: (visible: number) => ReactNode;
}

function FastDemoAnswer({ content, animate, onRevealComplete, onRevealStep }: FastDemoAnswerProps) {
  const knownFacts = content.known_facts ?? [];
  const safeSources = selectSafeSources(content.sources);

  // Block specs in actual display order. A block is added only when present, so
  // a missing block contributes no words and therefore no reveal step.
  const specs: BlockSpec[] = [];

  specs.push({
    key: 'summary',
    words: countWords(content.summary),
    render: (visible) => (
      <RevealParagraph className="answer-summary" text={content.summary} visible={visible} />
    ),
  });

  if (content.analysis) {
    const analysis = content.analysis;
    specs.push({
      key: 'analysis',
      words: countWords(analysis),
      render: (visible) => (
        <section className="answer-section analysis-section">
          <h3>Phân tích sơ bộ</h3>
          <RevealParagraph text={analysis} visible={visible} />
        </section>
      ),
    });
  }

  if (content.clarifying_questions.length > 0) {
    const lead = 'Để tôi hỗ trợ chính xác hơn, bạn cho tôi biết thêm:';
    const items = content.clarifying_questions.map((item, index) => stripRedundantOrdinal(item, index));
    specs.push({
      key: 'clarification',
      words: countWords(lead) + items.reduce((sum, item) => sum + countWords(item), 0),
      render: (visible) => {
        const leadWords = countWords(lead);
        return (
          <section className="answer-section clarification-section">
            <p className="clarification-lead">{wordPrefix(lead, visible)}</p>
            <ol className="clarification-list">
              {revealListItems(items, visible - leadWords).map((item, index) => (
                <li key={`q-${index}`}>{item}</li>
              ))}
            </ol>
          </section>
        );
      },
    });
  }

  if (content.checklist.length > 0) {
    const items = content.checklist;
    specs.push({
      key: 'checklist',
      words: items.reduce((sum, item) => sum + countWords(item), 0),
      render: (visible) => (
        <section className="answer-section checklist-section">
          <h3>Chứng cứ nên chuẩn bị</h3>
          <ul>
            {revealListItems(items, visible).map((item, index) => <li key={`c-${index}`}>{item}</li>)}
          </ul>
        </section>
      ),
    });
  }

  if (content.next_steps.length > 0) {
    const items = content.next_steps.map((item, index) => stripRedundantOrdinal(item, index));
    specs.push({
      key: 'next-steps',
      words: items.reduce((sum, item) => sum + countWords(item), 0),
      render: (visible) => (
        <section className="answer-section next-steps-section">
          <h3>Bước tiếp theo</h3>
          <ol>
            {revealListItems(items, visible).map((item, index) => <li key={`n-${index}`}>{item}</li>)}
          </ol>
        </section>
      ),
    });
  }

  if (content.draft && content.draft.body) {
    const draft = content.draft;
    specs.push({
      key: 'draft',
      words: countWords(draft.body),
      // The heading and the Sao chép control are structural: they render whole
      // when the block starts and are never word-revealed.
      render: (visible) => (
        <DraftCard title={draft.title} body={wordPrefix(draft.body, visible)} />
      ),
    });
  }

  if (knownFacts.length > 0) {
    // A disclosure control, not prose: it appears intact and stays functional.
    specs.push({
      key: 'known-facts',
      words: ATOMIC_BLOCK_WORD_COST,
      render: () => <KnownFacts items={knownFacts} />,
    });
  }

  if (content.uncertainty_notice) {
    const notice = content.uncertainty_notice;
    specs.push({
      key: 'uncertainty',
      words: countWords(notice),
      render: (visible) => (
        <RevealParagraph className="uncertainty-notice" text={notice} visible={visible} />
      ),
    });
  }

  if (safeSources.length > 0) {
    // Links must be complete and clickable the moment they appear, so this
    // block is atomic rather than word-revealed.
    specs.push({
      key: 'sources',
      words: ATOMIC_BLOCK_WORD_COST,
      render: () => <SourcePanel sources={content.sources} />,
    });
  }

  const totalWords = specs.reduce((sum, spec) => sum + spec.words, 0);
  const { revealedWords, isRevealing, revealAll } = useWordReveal(totalWords, animate, {
    onStep: onRevealStep,
    onComplete: onRevealComplete,
  });

  // Walk the specs, handing each its slice of the stream. A block starts only
  // after every earlier block has consumed its full word count.
  let consumed = 0;
  const rendered: ReactNode[] = [];
  for (const spec of specs) {
    const visible = revealedWords - consumed;
    if (visible <= 0) break;
    rendered.push(
      <RevealBlock key={spec.key}>{spec.render(Math.min(visible, spec.words))}</RevealBlock>,
    );
    consumed += spec.words;
  }

  return (
    <div className="structured-answer structured-answer--fast-demo">
      {isRevealing && (
        <button
          className="answer-reveal-skip"
          type="button"
          onClick={revealAll}
          aria-label="Hiển thị toàn bộ phản hồi ngay"
        >
          Hiện ngay
        </button>
      )}
      {rendered}
    </div>
  );
}
