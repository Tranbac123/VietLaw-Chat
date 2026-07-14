import { useCallback, useEffect, useRef } from 'react';
import type { ChatMessage } from '../api/types';
import { ErrorBanner } from './ErrorBanner';
import { LandingChatState } from './LandingChatState';
import { MessageBubble } from './MessageBubble';
import { ThinkingIndicator } from './ThinkingIndicator';

type AssistantResponsePhase = 'idle' | 'thinking' | 'revealing';

interface ChatWindowProps {
  messages: ChatMessage[];
  assistantResponsePhase: AssistantResponsePhase;
  animatingAssistantMessageId: string | null;
  onAnimationComplete: (messageId: string) => void;
  showLanding: boolean;
  error: string | null;
  onDismissError: () => void;
}

export function ChatWindow({
  messages,
  assistantResponsePhase,
  animatingAssistantMessageId,
  onAnimationComplete,
  showLanding,
  error,
  onDismissError,
}: ChatWindowProps) {
  const scrollRegionRef = useRef<HTMLDivElement>(null);
  const isNearBottomRef = useRef(true);
  const lastAutoScrollAtRef = useRef(0);

  const scrollToLatest = useCallback((force = false) => {
    const region = scrollRegionRef.current;
    if (!region) return;

    const distanceFromBottom = region.scrollHeight - region.scrollTop - region.clientHeight;
    if (!force && distanceFromBottom > 112) return;

    const now = performance.now();
    if (!force && now - lastAutoScrollAtRef.current < 120) return;
    lastAutoScrollAtRef.current = now;
    region.scrollTo({ top: region.scrollHeight, behavior: 'auto' });
  }, []);

  useEffect(() => {
    if (assistantResponsePhase === 'thinking') {
      const frameId = window.requestAnimationFrame(() => scrollToLatest(true));
      return () => window.cancelAnimationFrame(frameId);
    }

    if (assistantResponsePhase === 'revealing') {
      const frameId = window.requestAnimationFrame(() => scrollToLatest());
      return () => window.cancelAnimationFrame(frameId);
    }

    return undefined;
  }, [assistantResponsePhase, scrollToLatest]);

  const handleScroll = () => {
    const region = scrollRegionRef.current;
    if (!region) return;
    isNearBottomRef.current = region.scrollHeight - region.scrollTop - region.clientHeight <= 112;
  };

  return (
    <section className="chat-window" aria-label="Khu vực chat">
      {error && <ErrorBanner message={error} onDismiss={onDismissError} />}

      <div className="chat-scroll-region" ref={scrollRegionRef} onScroll={handleScroll}>
        {showLanding ? (
          <LandingChatState />
        ) : (
          <div className="message-list">
            {messages.map((message) => (
              <MessageBubble
                key={message.message_id}
                message={message}
                animate={message.message_id === animatingAssistantMessageId}
                onAnimationComplete={onAnimationComplete}
                onAnimationProgress={() => {
                  if (isNearBottomRef.current) scrollToLatest();
                }}
              />
            ))}
            {assistantResponsePhase === 'thinking' && <ThinkingIndicator />}
          </div>
        )}
      </div>
    </section>
  );
}
