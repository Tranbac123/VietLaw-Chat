import { useEffect, useRef, useState } from 'react';

/**
 * Simulated word-by-word reveal for structured Fast Demo legal answers.
 *
 * NOT provider streaming. The complete backend response has already arrived and
 * been persisted before a single word is shown; this only decides when existing
 * text becomes visible. There is no SSE, no WebSocket and no incremental
 * persistence anywhere in this path.
 *
 * There is exactly ONE reveal controller. The old character typewriter and the
 * earlier complete-block staging are both gone for this response kind: running
 * two of them concurrently is what made the reveal unreadable.
 *
 * Nothing here participates in the request lifecycle. The composer, Send,
 * idempotency and persistence are all settled before a reveal starts, so even a
 * permanently stuck reveal cannot disable Send or block the next submission.
 */

/**
 * Tick interval. One tick emits `wordsPerTick` words.
 *
 * 28 ms read as slightly too fast in the browser; 34 ms puts a ~200-word answer
 * at roughly 3.4 s, which is the intended demo pace.
 */
export const WORD_INTERVAL_MS = 34;
/** Upper bound on a whole sequence, so a long answer never crawls. */
export const MAX_TOTAL_REVEAL_MS = 6_500;
/** Word-count thresholds for the adaptive rate. */
export const SHORT_RESPONSE_WORDS = 120;
export const MEDIUM_RESPONSE_WORDS = 300;
/** Nominal word cost for a block that must appear intact (links, controls). */
export const ATOMIC_BLOCK_WORD_COST = 2;

export function prefersReducedMotion(): boolean {
  return typeof window !== 'undefined'
    && typeof window.matchMedia === 'function'
    && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
}

/**
 * Words per tick, chosen from total length.
 *
 * Short answers emit one word at a time so the generation effect is visible;
 * longer ones emit two or three so a big legal answer finishes in seconds
 * rather than tens of seconds. Never character-by-character.
 */
export function wordsPerTick(totalWords: number): number {
  const byLength = totalWords <= SHORT_RESPONSE_WORDS
    ? 1
    : totalWords <= MEDIUM_RESPONSE_WORDS ? 2 : 3;
  // Hard ceiling on the whole sequence. For an unusually long answer this wins
  // over the length band, so the reveal cannot drift into tens of seconds.
  const byBudget = Math.ceil((totalWords * WORD_INTERVAL_MS) / MAX_TOTAL_REVEAL_MS);
  return Math.max(1, byLength, byBudget);
}

/**
 * Split into whitespace-delimited words, keeping punctuation attached to its
 * word and preserving the original separators so a partial render is always a
 * literal prefix of the source text. Vietnamese diacritics are untouched: this
 * never splits inside a word.
 */
export function splitWords(text: string): string[] {
  return text.length === 0 ? [] : text.split(/(?<=\s)/);
}

export function countWords(text: string): number {
  return splitWords(text).length;
}

/** The first `count` words of `text`, trimmed of the trailing separator. */
export function wordPrefix(text: string, count: number): string {
  if (count <= 0) return '';
  const words = splitWords(text);
  if (count >= words.length) return text;
  return words.slice(0, count).join('').replace(/\s+$/, '');
}

export interface WordReveal {
  /** How many words of the whole response are currently visible. */
  revealedWords: number;
  /** True while words are still being emitted. */
  isRevealing: boolean;
  /** Show everything now. Safe at any time. */
  revealAll: () => void;
}

export interface WordRevealOptions {
  onStep?: () => void;
  onComplete?: () => void;
}

/**
 * Emit `totalWords` words over time.
 *
 * When `animate` is false or reduced motion is requested, everything is visible
 * synchronously from the first render and **no timer is scheduled at all** — so
 * there is never pending work for a page or a test to wait on.
 */
export function useWordReveal(
  totalWords: number,
  animate: boolean,
  { onStep, onComplete }: WordRevealOptions = {},
): WordReveal {
  const total = Math.max(totalWords, 0);
  const reduced = prefersReducedMotion();
  const staged = animate && !reduced && total > 1;

  const [revealedWords, setRevealedWords] = useState(() => (staged ? 1 : total));
  // Once fully revealed the response stays revealed for the life of this
  // mounted component: re-renders, resizes and disclosure toggles never replay.
  const completedRef = useRef(!staged);
  const notifiedRef = useRef(false);
  const onStepRef = useRef(onStep);
  const onCompleteRef = useRef(onComplete);
  onStepRef.current = onStep;
  onCompleteRef.current = onComplete;

  const notifyComplete = () => {
    if (notifiedRef.current) return;
    notifiedRef.current = true;
    onCompleteRef.current?.();
  };

  useEffect(() => {
    if (!staged || completedRef.current) {
      completedRef.current = true;
      setRevealedWords(total);
      notifyComplete();
      return undefined;
    }

    const step = wordsPerTick(total);
    const interval = setInterval(() => {
      setRevealedWords((current) => {
        const next = Math.min(current + step, total);
        if (next >= total) {
          clearInterval(interval);
          completedRef.current = true;
          notifyComplete();
        }
        return next;
      });
      onStepRef.current?.();
    }, WORD_INTERVAL_MS);

    // Cancellation on unmount, chat switch or a newer response: no timer may
    // outlive the component and write into another chat's UI.
    return () => clearInterval(interval);
  }, [staged, total]);

  return {
    revealedWords: staged ? revealedWords : total,
    isRevealing: staged && revealedWords < total,
    revealAll: () => {
      completedRef.current = true;
      setRevealedWords(total);
      notifyComplete();
    },
  };
}
