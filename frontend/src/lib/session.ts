const SESSION_STORAGE_KEY = 'vietlaw_chat_session_id';

function createSessionId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return `session_${crypto.randomUUID()}`;
  }

  return `session_${Date.now()}_${Math.random().toString(36).slice(2)}`;
}

export function getOrCreateSessionId(): string {
  const existing = window.localStorage.getItem(SESSION_STORAGE_KEY);
  if (existing) return existing;

  const sessionId = createSessionId();
  window.localStorage.setItem(SESSION_STORAGE_KEY, sessionId);
  return sessionId;
}
