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
 * unsafe/malformed, or on any `http:` value at all when `isDev` is
 * false), and strips a valid trailing slash -- or reports "not
 * configured" (`undefined`) when nothing was set at all.
 */
export function normalizeApiBaseUrl(
  configuredValue: string | undefined,
  isDev: boolean,
): string | undefined {
  const trimmed = configuredValue?.trim();
  if (!trimmed) {
    return undefined;
  }
  let url: URL;
  try {
    url = new URL(trimmed);
  } catch {
    throw new ApiBaseUrlConfigError(`VIETLAW: VITE_API_BASE_URL is not a valid URL ("${trimmed}").`);
  }
  assertValidApiBaseUrl(trimmed, url, isDev);
  return trimmed.replace(/\/$/, '');
}
