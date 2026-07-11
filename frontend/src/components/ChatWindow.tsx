import type { ChatMessage } from '../api/types';
import { ErrorBanner } from './ErrorBanner';
import { LandingChatState } from './LandingChatState';
import { LoadingIndicator } from './LoadingIndicator';
import { MessageBubble } from './MessageBubble';

interface ChatWindowProps {
  messages: ChatMessage[];
  sending: boolean;
  error: string | null;
  onDismissError: () => void;
  onDemoSubmit: (question: string, userType: 'citizen' | 'household_business' | 'foreign_visitor') => void;
}

export function ChatWindow({
  messages,
  sending,
  error,
  onDismissError,
  onDemoSubmit,
}: ChatWindowProps) {
  return (
    <section className="chat-window" aria-label="Cuộc trò chuyện">
      <header className="chat-header">
        <div>
          <p className="chat-product-name">VietLaw-Chat <span>MVP Demo</span></p>
          <p>Trợ lý định hướng pháp lý ban đầu bằng tiếng Việt</p>
        </div>
      </header>

      {error && <ErrorBanner message={error} onDismiss={onDismissError} />}

      <div className="chat-scroll-region">
        {messages.length === 0 ? (
          <LandingChatState disabled={sending} onDemoSubmit={onDemoSubmit} />
        ) : (
          <div className="message-list">
            {messages.map((message) => <MessageBubble key={message.message_id} message={message} />)}
            {sending && <LoadingIndicator />}
          </div>
        )}
      </div>
    </section>
  );
}
