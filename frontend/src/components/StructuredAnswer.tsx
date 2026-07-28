import { useEffect, useMemo, useRef, useState } from 'react';
import type { AnalyzeContent } from '../api/types';
import {
  getAdaptiveTypewriterTiming,
  LIST_ITEM_REVEAL_MS,
  segmentGraphemes,
} from '../lib/animation';
import { formatDomain } from '../lib/format';
import { stripRedundantOrdinal } from '../lib/listText';
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
  const [revealState, setRevealState] = useState(() => (
    initialRevealState(content, animate && !reducedMotion, summaryGraphemes.length)
  ));
  const [isRevealing, setIsRevealing] = useState(animate && !reducedMotion);
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

    if (!animate) {
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
  }, [animate, content, summaryGraphemes.length, typewriterTiming.charsPerSecond, visibleChecklist]);

  const visibleSummary = summaryGraphemes.slice(0, revealState.summaryLength).join('');
  const animateItems = isRevealing && !prefersReducedMotion();

  // Social turns (greeting/identity/capability) are a direct conversational reply, not
  // a legal analysis: no domain/risk/decision badges, no clarification/checklist/next-step
  // sections, no source panel, no legal safety disclaimer -- just the assistant text with
  // the same reveal animation as a normal message. Anything that is not literally
  // response_kind === 'social' (including older persisted messages without the field)
  // falls through to the existing full legal rendering below.
  // Inline literal comparison (not a hoisted boolean) so TypeScript narrows the
  // discriminated union and the code below is known to be the legal variant.
  if (
    content.response_kind === 'social'
    || content.response_kind === 'capability'
    || content.response_kind === 'scope'
  ) {
    return (
      <div className="structured-answer structured-answer--social">
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
        <p className="message-text">
          {visibleSummary}
          {isRevealing && revealState.summaryLength < summaryGraphemes.length && (
            <span className="typewriter-cursor" aria-hidden="true">▍</span>
          )}
        </p>
      </div>
    );
  }

  // FAST DEMO V2 legal rendering. The fast-demo backend owns block selection,
  // so the baseline follow-up suppression (which hides checklist/sources on any
  // turn that used chat history) must not apply here.
  if (content.metadata?.fast_demo === true) {
    return (
      <FastDemoAnswer
        content={content}
        visibleSummary={visibleSummary}
        isRevealing={isRevealing}
        showCursor={isRevealing && revealState.summaryLength < summaryGraphemes.length}
        onSkip={() => completeNowRef.current?.()}
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


interface FastDemoAnswerProps {
  content: AnalyzeContent;
  visibleSummary: string;
  isRevealing: boolean;
  showCursor: boolean;
  onSkip: () => void;
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

function FastDemoAnswer({ content, visibleSummary, isRevealing, showCursor, onSkip }: FastDemoAnswerProps) {
  const sources = content.sources;
  const knownFacts = content.known_facts ?? [];

  return (
    <div className="structured-answer structured-answer--fast-demo">
      {isRevealing && (
        <button
          className="answer-reveal-skip"
          type="button"
          onClick={onSkip}
          aria-label="Hiển thị toàn bộ phản hồi ngay"
        >
          Hiện ngay
        </button>
      )}

      <p className="answer-summary">
        {visibleSummary}
        {showCursor && <span className="typewriter-cursor" aria-hidden="true">▍</span>}
      </p>

      {content.analysis && (
        <section className="answer-section analysis-section">
          <h3>Phân tích sơ bộ</h3>
          <p>{content.analysis}</p>
        </section>
      )}

      {content.clarifying_questions.length > 0 && (
        <section className="answer-section clarification-section">
          <p className="clarification-lead">Để tôi hỗ trợ chính xác hơn, bạn cho tôi biết thêm:</p>
          <ol className="clarification-list">
            {content.clarifying_questions.map((item, index) => (
              <li key={`q-${index}`}>{stripRedundantOrdinal(item, index)}</li>
            ))}
          </ol>
        </section>
      )}

      {content.checklist.length > 0 && (
        <section className="answer-section checklist-section">
          <h3>Chứng cứ nên chuẩn bị</h3>
          <ul>
            {content.checklist.map((item, index) => <li key={`c-${index}`}>{item}</li>)}
          </ul>
        </section>
      )}

      {content.next_steps.length > 0 && (
        <section className="answer-section next-steps-section">
          <h3>Bước tiếp theo</h3>
          <ol>
            {content.next_steps.map((item, index) => (
              <li key={`n-${index}`}>{stripRedundantOrdinal(item, index)}</li>
            ))}
          </ol>
        </section>
      )}

      {content.draft && content.draft.body && (
        <DraftCard title={content.draft.title} body={content.draft.body} />
      )}

      <KnownFacts items={knownFacts} />

      {content.uncertainty_notice && (
        <p className="uncertainty-notice">{content.uncertainty_notice}</p>
      )}

      {/* No valid sources -> no panel at all, never empty-source boilerplate.
          SourcePanel validates, so an array of unsafe URLs also renders nothing. */}
      <SourcePanel sources={sources} />
    </div>
  );
}
