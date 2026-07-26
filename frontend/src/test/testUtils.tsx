import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent, { type UserEvent } from '@testing-library/user-event';
import { StrictMode } from 'react';
import { expect, vi, type Mock } from 'vitest';
import * as apiClient from '../api/client';
import type {
  AnalyzeResponse,
  ChatDetailResponse,
  ChatListResponse,
  ChatMessage,
  LegalAnalyzeResponse,
} from '../api/types';
import { App } from '../App';

/** The mocked `../api/client` functions, typed for assertions. */
export function apiMocks() {
  return {
    analyze: apiClient.analyze as unknown as Mock,
    listChats: apiClient.listChats as unknown as Mock,
    getChat: apiClient.getChat as unknown as Mock,
  };
}

/** A promise whose settlement the test controls, for ordering races. */
export interface Deferred<T> {
  promise: Promise<T>;
  resolve: (value: T) => void;
  reject: (reason?: unknown) => void;
}

export function deferred<T>(): Deferred<T> {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}

let responseCounter = 0;

/**
 * A legal analyze response. The summary is deliberately short: the reveal is a
 * real typewriter driven by rAF, so long fixture prose would make every test
 * slow without testing anything extra.
 */
export function makeAnalyzeResponse(
  overrides: Partial<LegalAnalyzeResponse> = {},
): AnalyzeResponse {
  responseCounter += 1;
  const n = responseCounter;
  return {
    contract_version: '1.0',
    request_id: `req-${n}`,
    chat_id: `chat-${n}`,
    user_message_id: `srv-user-${n}`,
    assistant_message_id: `srv-assistant-${n}`,
    response_kind: 'legal',
    domain: 'civil_dispute',
    risk_level: 'low',
    decision: 'answer_with_guidance',
    confidence: { domain: 0.9, risk: 0.9, answer: 0.9 },
    summary: `Tóm tắt ${n}.`,
    clarifying_questions: [],
    checklist: [],
    next_steps: [],
    sources: [],
    safety_notice: 'Thông tin tham khảo.',
    metadata: {},
    ...overrides,
  } as AnalyzeResponse;
}

export function makeChatList(ids: string[]): ChatListResponse {
  return {
    chats: ids.map((id) => ({
      chat_id: id,
      title: `Tiêu đề ${id}`,
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
      message_count: 2,
    })),
  } as ChatListResponse;
}

export function makeUserMessage(chatId: string, id: string, text: string): ChatMessage {
  return {
    message_id: id,
    chat_id: chatId,
    role: 'user',
    content_type: 'text',
    content_text: text,
    content_json: null,
    created_at: '2026-01-01T00:00:00Z',
  };
}

export function makeChatDetail(chatId: string, messages: ChatMessage[]): ChatDetailResponse {
  return { chat_id: chatId, messages } as ChatDetailResponse;
}

/** Default happy-path wiring: an empty sidebar and a resolving analyze. */
export function primeDefaultApi(): void {
  const { listChats, analyze, getChat } = apiMocks();
  listChats.mockResolvedValue(makeChatList([]));
  analyze.mockImplementation(() => Promise.resolve(makeAnalyzeResponse()));
  getChat.mockImplementation((chatId: string) => Promise.resolve(makeChatDetail(chatId, [])));
}

export interface RenderedApp {
  user: UserEvent;
}

export function renderApp({ strict = false } = {}): RenderedApp {
  const user = userEvent.setup();
  render(strict ? (<StrictMode><App /></StrictMode>) : <App />);
  return { user };
}

export function composerTextarea(): HTMLTextAreaElement {
  return screen.getByLabelText('Câu hỏi pháp lý') as HTMLTextAreaElement;
}

export function sendButton(): HTMLButtonElement {
  return screen.getByRole('button', { name: 'Gửi câu hỏi' }) as HTMLButtonElement;
}

/**
 * Sends through the real controls: type into the textarea, then either click
 * Send or press Enter. Calling the submit handler directly would not exercise
 * the composer, which is the thing that keeps regressing.
 */
export async function sendViaControls(
  user: UserEvent,
  text: string,
  { via = 'click' as 'click' | 'enter' } = {},
): Promise<void> {
  const textarea = composerTextarea();
  await waitFor(() => expect(textarea).not.toBeDisabled());
  await user.click(textarea);
  await user.type(textarea, text);

  if (via === 'enter') {
    await user.keyboard('{Enter}');
    return;
  }

  const button = sendButton();
  await waitFor(() => expect(button).not.toBeDisabled());
  await user.click(button);
}

/** Waits until the composer is idle and ready to accept another submission. */
export async function waitForComposerReady(): Promise<void> {
  await waitFor(() => {
    expect(composerTextarea()).not.toBeDisabled();
  }, { timeout: 15_000 });
}

/** All rendered assistant response bubbles. */
export function assistantBubbles(): HTMLElement[] {
  return screen.queryAllByLabelText('Phản hồi từ VietLaw-Chat');
}

/** All rendered user message bubbles. */
export function userBubbles(): HTMLElement[] {
  return screen.queryAllByLabelText('Tin nhắn của bạn');
}

export function countUserMessagesWithText(text: string): number {
  return userBubbles().filter((bubble) => bubble.textContent?.includes(text)).length;
}

export async function waitForAssistantText(text: string): Promise<void> {
  await waitFor(() => {
    const found = assistantBubbles().some((bubble) => bubble.textContent?.includes(text));
    expect(found).toBe(true);
  }, { timeout: 15_000 });
}

export { screen, waitFor, within, userEvent, vi };
