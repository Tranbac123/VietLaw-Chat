/**
 * VietLaw Limited Demo Deployment Readiness V1: a production build must
 * reject or visibly fail when `VITE_API_BASE_URL` is missing, rather than
 * silently calling `localhost`.
 *
 * `normalizeApiBaseUrl` (the environment-parameterized half of that
 * decision -- validate/trim/strip-trailing-slash/"not configured") is
 * unit-tested here with plain arguments, including an explicit `isDev`
 * boolean (Deployment Correction Round 2, MEDIUM-03). The DEV-vs-PROD
 * FALLBACK branch itself (the literal `'http://localhost:8000'` string)
 * intentionally is NOT extracted into a parameterized, testable function:
 * doing so once (during initial implementation) defeated Vite's
 * compile-time `import.meta.env.DEV` substitution + esbuild's dead-code
 * elimination, leaving that literal string sitting inert but PRESENT in
 * the production bundle -- exactly what this task's frontend production
 * smoke check (`grep`-verified separately, see
 * VIETLAW_LIMITED_DEMO_DEPLOYMENT_READINESS_REPORT_V1.md §16) must catch.
 * That behavior is proven against the actual built `dist/` output instead,
 * not by a unit test that would reintroduce the same regression to make
 * itself possible. Passing `isDev` as a plain boolean ARGUMENT into
 * `normalizeApiBaseUrl` does not have this problem -- it does not
 * introduce or depend on that literal string at all.
 */
import { describe, expect, it } from 'vitest';
import { ApiBaseUrlConfigError, normalizeApiBaseUrl } from '../api/client';

describe('normalizeApiBaseUrl', () => {
  it('returns the configured URL unchanged when it has no trailing slash', () => {
    expect(normalizeApiBaseUrl('https://vietlaw-backend.up.railway.app', false)).toBe(
      'https://vietlaw-backend.up.railway.app',
    );
  });

  it('strips a trailing slash', () => {
    expect(normalizeApiBaseUrl('https://vietlaw-backend.up.railway.app/', false)).toBe(
      'https://vietlaw-backend.up.railway.app',
    );
  });

  it('trims surrounding whitespace', () => {
    expect(normalizeApiBaseUrl('  https://vietlaw-backend.up.railway.app  ', false)).toBe(
      'https://vietlaw-backend.up.railway.app',
    );
  });

  it('reports "not configured" (undefined) for missing, empty, or whitespace-only values', () => {
    expect(normalizeApiBaseUrl(undefined, false)).toBeUndefined();
    expect(normalizeApiBaseUrl('', false)).toBeUndefined();
    expect(normalizeApiBaseUrl('   ', false)).toBeUndefined();
    expect(normalizeApiBaseUrl(undefined, true)).toBeUndefined();
  });
});

/**
 * Deployment Correction Round 1 (MEDIUM-04): strict validation of an
 * explicitly configured `VITE_API_BASE_URL`. Trim-only normalization
 * previously accepted anything, including scheme confusion
 * (`javascript:`), relative/protocol-relative values, and URLs carrying
 * credentials, a query string, or a fragment -- all of which must now be
 * rejected before any `fetch` ever runs, in EVERY environment.
 */
describe('normalizeApiBaseUrl strict validation (environment-independent)', () => {
  it('accepts a plain https origin in both dev and prod', () => {
    expect(normalizeApiBaseUrl('https://backend.example.com', false)).toBe(
      'https://backend.example.com',
    );
    expect(normalizeApiBaseUrl('https://backend.example.com', true)).toBe(
      'https://backend.example.com',
    );
  });

  it('accepts and normalizes a trailing slash', () => {
    expect(normalizeApiBaseUrl('https://backend.example.com/', false)).toBe(
      'https://backend.example.com',
    );
  });

  const rejectedInBothEnvironments: Array<[string, string]> = [
    ['javascript:alert(1)', 'javascript: scheme'],
    ['not-a-url', 'not a URL at all'],
    ['/backend', 'relative path'],
    ['//attacker.example', 'protocol-relative URL'],
    ['ftp://example.com', 'non-http(s) scheme'],
    ['https://user:password@example.com', 'embedded credentials'],
    ['https://example.com?token=x', 'query string'],
    ['https://example.com/#fragment', 'fragment'],
  ];

  it.each(rejectedInBothEnvironments)('rejects %s (%s) in production', (value) => {
    expect(() => normalizeApiBaseUrl(value, false)).toThrow(ApiBaseUrlConfigError);
  });

  it.each(rejectedInBothEnvironments)('rejects %s (%s) in development too', (value) => {
    expect(() => normalizeApiBaseUrl(value, true)).toThrow(ApiBaseUrlConfigError);
  });
});

/**
 * Deployment Correction Round 2 (MEDIUM-03): the independent review found
 * that `http://localhost:8000` (and `http://127.0.0.1:8000`) was accepted
 * and embedded into an ACTUAL production build, because the previous
 * validation had no environment awareness at all -- it allowed local HTTP
 * unconditionally. Production must now reject every HTTP URL, including
 * all loopback hostnames; only a development build may accept them.
 */
describe('normalizeApiBaseUrl production HTTPS-only boundary', () => {
  const loopbackHttpUrls: Array<[string, string]> = [
    ['http://localhost:8000', 'http://localhost'],
    ['http://127.0.0.1:8000', 'http://127.0.0.1'],
    ['http://[::1]:8000', 'http://[::1]'],
  ];

  it.each(loopbackHttpUrls)('rejects %s (%s) in production (isDev=false)', (value) => {
    expect(() => normalizeApiBaseUrl(value, false)).toThrow(ApiBaseUrlConfigError);
  });

  it.each(loopbackHttpUrls)('accepts %s (%s) in development (isDev=true)', (value) => {
    expect(normalizeApiBaseUrl(value, true)).toBe(value);
  });

  it('rejects a non-loopback http:// URL even in development', () => {
    expect(() => normalizeApiBaseUrl('http://backend.example.com', true)).toThrow(
      ApiBaseUrlConfigError,
    );
  });

  it('rejects a non-loopback http:// URL in production', () => {
    expect(() => normalizeApiBaseUrl('http://backend.example.com', false)).toThrow(
      ApiBaseUrlConfigError,
    );
  });
});
