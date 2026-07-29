/**
 * Reload restores the chat the user was actually looking at.
 *
 * Before this, a browser reload always dropped the user into New Chat even
 * though the conversation existed and was accessible. "Reload" here is an
 * unmount followed by a fresh mount, which is what a real reload does to the
 * React tree while leaving `localStorage` intact.
 *
 * These drive the real App/chat-selection seam, not the storage helper in
 * isolation: the bug was in *when* restoration happens relative to the chat
 * list, which a unit test of the helper could never have caught.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup } from '@testing-library/react';
import {
  apiMocks,
  assistantBubbles,
  composerTextarea,
  makeAnalyzeResponse,
  makeChatDetail,
  makeChatList,
  makeUserMessage,
  primeDefaultApi,
  renderApp,
  screen,
  waitFor,
  waitForAssistantText,
  waitForComposerReady,
} from './testUtils';
import {
  SELECTED_CHAT_STORAGE_KEY,
  isValidChatId,
  readSelectedChatId,
} from '../lib/selectedChat';
import type { AnalyzeContent, ChatMessage, LegalAnalyzeResponse } from '../api/types';

vi.mock('../api/client', async () => {
  const { createApiClientMock } = await import('./apiMockFactory');
  return createApiClientMock();
});

const CHAT_A = 'chat_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const CHAT_B = 'chat_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb';
const PERSISTED_SUMMARY = 'Câu trả lời đã lưu từ trước.';

beforeEach(() => {
  primeDefaultApi();
});

function storedId(): string | null {
  return window.localStorage.getItem(SELECTED_CHAT_STORAGE_KEY);
}

/** A persisted structured assistant answer, as the chat store returns it. */
function persistedAssistantMessage(chatId: string): ChatMessage {
  const legal = makeAnalyzeResponse({
    summary: PERSISTED_SUMMARY,
    analysis: 'Phân tích đã lưu.',
    next_steps: ['Bước đã lưu'],
  }) as LegalAnalyzeResponse;
  const content = {
    response_kind: 'legal',
    domain: legal.domain, risk_level: legal.risk_level, decision: legal.decision,
    confidence: legal.confidence,
    summary: legal.summary,
    clarifying_questions: [], checklist: [], next_steps: legal.next_steps,
    sources: [], safety_notice: '',
    metadata: { fast_demo: true },
    analysis: legal.analysis ?? null,
    draft: null, known_facts: [], uncertainty_notice: null,
  } as AnalyzeContent;
  return {
    message_id: `${chatId}-assistant`,
    chat_id: chatId,
    role: 'assistant',
    content_type: 'structured',
    content_text: null,
    content_json: content,
    created_at: '2026-01-01T00:00:00Z',
  };
}

function primeChats(ids: string[]): void {
  const { listChats, getChat } = apiMocks();
  listChats.mockResolvedValue(makeChatList(ids));
  getChat.mockImplementation((chatId: string) => {
    if (!ids.includes(chatId)) {
      return Promise.reject(new Error('chat_not_found'));
    }
    return Promise.resolve(
      makeChatDetail(chatId, [
        makeUserMessage(chatId, `${chatId}-user`, `Tin nhắn của ${chatId}`),
        persistedAssistantMessage(chatId),
      ]),
    );
  });
}

async function openChatByTitle(user: Awaited<ReturnType<typeof renderApp>>['user'], id: string) {
  const button = await screen.findByRole('button', { name: new RegExp(`Tiêu đề ${id}`) });
  await user.click(button);
}

/** Unmount and mount again: what a browser reload does to the React tree. */
function reload() {
  cleanup();
  return renderApp();
}

describe('selecting a chat remembers it', () => {
  it('persists the chat id when a chat is opened', async () => {
    primeChats([CHAT_A, CHAT_B]);
    const { user } = renderApp();
    await waitForComposerReady();

    expect(storedId()).toBeNull();
    await openChatByTitle(user, CHAT_A);
    await waitFor(() => expect(storedId()).toBe(CHAT_A));
  });

  it('updates the remembered id when the user switches chats', async () => {
    primeChats([CHAT_A, CHAT_B]);
    const { user } = renderApp();
    await waitForComposerReady();

    await openChatByTitle(user, CHAT_A);
    await waitFor(() => expect(storedId()).toBe(CHAT_A));

    await openChatByTitle(user, CHAT_B);
    await waitFor(() => expect(storedId()).toBe(CHAT_B));
  });

  it('remembers the chat a first message created', async () => {
    const { analyze, listChats, getChat } = apiMocks();
    listChats.mockResolvedValue(makeChatList([]));
    getChat.mockResolvedValue(makeChatDetail(CHAT_A, []));
    analyze.mockResolvedValue(makeAnalyzeResponse({ chat_id: CHAT_A, summary: 'Trả lời.' }));

    const { user } = renderApp();
    await waitForComposerReady();
    const { sendViaControls } = await import('./testUtils');
    await sendViaControls(user, 'câu hỏi đầu tiên');
    await waitForAssistantText('Trả lời.');

    expect(storedId()).toBe(CHAT_A);
  });

  it('forgets the chat when the user explicitly starts a New Chat', async () => {
    primeChats([CHAT_A]);
    const { user } = renderApp();
    await waitForComposerReady();

    await openChatByTitle(user, CHAT_A);
    await waitFor(() => expect(storedId()).toBe(CHAT_A));

    await user.click(screen.getByRole('button', { name: /Cuộc trò chuyện mới|Chat mới/i }));
    expect(storedId()).toBeNull();
  });
});

describe('reload restores the selected chat', () => {
  it('restores the same chat and its messages', async () => {
    primeChats([CHAT_A, CHAT_B]);
    const first = renderApp();
    await waitForComposerReady();
    await openChatByTitle(first.user, CHAT_A);
    await waitFor(() => expect(storedId()).toBe(CHAT_A));

    reload();

    // Same chat id, and its messages are on screen.
    await waitFor(() => expect(readSelectedChatId()).toBe(CHAT_A));
    await screen.findByText(`Tin nhắn của ${CHAT_A}`);
    await waitForAssistantText(PERSISTED_SUMMARY);
  });

  it('renders a persisted answer fully without replaying the word reveal', async () => {
    primeChats([CHAT_A]);
    const first = renderApp();
    await waitForComposerReady();
    await openChatByTitle(first.user, CHAT_A);
    await waitFor(() => expect(storedId()).toBe(CHAT_A));

    reload();

    await waitForAssistantText(PERSISTED_SUMMARY);
    const bubble = assistantBubbles()[0];
    // Complete on arrival: summary, analysis and next steps are all present,
    // so nothing was staged word by word.
    expect(bubble.textContent).toContain(PERSISTED_SUMMARY);
    expect(bubble.textContent).toContain('Phân tích đã lưu.');
    expect(bubble.textContent).toContain('Bước đã lưu');
  });

  it('creates no chat and dispatches no request during restoration', async () => {
    primeChats([CHAT_A]);
    const first = renderApp();
    await waitForComposerReady();
    await openChatByTitle(first.user, CHAT_A);
    await waitFor(() => expect(storedId()).toBe(CHAT_A));

    const { analyze } = apiMocks();
    analyze.mockClear();
    reload();
    await waitForAssistantText(PERSISTED_SUMMARY);

    expect(analyze).not.toHaveBeenCalled();
  });

  it('leaves the composer usable after restoration', async () => {
    primeChats([CHAT_A]);
    const first = renderApp();
    await waitForComposerReady();
    await openChatByTitle(first.user, CHAT_A);
    await waitFor(() => expect(storedId()).toBe(CHAT_A));

    reload();
    await waitForAssistantText(PERSISTED_SUMMARY);
    await waitForComposerReady();
    expect(composerTextarea()).not.toBeDisabled();
  });

  it('waits for the chat list instead of briefly selecting the wrong chat', async () => {
    primeChats([CHAT_A]);
    window.localStorage.setItem(SELECTED_CHAT_STORAGE_KEY, CHAT_A);

    const { listChats } = apiMocks();
    const { deferred } = await import('./testUtils');
    const pending = deferred<ReturnType<typeof makeChatList>>();
    listChats.mockReturnValue(pending.promise);

    renderApp();

    // While the list is unresolved the app has not committed to any chat and
    // has not created one.
    expect(screen.queryByText(`Tin nhắn của ${CHAT_A}`)).toBeNull();
    expect(composerTextarea()).toBeDisabled();

    pending.resolve(makeChatList([CHAT_A]));
    await screen.findByText(`Tin nhắn của ${CHAT_A}`);
    await waitForComposerReady();
  });
});

describe('restoration falls back safely', () => {
  it('stays on New Chat when nothing was remembered', async () => {
    primeChats([CHAT_A]);
    renderApp();
    await waitForComposerReady();

    expect(screen.queryByText(`Tin nhắn của ${CHAT_A}`)).toBeNull();
    expect(assistantBubbles()).toHaveLength(0);
  });

  it('stays on New Chat after an explicit New Chat and a reload', async () => {
    primeChats([CHAT_A]);
    const first = renderApp();
    await waitForComposerReady();
    await openChatByTitle(first.user, CHAT_A);
    await waitFor(() => expect(storedId()).toBe(CHAT_A));
    await first.user.click(screen.getByRole('button', { name: /Cuộc trò chuyện mới|Chat mới/i }));
    expect(storedId()).toBeNull();

    reload();
    await waitForComposerReady();
    expect(screen.queryByText(`Tin nhắn của ${CHAT_A}`)).toBeNull();
  });

  it('rejects and clears a malformed stored id', async () => {
    primeChats([CHAT_A]);
    window.localStorage.setItem(SELECTED_CHAT_STORAGE_KEY, '../../etc/passwd');

    renderApp();
    await waitForComposerReady();

    expect(storedId()).toBeNull();
    expect(assistantBubbles()).toHaveLength(0);
  });

  it.each([
    ['', 'empty'],
    ['not-a-chat', 'wrong prefix'],
    ['chat_' + 'x'.repeat(200), 'oversized'],
  ])('treats %s as invalid (%s)', (value) => {
    expect(isValidChatId(value)).toBe(false);
  });

  it('falls back to New Chat when the remembered chat no longer exists', async () => {
    // The list no longer contains it: deleted since the last visit.
    primeChats([CHAT_B]);
    window.localStorage.setItem(SELECTED_CHAT_STORAGE_KEY, CHAT_A);

    renderApp();
    await waitForComposerReady();

    expect(storedId()).toBeNull();
    expect(screen.queryByText(`Tin nhắn của ${CHAT_A}`)).toBeNull();
    expect(assistantBubbles()).toHaveLength(0);
  });

  it('does not restore a chat that is not in this session\'s list', async () => {
    // CHAT_A belongs to another owner: this session's list never mentions it.
    primeChats([CHAT_B]);
    window.localStorage.setItem(SELECTED_CHAT_STORAGE_KEY, CHAT_A);

    const { getChat } = apiMocks();
    renderApp();
    await waitForComposerReady();

    // It was never even fetched, and the stale id was dropped.
    expect(getChat).not.toHaveBeenCalledWith(CHAT_A, expect.anything());
    expect(storedId()).toBeNull();
  });

  it('keeps the remembered id when the chat list itself fails to load', async () => {
    const { listChats } = apiMocks();
    listChats.mockRejectedValue(new Error('offline'));
    window.localStorage.setItem(SELECTED_CHAT_STORAGE_KEY, CHAT_A);

    renderApp();
    await waitForComposerReady();

    // A transient outage must not discard a valid selection.
    expect(storedId()).toBe(CHAT_A);
  });

  it('leaks no timer or state update from the previous mount', async () => {
    const warn = vi.spyOn(console, 'error').mockImplementation(() => {});
    primeChats([CHAT_A, CHAT_B]);
    const first = renderApp();
    await waitForComposerReady();
    await openChatByTitle(first.user, CHAT_A);
    await waitFor(() => expect(storedId()).toBe(CHAT_A));

    reload();
    await waitForAssistantText(PERSISTED_SUMMARY);
    await new Promise((resolve) => setTimeout(resolve, 400));

    const messages = warn.mock.calls.map((call) => String(call[0] ?? ''));
    expect(messages.some((m) => m.includes('not wrapped in act'))).toBe(false);
    expect(messages.some((m) => m.includes('unmounted component'))).toBe(false);
    warn.mockRestore();
  });
});
