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

  it('rejects a bare trailing slash (MEDIUM-01: no path exception, not even an empty one)', () => {
    expect(() => normalizeApiBaseUrl('https://vietlaw-backend.up.railway.app/', false)).toThrow(
      ApiBaseUrlConfigError,
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

  it('rejects a trailing slash (MEDIUM-01: exact origin only, no path at all)', () => {
    expect(() => normalizeApiBaseUrl('https://backend.example.com/', false)).toThrow(
      ApiBaseUrlConfigError,
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

/**
 * Bounded pre-deploy hardening: `VITE_API_BASE_URL` must be an exact
 * origin -- scheme + host(+port), nothing else. A path previously passed
 * validation and `vite build` (e.g. `https://x.up.railway.app/api`),
 * contradicting `frontend/.env.production.example`'s documented "no path"
 * contract and doubling up with request paths the app itself appends.
 */
describe('normalizeApiBaseUrl exact-origin (no path) boundary', () => {
  const pathBearingUrls: Array<[string, string]> = [
    ['https://x.up.railway.app/api', 'a real path'],
    ['https://x.up.railway.app/api/', 'a real path with trailing slash'],
    ['https://x.up.railway.app/foo', 'an unrelated path'],
  ];

  it.each(pathBearingUrls)('rejects %s (%s) in production', (value) => {
    expect(() => normalizeApiBaseUrl(value, false)).toThrow(ApiBaseUrlConfigError);
  });

  it.each(pathBearingUrls)('rejects %s (%s) in development too', (value) => {
    expect(() => normalizeApiBaseUrl(value, true)).toThrow(ApiBaseUrlConfigError);
  });

  it('accepts a bare origin with no path', () => {
    expect(normalizeApiBaseUrl('https://x.up.railway.app', false)).toBe(
      'https://x.up.railway.app',
    );
  });

  it('rejects a bare origin with only a trailing slash (MEDIUM-01: no exception for it)', () => {
    expect(() => normalizeApiBaseUrl('https://x.up.railway.app/', false)).toThrow(
      ApiBaseUrlConfigError,
    );
  });
});

/**
 * Review finding MEDIUM-01: WHATWG `URL` normalizes dot segments (and
 * their percent-encoded forms) while parsing, so a raw value like
 * `https://example.com/a/..` or `https://example.com/%2e` previously
 * parsed to a `pathname` of `/` -- identical to a bare origin. A first
 * fix compared the raw (trimmed) value against `url.origin`, but still
 * carved out an exception for a raw value equal to `${url.origin}/` --
 * which is itself a normalized-form special case, and review found it
 * insufficient (a bare trailing slash must ALSO be rejected: the contract
 * is an exact origin, and a trailing slash is a path, even an empty one).
 * The current fix (`assertRawExactOriginShape`) rejects PRE-PARSE, purely
 * syntactically: the entire remainder after `scheme://` must contain none
 * of `/ \ ? #`. A path, a dot segment, its percent-encoded form, and a
 * bare trailing slash all necessarily contain a literal `/` (or `\`,
 * normalized to `/` by the parser for special schemes) separating them
 * from the authority -- so this single rule rejects all of them without
 * the parser ever running on the rejected value, and without enumerating
 * dot-segment encodings one by one.
 */
describe('normalizeApiBaseUrl raw-value exact-origin boundary (MEDIUM-01)', () => {
  const validExactOrigins: Array<[string, string]> = [
    ['https://example.com', 'bare origin, no port'],
    ['https://example.com:8443', 'bare origin, explicit port'],
  ];

  it.each(validExactOrigins)('accepts %s (%s)', (value) => {
    expect(normalizeApiBaseUrl(value, false)).toBe(value);
  });

  const pathShapedUrls: Array<[string, string]> = [
    ['https://example.com/', 'bare trailing slash -- an empty path is still a path'],
    ['https://example.com/api', 'ordinary path'],
    ['https://example.com/api/', 'ordinary path with trailing slash'],
    ['https://example.com/.', 'single dot segment'],
    ['https://example.com/..', 'double dot segment'],
    ['https://example.com/a/..', 'trailing double dot segment after a real path'],
    ['https://example.com/%2e', 'percent-encoded dot segment, lowercase'],
    ['https://example.com/%2E', 'percent-encoded dot segment, uppercase'],
    ['https://example.com/%2e%2e', 'percent-encoded double dot segment, lowercase'],
    ['https://example.com/%2E%2E', 'percent-encoded double dot segment, uppercase'],
    ['https://example.com/a/%2e%2e', 'percent-encoded double dot segment after a real path'],
    ['https://example.com/a/%2E%2E/', 'percent-encoded double dot segment with trailing slash'],
    ['https://example.com\\foo', 'backslash path (normalized to / for special schemes)'],
    ['https://example.com?x=1', 'query string'],
    ['https://example.com#x', 'fragment'],
    ['https://user:pass@example.com', 'embedded credentials'],
    ['invalid-value', 'not a URL at all'],
  ];

  it.each(pathShapedUrls)('rejects %s (%s) in production', (value) => {
    expect(() => normalizeApiBaseUrl(value, false)).toThrow(ApiBaseUrlConfigError);
  });

  it.each(pathShapedUrls)('rejects %s (%s) in development too', (value) => {
    expect(() => normalizeApiBaseUrl(value, true)).toThrow(ApiBaseUrlConfigError);
  });

  it('rejects http:// loopback dot-segment and trailing-slash bypass attempts in development', () => {
    expect(() => normalizeApiBaseUrl('http://localhost:8000/%2e', true)).toThrow(
      ApiBaseUrlConfigError,
    );
    expect(() => normalizeApiBaseUrl('http://localhost:8000/..', true)).toThrow(
      ApiBaseUrlConfigError,
    );
    expect(() => normalizeApiBaseUrl('http://localhost:8000/', true)).toThrow(
      ApiBaseUrlConfigError,
    );
  });
});
