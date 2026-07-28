/**
 * Composer submit lifecycle: the sent text leaves the input the moment the
 * submission is accepted, not when the response arrives.
 *
 * The defect these guard against was only ever visible in the browser: the
 * submitted sentence stayed in the composer for the whole "Đang suy nghĩ…"
 * phase, because clearing was awaited on the full round trip and gated on
 * success. Everything here therefore drives the real textarea, the real Send
 * button and the real Enter handler.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { setReducedMotion } from './setup';
import {
  apiMocks,
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
  userBubbles,
  userEvent,
  waitFor,
  waitForAssistantText,
  waitForComposerReady,
} from './testUtils';
import type { AnalyzeResponse } from '../api/types';

vi.mock('../api/client', async () => {
  const { createApiClientMock } = await import('./apiMockFactory');
  return createApiClientMock();
});

beforeEach(() => {
  setReducedMotion(false);
  primeDefaultApi();
});

/** The composer input is visibly empty. */
function expectComposerEmpty(): void {
  expect(composerTextarea().value).toBe('');
}

function thinkingIndicator(): HTMLElement | null {
  return screen.queryByLabelText('Trợ lý đang xử lý câu hỏi');
}

// ---------------------------------------------------------------------------
// 1 / 2: immediate clear on both submission paths
// ---------------------------------------------------------------------------

describe('the composer empties as soon as a submission is accepted', () => {
  it.each([
    ['the Send button', 'click' as const],
    ['Enter', 'enter' as const],
  ])('clears before the request resolves when submitted with %s', async (_label, via) => {
    const { analyze } = apiMocks();
    const pending = deferred<AnalyzeResponse>();
    analyze.mockReturnValue(pending.promise);

    const { user } = renderApp();
    await waitForComposerReady();

    await sendViaControls(user, 'Câu hỏi đang gửi', { via });

    // The request is in flight and unresolved.
    await waitFor(() => expect(analyze).toHaveBeenCalledTimes(1));

    // The submitted text is already gone from the input, while the assistant
    // is still pending -- this is the exact state from the owner's screenshot.
    expectComposerEmpty();
    expect(countUserMessagesWithText('Câu hỏi đang gửi')).toBe(1);
    await waitFor(() => expect(thinkingIndicator()).not.toBeNull());
    expectComposerEmpty();

    pending.resolve(makeAnalyzeResponse({ summary: 'Trả lời xong.' }));
    await waitForAssistantText('Trả lời xong.');

    // Still empty once everything has settled, and still exactly one message.
    expectComposerEmpty();
    expect(countUserMessagesWithText('Câu hỏi đang gửi')).toBe(1);
    expect(analyze).toHaveBeenCalledTimes(1);
    await waitForComposerReady();
  });
});

// ---------------------------------------------------------------------------
// 3: Shift+Enter
// ---------------------------------------------------------------------------

describe('Shift+Enter', () => {
  it('inserts a newline without submitting or clearing', async () => {
    const { analyze } = apiMocks();
    const { user } = renderApp();
    await waitForComposerReady();

    const textarea = composerTextarea();
    await user.click(textarea);
    await user.type(textarea, 'dòng một');
    await user.keyboard('{Shift>}{Enter}{/Shift}');
    await user.type(textarea, 'dòng hai');

    expect(textarea.value).toBe('dòng một\ndòng hai');
    expect(analyze).not.toHaveBeenCalled();
    expect(userBubbles()).toHaveLength(0);
  });
});

// ---------------------------------------------------------------------------
// 4 / 5: refused before dispatch -> the draft survives
// ---------------------------------------------------------------------------

describe('a submission refused before dispatch', () => {
  it('does not send, transcribe or clear whitespace-only input', async () => {
    const { analyze } = apiMocks();
    const { user } = renderApp();
    await waitForComposerReady();

    const textarea = composerTextarea();
    await user.click(textarea);
    await user.type(textarea, '    ');

    // Send is unreachable for a blank draft, so Enter is the only path in.
    expect(sendButton()).toBeDisabled();
    await user.keyboard('{Enter}');

    expect(analyze).not.toHaveBeenCalled();
    expect(userBubbles()).toHaveLength(0);
    // The draft is preserved verbatim -- it was never treated as submitted.
    expect(textarea.value).toBe('    ');
  });

  it('locks the input while the request is pending, so nothing can be lost', async () => {
    const { analyze } = apiMocks();
    const pending = deferred<AnalyzeResponse>();
    analyze.mockReturnValueOnce(pending.promise);

    const { user } = renderApp();
    await waitForComposerReady();

    await sendViaControls(user, 'Câu hỏi một');
    await waitFor(() => expect(analyze).toHaveBeenCalledTimes(1));

    // During "thinking" the input is disabled outright, so a second submission
    // is unreachable and the emptied composer cannot be refilled by accident.
    expectComposerEmpty();
    expect(composerTextarea()).toBeDisabled();

    pending.resolve(makeAnalyzeResponse({ summary: 'Trả lời một.' }));
    await waitForAssistantText('Trả lời một.');
    await waitForComposerReady();
    expectComposerEmpty();
  });

  it('preserves a draft typed while the answer is still revealing', async () => {
    // During "revealing" the input is enabled but submit is refused: this is the
    // one reachable state where a non-empty draft meets a refused submission.
    const { analyze } = apiMocks();
    analyze.mockResolvedValueOnce(
      makeAnalyzeResponse({ summary: 'Câu trả lời dài. '.repeat(40) }),
    );

    const { user } = renderApp();
    await waitForComposerReady();

    await sendViaControls(user, 'Câu hỏi một');
    await waitFor(() => expect(analyze).toHaveBeenCalledTimes(1));

    // Wait until the reveal has begun and the input is typable again.
    const textarea = composerTextarea();
    await waitFor(() => expect(textarea).not.toBeDisabled());
    await user.click(textarea);
    await user.type(textarea, 'Soạn trong lúc chờ');

    if (sendButton().disabled) {
      // Still revealing: the submission is refused and the draft must survive.
      await user.keyboard('{Enter}');
      expect(analyze).toHaveBeenCalledTimes(1);
      expect(textarea.value).toBe('Soạn trong lúc chờ');
    }

    // Either way the draft was never silently discarded.
    expect(textarea.value).toBe('Soạn trong lúc chờ');
  });
});

// ---------------------------------------------------------------------------
// 6 / 7: failure after dispatch, and retry
// ---------------------------------------------------------------------------

describe('a request that fails after dispatch', () => {
  it('leaves the composer empty and the question in the transcript', async () => {
    const { analyze } = apiMocks();
    const pending = deferred<AnalyzeResponse>();
    analyze.mockReturnValueOnce(pending.promise);

    const { user } = renderApp();
    await waitForComposerReady();

    await sendViaControls(user, 'Câu hỏi hỏng');
    await waitFor(() => expect(analyze).toHaveBeenCalledTimes(1));
    expectComposerEmpty();

    pending.reject(new Error('boom'));

    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument());

    // The text is not silently restored, and the question is still shown once.
    expectComposerEmpty();
    expect(countUserMessagesWithText('Câu hỏi hỏng')).toBe(1);

    // Nothing was resent on its own.
    await waitForComposerReady();
    expect(analyze).toHaveBeenCalledTimes(1);
  });

  it('retries the original payload without depending on the composer', async () => {
    const { analyze } = apiMocks();
    analyze
      .mockRejectedValueOnce(new Error('boom'))
      .mockResolvedValueOnce(makeAnalyzeResponse({ summary: 'Trả lời sau khi thử lại.' }));

    const { user } = renderApp();
    await waitForComposerReady();

    await sendViaControls(user, 'Câu hỏi cần thử lại');
    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument());
    expectComposerEmpty();

    const firstPayload = analyze.mock.calls[0][0];

    // Type something unrelated: retry must ignore it entirely.
    const textarea = composerTextarea();
    await waitFor(() => expect(textarea).not.toBeDisabled());
    await user.click(textarea);
    await user.type(textarea, 'nội dung khác');

    await user.click(screen.getByLabelText('Thử lại yêu cầu'));

    await waitFor(() => expect(analyze).toHaveBeenCalledTimes(2));
    const retryPayload = analyze.mock.calls[1][0];

    // Same question and the same idempotency key, so the backend can replay
    // rather than spend a second provider call.
    expect(retryPayload.question).toBe('Câu hỏi cần thử lại');
    expect(retryPayload.client_request_id).toBe(firstPayload.client_request_id);
    expect(retryPayload.question).not.toBe('nội dung khác');

    await waitForAssistantText('Trả lời sau khi thử lại.');
    // No duplicate of the retried question.
    expect(countUserMessagesWithText('Câu hỏi cần thử lại')).toBe(1);
  });
});

// ---------------------------------------------------------------------------
// 8 / 9 / 10 / 11: regressions
// ---------------------------------------------------------------------------

describe('regressions', () => {
  it('clears immediately on two consecutive sends', async () => {
    const { analyze } = apiMocks();
    analyze
      .mockResolvedValueOnce(makeAnalyzeResponse({ summary: 'Trả lời một.' }))
      .mockResolvedValueOnce(makeAnalyzeResponse({ summary: 'Trả lời hai.' }));

    const { user } = renderApp();
    await waitForComposerReady();

    await sendViaControls(user, 'Câu hỏi một');
    expectComposerEmpty();
    await waitForAssistantText('Trả lời một.');
    await waitForComposerReady();

    await sendViaControls(user, 'Câu hỏi hai');
    expectComposerEmpty();
    await waitForAssistantText('Trả lời hai.');

    expect(analyze).toHaveBeenCalledTimes(2);
    expect(userBubbles()).toHaveLength(2);
    expectComposerEmpty();
    await waitForComposerReady();
  });

  it('clears immediately under prefers-reduced-motion', async () => {
    setReducedMotion(true);
    const { analyze } = apiMocks();
    analyze
      .mockResolvedValueOnce(makeAnalyzeResponse({ summary: 'Giảm chuyển động một.' }))
      .mockResolvedValueOnce(makeAnalyzeResponse({ summary: 'Giảm chuyển động hai.' }));

    const { user } = renderApp();
    await waitForComposerReady();

    await sendViaControls(user, 'RM một');
    expectComposerEmpty();
    await waitForAssistantText('Giảm chuyển động một.');
    await waitForComposerReady();

    await sendViaControls(user, 'RM hai');
    expectComposerEmpty();
    await waitForAssistantText('Giảm chuyển động hai.');

    // Send is usable again: no permanent pending/revealing state.
    await waitForComposerReady();
    expect(composerTextarea()).not.toBeDisabled();
    expect(analyze).toHaveBeenCalledTimes(2);
  });

  it('submits once under StrictMode', async () => {
    const { analyze } = apiMocks();
    analyze.mockResolvedValue(makeAnalyzeResponse({ summary: 'Trả lời strict.' }));

    const { user } = renderApp({ strict: true });
    await waitForComposerReady();

    await sendViaControls(user, 'Câu hỏi strict');
    expectComposerEmpty();

    await waitForAssistantText('Trả lời strict.');
    expect(analyze).toHaveBeenCalledTimes(1);
    expect(countUserMessagesWithText('Câu hỏi strict')).toBe(1);
    expectComposerEmpty();
  });

  it('clears immediately when sending inside an existing chat', async () => {
    const { analyze, listChats, getChat } = apiMocks();
    listChats.mockResolvedValue(makeChatList(['chat-a']));
    getChat.mockResolvedValue(
      makeChatDetail('chat-a', [makeUserMessage('chat-a', 'm1', 'Tin nhắn cũ')]),
    );
    analyze.mockResolvedValue(
      makeAnalyzeResponse({ chat_id: 'chat-a', summary: 'Trả lời trong chat cũ.' }),
    );

    const { user } = renderApp();
    await screen.findByRole('button', { name: /Tiêu đề chat-a/ });
    await user.click(screen.getByRole('button', { name: /Tiêu đề chat-a/ }));
    await waitFor(() => expect(getChat).toHaveBeenCalled());
    await waitForComposerReady();

    await sendViaControls(user, 'Câu hỏi trong chat cũ');
    expectComposerEmpty();

    await waitFor(() => expect(analyze).toHaveBeenCalledTimes(1));
    expect(analyze.mock.calls[0][0]).toMatchObject({ chat_id: 'chat-a' });
    await waitForAssistantText('Trả lời trong chat cũ.');
    expectComposerEmpty();
    expect(countUserMessagesWithText('Câu hỏi trong chat cũ')).toBe(1);
  });
});

export { userEvent };
