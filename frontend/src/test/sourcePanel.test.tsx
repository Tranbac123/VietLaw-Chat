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

// -- Public Beta V0: official-source-search citation variant -----------------

function officialSearchSource(overrides: Partial<SourceObject> = {}): SourceObject {
  return {
    id: 'official_search_001',
    title: 'Nghị định về xử phạt vi phạm hành chính',
    source_name: 'Nghị định 168/2024/NĐ-CP',
    url: 'https://vbpl.vn/TW/Pages/vbpq-toanvan.aspx?ItemID=1',
    snippet: 'Nội dung điều khoản liên quan.',
    source_type: 'official_source',
    last_checked: '2026-07-31',
    document_title: 'Nghị định 168/2024/NĐ-CP',
    document_number: '168/2024/NĐ-CP',
    retrieved_at: '2026-07-31T10:00:00Z',
    ...overrides,
  };
}

describe('SourcePanel — official-source-search rendering', () => {
  it('renders the official-search citation block, distinct from the curated MODE_2D block', () => {
    render(<SourcePanel sources={[officialSearchSource()]} />);

    expect(screen.getByRole('heading', { name: 'Nguồn pháp luật chính thức' })).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Căn cứ pháp lý' })).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Xem nguồn chính thức' })).toBeInTheDocument();
  });

  it('shows the official domain hostname and the retrieval date', () => {
    render(<SourcePanel sources={[officialSearchSource()]} />);

    expect(screen.getByText('vbpl.vn', { exact: false })).toBeInTheDocument();
    expect(screen.getByText(/2026-07-31T10:00:00Z/)).toBeInTheDocument();
  });

  it('shows the document number and article number when present', () => {
    render(<SourcePanel sources={[officialSearchSource({ article_number: '12' })]} />);
    expect(screen.getByText(/Số 168\/2024\/NĐ-CP/)).toBeInTheDocument();
    expect(screen.getByText(/Điều 12/)).toBeInTheDocument();
  });

  it('a curated MODE_2D source never renders the official-search variant', () => {
    render(<SourcePanel sources={[citationSource()]} />);
    expect(screen.queryByRole('heading', { name: 'Nguồn pháp luật chính thức' })).not.toBeInTheDocument();
  });
});

// -- Legal Correction Round 1: traffic multi-provision citation rendering ---

const ND168_URL = 'https://vbpl.vn/TW/Pages/vbpq-toanvan.aspx?ItemID=173920&Keyword=';
const LUAT36_URL = 'https://vbpl.vn/TW/Pages/vbpq-toanvan.aspx?ItemID=170620';

function trafficCitationSource(overrides: Partial<SourceObject> = {}): SourceObject {
  return {
    id: 'traffic_red_light__motorcycle__safe_v1__primary_penalty',
    title: 'Căn cứ mức phạt',
    source_name: 'Nghị định 168/2024/NĐ-CP',
    url: ND168_URL,
    snippet: 'Mức phạt 4.000.000 - 6.000.000 đồng...',
    source_type: 'official_source',
    last_checked: '2026-07-31',
    document_title: 'Nghị định 168/2024/NĐ-CP',
    document_number: '168/2024/NĐ-CP',
    article_number: '7',
    clause_number: '7',
    point_number: 'c',
    citation_role: 'primary_penalty',
    relevance_note: 'Điều 7 khoản 7 điểm c — Mức phạt 4.000.000 - 6.000.000 đồng.',
    ...overrides,
  };
}

function redLightThreeCitations(): SourceObject[] {
  return [
    trafficCitationSource(),
    trafficCitationSource({
      id: 'traffic_red_light__motorcycle__safe_v1__licence_point_deduction',
      title: 'Căn cứ trừ điểm GPLX',
      url: ND168_URL, // deliberately the SAME url as the primary_penalty citation
      article_number: '7',
      clause_number: '13',
      point_number: 'b',
      citation_role: 'licence_point_deduction',
      relevance_note: 'Điều 7 khoản 13 điểm b — Trừ 4 điểm giấy phép lái xe.',
    }),
    trafficCitationSource({
      id: 'traffic_red_light__motorcycle__safe_v1__signal_interpretation',
      title: 'Quy tắc tín hiệu giao thông',
      url: LUAT36_URL,
      document_title: 'Luật Trật tự, an toàn giao thông đường bộ 36/2024/QH15',
      document_number: '36/2024/QH15',
      article_number: '11',
      clause_number: '1-4',
      point_number: null,
      citation_role: 'signal_interpretation',
      relevance_note: 'Điều 11 khoản 1-4 — Hiệu lệnh người điều khiển giao thông ưu tiên hơn đèn.',
    }),
  ];
}

describe('SourcePanel — traffic multi-provision citation rendering (Legal Correction Round 1)', () => {
  it('renders all three role-labeled cards directly, with no click required', () => {
    render(<SourcePanel sources={redLightThreeCitations()} />);

    expect(screen.getByRole('heading', { name: 'Căn cứ mức phạt' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Căn cứ trừ điểm GPLX' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Quy tắc tín hiệu giao thông' })).toBeInTheDocument();
    // No collapse-behind-a-toggle control for this variant.
    expect(screen.queryByRole('button', { name: /Nguồn tham khảo/ })).not.toBeInTheDocument();
  });

  it('two citations sharing the exact same document URL are NOT collapsed into one card', () => {
    render(<SourcePanel sources={redLightThreeCitations()} />);

    const links = screen.getAllByRole('link', { name: 'Xem văn bản chính thức' });
    expect(links).toHaveLength(3);
    const nd168Links = links.filter((link) => link.getAttribute('href') === ND168_URL);
    expect(nd168Links).toHaveLength(2); // primary_penalty + licence_point_deduction, distinct cards
  });

  it('each citation card links to its own official URL', () => {
    render(<SourcePanel sources={redLightThreeCitations()} />);

    const signalHeading = screen.getByRole('heading', { name: 'Quy tắc tín hiệu giao thông' });
    const signalCard = signalHeading.closest('.legal-citation');
    expect(signalCard).not.toBeNull();
    const signalLink = signalCard!.querySelector('a');
    expect(signalLink).toHaveAttribute('href', LUAT36_URL);
  });

  it('never labels the signal-interpretation citation as the penalty provision', () => {
    render(<SourcePanel sources={redLightThreeCitations()} />);

    const signalHeading = screen.getByRole('heading', { name: 'Quy tắc tín hiệu giao thông' });
    const signalCard = signalHeading.closest('.legal-citation');
    expect(signalCard).not.toBeNull();
    expect(signalCard!.textContent).not.toContain('Căn cứ mức phạt');
  });

  it('renders a multi-khoản clause range ("khoản 1-4") without inventing a điểm', () => {
    render(<SourcePanel sources={redLightThreeCitations()} />);

    expect(screen.getByText('Điều 11 khoản 1-4')).toBeInTheDocument();
  });

  it('a single-citation rule (e.g. the helmet rule) still uses its role heading, not the generic one', () => {
    render(
      <SourcePanel
        sources={[
          trafficCitationSource({
            id: 'traffic_no_helmet__motorcycle__driver_safe_v1__primary_penalty',
            document_title: 'Nghị định 168/2024/NĐ-CP',
            article_number: '7',
            clause_number: '2',
            point_number: 'h',
            relevance_note: 'Điều 7 khoản 2 điểm h — Mức phạt 400.000 - 600.000 đồng.',
          }),
        ]}
      />,
    );

    expect(screen.getByRole('heading', { name: 'Căn cứ mức phạt' })).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Căn cứ pháp lý' })).not.toBeInTheDocument();
    expect(screen.getAllByRole('link')).toHaveLength(1);
  });

  it('a response mixing a traffic citation with a non-traffic source falls back to the generic disclosure', async () => {
    const user = userEvent.setup();
    render(<SourcePanel sources={[trafficCitationSource(), genericSource()]} />);

    // Not every safe source is a traffic citation, so the traffic-only fast
    // path must not apply -- falls back to the existing disclosure variant.
    await user.click(screen.getByRole('button', { name: /Nguồn tham khảo \(2\)/ }));
    expect(screen.getByRole('link', { name: /Danh mục chứng cứ/ })).toBeInTheDocument();
  });
});
