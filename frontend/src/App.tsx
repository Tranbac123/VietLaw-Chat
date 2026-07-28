import { useCallback, useEffect, useRef, useState } from 'react';
import { analyze, ApiClientError, getChat, listChats } from './api/client';
import type { AnalyzeContent, AnalyzeResponse, ChatListItem, ChatMessage, UserType } from './api/types';
import { ChatLayout } from './components/ChatLayout';
import { ChatWindow } from './components/ChatWindow';
import { Composer } from './components/Composer';
import { Sidebar } from './components/Sidebar';
import { MIN_THINKING_MS } from './lib/animation';
import { getOrCreateSessionId } from './lib/session';

type AssistantResponsePhase = 'idle' | 'thinking' | 'revealing';

type AnalyzeRaceResult =
  | { kind: 'response'; response: AnalyzeResponse }
  | { kind: 'cancelled' };

interface ActiveResponseFlow {
  generation: number;
  temporaryUserMessageId: string;
  cancel: () => void;
}

function waitForMinimumThinkingDuration(remainingMs: number, cancellation: Promise<void>): Promise<boolean> {
  if (remainingMs <= 0) return Promise.resolve(true);

  return new Promise((resolve) => {
    const timeoutId = window.setTimeout(() => resolve(true), remainingMs);
    void cancellation.then(() => {
      window.clearTimeout(timeoutId);
      resolve(false);
    });
  });
}

function pickAnalyzeContent(response: AnalyzeResponse): AnalyzeContent {
  if (
    response.response_kind === 'social'
    || response.response_kind === 'capability'
    || response.response_kind === 'scope'
  ) {
    return {
      response_kind: response.response_kind,
      domain: null,
      risk_level: null,
      decision: null,
      summary: response.summary,
      clarifying_questions: response.clarifying_questions,
      checklist: response.checklist,
      next_steps: response.next_steps,
      sources: response.sources,
      safety_notice: response.safety_notice,
      confidence: null,
      metadata: response.metadata,
    };
  }
  return {
    response_kind: 'legal',
    domain: response.domain,
    risk_level: response.risk_level,
    decision: response.decision,
    summary: response.summary,
    clarifying_questions: response.clarifying_questions,
    checklist: response.checklist,
    next_steps: response.next_steps,
    sources: response.sources,
    safety_notice: response.safety_notice,
    confidence: response.confidence,
    metadata: response.metadata,
    analysis: response.analysis ?? null,
    draft: response.draft ?? null,
    known_facts: response.known_facts ?? [],
    uncertainty_notice: response.uncertainty_notice ?? null,
  };
}

/**
 * The immutable record of a submission that was dispatched and then failed.
 * Retry replays it verbatim, so the composer is never the store of record for
 * in-flight text.
 */
interface Resubmission {
  question: string;
  clientRequestId: string;
  userType: UserType;
  temporaryUserMessageId: string;
}

function newClientRequestId(): string {
  const cryptoRef = typeof crypto !== 'undefined' ? crypto : undefined;
  if (cryptoRef?.randomUUID) return cryptoRef.randomUUID();
  return `crid_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 12)}`;
}

function messageFromError(error: unknown): string {
  if (error instanceof ApiClientError) return error.message;
  return 'Không thể kết nối backend. Vui lòng kiểm tra server.';
}

export function App() {
  const sessionId = useRef(getOrCreateSessionId()).current;
  const [activeChatId, setActiveChatId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [chats, setChats] = useState<ChatListItem[]>([]);
  const [selectedUserType, setSelectedUserType] = useState<UserType>('citizen');
  const [loadingChat, setLoadingChat] = useState(false);
  const [loadingChats, setLoadingChats] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [failedSubmission, setFailedSubmission] = useState<Resubmission | null>(null);
  const [assistantResponsePhase, setAssistantResponsePhase] = useState<AssistantResponsePhase>('idle');
  const [animatingAssistantMessageId, setAnimatingAssistantMessageId] = useState<string | null>(null);
  const responseGenerationRef = useRef(0);
  const activeResponseFlowRef = useRef<ActiveResponseFlow | null>(null);
  const animatingAssistantMessageIdRef = useRef<string | null>(null);

  const removeOptimisticUserMessage = useCallback((messageId: string) => {
    setMessages((currentMessages) => currentMessages.filter((message) => message.message_id !== messageId));
  }, []);

  const cancelResponseFlow = useCallback(() => {
    const activeResponseFlow = activeResponseFlowRef.current;
    responseGenerationRef.current += 1;
    activeResponseFlow?.cancel();
    activeResponseFlowRef.current = null;
    if (activeResponseFlow) removeOptimisticUserMessage(activeResponseFlow.temporaryUserMessageId);
    animatingAssistantMessageIdRef.current = null;
    setAssistantResponsePhase('idle');
    setAnimatingAssistantMessageId(null);
  }, [removeOptimisticUserMessage]);

  useEffect(() => () => {
    responseGenerationRef.current += 1;
    activeResponseFlowRef.current?.cancel();
  }, []);

  const refreshChats = useCallback(async () => {
    setLoadingChats(true);
    try {
      const response = await listChats(sessionId);
      setChats(response.chats);
    } catch (caughtError) {
      setChats([]);
      setError(messageFromError(caughtError));
    } finally {
      setLoadingChats(false);
    }
  }, [sessionId]);

  useEffect(() => {
    void refreshChats();
  }, [refreshChats]);

  const submitQuestion = useCallback(async (
    question: string,
    onAccepted?: () => void,
    resubmission?: Resubmission,
  ) => {
    // A retry reuses the original idempotency key, so a request the backend may
    // already have processed replays instead of spending a second provider
    // call, and reuses the original placeholder id so the message already in the
    // transcript is replaced rather than duplicated.
    const clientRequestId = resubmission?.clientRequestId ?? newClientRequestId();
    const requestedUserType = resubmission?.userType ?? selectedUserType;
    if (assistantResponsePhase !== 'idle' || loadingChat) return false;

    const generation = responseGenerationRef.current + 1;
    responseGenerationRef.current = generation;
    const temporaryUserMessageId = resubmission?.temporaryUserMessageId
      ?? `temporary-user-${generation}`;
    const requestCreatedAt = new Date().toISOString();
    let cancelFlow!: () => void;
    const cancellation = new Promise<void>((resolve) => {
      let cancelled = false;
      cancelFlow = () => {
        if (cancelled) return;
        cancelled = true;
        resolve();
      };
    });

    activeResponseFlowRef.current = { generation, temporaryUserMessageId, cancel: cancelFlow };
    const optimisticUserMessage: ChatMessage = {
      message_id: temporaryUserMessageId,
      chat_id: activeChatId ?? `temporary-chat-${generation}`,
      role: 'user',
      content_type: 'text',
      content_text: question,
      content_json: null,
      created_at: requestCreatedAt,
    };
    setMessages((currentMessages) => (
      // On a retry the placeholder is already on screen; replace it in place so
      // the transcript never shows the same question twice.
      currentMessages.some((message) => message.message_id === temporaryUserMessageId)
        ? currentMessages.map((message) => (
          message.message_id === temporaryUserMessageId ? optimisticUserMessage : message
        ))
        : [...currentMessages, optimisticUserMessage]
    ));
    setAssistantResponsePhase('thinking');
    setError(null);
    setFailedSubmission(null);
    // The submission is now accepted and about to be dispatched: this is the
    // moment the composer may empty itself.
    onAccepted?.();
    const requestStartedAt = performance.now();

    try {
      const result = await Promise.race<AnalyzeRaceResult>([
        analyze({
          session_id: sessionId,
          ...(activeChatId ? { chat_id: activeChatId } : {}),
          question,
          user_type: requestedUserType,
          language: 'vi',
          client_request_id: clientRequestId,
        }).then((response) => ({ kind: 'response', response })),
        cancellation.then(() => ({ kind: 'cancelled' })),
      ]);

      if (result.kind === 'cancelled' || responseGenerationRef.current !== generation) return false;

      const elapsedMs = performance.now() - requestStartedAt;
      const remainingMs = Math.max(0, MIN_THINKING_MS - elapsedMs);
      const minimumThinkingMet = await waitForMinimumThinkingDuration(remainingMs, cancellation);
      if (!minimumThinkingMet || responseGenerationRef.current !== generation) return false;

      const { response } = result;
      const userMessage: ChatMessage = {
        message_id: response.user_message_id,
        chat_id: response.chat_id,
        role: 'user',
        content_type: 'text',
        content_text: question,
        content_json: null,
        created_at: requestCreatedAt,
      };
      const assistantMessage: ChatMessage = {
        message_id: response.assistant_message_id,
        chat_id: response.chat_id,
        role: 'assistant',
        content_type: 'structured',
        content_text: null,
        content_json: pickAnalyzeContent(response),
        created_at: new Date().toISOString(),
      };

      setActiveChatId(response.chat_id);
      setMessages((currentMessages) => [
        ...currentMessages.map((message) => (
          message.message_id === temporaryUserMessageId ? userMessage : message
        )),
        assistantMessage,
      ]);
      animatingAssistantMessageIdRef.current = response.assistant_message_id;
      setAnimatingAssistantMessageId(response.assistant_message_id);
      setAssistantResponsePhase('revealing');
      void refreshChats();
      return true;
    } catch (caughtError) {
      if (responseGenerationRef.current !== generation) return false;
      // The question stays in the transcript. Rolling it back made sense only
      // while the composer still held the text; now that the composer empties on
      // acceptance, removing it too would erase the message entirely. Retry is
      // offered from the error banner and reuses the snapshot below, so nothing
      // has to be retyped and no automatic resend happens.
      setError(messageFromError(caughtError));
      setFailedSubmission({
        question,
        clientRequestId,
        userType: requestedUserType,
        temporaryUserMessageId,
      });
      setAssistantResponsePhase('idle');
      return false;
    } finally {
      if (activeResponseFlowRef.current?.generation === generation) {
        activeResponseFlowRef.current = null;
      }
    }
  }, [
    activeChatId,
    assistantResponsePhase,
    loadingChat,
    refreshChats,
    removeOptimisticUserMessage,
    selectedUserType,
    sessionId,
  ]);

  /** Replays the failed submission. Never triggered automatically. */
  const retryFailedSubmission = useCallback(() => {
    if (!failedSubmission) return;
    void submitQuestion(failedSubmission.question, undefined, failedSubmission);
  }, [failedSubmission, submitQuestion]);

  const openChat = useCallback(async (chatId: string) => {
    if (loadingChat || chatId === activeChatId) return;

    cancelResponseFlow();
    setLoadingChat(true);
    setError(null);
    setFailedSubmission(null);
    try {
      const response = await getChat(chatId, sessionId);
      setActiveChatId(response.chat_id);
      setMessages(response.messages);
    } catch (caughtError) {
      setError(messageFromError(caughtError));
    } finally {
      setLoadingChat(false);
    }
  }, [activeChatId, cancelResponseFlow, loadingChat, sessionId]);

  function startNewChat() {
    if (loadingChat) return;
    cancelResponseFlow();
    setActiveChatId(null);
    setMessages([]);
    setError(null);
    setFailedSubmission(null);
  }

  const handleAnimationComplete = useCallback((messageId: string) => {
    if (animatingAssistantMessageIdRef.current !== messageId) return;
    animatingAssistantMessageIdRef.current = null;
    setAnimatingAssistantMessageId(null);
    setAssistantResponsePhase((currentPhase) => (
      currentPhase === 'revealing' ? 'idle' : currentPhase
    ));
  }, []);

  const controlsDisabled = assistantResponsePhase !== 'idle' || loadingChat;
  const composerInputDisabled = assistantResponsePhase === 'thinking' || loadingChat;
  const composerSubmitDisabled = assistantResponsePhase !== 'idle' || loadingChat;
  const isEmptyChat = messages.length === 0;
  const hasStartedConversation = !isEmptyChat || assistantResponsePhase !== 'idle';
  const showLanding = !hasStartedConversation;
  const hasAssistantMessage = messages.some((message) => message.role === 'assistant');

  return (
    <ChatLayout
      isEmptyChat={showLanding}
      selectedUserType={selectedUserType}
      disabled={controlsDisabled}
      onUserTypeChange={setSelectedUserType}
      sidebar={(
        <Sidebar
          chats={chats}
          activeChatId={activeChatId}
          loading={loadingChats}
          onNewChat={startNewChat}
          onSelectChat={(chatId) => void openChat(chatId)}
        />
      )}
    >
      <ChatWindow
        messages={messages}
        assistantResponsePhase={assistantResponsePhase}
        animatingAssistantMessageId={animatingAssistantMessageId}
        onAnimationComplete={handleAnimationComplete}
        showLanding={showLanding}
        error={error}
        onDismissError={() => { setError(null); setFailedSubmission(null); }}
        onRetry={failedSubmission ? retryFailedSubmission : undefined}
      />
      <Composer
        inputDisabled={composerInputDisabled}
        submitDisabled={composerSubmitDisabled}
        isEmptyChat={showLanding}
        onSend={submitQuestion}
      />
    </ChatLayout>
  );
}
