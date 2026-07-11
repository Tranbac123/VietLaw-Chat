import type { ChatListItem } from '../api/types';
import { formatDate } from '../lib/format';

interface ConversationListProps {
  chats: ChatListItem[];
  activeChatId: string | null;
  loading: boolean;
  onSelect: (chatId: string) => void;
}

export function ConversationList({ chats, activeChatId, loading, onSelect }: ConversationListProps) {
  if (loading) return <p className="conversation-status">Đang tải cuộc trò chuyện...</p>;
  if (chats.length === 0) return <p className="conversation-status">Chưa có cuộc trò chuyện nào.</p>;

  return (
    <ul className="conversation-list">
      {chats.map((chat) => (
        <li key={chat.chat_id}>
          <button
            className={`conversation-item ${activeChatId === chat.chat_id ? 'is-active' : ''}`}
            type="button"
            onClick={() => onSelect(chat.chat_id)}
          >
            <span className="conversation-title">{chat.title || 'Chat mới'}</span>
            <span className="conversation-date">{formatDate(chat.updated_at)}</span>
          </button>
        </li>
      ))}
    </ul>
  );
}
