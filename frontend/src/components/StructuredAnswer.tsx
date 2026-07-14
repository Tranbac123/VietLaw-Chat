import { useEffect, useMemo, useRef, useState } from 'react';
import type { AnalyzeContent } from '../api/types';
import {
  getAdaptiveTypewriterTiming,
  LIST_ITEM_REVEAL_MS,
  segmentGraphemes,
} from '../lib/animation';
import { formatDomain } from '../lib/format';
import { DecisionBadge } from './DecisionBadge';
import { RiskBadge } from './RiskBadge';
import { SafetyNotice } from './SafetyNotice';
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
        ...content.clarifying_questions.map((_, index) => () => {
          setRevealState((current) => ({ ...current, clarifyingCount: index + 1 }));
        }),
        ...content.checklist.map((_, index) => () => {
          setRevealState((current) => ({ ...current, checklistCount: index + 1 }));
        }),
        ...content.next_steps.map((_, index) => () => {
          setRevealState((current) => ({ ...current, nextStepsCount: index + 1 }));
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
  }, [animate, content, summaryGraphemes.length, typewriterTiming.charsPerSecond]);

  const visibleSummary = summaryGraphemes.slice(0, revealState.summaryLength).join('');
  const animateItems = isRevealing && !prefersReducedMotion();

  return (
    <div className="structured-answer">
      <div className="answer-badges" aria-label="Phân loại phản hồi">
        <span className={`badge domain-badge domain-${content.domain}`}>{formatDomain(content.domain)}</span>
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

      <section className="answer-summary">
        <h2>Tóm tắt ban đầu</h2>
        <p>
          {visibleSummary}
          {isRevealing && revealState.summaryLength < summaryGraphemes.length && (
            <span className="typewriter-cursor" aria-hidden="true">▍</span>
          )}
        </p>
      </section>

      <AnswerList
        title="Câu hỏi cần làm rõ"
        items={content.clarifying_questions}
        visibleCount={revealState.clarifyingCount}
        animateItems={animateItems}
      />
      <AnswerList
        title="Checklist giấy tờ"
        items={content.checklist}
        visibleCount={revealState.checklistCount}
        animateItems={animateItems}
      />
      <AnswerList
        title="Bước tiếp theo an toàn"
        items={content.next_steps}
        visibleCount={revealState.nextStepsCount}
        animateItems={animateItems}
      />
      {revealState.showSources && <SourcePanel sources={content.sources} />}
      {revealState.showSafetyNotice && <SafetyNotice notice={content.safety_notice} />}
    </div>
  );
}
