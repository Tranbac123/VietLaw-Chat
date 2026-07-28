/**
 * Phase B (frontend): short messages send cleanly, and a conversation keeps its
 * thread across an intervening greeting.
 *
 * These drive the real composer controls rather than calling the submit handler,
 * because both defects were only ever visible through the UI: "ok" surfaced an
 * invalid-data banner, and a vague follow-up rendered an answer that had
 * forgotten the issue described two turns earlier.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { AnalyzeResponse, SocialAnalyzeResponse } from '../api/types';
import {
  apiMocks,
  assistantBubbles,
  makeAnalyzeResponse,
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

let socialCounter = 0;

/** A non-legal (social/scope) response, as the backend returns for "ok"/"hello". */
function makeSocialResponse(summary: string): AnalyzeResponse {
  socialCounter += 1;
  const n = socialCounter;
  return {
    contract_version: '1.0',
    request_id: `req-social-${n}`,
    chat_id: `chat-social-${n}`,
    user_message_id: `srv-user-social-${n}`,
    assistant_message_id: `srv-assistant-social-${n}`,
    response_kind: 'social',
    domain: null,
    risk_level: null,
    decision: null,
    confidence: null,
    summary,
    clarifying_questions: [],
    checklist: [],
    next_steps: [],
    sources: [],
    safety_notice: '',
    metadata: {},
  } as SocialAnalyzeResponse;
}

/** No error banner is showing. */
function expectNoErrorBanner(): void {
  expect(screen.queryByRole('alert')).toBeNull();
  expect(document.body.textContent ?? '').not.toMatch(/không hợp lệ/i);
}

describe('short messages send without an invalid-data error', () => {
  it.each([
    ['ok', 'Vâng. Khi nào bạn cần hỗ trợ, bạn cứ mô tả nhé.'],
    ['hello', 'Xin chào! Tôi có thể giúp gì cho bạn?'],
  ])('sends %s through the Send button', async (text, reply) => {
    const { analyze } = apiMocks();
    analyze.mockResolvedValue(makeSocialResponse(reply));

    const { user } = renderApp();
    await waitForComposerReady();

    await sendViaControls(user, text);

    await waitFor(() => expect(analyze).toHaveBeenCalledTimes(1));
    expect(analyze.mock.calls[0][0]).toMatchObject({ question: text });

    await waitForAssistantText(reply);
    expectNoErrorBanner();

    // Send becomes usable again.
    await waitForComposerReady();
    expect(sendButton()).toBeDisabled(); // empty draft, not a stuck composer
  });

  it('sends a short message with Enter', async () => {
    const { analyze } = apiMocks();
    analyze.mockResolvedValue(makeSocialResponse('Vâng, tôi đây.'));

    const { user } = renderApp();
    await waitForComposerReady();

    await sendViaControls(user, 'ok', { via: 'enter' });

    await waitFor(() => expect(analyze).toHaveBeenCalledTimes(1));
    await waitForAssistantText('Vâng, tôi đây.');
    expectNoErrorBanner();
    await waitForComposerReady();
  });

  it('sends two consecutive short messages without a refresh', async () => {
    const { analyze } = apiMocks();
    analyze
      .mockResolvedValueOnce(makeSocialResponse('Chào bạn nhé.'))
      .mockResolvedValueOnce(makeSocialResponse('Vâng, tôi vẫn ở đây.'));

    const { user } = renderApp();
    await waitForComposerReady();

    await sendViaControls(user, 'hello');
    await waitForAssistantText('Chào bạn nhé.');
    await waitForComposerReady();

    await sendViaControls(user, 'ok');
    await waitFor(() => expect(analyze).toHaveBeenCalledTimes(2));
    await waitForAssistantText('Vâng, tôi vẫn ở đây.');

    expectNoErrorBanner();
    expect(assistantBubbles()).toHaveLength(2);
    await waitForComposerReady();
  });
});

describe('a rendered conversation keeps its thread across a greeting', () => {
  it('answers a vague follow-up using the earlier issue', async () => {
    const { analyze } = apiMocks();

    const issueReply = 'Việc chủ nhà chưa bàn giao nhà như thỏa thuận là điều cần làm rõ sớm.';
    const followUpReply =
      'Việc chủ nhà chưa bàn giao nhà như thỏa thuận là điều cần làm rõ sớm. '
      + 'Dưới đây là những bước bạn có thể làm ngay.';

    analyze
      // 1: the user describes the rental issue.
      .mockResolvedValueOnce(makeAnalyzeResponse({ chat_id: 'chat-b', summary: issueReply }))
      // 2: an intervening greeting.
      .mockResolvedValueOnce({ ...makeSocialResponse('Xin chào!'), chat_id: 'chat-b' })
      // 3: the vague follow-up, answered from context.
      .mockResolvedValueOnce(
        makeAnalyzeResponse({
          chat_id: 'chat-b',
          summary: followUpReply,
          next_steps: ['Giữ lại chứng từ chuyển khoản và tin nhắn trao đổi với chủ nhà.'],
        }),
      );

    const { user } = renderApp();
    await waitForComposerReady();

    await sendViaControls(user, 'tôi đặt cọc mà chủ nhà không cho vào ở thì phải làm sao?');
    await waitForAssistantText('chưa bàn giao');
    await waitForComposerReady();

    await sendViaControls(user, 'chào bạn');
    await waitForAssistantText('Xin chào!');
    await waitForComposerReady();

    await sendViaControls(user, 'tôi nên làm gì?');
    await waitFor(() => expect(analyze).toHaveBeenCalledTimes(3));
    await waitForAssistantText('Dưới đây là những bước bạn có thể làm ngay.');

    // Every turn stayed in the same chat, so the backend could see the history.
    expect(analyze.mock.calls[1][0]).toMatchObject({ chat_id: 'chat-b' });
    expect(analyze.mock.calls[2][0]).toMatchObject({ chat_id: 'chat-b' });

    // The displayed answer continues the earlier issue...
    const bubbles = assistantBubbles();
    const finalBubble = bubbles[bubbles.length - 1];
    expect(finalBubble?.textContent ?? '').toMatch(/bàn giao/);

    // ...and never claims to have lost it.
    const page = document.body.textContent ?? '';
    expect(page).not.toMatch(/chưa có thông tin/i);
    expect(page).not.toMatch(/không có thông tin/i);
    expect(page).not.toMatch(/mô tả lại/i);

    // No duplicates, and the composer is still usable.
    expect(assistantBubbles()).toHaveLength(3);
    expectNoErrorBanner();
    await waitForComposerReady();
  });
});
