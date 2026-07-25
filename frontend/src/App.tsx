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

  const submitQuestion = useCallback(async (question: string, requestedUserType = selectedUserType) => {
    const clientRequestId = newClientRequestId();
    if (assistantResponsePhase !== 'idle' || loadingChat) return false;

    const generation = responseGenerationRef.current + 1;
    responseGenerationRef.current = generation;
    const temporaryUserMessageId = `temporary-user-${generation}`;
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
    setMessages((currentMessages) => [
      ...currentMessages,
      {
        message_id: temporaryUserMessageId,
        chat_id: activeChatId ?? `temporary-chat-${generation}`,
        role: 'user',
        content_type: 'text',
        content_text: question,
        content_json: null,
        created_at: requestCreatedAt,
      },
    ]);
    setAssistantResponsePhase('thinking');
    setError(null);
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
      removeOptimisticUserMessage(temporaryUserMessageId);
      setError(messageFromError(caughtError));
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

  const openChat = useCallback(async (chatId: string) => {
    if (loadingChat || chatId === activeChatId) return;

    cancelResponseFlow();
    setLoadingChat(true);
    setError(null);
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
        onDismissError={() => setError(null)}
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
