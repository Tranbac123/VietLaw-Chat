import type { ChatListItem } from '../api/types';
import { ConversationList } from './ConversationList';

interface SidebarProps {
  chats: ChatListItem[];
  activeChatId: string | null;
  loading: boolean;
  onNewChat: () => void;
  onSelectChat: (chatId: string) => void;
}

export function Sidebar({ chats, activeChatId, loading, onNewChat, onSelectChat }: SidebarProps) {
  return (
    <aside className="sidebar" aria-label="Danh sách cuộc trò chuyện">
      <div className="sidebar-brand">
        <span className="brand-symbol" aria-hidden="true">V</span>
        <div>
          <p className="brand-name">VietLaw-Chat</p>
          <p className="brand-caption">MVP Demo</p>
        </div>
      </div>

      <button className="new-chat-button" type="button" onClick={onNewChat}>
        <span aria-hidden="true">+</span>
        Chat mới
      </button>

      <div className="sidebar-conversations">
        <p className="sidebar-section-title">Cuộc trò chuyện</p>
        <ConversationList
          chats={chats}
          activeChatId={activeChatId}
          loading={loading}
          onSelect={onSelectChat}
        />
      </div>

      <p className="sidebar-footnote">Chỉ lưu trong phiên trình duyệt hiện tại.</p>
    </aside>
  );
}
