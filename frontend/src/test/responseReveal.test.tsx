/**
 * Phase C: simulated word-by-word reveal for structured Fast Demo answers.
 *
 * This is NOT provider streaming: the complete response has already arrived and
 * been persisted before the first word is shown. There is exactly one reveal
 * controller — no character typewriter, no separate block-staging timer.
 *
 * The assertions fall into two groups: what the user sees (word order, block
 * sequencing, intact controls), and what the reveal must never touch (Send, the
 * composer, the next submission, another chat). The second group matters more:
 * an earlier version of this UI gated the composer on a `revealing` phase and
 * left Send permanently disabled.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, render } from '@testing-library/react';
import { setReducedMotion } from './setup';
import { StructuredAnswer } from '../components/StructuredAnswer';
import {
  MAX_TIMER_TICKS,
  MAX_TOTAL_REVEAL_MS,
  MIN_TIMER_TICKS,
  SHORT_RESPONSE_MIN_REVEAL_MS,
  WORD_INTERVAL_MS,
  actualRevealDurationMs,
  countWords,
  effectiveWordsPerTick,
  lengthBandWordsPerTick,
  requiredTickCount,
  wordsAfterTick,
} from '../lib/reveal';
import {
  apiMocks,
  assistantBubbles,
  composerTextarea,
  countUserMessagesWithText,
  deferred,
  makeAnalyzeResponse,
  makeChatDetail,
  makeChatList,
  makeUserMessage,
  primeDefaultApi,
  renderApp,
  screen,
  sendButton,
  sendViaControls,
  waitFor,
  waitForAssistantText,
  waitForComposerReady,
} from './testUtils';
import type {
  AnalyzeContent,
  AnalyzeResponse,
  LegalAnalyzeResponse,
  SocialAnalyzeResponse,
} from '../api/types';

vi.mock('../api/client', async () => {
  const { createApiClientMock } = await import('./apiMockFactory');
  return createApiClientMock();
});

beforeEach(() => {
  setReducedMotion(false);
  primeDefaultApi();
});

const SUMMARY = 'Theo thông tin bạn cung cấp, khoản tiền đặt cọc đang là vấn đề trung tâm.';
const ANALYSIS = 'Đặt cọc là biện pháp bảo đảm giao kết hợp đồng.';
const SAFE_SOURCE = {
  id: 's1', title: 'Điều 328', source_name: 'Bộ luật Dân sự',
  url: 'https://example.org/dieu-328', snippet: 'trích dẫn',
  source_type: 'official_source' as const, last_checked: '2026-01-01',
};

/** A fast-demo legal response: the branch that word-reveals. */
function makeLegalResponse(overrides: Partial<LegalAnalyzeResponse> = {}): AnalyzeResponse {
  const base = makeAnalyzeResponse({ summary: SUMMARY, ...overrides }) as LegalAnalyzeResponse;
  return { ...base, metadata: { fast_demo: true, ...(overrides.metadata ?? {}) } } as AnalyzeResponse;
}

function makeRichResponse(overrides: Partial<LegalAnalyzeResponse> = {}): AnalyzeResponse {
  return makeLegalResponse({
    summary: SUMMARY,
    analysis: ANALYSIS,
    clarifying_questions: ['Bạn đã được bàn giao nhà chưa?', 'Có thỏa thuận bằng văn bản không?'],
    checklist: ['Sao kê chuyển khoản', 'Tin nhắn trao đổi'],
    next_steps: ['Giữ lại chứng từ', 'Gửi yêu cầu bằng văn bản'],
    known_facts: ['Số tiền đặt cọc: 20.000.000 đồng'],
    uncertainty_notice: 'Một số thông tin còn thiếu.',
    ...overrides,
  });
}

let socialCounter = 0;

function makeNonLegalResponse(kind: 'social' | 'capability', summary: string): AnalyzeResponse {
  socialCounter += 1;
  return {
    contract_version: '1.0',
    request_id: `req-${kind}-${socialCounter}`,
    chat_id: `chat-${kind}-${socialCounter}`,
    user_message_id: `srv-user-${kind}-${socialCounter}`,
    assistant_message_id: `srv-asst-${kind}-${socialCounter}`,
    response_kind: kind,
    domain: null, risk_level: null, decision: null, confidence: null,
    summary,
    clarifying_questions: [], checklist: [], next_steps: [], sources: [],
    safety_notice: '', metadata: {},
  } as unknown as SocialAnalyzeResponse;
}

function contentFrom(response: AnalyzeResponse): AnalyzeContent {
  const legal = response as LegalAnalyzeResponse;
  return {
    response_kind: 'legal',
    domain: legal.domain, risk_level: legal.risk_level, decision: legal.decision,
    confidence: legal.confidence,
    summary: legal.summary,
    clarifying_questions: legal.clarifying_questions,
    checklist: legal.checklist,
    next_steps: legal.next_steps,
    sources: legal.sources,
    safety_notice: legal.safety_notice,
    metadata: legal.metadata,
    analysis: legal.analysis ?? null,
    draft: legal.draft ?? null,
    known_facts: legal.known_facts ?? [],
    uncertainty_notice: legal.uncertainty_notice ?? null,
  } as AnalyzeContent;
}

function renderAnswer(response: AnalyzeResponse) {
  return render(<StructuredAnswer content={contentFrom(response)} animate />);
}

/** Blocks currently present. An unstarted block renders nothing at all. */
function blocksIn(container: HTMLElement): HTMLElement[] {
  return Array.from(container.querySelectorAll('.answer-block')) as HTMLElement[];
}

function summaryTextIn(container: HTMLElement): string {
  return container.querySelector('.answer-summary')?.textContent ?? '';
}

/** Advance one reveal tick. */
function tick(times = 1): void {
  act(() => { vi.advanceTimersByTime(WORD_INTERVAL_MS * times); });
}

/** Blocks of the newest assistant answer in the App-level tests. */
function appBlocks(): HTMLElement[] {
  const bubbles = assistantBubbles();
  const latest = bubbles[bubbles.length - 1];
  return latest ? Array.from(latest.querySelectorAll('.answer-block')) as HTMLElement[] : [];
}

// ---------------------------------------------------------------------------
// Word-level reveal, driven by a controlled clock
// ---------------------------------------------------------------------------

describe('word-by-word reveal', () => {
  beforeEach(() => { vi.useFakeTimers(); });
  afterEach(() => {
    cleanup();
    // Requirement 17: nothing may remain scheduled once the tree is gone.
    expect(vi.getTimerCount()).toBe(0);
    vi.useRealTimers();
  });

  it('does not show the complete summary on the first paint', () => {
    const { container } = renderAnswer(makeRichResponse());
    const shown = summaryTextIn(container);

    expect(shown.length).toBeGreaterThan(0);
    expect(shown).not.toBe(SUMMARY);
    expect(SUMMARY.startsWith(shown)).toBe(true);
  });

  it('reveals the summary progressively, in original word order', () => {
    const { container } = renderAnswer(makeRichResponse());

    let previous = summaryTextIn(container);
    let grew = 0;
    for (let step = 0; step < 40 && summaryTextIn(container) !== SUMMARY; step += 1) {
      tick();
      const now = summaryTextIn(container);
      // Every intermediate state is a literal prefix of the source text, so
      // words can only be appended and never reordered or mutated.
      expect(SUMMARY.startsWith(now)).toBe(true);
      expect(now.length).toBeGreaterThanOrEqual(previous.length);
      if (now.length > previous.length) grew += 1;
      previous = now;
    }

    // It genuinely arrived in several steps rather than one jump.
    expect(grew).toBeGreaterThan(2);
    expect(summaryTextIn(container)).toBe(SUMMARY);
  });

  it('keeps Vietnamese diacritics and punctuation intact at every step', () => {
    const { container } = renderAnswer(makeRichResponse());

    for (let step = 0; step < 40; step += 1) {
      const shown = summaryTextIn(container);
      // A prefix never splits inside a word, so no partial grapheme can appear.
      if (shown && shown !== SUMMARY) {
        expect(SUMMARY.startsWith(shown)).toBe(true);
        expect(shown.endsWith('�')).toBe(false);
      }
      tick();
    }
    expect(summaryTextIn(container)).toBe(SUMMARY);
    expect(summaryTextIn(container)).toContain('đặt cọc');
    expect(summaryTextIn(container)).toContain('.');
  });

  it('does not start a block before the previous block finishes', () => {
    const { container } = renderAnswer(makeRichResponse());

    // While the summary is incomplete, no second block exists at all.
    while (summaryTextIn(container) !== SUMMARY) {
      expect(blocksIn(container)).toHaveLength(1);
      tick();
    }

    // The analysis block only appears after the summary is whole.
    while (blocksIn(container).length < 2) tick();
    expect(summaryTextIn(container)).toBe(SUMMARY);
    expect(container.querySelector('.analysis-section')).not.toBeNull();
  });

  it('retains list item boundaries while a list reveals', () => {
    const { container } = renderAnswer(makeRichResponse());
    const items = ['Giữ lại chứng từ', 'Gửi yêu cầu bằng văn bản'];

    let sawPartialList = false;
    for (let step = 0; step < 400; step += 1) {
      const list = container.querySelector('.next-steps-section ol');
      if (list) {
        const rendered = Array.from(list.querySelectorAll('li')).map((li) => li.textContent ?? '');
        // Each rendered item is a prefix of its OWN source item: words are
        // never carried across an item boundary.
        rendered.forEach((text, index) => {
          expect(items[index].startsWith(text)).toBe(true);
        });
        if (rendered.length > 0 && rendered.length < items.length) sawPartialList = true;
        if (rendered.length === items.length && rendered[1] === items[1]) break;
      }
      tick();
    }
    expect(sawPartialList).toBe(true);
  });

  it('adds no word sequence for a missing block', () => {
    const withAnalysis = renderAnswer(makeRichResponse());
    act(() => { vi.advanceTimersByTime(30_000); });
    const withCount = blocksIn(withAnalysis.container).length;
    cleanup();

    const without = renderAnswer(makeRichResponse({ analysis: null }));
    act(() => { vi.advanceTimersByTime(30_000); });
    expect(blocksIn(without.container).length).toBe(withCount - 1);
    expect(without.container.querySelector('.analysis-section')).toBeNull();
  });

  it('renders the source link as one intact clickable control at its step', () => {
    const { container } = renderAnswer(makeRichResponse({ sources: [SAFE_SOURCE] }));

    // Nothing partial: the link is absent until its step, then whole.
    act(() => { vi.advanceTimersByTime(30_000); });
    const link = container.querySelector('a[href="https://example.org/dieu-328"]');
    expect(link).not.toBeNull();
    expect(link?.textContent).toBe('Nguồn tham khảo');
  });

  it('keeps the copy control intact and never word-revealed', () => {
    const { container } = renderAnswer(
      makeRichResponse({ draft: { title: 'Tin nhắn gửi chủ nhà', body: 'Kính gửi anh chị, tôi đề nghị hoàn trả tiền cọc.' } }),
    );

    for (let step = 0; step < 400; step += 1) {
      const button = container.querySelector('.draft-copy-button');
      if (button) {
        // The label is structural: it is complete the moment it exists.
        expect(button.textContent).toBe('Sao chép');
        break;
      }
      tick();
    }
    expect(container.querySelector('.draft-copy-button')).not.toBeNull();
  });

  it('shows everything immediately under reduced motion with zero timers', () => {
    setReducedMotion(true);
    const { container } = renderAnswer(makeRichResponse({ sources: [SAFE_SOURCE] }));

    expect(summaryTextIn(container)).toBe(SUMMARY);
    expect(container.querySelector('.analysis-section')).not.toBeNull();
    expect(container.querySelector('a[href="https://example.org/dieu-328"]')).not.toBeNull();
    expect(vi.getTimerCount()).toBe(0);
  });

  it('completes a one-word-block answer with no scheduled work', () => {
    const { container } = renderAnswer(makeLegalResponse({ summary: 'Xong' }));
    expect(summaryTextIn(container)).toBe('Xong');
    expect(vi.getTimerCount()).toBe(0);
  });

  it('does not render a source block for an unsafe-only source set', () => {
    const { container } = renderAnswer(
      makeRichResponse({
        sources: [{ ...SAFE_SOURCE, id: 'bad', url: 'javascript:alert(1)' }],
      }),
    );
    act(() => { vi.advanceTimersByTime(30_000); });
    expect(container.textContent ?? '').not.toContain('Nguồn tham khảo');
  });

  // -------------------------------------------------------------------------
  // M-01 correction: the ceiling must be proven with the hook's ACTUAL integer
  // tick semantics, not `(total / step) * interval`. That formula ignores that
  // one word is already visible before the first tick and that a partial tick
  // still costs a full WORD_INTERVAL_MS -- which is exactly why the previously
  // committed formula silently exceeded the ceiling at 2294 words (6528 ms).
  // -------------------------------------------------------------------------

  it('uses the demo-pacing rate for short and medium responses', () => {
    expect(lengthBandWordsPerTick(50)).toBe(1);
    expect(lengthBandWordsPerTick(200)).toBe(2);
    expect(lengthBandWordsPerTick(400)).toBe(3);
  });

  it('the previously committed formula exceeded budget at 2294 words', () => {
    // Documents the exact regression the independent review found, using the
    // HISTORICAL constants that were live at the time (34 ms / 6500 ms) --
    // hardcoded on purpose rather than importing the current `WORD_INTERVAL_MS`
    // / `MAX_TOTAL_REVEAL_MS`, since those have since been retuned (to 50 ms /
    // 8000 ms) for pacing reasons unrelated to this bug. This test's job is to
    // document that the OLD formula broke its OWN contemporary ceiling, not to
    // track whatever the current tuning happens to be.
    //
    // The old `wordsPerTick` computed its budget-derived rate from
    // `totalWords` directly (not from the words actually left to reveal after
    // the already-visible first word), and the naive `(total / step) *
    // interval` continuous formula silently UNDER-counts the real cost versus
    // the hook's actual integer-tick loop, which always rounds a partial tick
    // up to a full interval. Simulating the real loop with the old step
    // formula is what actually reproduces the 6528 ms overrun.
    const HISTORICAL_WORD_INTERVAL_MS = 34;
    const HISTORICAL_MAX_TOTAL_REVEAL_MS = 6500;
    const oldStep = Math.max(
      1, 3,
      Math.ceil((2294 * HISTORICAL_WORD_INTERVAL_MS) / HISTORICAL_MAX_TOTAL_REVEAL_MS),
    );
    let revealed = 1;
    let ticks = 0;
    while (revealed < 2294) {
      revealed = Math.min(revealed + oldStep, 2294);
      ticks += 1;
    }
    const oldDurationMs = ticks * HISTORICAL_WORD_INTERVAL_MS;
    expect(oldDurationMs).toBeGreaterThan(HISTORICAL_MAX_TOTAL_REVEAL_MS);
  });

  it.each([0, 1, 120, 121, 300, 301, 573, 574, 2293, 2294, 2295, 5000])(
    'keeps the actual rendered duration within the ceiling at %i words',
    (words) => {
      const duration = actualRevealDurationMs(words);
      expect(duration).toBeLessThanOrEqual(MAX_TOTAL_REVEAL_MS);
      expect(effectiveWordsPerTick(words)).toBeGreaterThanOrEqual(1);
    },
  );

  it('fails the boundary case that the committed implementation got wrong', () => {
    // 2294 is the first word count where the OLD formula broke the ceiling.
    // The corrected implementation must land at or under it.
    expect(actualRevealDurationMs(2294)).toBeLessThanOrEqual(MAX_TOTAL_REVEAL_MS);
  });

  it('never exceeds the ceiling for any word count in 0..10000', () => {
    let worstCase = 0;
    for (let words = 0; words <= 10_000; words += 1) {
      const duration = actualRevealDurationMs(words);
      if (duration > worstCase) worstCase = duration;
      expect(duration).toBeLessThanOrEqual(MAX_TOTAL_REVEAL_MS);
      expect(effectiveWordsPerTick(words)).toBeGreaterThanOrEqual(1);
    }
    // The ceiling is real, not decorative: something in the range actually
    // gets close to it.
    expect(worstCase).toBeGreaterThan(MAX_TOTAL_REVEAL_MS * 0.9);
  });

  it('the effective rate is not capped at 3 for very long responses', () => {
    // The demo-pacing band tops out at 3, but the budget-driven rate must be
    // free to exceed it -- otherwise the ceiling above could not hold for long
    // answers. 5000 words at a rate capped at 3 would take 5000/3*50 ≈ 83 s.
    expect(effectiveWordsPerTick(5000)).toBeGreaterThan(3);
  });

  it('MAX_TIMER_TICKS is the floor of the ceiling divided by the interval', () => {
    expect(MAX_TIMER_TICKS).toBe(Math.floor(MAX_TOTAL_REVEAL_MS / WORD_INTERVAL_MS));
  });

  it('reveals the ~202-word fixture answer at the AI-like demo pace', () => {
    // Requested range 5.0-5.8 s (the owner considered the prior 3.43 s too
    // fast, reading like a pre-generated answer being flashed). Asserted here
    // so a later timing change cannot drift it silently.
    const seconds = actualRevealDurationMs(202) / 1000;
    expect(seconds).toBeGreaterThanOrEqual(5.0);
    expect(seconds).toBeLessThanOrEqual(5.8);
  });

  // ---------------------------------------------------------------------------
  // Reveal floor: a genuinely short response must still visibly animate.
  // ---------------------------------------------------------------------------

  it('MIN_TIMER_TICKS is the ceiling of the floor divided by the interval', () => {
    expect(MIN_TIMER_TICKS).toBe(Math.ceil(SHORT_RESPONSE_MIN_REVEAL_MS / WORD_INTERVAL_MS));
  });

  it.each([5, 8, 10, 15])(
    'stretches a short %i-word response to at least the reveal floor',
    (words) => {
      const duration = actualRevealDurationMs(words);
      expect(duration).toBeGreaterThanOrEqual(SHORT_RESPONSE_MIN_REVEAL_MS);
      // Nowhere near the imperceptible 100-200 ms a naive 1-word/tick rate
      // would have given a 5-15 word response before the floor existed.
      expect(duration).toBeGreaterThan(200);
    },
  );

  it('spreads a short response across the whole floor rather than padding after full reveal', () => {
    // 5 words, floor = 12 ticks. If words were front-loaded and the remaining
    // ticks were silent padding, revealedWords would already equal the total
    // well before the halfway tick. Even distribution keeps genuine growth
    // happening across the whole window.
    const total = 5;
    const required = requiredTickCount(total);
    const atHalfway = wordsAfterTick(total, Math.floor(required / 2), required);
    const atFull = wordsAfterTick(total, required, required);
    expect(atFull).toBe(total);
    expect(atHalfway).toBeLessThan(total);
  });

  it('counts words rather than characters', () => {
    expect(countWords('một hai ba')).toBe(3);
    expect(countWords('')).toBe(0);
  });
});

// ---------------------------------------------------------------------------
// Immediate responses
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// Universal conversational reveal: PHASE C CORRECTION §2.
//
// Previously, social/capability/scope answers fell through to a branch whose
// `typewriterAnimate` is unconditionally false whenever `metadata.fast_demo`
// is true -- which every Fast Demo response is, social included. So "hello"
// and "bạn là ai" popped in instantly while a rental answer animated: not two
// controllers racing, but one kind of response falling outside the only
// controller entirely. `SocialAnswer` now routes these through the exact same
// `useWordReveal` hook `FastDemoAnswer` uses -- there is still exactly one
// reveal controller, it now simply covers every assistant-generated text
// response instead of only structured legal ones.
// ---------------------------------------------------------------------------

/** The social/capability/scope paragraph's current text, or '' if absent. */
function socialTextIn(): string {
  return document.querySelector('.structured-answer--social .message-text')?.textContent ?? '';
}

describe('conversational assistant text reveals progressively by words', () => {
  it.each([
    ['hello', 'Xin chào! Tôi là VietLaw. Tôi có thể hỗ trợ bạn tìm hiểu và xử lý các tình huống pháp lý.'],
    ['bạn là ai', 'Tôi là VietLaw. Tôi hỗ trợ các tình huống pháp lý trong phạm vi hiện được hỗ trợ.'],
    ['tôi là ai', 'Tôi chưa biết danh tính của bạn. Tôi chỉ biết những thông tin bạn đã chủ động cung cấp.'],
    ['bạn nhớ gì về tôi', 'Tôi chưa ghi nhận thông tin nào về bạn trong cuộc trò chuyện này hiện tại.'],
  ])('reveals the answer to %s progressively, ending exactly at the source text', async (message, fullText) => {
    const { analyze } = apiMocks();
    analyze.mockResolvedValue(makeNonLegalResponse('social', fullText));

    const { user } = renderApp();
    await waitForComposerReady();
    await sendViaControls(user, message);

    // First paint: something appeared, but not yet the whole answer.
    await waitFor(() => expect(socialTextIn().length).toBeGreaterThan(0));
    const firstPaint = socialTextIn();
    expect(firstPaint).not.toBe(fullText);
    expect(fullText.startsWith(firstPaint)).toBe(true);

    // Every subsequent observed state remains an ordered prefix -- proving
    // words are appended, never reordered, and never split mid-word (which
    // would indicate a character-level reveal rather than a word one).
    let previous = firstPaint;
    for (let i = 0; i < 50 && socialTextIn() !== fullText; i += 1) {
      await new Promise((resolve) => setTimeout(resolve, 30));
      const now = socialTextIn();
      expect(fullText.startsWith(now)).toBe(true);
      expect(now.length).toBeGreaterThanOrEqual(previous.length);
      previous = now;
    }

    await waitFor(() => expect(socialTextIn()).toBe(fullText));
    // Composer/Send remain usable throughout and after -- the reveal never
    // touches the send lifecycle, per the existing Phase C guarantee.
    expect(composerTextarea()).not.toBeDisabled();
  });

  it('renders a short conversational answer immediately under reduced motion', async () => {
    setReducedMotion(true);
    const { analyze } = apiMocks();
    const fullText = 'Xin chào! Tôi là VietLaw. Tôi có thể hỗ trợ bạn về các tình huống pháp lý.';
    analyze.mockResolvedValue(makeNonLegalResponse('social', fullText));

    const { user } = renderApp();
    await waitForComposerReady();
    await sendViaControls(user, 'hello');

    await waitFor(() => expect(socialTextIn()).toBe(fullText));
    await waitForComposerReady();
  });

  it('cancels the timer for a conversational answer on chat switch', async () => {
    const { analyze, listChats, getChat } = apiMocks();
    listChats.mockResolvedValue(makeChatList(['chat-social-b']));
    getChat.mockResolvedValue(
      makeChatDetail('chat-social-b', [makeUserMessage('chat-social-b', 'm1', 'Tin nhắn chat B')]),
    );
    const fullText = 'Xin chào! Tôi là VietLaw. Tôi có thể hỗ trợ bạn tìm hiểu các tình huống pháp lý hiện có.';
    analyze.mockResolvedValue({ ...makeNonLegalResponse('social', fullText), chat_id: 'chat-social-a' });

    const { user } = renderApp();
    await waitForComposerReady();
    await sendViaControls(user, 'hello');
    await waitFor(() => expect(socialTextIn().length).toBeGreaterThan(0));
    expect(socialTextIn()).not.toBe(fullText); // genuinely still revealing

    await user.click(await screen.findByRole('button', { name: /Tiêu đề chat-social-b/ }));
    await waitFor(() => expect(getChat).toHaveBeenCalled());
    await new Promise((resolve) => setTimeout(resolve, 400));

    // Chat A's answer is gone entirely -- nothing leaked into chat B, and
    // nothing from the abandoned timer wrote into the new chat's tree.
    expect(document.body.textContent ?? '').not.toContain(fullText);
    expect(socialTextIn()).toBe('');
  });
});

describe('responses that are never word-revealed', () => {
  it('shows a controlled error immediately and keeps the composer usable', async () => {
    const { ApiClientError } = await import('../api/client');
    const { analyze } = apiMocks();
    analyze.mockRejectedValueOnce(
      new (ApiClientError as unknown as new (c: string, m: string, s?: number) => Error)(
        'idempotency_unavailable', 'Hệ thống tạm thời chưa xử lý được yêu cầu này.', 503,
      ),
    );

    const { user } = renderApp();
    await waitForComposerReady();
    await sendViaControls(user, 'câu hỏi lỗi');

    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument());
    expect(appBlocks()).toHaveLength(0);
    await waitForComposerReady();
    expect(composerTextarea()).not.toBeDisabled();
  });
});

// ---------------------------------------------------------------------------
// The reveal never controls the send lifecycle
// ---------------------------------------------------------------------------

describe('send lifecycle is independent of the word reveal', () => {
  it('leaves the composer and Send usable while words are still arriving', async () => {
    const { analyze } = apiMocks();
    analyze.mockResolvedValue(makeRichResponse());

    const { user } = renderApp();
    await waitForComposerReady();
    await sendViaControls(user, 'câu hỏi');

    await waitFor(() => expect(appBlocks().length).toBeGreaterThan(0));
    expect(composerTextarea()).not.toBeDisabled();
    await user.click(composerTextarea());
    await user.type(composerTextarea(), 'x');
    expect(sendButton()).not.toBeDisabled();
  });

  it('accepts a second submission during the reveal', async () => {
    const { analyze } = apiMocks();
    analyze
      .mockResolvedValueOnce(makeRichResponse())
      .mockResolvedValueOnce(makeRichResponse({ summary: 'Câu trả lời hai.' }));

    const { user } = renderApp();
    await waitForComposerReady();
    await sendViaControls(user, 'câu hỏi một');
    await waitFor(() => expect(appBlocks().length).toBeGreaterThan(0));

    await sendViaControls(user, 'câu hỏi hai');
    await waitFor(() => expect(analyze).toHaveBeenCalledTimes(2));
    await waitForAssistantText('Câu trả lời hai.');

    expect(countUserMessagesWithText('câu hỏi một')).toBe(1);
    expect(countUserMessagesWithText('câu hỏi hai')).toBe(1);
    expect(assistantBubbles()).toHaveLength(2);
  });

  it('treats Enter and the Send button identically during a reveal', async () => {
    const { analyze } = apiMocks();
    analyze.mockResolvedValue(makeRichResponse());

    const { user } = renderApp();
    await waitForComposerReady();
    await sendViaControls(user, 'gửi bằng nút');
    await waitFor(() => expect(appBlocks().length).toBeGreaterThan(0));

    await sendViaControls(user, 'gửi bằng enter', { via: 'enter' });
    await waitFor(() => expect(analyze).toHaveBeenCalledTimes(2));
    expect(countUserMessagesWithText('gửi bằng enter')).toBe(1);
  });

  it('never leaves the composer permanently disabled', async () => {
    const { analyze } = apiMocks();
    analyze.mockResolvedValue(makeRichResponse());

    const { user } = renderApp();
    await waitForComposerReady();
    await sendViaControls(user, 'câu hỏi');
    await waitForAssistantText('Một số thông tin còn thiếu.');
    expect(composerTextarea()).not.toBeDisabled();
  });
});

// ---------------------------------------------------------------------------
// Chat navigation and cleanup
// ---------------------------------------------------------------------------

describe('chat navigation and cleanup', () => {
  it('cancels the reveal on unmount without a state-update warning', async () => {
    const warn = vi.spyOn(console, 'error').mockImplementation(() => {});
    const { analyze } = apiMocks();
    analyze.mockResolvedValue(makeRichResponse());

    const { user } = renderApp();
    await waitForComposerReady();
    await sendViaControls(user, 'câu hỏi');
    await waitFor(() => expect(appBlocks().length).toBeGreaterThan(0));

    cleanup();
    await new Promise((resolve) => setTimeout(resolve, 400));

    const messages = warn.mock.calls.map((call) => String(call[0] ?? ''));
    expect(messages.some((m) => m.includes('not wrapped in act'))).toBe(false);
    expect(messages.some((m) => m.includes('unmounted component'))).toBe(false);
    warn.mockRestore();
  });

  it('does not leak a reveal into a newly opened chat', async () => {
    const { analyze, listChats, getChat } = apiMocks();
    listChats.mockResolvedValue(makeChatList(['chat-b']));
    getChat.mockResolvedValue(
      makeChatDetail('chat-b', [makeUserMessage('chat-b', 'm1', 'Tin nhắn chat B')]),
    );
    analyze.mockResolvedValue(makeRichResponse({ chat_id: 'chat-a', summary: 'Của chat A.' }));

    const { user } = renderApp();
    await waitForComposerReady();
    await sendViaControls(user, 'câu hỏi chat A');
    await waitFor(() => expect(appBlocks().length).toBeGreaterThan(0));

    await user.click(await screen.findByRole('button', { name: /Tiêu đề chat-b/ }));
    await waitFor(() => expect(getChat).toHaveBeenCalled());
    await new Promise((resolve) => setTimeout(resolve, 400));

    expect(document.body.textContent ?? '').not.toContain('Của chat A.');
    expect(assistantBubbles()).toHaveLength(0);
  });

  it('renders a reopened chat fully without replaying the reveal', async () => {
    const { listChats, getChat } = apiMocks();
    listChats.mockResolvedValue(makeChatList(['chat-old']));
    getChat.mockResolvedValue(
      makeChatDetail('chat-old', [
        makeUserMessage('chat-old', 'm1', 'Câu hỏi cũ'),
        {
          message_id: 'm2', chat_id: 'chat-old', role: 'assistant',
          content_type: 'structured', content_text: null,
          content_json: contentFrom(makeRichResponse({ summary: 'Đã lưu đầy đủ.' })),
          created_at: '2026-01-01T00:00:00Z',
        },
      ]),
    );

    const { user } = renderApp();
    await user.click(await screen.findByRole('button', { name: /Tiêu đề chat-old/ }));
    await waitFor(() => expect(getChat).toHaveBeenCalled());

    // A persisted answer is not "newly received": complete on first paint.
    await waitForAssistantText('Đã lưu đầy đủ.');
    const bubble = assistantBubbles()[0];
    expect(bubble.textContent).toContain('Một số thông tin còn thiếu.');
    expect(bubble.querySelector('.analysis-section')).not.toBeNull();
  });
});

// ---------------------------------------------------------------------------
// L-01 correction: the previous reveal must retire the instant a new
// submission is ACCEPTED, not when the new response eventually arrives.
//
// The committed version only updated `animatingAssistantMessageId` after the
// second response was received, so response A kept its own word-reveal timer
// running for the entire "thinking" phase of B -- silently, since visually A
// looked like it was still (correctly) revealing. The "Hiện ngay" skip control
// is rendered only while a response's own `isRevealing` is true, so its
// presence/absence is used here as the black-box signal for "is this
// response's reveal still running" without reaching into React internals.
// ---------------------------------------------------------------------------

function skipButtonIn(bubble: HTMLElement): HTMLElement | null {
  return bubble.querySelector('.answer-reveal-skip');
}

describe('the previous reveal is retired the instant a new submission is accepted', () => {
  it('makes A fully visible before B resolves, and only B reveals afterward', async () => {
    const { analyze } = apiMocks();
    const pendingB = deferred<AnalyzeResponse>();
    analyze
      .mockResolvedValueOnce(makeRichResponse({ summary: 'Câu trả lời A.' }))
      .mockReturnValueOnce(pendingB.promise);

    const { user } = renderApp();
    await waitForComposerReady();
    await sendViaControls(user, 'câu hỏi A');
    await waitForAssistantText('Câu trả lời A.');

    // A must genuinely still be revealing at this point, or the test proves
    // nothing: assert the skip control -- and therefore `isRevealing` -- is
    // still present immediately after A's first word appears.
    const bubbleA = assistantBubbles()[0];
    expect(skipButtonIn(bubbleA)).not.toBeNull();
    const partialBlockCount = bubbleA.querySelectorAll('.answer-block').length;

    // Submit B while A is still mid-reveal.
    await sendViaControls(user, 'câu hỏi B');

    // --- Before B resolves ---
    // A is fully visible: its own skip control is gone (isRevealing = false,
    // which the component only sets once every block has fully arrived), its
    // block count only grew, and the LAST block's complete text (the
    // uncertainty notice) is present -- not a partial prefix of it, the whole
    // sentence, which is only possible once every earlier block finished too.
    expect(skipButtonIn(bubbleA)).toBeNull();
    expect(bubbleA.querySelectorAll('.answer-block').length).toBeGreaterThanOrEqual(partialBlockCount);
    expect(bubbleA.textContent).toContain('Câu trả lời A.');
    expect(bubbleA.textContent).toContain('Một số thông tin còn thiếu.');

    // Request B is genuinely in flight, and nothing has completed for it yet.
    expect(analyze).toHaveBeenCalledTimes(2);
    expect(assistantBubbles()).toHaveLength(1); // no second answer exists yet
    expect(countUserMessagesWithText('câu hỏi B')).toBe(1);

    // Composer behaves exactly like any other accepted, in-flight request.
    expect(composerTextarea()).toBeDisabled();
    expect(composerTextarea().value).toBe('');

    // --- Resolve B ---
    pendingB.resolve(makeRichResponse({ summary: 'Câu trả lời B.' }));
    await waitForAssistantText('Câu trả lời B.');

    // Only B reveals: A does not reanimate, and there is no duplicate block
    // or wrong-message completion callback touching A's now-settled content.
    expect(skipButtonIn(bubbleA)).toBeNull();
    expect(bubbleA.textContent).toContain('Câu trả lời A.');
    expect(assistantBubbles()).toHaveLength(2);

    const bubbleB = assistantBubbles()[1];
    expect(bubbleB.textContent).toContain('Câu trả lời B.');
  });

  it('does not retire the previous reveal when a submission is rejected', async () => {
    const { analyze } = apiMocks();
    analyze.mockResolvedValueOnce(makeRichResponse({ summary: 'Câu trả lời A.' }));

    const { user } = renderApp();
    await waitForComposerReady();
    await sendViaControls(user, 'câu hỏi A');
    await waitForAssistantText('Câu trả lời A.');

    const bubbleA = assistantBubbles()[0];
    expect(skipButtonIn(bubbleA)).not.toBeNull();

    // Whitespace-only: refused before dispatch, never accepted.
    await user.click(composerTextarea());
    await user.type(composerTextarea(), '    ');
    await user.keyboard('{Enter}');

    // A's reveal is completely unaffected by a submission that never happened.
    expect(analyze).toHaveBeenCalledTimes(1);
    expect(skipButtonIn(bubbleA)).not.toBeNull();
  });
});
