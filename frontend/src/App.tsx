import { useCallback, useEffect, useRef, useState } from 'react';
import { analyze, ApiClientError, getChat, listChats } from './api/client';
import type { AnalyzeContent, AnalyzeResponse, ChatListItem, ChatMessage, UserType } from './api/types';
import { ChatLayout } from './components/ChatLayout';
import { ChatWindow } from './components/ChatWindow';
import { Composer } from './components/Composer';
import { Sidebar } from './components/Sidebar';
import { getOrCreateSessionId } from './lib/session';

function pickAnalyzeContent(response: AnalyzeResponse): AnalyzeContent {
  return {
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
  };
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
  const [userType, setUserType] = useState<UserType>('citizen');
  const [sending, setSending] = useState(false);
  const [loadingChat, setLoadingChat] = useState(false);
  const [loadingChats, setLoadingChats] = useState(true);
  const [error, setError] = useState<string | null>(null);

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

  const submitQuestion = useCallback(async (question: string, requestedUserType = userType) => {
    if (sending || loadingChat) return;

    setSending(true);
    setError(null);

    try {
      const response = await analyze({
        session_id: sessionId,
        ...(activeChatId ? { chat_id: activeChatId } : {}),
        question,
        user_type: requestedUserType,
        language: 'vi',
      });
      const createdAt = new Date().toISOString();
      const userMessage: ChatMessage = {
        message_id: response.user_message_id,
        chat_id: response.chat_id,
        role: 'user',
        content_type: 'text',
        content_text: question,
        content_json: null,
        created_at: createdAt,
      };
      const assistantMessage: ChatMessage = {
        message_id: response.assistant_message_id,
        chat_id: response.chat_id,
        role: 'assistant',
        content_type: 'structured',
        content_text: null,
        content_json: pickAnalyzeContent(response),
        created_at: createdAt,
      };

      setActiveChatId(response.chat_id);
      setMessages((currentMessages) => [...currentMessages, userMessage, assistantMessage]);
      void refreshChats();
    } catch (caughtError) {
      setError(messageFromError(caughtError));
    } finally {
      setSending(false);
    }
  }, [activeChatId, loadingChat, refreshChats, sending, sessionId, userType]);

  const openChat = useCallback(async (chatId: string) => {
    if (sending || loadingChat || chatId === activeChatId) return;

    setLoadingChat(true);
    setError(null);
    try {
      const response = await getChat(chatId);
      setActiveChatId(response.chat_id);
      setMessages(response.messages);
    } catch (caughtError) {
      setError(messageFromError(caughtError));
    } finally {
      setLoadingChat(false);
    }
  }, [activeChatId, loadingChat, sending]);

  function startNewChat() {
    if (sending || loadingChat) return;
    setActiveChatId(null);
    setMessages([]);
    setError(null);
  }

  function submitDemo(question: string, demoUserType: 'citizen' | 'household_business' | 'foreign_visitor') {
    setUserType(demoUserType);
    void submitQuestion(question, demoUserType);
  }

  const disabled = sending || loadingChat;

  return (
    <ChatLayout
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
        sending={disabled}
        error={error}
        onDismissError={() => setError(null)}
        onDemoSubmit={submitDemo}
      />
      <Composer
        disabled={disabled}
        userType={userType}
        onUserTypeChange={setUserType}
        onSend={(question) => void submitQuestion(question)}
      />
    </ChatLayout>
  );
}
