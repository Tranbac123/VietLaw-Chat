import { vi } from 'vitest';

/**
 * Factory for the mocked `../api/client` module.
 *
 * Lives in its own module because `vi.mock` factories are hoisted above
 * imports and therefore cannot close over anything imported normally; test
 * files pull this in through a dynamic import inside the factory.
 *
 * `ApiClientError` is re-implemented rather than re-exported so `instanceof`
 * checks in App keep working against the mocked module identity.
 */
export function createApiClientMock() {
  class ApiClientError extends Error {
    constructor(
      public readonly code: string,
      message: string,
      public readonly status?: number,
    ) {
      super(message);
      this.name = 'ApiClientError';
    }
  }

  return {
    ApiClientError,
    analyze: vi.fn(),
    listChats: vi.fn(),
    getChat: vi.fn(),
    createChat: vi.fn(),
    deleteChat: vi.fn(),
    getHealth: vi.fn(),
  };
}
