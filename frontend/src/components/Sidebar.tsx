import type { ChatListItem } from '../api/types';
import vietLawLogo from '../assets/brand/vietlaw-logo.png';
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
    <aside className="sidebar" aria-label="Lịch sử chat">
      <div className="sidebar-brand">
        <img src={vietLawLogo} alt="" aria-hidden="true" className="brand-logo" draggable={false} />
        <div>
          <p className="brand-name">VietLaw-Chat</p>
        </div>
      </div>

      <button className="new-chat-button" type="button" onClick={onNewChat}>
        <span aria-hidden="true">+</span>
        Chat mới
      </button>

      <div className="sidebar-conversations">
        <p className="sidebar-section-title">Lịch sử chat</p>
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
