/**
 * Which chat the user was last looking at, so a browser reload returns to it
 * instead of dropping the user into New Chat.
 *
 * Deliberately minimal. This stores **only a chat identifier** -- never
 * messages, never legal facts, never any response. It is a UI convenience, not
 * a cache and not a security boundary.
 *
 * A stored id is NOT authorization. Restoration only ever accepts an id that
 * appears in the session-scoped chat list the backend returned, and every
 * subsequent read still goes through the backend's own ownership check
 * (`get_chat_for_session`). A tampered or copied id therefore restores nothing.
 */

/** Versioned so a future shape change cannot be misread as this one. */
const SELECTED_CHAT_KEY = 'vietlaw.selected_chat_id.v1';

/**
 * Exact shape check, matched to the backend's own generator:
 * `f"chat_{uuid4().hex}"` in `sqlite_chat_store.py` -- "chat_" followed by
 * exactly 32 lowercase hex characters. Not a loose "looks plausible" pattern:
 * anything of a different length, uppercase, or non-hex is a value this
 * backend could never have issued, so it is rejected before it can reach a
 * request.
 */
const CHAT_ID_PATTERN = /^chat_[0-9a-f]{32}$/;

export function isValidChatId(value: unknown): value is string {
  return typeof value === 'string' && CHAT_ID_PATTERN.test(value);
}

function storage(): Storage | null {
  try {
    return typeof window === 'undefined' ? null : window.localStorage;
  } catch {
    // Private mode or a blocked origin: the feature degrades to "no memory".
    return null;
  }
}

/** The remembered chat id, or null when absent or malformed. */
export function readSelectedChatId(): string | null {
  const store = storage();
  if (!store) return null;
  let raw: string | null;
  try {
    raw = store.getItem(SELECTED_CHAT_KEY);
  } catch {
    return null;
  }
  if (raw === null) return null;
  if (!isValidChatId(raw)) {
    // Malformed values are cleared on sight rather than left to fail later.
    clearSelectedChatId();
    return null;
  }
  return raw;
}

export function writeSelectedChatId(chatId: string): void {
  const store = storage();
  if (!store || !isValidChatId(chatId)) return;
  try {
    store.setItem(SELECTED_CHAT_KEY, chatId);
  } catch {
    // A full or unavailable store must never break sending a message.
  }
}

export function clearSelectedChatId(): void {
  const store = storage();
  if (!store) return;
  try {
    store.removeItem(SELECTED_CHAT_KEY);
  } catch {
    // ignored on purpose
  }
}

export const SELECTED_CHAT_STORAGE_KEY = SELECTED_CHAT_KEY;
