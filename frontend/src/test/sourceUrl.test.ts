/**
 * Phase A: the validated-source boundary.
 *
 * Only absolute http(s) URLs may ever become links, decided by the platform
 * URL parser rather than a string-prefix check.
 */
import { describe, expect, it } from 'vitest';
import type { SourceObject } from '../api/types';
import { isSafeSourceUrl, selectSafeSources } from '../lib/sourceUrl';

function makeSource(id: string, url: string | null): SourceObject {
  return {
    id,
    title: `Tiêu đề ${id}`,
    source_name: 'Nguồn',
    url,
    snippet: 'Trích dẫn',
    source_type: 'official_source',
    last_checked: '2026-01-01',
  };
}

describe('isSafeSourceUrl', () => {
  it('accepts absolute http and https URLs', () => {
    expect(isSafeSourceUrl('https://thuvienphapluat.vn/van-ban/123')).toBe(true);
    expect(isSafeSourceUrl('http://example.gov.vn/a')).toBe(true);
    expect(isSafeSourceUrl('  https://example.com/padded  ')).toBe(true);
    expect(isSafeSourceUrl('HTTPS://EXAMPLE.COM/UPPER')).toBe(true);
  });

  it('rejects empty and whitespace-only values', () => {
    expect(isSafeSourceUrl('')).toBe(false);
    expect(isSafeSourceUrl('   ')).toBe(false);
    expect(isSafeSourceUrl(null)).toBe(false);
    expect(isSafeSourceUrl(undefined)).toBe(false);
  });

  it('rejects malformed, relative and protocol-relative URLs', () => {
    expect(isSafeSourceUrl('not a url')).toBe(false);
    expect(isSafeSourceUrl('http://')).toBe(false);
    expect(isSafeSourceUrl('/van-ban/123')).toBe(false);
    expect(isSafeSourceUrl('./relative')).toBe(false);
    expect(isSafeSourceUrl('example.com/no-scheme')).toBe(false);
    expect(isSafeSourceUrl('//example.com/protocol-relative')).toBe(false);
  });

  it('rejects every non-HTTP(S) scheme', () => {
    for (const url of [
      'javascript:alert(1)',
      'JavaScript:alert(1)',
      'data:text/html;base64,PHNjcmlwdD4=',
      'vbscript:msgbox(1)',
      'file:///etc/passwd',
      'blob:https://example.com/uuid',
      'ftp://example.com/file.pdf',
      'mailto:someone@example.com',
      'tel:+842838222222',
    ]) {
      expect(isSafeSourceUrl(url), url).toBe(false);
    }
  });
});

describe('selectSafeSources', () => {
  it('returns nothing when there are no sources or none are safe', () => {
    expect(selectSafeSources([])).toEqual([]);
    expect(selectSafeSources(null)).toEqual([]);
    expect(selectSafeSources([
      makeSource('s1', 'javascript:alert(1)'),
      makeSource('s2', null),
      makeSource('s3', '/relative'),
    ])).toEqual([]);
  });

  it('keeps every valid source and drops only the unsafe ones', () => {
    const safe = selectSafeSources([
      makeSource('s1', 'https://a.example.com/1'),
      makeSource('s2', 'javascript:alert(1)'),
      makeSource('s3', 'https://b.example.com/2'),
      makeSource('s4', 'https://c.example.com/3'),
    ]);

    expect(safe.map(({ source }) => source.id)).toEqual(['s1', 's3', 's4']);
  });

  it('de-duplicates identical normalized URLs', () => {
    const safe = selectSafeSources([
      makeSource('s1', 'https://example.com/a'),
      makeSource('s2', 'https://example.com/a'),
      makeSource('s3', '  https://example.com/a  '),
      makeSource('s4', 'https://example.com/b'),
    ]);

    expect(safe).toHaveLength(2);
    expect(safe.map(({ source }) => source.id)).toEqual(['s1', 's4']);
  });

  it('preserves the original order of valid sources', () => {
    const safe = selectSafeSources([
      makeSource('first', 'https://example.com/1'),
      makeSource('second', 'https://example.com/2'),
      makeSource('third', 'https://example.com/3'),
    ]);
    expect(safe.map(({ source }) => source.id)).toEqual(['first', 'second', 'third']);
  });
});
