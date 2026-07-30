/**
 * MODE_2D: the source panel becomes a legal-citation panel when the backend
 * has resolved curated article-level metadata for a source, and falls back
 * to the original generic display for every source without it.
 */
import { afterEach, describe, expect, it } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { SourceObject } from '../api/types';
import { SourcePanel } from '../components/SourcePanel';

afterEach(() => {
  cleanup();
});

const CONGBAO_URL = 'https://congbao.chinhphu.vn/van-ban/luat-so-91-2015-qh13-18397.htm';

function citationSource(overrides: Partial<SourceObject> = {}): SourceObject {
  return {
    id: 'civil_deposit_001',
    title: 'Đặt cọc để bảo đảm giao kết hoặc thực hiện hợp đồng',
    source_name: 'Bộ luật Dân sự 2015 - Điều 328',
    url: CONGBAO_URL,
    snippet: 'Đặt cọc là việc...',
    source_type: 'official_source',
    last_checked: '2026-07-30',
    document_title: 'Bộ luật Dân sự 2015',
    document_number: '91/2015/QH13',
    article_number: '328',
    article_title: 'Đặt cọc',
    clause_numbers: [1, 2],
    applicable_clause: 2,
    relevance_note:
      'Quy định này liên quan vì khoản đặt cọc được dùng để bảo đảm việc giao kết ' +
      'hoặc thực hiện hợp đồng thuê nhà. Việc áp dụng cụ thể còn phụ thuộc thỏa thuận ' +
      'đặt cọc và bên nào từ chối hoặc không thực hiện cam kết.',
    ...overrides,
  };
}

function genericSource(overrides: Partial<SourceObject> = {}): SourceObject {
  return {
    id: 'civil_rental_001',
    title: 'Danh mục chứng cứ',
    source_name: 'Hướng dẫn thực hành',
    url: 'https://example.gov.vn/checklist',
    snippet: 'Chuẩn bị hồ sơ...',
    source_type: 'legal_snippet',
    last_checked: '2026-07-30',
    ...overrides,
  };
}

describe('SourcePanel — legal-citation rendering', () => {
  it('renders the citation panel with article, clause, document identity and relevance visible without opening the link', () => {
    render(<SourcePanel sources={[citationSource()]} />);

    expect(screen.getByRole('heading', { level: 3, name: 'Căn cứ pháp lý' })).toBeInTheDocument();
    expect(screen.getByText('Khoản 2 Điều 328 — Bộ luật Dân sự 2015, số 91/2015/QH13')).toBeInTheDocument();
    expect(screen.getByText(/Quy định này liên quan vì/)).toBeInTheDocument();

    const link = screen.getByRole('link', { name: 'Xem văn bản chính thức' });
    expect(link).toHaveAttribute('href', CONGBAO_URL);
  });

  it('exposes the citation label as a level-3 heading for assistive-technology navigation (L-02)', () => {
    render(<SourcePanel sources={[citationSource()]} />);

    const heading = screen.getByRole('heading', { name: 'Căn cứ pháp lý' });
    expect(heading.tagName).toBe('H3');
  });

  it('omits the clause prefix when no clause was resolved, without inventing one', () => {
    render(<SourcePanel sources={[citationSource({ applicable_clause: null })]} />);

    expect(screen.getByText('Điều 328 — Bộ luật Dân sự 2015, số 91/2015/QH13')).toBeInTheDocument();
    expect(screen.queryByText(/^Khoản/)).not.toBeInTheDocument();
  });

  it('renders exactly one citation, never a duplicate generic source card alongside it', () => {
    render(<SourcePanel sources={[citationSource()]} />);

    expect(screen.getAllByRole('heading', { name: 'Căn cứ pháp lý' })).toHaveLength(1);
    expect(screen.queryByText('Nguồn tham khảo')).not.toBeInTheDocument();
    expect(screen.getAllByRole('link')).toHaveLength(1);
  });

  it('the citation link always uses the backend-supplied source_url, never a substituted one', () => {
    // The panel must render exactly what the backend sends -- it has no
    // logic of its own that could substitute a different URL. The migrated
    // curated data (data/legal_snippets.json, verified separately in the
    // official-source-migration suite) is what actually keeps the legacy
    // vbpl.moj.gov.vn URL out of a real response; this test only proves the
    // panel is a faithful pass-through, using the real migrated URL.
    render(<SourcePanel sources={[citationSource({ url: CONGBAO_URL })]} />);

    const link = screen.getByRole('link', { name: 'Xem văn bản chính thức' });
    expect(link).toHaveAttribute('href', CONGBAO_URL);
    expect(link.getAttribute('href')).not.toContain('vbpl.moj.gov.vn');
  });

  it('falls back to the existing generic display for a source without article-level metadata', () => {
    render(<SourcePanel sources={[genericSource()]} />);

    expect(screen.queryByRole('heading', { name: 'Căn cứ pháp lý' })).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Nguồn tham khảo' })).toBeInTheDocument();
  });

  it('renders no empty section for a source-less response', () => {
    const { container } = render(<SourcePanel sources={[]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('mixed sources: the citation renders for the article-level source, generic link for the other', async () => {
    const user = userEvent.setup();
    render(<SourcePanel sources={[citationSource(), genericSource()]} />);

    // Two sources -> the disclosure variant.
    await user.click(screen.getByRole('button', { name: /Nguồn tham khảo \(2\)/ }));

    expect(screen.getByRole('heading', { name: 'Căn cứ pháp lý' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Danh mục chứng cứ/ })).toBeInTheDocument();
  });
});
