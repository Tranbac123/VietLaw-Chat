/**
 * Deployment Correction Round 2 (MEDIUM-03): `VITE_API_BASE_URL` validation,
 * extracted to its own module with NO `import.meta.env` reference anywhere
 * in it, so it can be imported from BOTH `src/api/client.ts` (runtime,
 * bundled into the app) AND `vite.config.ts` (Node/build-time, evaluated
 * before any bundling happens) without either context tripping over the
 * other's environment. `vite.config.ts` uses this to fail the `vite build`
 * command itself when a configured value is invalid for the target
 * environment -- catching a malformed/unsafe/HTTP-in-production value
 * before a single byte of `dist/` is ever written, not merely at runtime
 * in the browser.
 */

/**
 * Thrown when an explicitly configured `VITE_API_BASE_URL` fails strict
 * validation -- distinct from "not configured at all" (reported as
 * `undefined`, letting the caller decide what happens next). A
 * malformed/unsafe value must fail closed before any `fetch` ever runs,
 * and (Round 2) before a production `dist/` bundle is ever produced.
 */
export class ApiBaseUrlConfigError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'ApiBaseUrlConfigError';
  }
}

//: The ONLY hostnames `http:` may ever be used with, and only when `isDev`
//: is true. An independent review's actual production build with
//: `VITE_API_BASE_URL=http://localhost:8000` succeeded and embedded
//: `localhost:8000` in the bundle, because the previous check had no
//: environment parameter at all -- it allowed local HTTP unconditionally,
//: in every build. `[::1]` (bracketed, as `URL.hostname` renders an IPv6
//: literal) is the loopback form `http://[::1]:<port>` requires.
const _DEV_ONLY_HTTP_HOSTNAMES = new Set(['localhost', '127.0.0.1', '[::1]']);

//: Review finding MEDIUM-01 (second pass): the exact-origin boundary must
//: reject the raw configured value SYNTACTICALLY, before WHATWG `URL`
//: ever gets a chance to normalize it. A prior fix compared the raw value
//: against `url.origin` (with a trailing-slash exception) -- but WHATWG
//: normalization means many distinct raw strings collapse to the same
//: `origin`/`pathname`, and enumerating which of those normalized forms
//: to special-case (a bare trailing slash today, some other equivalent
//: form tomorrow) is exactly the blacklist-of-encodings trap this must
//: avoid. Requiring the ENTIRE remainder after `scheme://` to contain
//: none of `/ \ ? #` sidesteps normalization entirely: a path, a dot
//: segment, its percent-encoded form, and a bare trailing slash all
//: necessarily start with a literal `/` (or, since backslash is
//: URL-normalized to `/` for special schemes, a literal `\`) separating
//: them from the authority -- so all of them are rejected by this single
//: syntactic rule, without the parser ever running on the rejected value.
const _RAW_EXACT_ORIGIN_SHAPE = /^https?:\/\/[^/\\?#]+$/i;

/**
 * Rejects a configured value that is not syntactically `scheme://authority`
 * with nothing else -- no path (including a bare trailing slash), no
 * backslash, no query, no fragment -- before it is ever handed to `new
 * URL(...)` for semantic parsing. See `_RAW_EXACT_ORIGIN_SHAPE` for why
 * this must run pre-normalization rather than post-parse.
 */
function assertRawExactOriginShape(value: string): void {
  if (!_RAW_EXACT_ORIGIN_SHAPE.test(value)) {
    throw new ApiBaseUrlConfigError(
      'VIETLAW: VITE_API_BASE_URL must be an exact origin (scheme + host, ' +
        `optionally + port) with nothing else -- no path, trailing slash, ` +
        `backslash, query, or fragment (got "${value}").`,
    );
  }
}

/**
 * Strict validation for an explicitly configured `VITE_API_BASE_URL`.
 * `isDev` is the ONLY thing that can permit `http:`, and only for
 * `localhost`/`127.0.0.1`/`[::1]`. In production (`isDev=false`), every
 * `http:` URL is rejected, including all three loopback hostnames -- there
 * is no "local HTTP" exception once a build is a production build,
 * regardless of what hostname is configured. Also rejects embedded
 * credentials, a query string, or a fragment. `new URL(value)` with no
 * base argument itself rejects relative paths (`/backend`),
 * protocol-relative values (`//attacker.example`), and non-URL strings
 * (`not-a-url`) by throwing.
 */
function assertValidApiBaseUrl(value: string, url: URL, isDev: boolean): void {
  const isDevOnlyLocalHttp =
    isDev && url.protocol === 'http:' && _DEV_ONLY_HTTP_HOSTNAMES.has(url.hostname);
  if (url.protocol !== 'https:' && !isDevOnlyLocalHttp) {
    throw new ApiBaseUrlConfigError(
      `VIETLAW: VITE_API_BASE_URL must use https:// (got "${value}").`,
    );
  }
  if (url.username || url.password) {
    throw new ApiBaseUrlConfigError(
      'VIETLAW: VITE_API_BASE_URL must not contain embedded credentials.',
    );
  }
  if (url.search) {
    throw new ApiBaseUrlConfigError('VIETLAW: VITE_API_BASE_URL must not contain a query string.');
  }
  if (url.hash) {
    throw new ApiBaseUrlConfigError('VIETLAW: VITE_API_BASE_URL must not contain a fragment.');
  }
  if (!url.hostname) {
    throw new ApiBaseUrlConfigError('VIETLAW: VITE_API_BASE_URL must have a valid hostname.');
  }
}

/**
 * Trims whitespace, validates an explicitly configured value strictly for
 * the given environment (throwing `ApiBaseUrlConfigError` on anything
 * unsafe/malformed, on a value that isn't syntactically an exact
 * `scheme://authority` origin, or on any `http:` value at all when
 * `isDev` is false) -- or reports "not configured" (`undefined`) when
 * nothing was set at all. The raw-shape check runs BEFORE `new URL(...)`
 * parsing (see `assertRawExactOriginShape`), so a value is never accepted
 * on the strength of how the parser happened to normalize it.
 */
export function normalizeApiBaseUrl(
  configuredValue: string | undefined,
  isDev: boolean,
): string | undefined {
  const trimmed = configuredValue?.trim();
  if (!trimmed) {
    return undefined;
  }
  assertRawExactOriginShape(trimmed);
  let url: URL;
  try {
    url = new URL(trimmed);
  } catch {
    throw new ApiBaseUrlConfigError(`VIETLAW: VITE_API_BASE_URL is not a valid URL ("${trimmed}").`);
  }
  assertValidApiBaseUrl(trimmed, url, isDev);
  return trimmed;
}
