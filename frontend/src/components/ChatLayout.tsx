import type { ReactNode } from 'react';

interface ChatLayoutProps {
  sidebar: ReactNode;
  children: ReactNode;
}

export function ChatLayout({ sidebar, children }: ChatLayoutProps) {
  return (
    <div className="app-shell">
      {sidebar}
      <main className="app-main">{children}</main>
    </div>
  );
}
