import type {
  AnalyzeRequest,
  AnalyzeResponse,
  ApiErrorResponse,
  ChatCreateResponse,
  ChatDetailResponse,
  ChatListResponse,
  DeleteChatResponse,
} from './types';
import { ApiBaseUrlConfigError, normalizeApiBaseUrl } from '../lib/apiBaseUrl';

// Re-exported for existing importers/tests -- the validation logic itself
// now lives in `../lib/apiBaseUrl.ts` (Deployment Correction Round 2,
// MEDIUM-03) since `vite.config.ts` needs to import it too, at build time,
// from a Node context that has no `import.meta.env`. This file remains
// the one place that reads `import.meta.env.DEV`/`import.meta.env.
// VITE_API_BASE_URL` for the RUNTIME bundle.
export { ApiBaseUrlConfigError, normalizeApiBaseUrl };

/**
 * `VITE_API_BASE_URL` is embedded at BUILD time (Vite convention -- it is
 * never re-read at runtime and is not a secret). `import.meta.env.DEV` is
 * referenced DIRECTLY here (not passed in as a parameter) so Vite's
 * compile-time text substitution, followed by esbuild's dead-code
 * elimination on the resulting literal `if (false)`, removes the
 * `'http://localhost:8000'` string from a production bundle entirely --
 * not just leaves it unreachable. A production build that silently fell
 * back to it when the URL was left unset would look fully deployed while
 * quietly calling nothing real; local development keeps the convenience
 * default so `npm run dev` still works with zero configuration.
 */
const _configuredApiBaseUrl = normalizeApiBaseUrl(
  import.meta.env.VITE_API_BASE_URL,
  import.meta.env.DEV,
);
const API_BASE_URL =
  _configuredApiBaseUrl ??
  (import.meta.env.DEV
    ? 'http://localhost:8000'
    : (() => {
        throw new Error(
          'VIETLAW: VITE_API_BASE_URL is not set in this production build. Set it ' +
            'at build time (see frontend/.env.production.example) and rebuild -- ' +
            'the app must not silently call localhost in production.',
        );
      })());

export class ApiClientError extends Error {
  constructor(
    public readonly code: string,
    message: string,
    public readonly status?: number,
  ) {
    super(message);
    this.name = 'ApiClientError';
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;

  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      headers: {
        ...(init?.body ? { 'Content-Type': 'application/json' } : {}),
        ...init?.headers,
      },
      ...init,
    });
  } catch {
    throw new ApiClientError('network_error', 'Không thể kết nối backend. Vui lòng kiểm tra server.');
  }

  if (!response.ok) {
    const body = await response.json().catch(() => null) as ApiErrorResponse | null;
    throw new ApiClientError(
      body?.error?.code ?? `http_${response.status}`,
      body?.error?.message ?? 'Không thể kết nối backend. Vui lòng kiểm tra server.',
      response.status,
    );
  }

  return response.json() as Promise<T>;
}

export function analyze(payload: AnalyzeRequest): Promise<AnalyzeResponse> {
  return request('/api/analyze', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function createChat(sessionId: string): Promise<ChatCreateResponse> {
  return request('/api/chats', {
    method: 'POST',
    body: JSON.stringify({ session_id: sessionId }),
  });
}

export function listChats(sessionId: string): Promise<ChatListResponse> {
  return request(`/api/chats?session_id=${encodeURIComponent(sessionId)}`);
}

export function getChat(chatId: string, sessionId: string): Promise<ChatDetailResponse> {
  return request(
    `/api/chats/${encodeURIComponent(chatId)}?session_id=${encodeURIComponent(sessionId)}`,
  );
}

export function deleteChat(chatId: string, sessionId: string): Promise<DeleteChatResponse> {
  return request(
    `/api/chats/${encodeURIComponent(chatId)}?session_id=${encodeURIComponent(sessionId)}`,
    { method: 'DELETE' },
  );
}

export function getHealth(): Promise<unknown> {
  return request('/api/health');
}
