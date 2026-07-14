export const MIN_THINKING_MS = 500;
export const LIST_ITEM_REVEAL_MS = 100;
export const MIN_TYPEWRITER_CHARS_PER_SECOND = 60;
export const MAX_TYPEWRITER_CHARS_PER_SECOND = 240;
export const MAX_TYPEWRITER_DURATION_MS = 7_200;

interface GraphemeSegment {
  segment: string;
}

interface GraphemeSegmenter {
  segment(input: string): Iterable<GraphemeSegment>;
}

interface IntlWithSegmenter {
  Segmenter?: new (
    locales?: string | string[],
    options?: { granularity?: 'grapheme' },
  ) => GraphemeSegmenter;
}

export interface AdaptiveTypewriterTiming {
  charsPerSecond: number;
  durationMs: number;
}

export function segmentGraphemes(text: string): string[] {
  if (typeof Intl !== 'undefined') {
    const Segmenter = (Intl as typeof Intl & IntlWithSegmenter).Segmenter;
    if (Segmenter) {
      return Array.from(new Segmenter('vi', { granularity: 'grapheme' }).segment(text), ({ segment }) => segment);
    }
  }

  return Array.from(text);
}

export function getAdaptiveTypewriterTiming(graphemeCount: number): AdaptiveTypewriterTiming {
  if (graphemeCount <= 0) return { charsPerSecond: MIN_TYPEWRITER_CHARS_PER_SECOND, durationMs: 0 };

  const durationAtMinimumSpeed = (graphemeCount / MIN_TYPEWRITER_CHARS_PER_SECOND) * 1_000;
  const targetDurationMs = Math.min(MAX_TYPEWRITER_DURATION_MS, durationAtMinimumSpeed);
  const charsPerSecond = Math.min(
    MAX_TYPEWRITER_CHARS_PER_SECOND,
    Math.max(MIN_TYPEWRITER_CHARS_PER_SECOND, (graphemeCount / targetDurationMs) * 1_000),
  );

  return {
    charsPerSecond,
    durationMs: Math.ceil((graphemeCount / charsPerSecond) * 1_000),
  };
}
