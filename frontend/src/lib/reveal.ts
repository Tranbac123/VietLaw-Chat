import { useEffect, useRef, useState } from 'react';

/**
 * Simulated word-by-word reveal for assistant-generated text.
 *
 * NOT provider streaming. The complete backend response has already arrived and
 * been persisted before a single word is shown; this only decides when existing
 * text becomes visible. There is no SSE, no WebSocket and no incremental
 * persistence anywhere in this path.
 *
 * There is exactly ONE reveal controller, used for every kind of
 * assistant-generated textual content: structured Fast Demo legal responses,
 * social replies, capability/identity answers, memory-information answers and
 * bounded out-of-scope responses alike (see `SocialAnswer` / `FastDemoAnswer`
 * in `StructuredAnswer.tsx`, both of which call `useWordReveal` and nothing
 * else). The old character typewriter and the earlier complete-block staging
 * are both gone: running more than one presentation timer at once is exactly
 * what made a prior revision's reveal read as arriving all at once, and
 * letting some response kinds skip the controller entirely is what made
 * "hello" / "bạn là ai" appear to pop in instantly while rental answers
 * animated.
 *
 * Nothing here participates in the request lifecycle. The composer, Send,
 * idempotency and persistence are all settled before a reveal starts, so even a
 * permanently stuck reveal cannot disable Send or block the next submission.
 */

/**
 * Tick interval. Words are emitted on an even schedule across however many
 * ticks a response requires (see `requiredTickCount`) -- this is not "N words
 * added every tick".
 *
 * 34 ms (and 28 ms before that) read as too fast for a demo: a ~200-word
 * answer finished in ~3.4 s, which read like a pre-generated answer being
 * flashed rather than something being composed. 50 ms puts the same fixture at
 * ~5.05 s, which is the intended AI-like pace.
 */
export const WORD_INTERVAL_MS = 50;
/** Upper bound on a whole sequence, so a long answer never crawls. */
export const MAX_TOTAL_REVEAL_MS = 8_000;
/**
 * Lower bound on a whole sequence. Without this, a genuinely short answer
 * (5-15 words) finishes in a few hundred milliseconds at the length-band rate
 * of 1 word/tick -- imperceptible as an animation at all. This does not change
 * the per-tick word RATE; it extends the number of ticks a short response is
 * spread across (see `requiredTickCount`), so its words trickle out across the
 * full floor duration instead of appearing instantly and then padding silently
 * after the fact.
 */
export const SHORT_RESPONSE_MIN_REVEAL_MS = 600;
/** Word-count thresholds for the length-band rate (see `lengthBandWordsPerTick`). */
export const SHORT_RESPONSE_WORDS = 120;
export const MEDIUM_RESPONSE_WORDS = 300;
/** Nominal word cost for a block that must appear intact (links, controls). */
export const ATOMIC_BLOCK_WORD_COST = 2;

/**
 * The largest number of ticks a reveal is ever allowed to run.
 *
 * `floor`, not `ceil`: a partial tick still costs a full `WORD_INTERVAL_MS`, so
 * rounding up here would let the sequence exceed the ceiling by one tick.
 */
export const MAX_TIMER_TICKS = Math.floor(MAX_TOTAL_REVEAL_MS / WORD_INTERVAL_MS);
/** The smallest number of ticks a staged reveal is ever allowed to run. */
export const MIN_TIMER_TICKS = Math.ceil(SHORT_RESPONSE_MIN_REVEAL_MS / WORD_INTERVAL_MS);

export function prefersReducedMotion(): boolean {
  return typeof window !== 'undefined'
    && typeof window.matchMedia === 'function'
    && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
}

/**
 * The demo-pacing rate, independent of any duration ceiling: short answers
 * emit one word at a time so the generation effect stays visible; longer ones
 * emit two or three so a big legal answer does not crawl. Never
 * character-by-character.
 */
export function lengthBandWordsPerTick(totalWords: number): number {
  if (totalWords <= SHORT_RESPONSE_WORDS) return 1;
  if (totalWords <= MEDIUM_RESPONSE_WORDS) return 2;
  return 3;
}

/**
 * Words per tick, chosen so the actual rendered duration can never exceed
 * `MAX_TOTAL_REVEAL_MS` -- proven by exhaustive test, not just by construction.
 *
 * This represents the TARGET rate implied by length and by the duration
 * ceiling; it is not necessarily the literal number of words the hook adds on
 * any one tick (see `requiredTickCount` / the even-distribution schedule
 * below), which additionally accounts for the one word already visible before
 * the first tick and for the reveal-floor requirement.
 *
 * `effectiveWordsPerTick` is the larger of the demo-pacing rate
 * (`lengthBandWordsPerTick`, capped at 3 for a natural feel) and whatever rate
 * the remaining word count actually requires to fit inside `MAX_TIMER_TICKS`.
 * For a very long answer the budget-driven rate can exceed 3 -- there is no
 * hidden cap here, only the duration ceiling itself.
 */
export function effectiveWordsPerTick(totalWords: number): number {
  const remaining = Math.max(totalWords - 1, 0);
  const budgetRequiredStep = remaining === 0 ? 1 : Math.ceil(remaining / MAX_TIMER_TICKS);
  return Math.max(lengthBandWordsPerTick(totalWords), budgetRequiredStep);
}

/**
 * The number of ticks a staged reveal of this length actually runs for:
 * whichever is larger of the ticks the word count needs at
 * `effectiveWordsPerTick`, and `MIN_TIMER_TICKS` (the reveal floor). Zero for
 * anything with one word or fewer, since there is nothing to stage.
 */
export function requiredTickCount(totalWords: number): number {
  const remaining = Math.max(totalWords - 1, 0);
  if (remaining === 0) return 0;
  const naturalTicks = Math.ceil(remaining / effectiveWordsPerTick(totalWords));
  return Math.max(naturalTicks, MIN_TIMER_TICKS);
}

/** Actual rendered duration for a response of this length, in milliseconds. */
export function actualRevealDurationMs(totalWords: number): number {
  return requiredTickCount(totalWords) * WORD_INTERVAL_MS;
}

/**
 * How many words should be visible after `ticksElapsed` of `requiredTicks`
 * total ticks, for a response of `totalWords` words.
 *
 * Distributes the words AFTER the first (already visible before tick one)
 * evenly across every tick, rather than adding a fixed count per tick. This is
 * what makes a short, floor-padded reveal (e.g. 5 words spread across the
 * 12-tick/600 ms floor) actually trickle out across the whole window instead
 * of finishing in the first couple of ticks and then sitting complete while
 * silent padding ticks run out the floor -- the latter would satisfy the
 * duration floor numerically while still looking instantaneous.
 */
export function wordsAfterTick(
  totalWords: number,
  ticksElapsed: number,
  requiredTicks: number,
): number {
  if (requiredTicks <= 0) return totalWords;
  const remaining = Math.max(totalWords - 1, 0);
  const revealed = 1 + Math.ceil((ticksElapsed * remaining) / requiredTicks);
  return Math.min(revealed, totalWords);
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

    const requiredTicks = requiredTickCount(total);
    let ticksElapsed = 0;

    const interval = setInterval(() => {
      ticksElapsed += 1;
      setRevealedWords(wordsAfterTick(total, ticksElapsed, requiredTicks));
      onStepRef.current?.();
      if (ticksElapsed >= requiredTicks) {
        clearInterval(interval);
        completedRef.current = true;
        notifyComplete();
      }
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
