import type { ChatMessage } from '../api/types';
import { formatDate } from '../lib/format';
import { StructuredAnswer } from './StructuredAnswer';

export function MessageBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === 'user';

  return (
    <article className={`message-bubble ${isUser ? 'message-user' : 'message-assistant'}`}>
      <div className="message-meta">
        <span>{isUser ? 'Bạn' : 'VietLaw-Chat'}</span>
        <time dateTime={message.created_at}>{formatDate(message.created_at)}</time>
      </div>

      {message.content_type === 'structured' && message.content_json ? (
        <StructuredAnswer content={message.content_json} />
      ) : (
        <p className="message-text">{message.content_text || 'Không có nội dung để hiển thị.'}</p>
      )}
    </article>
  );
}
