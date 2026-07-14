import type { ReactNode } from 'react';
import type { UserType } from '../api/types';

interface ChatLayoutProps {
  sidebar: ReactNode;
  children: ReactNode;
  isEmptyChat: boolean;
  selectedUserType: UserType;
  disabled: boolean;
  onUserTypeChange: (userType: UserType) => void;
}

export function ChatLayout({
  sidebar,
  children,
  isEmptyChat,
  selectedUserType,
  disabled,
  onUserTypeChange,
}: ChatLayoutProps) {
  return (
    <div className="app-shell">
      {sidebar}
      <main className="app-main">
        <header className="main-topbar">
          <label className="user-type-control">
            <span className="user-type-label user-type-label-full">Nhóm người dùng</span>
            <span className="user-type-label user-type-label-short">Nhóm</span>
            <select
              value={selectedUserType}
              disabled={disabled}
              onChange={(event) => onUserTypeChange(event.target.value as UserType)}
              aria-label="Nhóm người dùng"
            >
              <option value="citizen">Người dân</option>
              <option value="household_business">Hộ kinh doanh</option>
              <option value="foreign_visitor">Khách nước ngoài</option>
              <option value="unknown">Chưa xác định</option>
            </select>
          </label>
        </header>
        <div className={`chat-content ${isEmptyChat ? 'chat-content--empty' : 'chat-content--conversation'}`}>
          {children}
        </div>
      </main>
    </div>
  );
}
