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
  MAX_TOTAL_REVEAL_MS,
  WORD_INTERVAL_MS,
  countWords,
  wordsPerTick,
} from '../lib/reveal';
import {
  apiMocks,
  assistantBubbles,
  composerTextarea,
  countUserMessagesWithText,
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

  it('adapts words per tick so a long answer stays bounded', () => {
    expect(wordsPerTick(50)).toBe(1);
    expect(wordsPerTick(200)).toBe(2);
    expect(wordsPerTick(400)).toBe(3);

    // The declared budget is the invariant, not a hard-coded number: whatever
    // WORD_INTERVAL_MS / MAX_TOTAL_REVEAL_MS are set to, no length may exceed it.
    for (const words of [50, 120, 202, 300, 400, 900, 2_000]) {
      const duration = (words / wordsPerTick(words)) * WORD_INTERVAL_MS;
      expect(duration).toBeLessThanOrEqual(MAX_TOTAL_REVEAL_MS);
    }
  });

  it('reveals the ~202-word fixture answer at the intended demo pace', () => {
    // The owner tunes this by feel in the browser; the range is asserted here so
    // a later timing change cannot drift it silently.
    const seconds = (202 / wordsPerTick(202)) * WORD_INTERVAL_MS / 1000;
    expect(seconds).toBeGreaterThanOrEqual(3.3);
    expect(seconds).toBeLessThanOrEqual(3.8);
  });

  it('counts words rather than characters', () => {
    expect(countWords('một hai ba')).toBe(3);
    expect(countWords('')).toBe(0);
  });
});

// ---------------------------------------------------------------------------
// Immediate responses
// ---------------------------------------------------------------------------

describe('responses that are never word-revealed', () => {
  it.each([
    ['social', 'Xin chào!'],
    ['capability', 'Tôi có thể giúp bạn về tiền cọc.'],
  ] as const)('shows a %s response immediately', async (kind, summary) => {
    const { analyze } = apiMocks();
    analyze.mockResolvedValue(makeNonLegalResponse(kind, summary));

    const { user } = renderApp();
    await waitForComposerReady();
    await sendViaControls(user, 'xin chào');

    await waitForAssistantText(summary);
    expect(appBlocks()).toHaveLength(0);
    await waitForComposerReady();
  });

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
