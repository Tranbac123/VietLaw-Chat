import type { ChatMessage } from '../api/types';
import { formatDate } from '../lib/format';
import { StructuredAnswer } from './StructuredAnswer';

interface MessageBubbleProps {
  message: ChatMessage;
  animate?: boolean;
  onAnimationComplete?: (messageId: string) => void;
  onAnimationProgress?: () => void;
}

export function MessageBubble({
  message,
  animate = false,
  onAnimationComplete,
  onAnimationProgress,
}: MessageBubbleProps) {
  const isUser = message.role === 'user';

  return (
    <article className={`message-bubble ${isUser ? 'message-user' : 'message-assistant'}`}>
      <div className="message-meta">
        <span>{isUser ? 'Bạn' : 'Trợ lý'}</span>
        <time dateTime={message.created_at}>{formatDate(message.created_at)}</time>
      </div>

      {message.content_type === 'structured' && message.content_json ? (
        <StructuredAnswer
          content={message.content_json}
          animate={animate}
          onAnimationComplete={() => onAnimationComplete?.(message.message_id)}
          onAnimationProgress={onAnimationProgress}
        />
      ) : (
        <p className="message-text">{message.content_text || 'Không có nội dung để hiển thị.'}</p>
      )}
    </article>
  );
}
