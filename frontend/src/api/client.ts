import type {
  AnalyzeRequest,
  AnalyzeResponse,
  ApiErrorResponse,
  ChatCreateResponse,
  ChatDetailResponse,
  ChatListResponse,
  DeleteChatResponse,
} from './types';

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000').replace(/\/$/, '');

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

export function getChat(chatId: string): Promise<ChatDetailResponse> {
  return request(`/api/chats/${encodeURIComponent(chatId)}`);
}

export function deleteChat(chatId: string): Promise<DeleteChatResponse> {
  return request(`/api/chats/${encodeURIComponent(chatId)}`, { method: 'DELETE' });
}

export function getHealth(): Promise<unknown> {
  return request('/api/health');
}
