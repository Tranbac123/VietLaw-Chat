import type { SourceObject } from '../api/types';

/**
 * The single validated-source boundary.
 *
 * Everything about source UI -- whether it renders at all, whether it is the
 * one-link or the disclosure variant, and every anchor href -- must come from
 * `selectSafeSources`. Previously one call site tested `sources.length` on the
 * raw array while the panel tested `source.url` for truthiness, so a response
 * carrying only unsafe URLs still rendered a source section with no usable
 * links.
 */

const ALLOWED_PROTOCOLS = new Set(['http:', 'https:']);

/**
 * True only for an absolute http(s) URL, decided by the platform URL parser.
 *
 * A prefix check is not enough: `new URL` is what rejects relative and
 * protocol-relative forms (both throw without a base) and what correctly reads
 * the scheme of `javascript:`, `data:`, `vbscript:`, `file:`, `blob:` and
 * `ftp:` rather than pattern-matching for them.
 */
export function isSafeSourceUrl(rawUrl: string | null | undefined): boolean {
  return safeSourceHref(rawUrl) !== null;
}

/** The normalized href for a safe URL, or null when it must not become a link. */
export function safeSourceHref(rawUrl: string | null | undefined): string | null {
  if (typeof rawUrl !== 'string') return null;

  const trimmed = rawUrl.trim();
  if (!trimmed) return null;

  let parsed: URL;
  try {
    // No base argument on purpose: relative ("/a/b") and protocol-relative
    // ("//host") inputs must fail rather than resolve against the app origin.
    parsed = new URL(trimmed);
  } catch {
    return null;
  }

  if (!ALLOWED_PROTOCOLS.has(parsed.protocol)) return null;
  if (!parsed.hostname) return null;

  return parsed.href;
}

export interface SafeSource {
  source: SourceObject;
  href: string;
}

/**
 * The safe, de-duplicated sources for a response, in their original order.
 * Two entries pointing at the same normalized URL are collapsed so the
 * disclosure never lists the same destination twice.
 */
export function selectSafeSources(sources: readonly SourceObject[] | null | undefined): SafeSource[] {
  if (!sources) return [];

  const seenHrefs = new Set<string>();
  const safeSources: SafeSource[] = [];

  for (const source of sources) {
    const href = safeSourceHref(source.url);
    if (href === null || seenHrefs.has(href)) continue;
    seenHrefs.add(href);
    safeSources.push({ source, href });
  }

  return safeSources;
}
