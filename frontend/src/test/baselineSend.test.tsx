/**
 * Phase 0 baseline: the non-negotiable send contract.
 *
 * These tests are the safety net every later phase is measured against. They
 * drive the real composer controls (textarea, Send button, Enter handler) and
 * assert user-visible outcomes, because the failures being guarded against
 * have all been "the handler still runs but the UI is stuck".
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { setReducedMotion } from './setup';
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

vi.mock('../api/client', async () => {
  const { createApiClientMock } = await import('./apiMockFactory');
  return createApiClientMock();
});

beforeEach(() => {
  primeDefaultApi();
});

describe('baseline send contract', () => {
  it('sends the first message from a new chat and shows the response', async () => {
    const { analyze } = apiMocks();
    analyze.mockResolvedValue(makeAnalyzeResponse({ summary: 'Trả lời một.' }));

    const { user } = renderApp();
    await waitForComposerReady();

    expect(sendButton()).toBeDisabled();
    await sendViaControls(user, 'Câu hỏi một');

    await waitFor(() => expect(analyze).toHaveBeenCalledTimes(1));
    expect(countUserMessagesWithText('Câu hỏi một')).toBe(1);
    await waitForAssistantText('Trả lời một.');
  });

  it('sends a second consecutive message without remounting', async () => {
    const { analyze } = apiMocks();
    analyze
      .mockResolvedValueOnce(makeAnalyzeResponse({ chat_id: 'chat-a', summary: 'Trả lời một.' }))
      .mockResolvedValueOnce(makeAnalyzeResponse({ chat_id: 'chat-a', summary: 'Trả lời hai.' }));

    const { user } = renderApp();
    await waitForComposerReady();

    await sendViaControls(user, 'Câu hỏi một');
    await waitForAssistantText('Trả lời một.');

    await waitForComposerReady();
    await sendViaControls(user, 'Câu hỏi hai');

    await waitFor(() => expect(analyze).toHaveBeenCalledTimes(2));
    await waitForAssistantText('Trả lời hai.');
    expect(countUserMessagesWithText('Câu hỏi hai')).toBe(1);
  });

  it('submits exactly once with Enter and keeps Shift+Enter as a newline', async () => {
    const { analyze } = apiMocks();
    analyze.mockResolvedValue(makeAnalyzeResponse({ summary: 'Trả lời enter.' }));

    const { user } = renderApp();
    await waitForComposerReady();

    const textarea = composerTextarea();
    await user.click(textarea);
    await user.type(textarea, 'Dòng một');
    await user.keyboard('{Shift>}{Enter}{/Shift}');
    await user.type(textarea, 'Dòng hai');

    expect(analyze).not.toHaveBeenCalled();
    expect(textarea.value).toContain('\n');

    await user.keyboard('{Enter}');

    await waitFor(() => expect(analyze).toHaveBeenCalledTimes(1));
    await waitForAssistantText('Trả lời enter.');
    expect(analyze).toHaveBeenCalledTimes(1);
  });

  it('sends from an existing persisted chat with that chat_id', async () => {
    const { analyze, listChats, getChat } = apiMocks();
    listChats.mockResolvedValue(makeChatList(['chat-a']));
    getChat.mockResolvedValue(
      makeChatDetail('chat-a', [makeUserMessage('chat-a', 'msg-1', 'Tin nhắn cũ')]),
    );
    analyze.mockResolvedValue(makeAnalyzeResponse({ chat_id: 'chat-a', summary: 'Trả lời A.' }));

    const { user } = renderApp();

    const chatButton = await screen.findByText('Tiêu đề chat-a');
    await user.click(chatButton);
    await waitFor(() => expect(getChat).toHaveBeenCalledWith('chat-a', expect.any(String)));
    await waitForComposerReady();

    await sendViaControls(user, 'Câu hỏi trong chat A');

    await waitFor(() => expect(analyze).toHaveBeenCalledTimes(1));
    expect(analyze.mock.calls[0][0]).toMatchObject({ chat_id: 'chat-a' });
    await waitForAssistantText('Trả lời A.');
  });

  it('recovers after a failure: error shown, controls usable, retry succeeds', async () => {
    const { analyze } = apiMocks();
    analyze
      .mockRejectedValueOnce(new Error('boom'))
      .mockResolvedValueOnce(makeAnalyzeResponse({ summary: 'Trả lời sau lỗi.' }));

    const { user } = renderApp();
    await waitForComposerReady();

    await sendViaControls(user, 'Câu hỏi lỗi');
    await waitFor(() => expect(analyze).toHaveBeenCalledTimes(1));

    // A safe error surfaces and the submitted question stays in the transcript.
    //
    // This was `toBe(0)` while the composer held the sent text until the
    // response arrived: rolling the message back was coherent then, because the
    // text was still in the input. The composer now empties the instant a
    // submission is accepted, so rolling the message back as well would erase
    // the question outright. It is retained and replayed through the error
    // banner's retry control instead.
    await waitFor(() => {
      expect(screen.getByText(/Không thể kết nối backend/)).toBeInTheDocument();
    });
    expect(countUserMessagesWithText('Câu hỏi lỗi')).toBe(1);

    // Loading cleared and the composer is usable again.
    await waitForComposerReady();
    await sendViaControls(user, 'Câu hỏi lại');

    await waitFor(() => expect(analyze).toHaveBeenCalledTimes(2));
    await waitForAssistantText('Trả lời sau lỗi.');
  });

  it('allows two consecutive sends under prefers-reduced-motion', async () => {
    setReducedMotion(true);
    const { analyze } = apiMocks();
    analyze
      .mockResolvedValueOnce(makeAnalyzeResponse({ summary: 'Giảm chuyển động một.' }))
      .mockResolvedValueOnce(makeAnalyzeResponse({ summary: 'Giảm chuyển động hai.' }));

    const { user } = renderApp();
    await waitForComposerReady();

    await sendViaControls(user, 'Câu hỏi một');
    await waitForAssistantText('Giảm chuyển động một.');

    // The regression this guards: reduced motion reveals everything at once but
    // must still report completion, or the composer stays disabled forever.
    await waitForComposerReady();
    expect(composerTextarea()).not.toBeDisabled();

    await sendViaControls(user, 'Câu hỏi hai');
    await waitFor(() => expect(analyze).toHaveBeenCalledTimes(2));
    await waitForAssistantText('Giảm chuyển động hai.');
    expect(composerTextarea()).not.toBeDisabled();
  });

  it('works under StrictMode without duplicating the analyze call', async () => {
    const { analyze } = apiMocks();
    analyze.mockResolvedValue(makeAnalyzeResponse({ summary: 'Trả lời strict.' }));

    const { user } = renderApp({ strict: true });
    await waitForComposerReady();

    await sendViaControls(user, 'Câu hỏi strict');

    await waitFor(() => expect(analyze).toHaveBeenCalledTimes(1));
    await waitForAssistantText('Trả lời strict.');
    expect(analyze).toHaveBeenCalledTimes(1);
    expect(countUserMessagesWithText('Câu hỏi strict')).toBe(1);
    expect(assistantBubbles()).toHaveLength(1);
  });

  it('never leaves the composer permanently disabled after a pending request settles', async () => {
    const { analyze } = apiMocks();
    const pending = deferred<ReturnType<typeof makeAnalyzeResponse>>();
    analyze.mockReturnValue(pending.promise);

    const { user } = renderApp();
    await waitForComposerReady();
    await sendViaControls(user, 'Câu hỏi treo');

    // While pending the composer is intentionally busy.
    await waitFor(() => expect(composerTextarea()).toBeDisabled());

    pending.resolve(makeAnalyzeResponse({ summary: 'Xong.' }));
    await waitForAssistantText('Xong.');
    await waitForComposerReady();
    expect(composerTextarea()).not.toBeDisabled();
  });
});
