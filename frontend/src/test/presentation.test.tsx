/**
 * Phase A rendered presentation: typography scale, ordered-list numbering and
 * the compact source CTA, asserted through the real StructuredAnswer render.
 */
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it } from 'vitest';
import type { AnalyzeContent, SourceObject } from '../api/types';
import { StructuredAnswer } from '../components/StructuredAnswer';
import globalsCss from '../styles/globals.css?raw';
import { setReducedMotion } from './setup';

function makeSource(id: string, url: string | null): SourceObject {
  return {
    id,
    title: `Tiêu đề ${id}`,
    source_name: 'Cổng thông tin',
    url,
    snippet: 'Đoạn trích dài của nguồn tham khảo.',
    source_type: 'official_source',
    last_checked: '2026-01-01',
  };
}

function makeContent(overrides: Partial<AnalyzeContent> = {}): AnalyzeContent {
  return {
    response_kind: 'legal',
    domain: 'civil_dispute',
    risk_level: 'low',
    decision: 'answer_with_guidance',
    summary: 'Tóm tắt.',
    clarifying_questions: [],
    checklist: [],
    next_steps: [],
    sources: [],
    safety_notice: 'Tham khảo.',
    confidence: { domain: 0.9, risk: 0.9, answer: 0.9 },
    metadata: { fast_demo: true },
    analysis: null,
    draft: null,
    known_facts: [],
    uncertainty_notice: null,
    ...overrides,
  } as AnalyzeContent;
}

function renderAnswer(overrides: Partial<AnalyzeContent> = {}) {
  return render(<StructuredAnswer content={makeContent(overrides)} />);
}

beforeEach(() => {
  // Static presentation only: remove reveal timing from these assertions.
  setReducedMotion(true);
});

describe('ordered-list numbering', () => {
  it('shows exactly one ordinal per next-step item', () => {
    renderAnswer({ next_steps: ['1. Thu thập bằng chứng', '2. Gửi yêu cầu', '3. Khởi kiện'] });

    const items = screen.getAllByRole('listitem');
    const texts = items.map((item) => item.textContent);

    expect(texts).toContain('Thu thập bằng chứng');
    expect(texts).toContain('Gửi yêu cầu');
    expect(texts).toContain('Khởi kiện');
    for (const text of texts) {
      expect(text).not.toMatch(/^\d+[.)]\s/);
    }
  });

  it('keeps semantic <ol> and <li> markup', () => {
    const { container } = renderAnswer({ next_steps: ['1. Một', '2. Hai'] });

    const orderedList = container.querySelector('.next-steps-section ol');
    expect(orderedList).not.toBeNull();
    expect(orderedList?.tagName).toBe('OL');
    expect(orderedList?.querySelectorAll('li')).toHaveLength(2);
  });

  it('strips redundant ordinals in clarifying questions too', () => {
    const { container } = renderAnswer({
      clarifying_questions: ['1. Bạn đặt cọc bao nhiêu?', '2. Có hợp đồng không?'],
    });

    const items = Array.from(container.querySelectorAll('.clarification-list li'));
    expect(items.map((item) => item.textContent)).toEqual([
      'Bạn đặt cọc bao nhiêu?',
      'Có hợp đồng không?',
    ]);
  });

  it('does not corrupt legitimate legal or numeric list text', () => {
    const { container } = renderAnswer({
      next_steps: ['Điều 2. Nội dung hợp đồng', '20.000.000 đồng tiền cọc', '1 tháng tiền thuê'],
    });

    const items = Array.from(container.querySelectorAll('.next-steps-section li'));
    expect(items.map((item) => item.textContent)).toEqual([
      'Điều 2. Nội dung hợp đồng',
      '20.000.000 đồng tiền cọc',
      '1 tháng tiền thuê',
    ]);
  });

  it('leaves a mismatched ordinal in place', () => {
    const { container } = renderAnswer({ next_steps: ['5. Mục năm', '2. Mục hai'] });
    const items = Array.from(container.querySelectorAll('.next-steps-section li'));
    expect(items[0].textContent).toBe('5. Mục năm');
    // Position 2 matches "2.", so that one is the redundant case.
    expect(items[1].textContent).toBe('Mục hai');
  });
});

describe('compact source references', () => {
  it('renders nothing at all when there is no valid source', () => {
    const { container } = renderAnswer({ sources: [] });
    expect(screen.queryByText(/Nguồn tham khảo/)).not.toBeInTheDocument();
    expect(container.querySelector('.source-cta')).toBeNull();
  });

  it('renders nothing when every source URL is unsafe', () => {
    const { container } = renderAnswer({
      sources: [makeSource('s1', 'javascript:alert(1)'), makeSource('s2', null)],
    });

    expect(screen.queryByText(/Nguồn tham khảo/)).not.toBeInTheDocument();
    expect(container.querySelector('.source-cta')).toBeNull();
    expect(container.querySelectorAll('a')).toHaveLength(0);
  });

  it('renders one compact direct link for exactly one valid source', () => {
    renderAnswer({ sources: [makeSource('s1', 'https://example.com/a')] });

    const link = screen.getByRole('link', { name: 'Nguồn tham khảo' });
    expect(link).toHaveAttribute('href', 'https://example.com/a');
    expect(link).toHaveAttribute('target', '_blank');
    expect(link).toHaveAttribute('rel', expect.stringContaining('noopener'));
    expect(link).toHaveAttribute('rel', expect.stringContaining('noreferrer'));

    // No disclosure, and none of the verbose card content.
    expect(screen.queryByRole('button', { name: /Nguồn tham khảo/ })).not.toBeInTheDocument();
    expect(screen.queryByText(/Đoạn trích dài/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Kiểm tra:/)).not.toBeInTheDocument();
    expect(screen.queryByText('Cổng thông tin')).not.toBeInTheDocument();
    expect(screen.queryByText('s1')).not.toBeInTheDocument();
  });

  it('renders one disclosure for multiple sources and hides links until expanded', async () => {
    const user = userEvent.setup();
    renderAnswer({
      sources: [
        makeSource('s1', 'https://example.com/a'),
        makeSource('s2', 'https://example.com/b'),
        makeSource('s3', 'https://example.com/c'),
      ],
    });

    const toggle = screen.getByRole('button', { name: /Nguồn tham khảo/ });
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryAllByRole('link')).toHaveLength(0);

    await user.click(toggle);

    expect(toggle).toHaveAttribute('aria-expanded', 'true');
    const links = screen.getAllByRole('link');
    expect(links).toHaveLength(3);
    expect(links.map((link) => link.getAttribute('href'))).toEqual([
      'https://example.com/a',
      'https://example.com/b',
      'https://example.com/c',
    ]);
    for (const link of links) {
      expect(link).toHaveAttribute('rel', expect.stringContaining('noopener'));
    }

    await user.click(toggle);
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryAllByRole('link')).toHaveLength(0);
  });

  it('preserves every valid secondary source while dropping unsafe ones', async () => {
    const user = userEvent.setup();
    renderAnswer({
      sources: [
        makeSource('s1', 'https://example.com/a'),
        makeSource('s2', 'javascript:alert(1)'),
        makeSource('s3', 'https://example.com/b'),
        makeSource('s4', '//example.com/protocol-relative'),
        makeSource('s5', 'https://example.com/c'),
      ],
    });

    await user.click(screen.getByRole('button', { name: /Nguồn tham khảo/ }));
    const links = screen.getAllByRole('link');
    expect(links).toHaveLength(3);
    expect(links.map((link) => link.getAttribute('href'))).toEqual([
      'https://example.com/a',
      'https://example.com/b',
      'https://example.com/c',
    ]);
  });

  it('de-duplicates only a genuinely repeated source (same id), not merely a repeated URL', async () => {
    // Legal Correction Round 1 (Traffic Safe Subset V1): two DISTINCT
    // citations (e.g. a rule's fine and its separate licence-point
    // deduction) can legitimately share one document's URL and must render
    // as two separate cards, never collapse into one -- so de-duplication
    // keys on `id`, not on the URL. A literal repeat of the same `id` (the
    // same logical source appearing twice in the array) still collapses.
    const user = userEvent.setup();
    renderAnswer({
      sources: [
        makeSource('s1', 'https://example.com/same'),
        makeSource('s1', 'https://example.com/same'), // true duplicate: same id
        makeSource('s2', 'https://example.com/same'), // distinct id, same URL -- kept
        makeSource('s3', 'https://example.com/other'),
      ],
    });

    await user.click(screen.getByRole('button', { name: /Nguồn tham khảo/ }));
    expect(screen.getAllByRole('link')).toHaveLength(3);
  });

  it('falls back to URL-based de-duplication when a source has no id', async () => {
    const user = userEvent.setup();
    renderAnswer({
      sources: [
        makeSource('', 'https://example.com/same'),
        makeSource('', 'https://example.com/same'),
        makeSource('', 'https://example.com/other'),
      ],
    });

    await user.click(screen.getByRole('button', { name: /Nguồn tham khảo/ }));
    expect(screen.getAllByRole('link')).toHaveLength(2);
  });

  it('exposes the disclosure to the keyboard', async () => {
    const user = userEvent.setup();
    renderAnswer({
      sources: [
        makeSource('s1', 'https://example.com/a'),
        makeSource('s2', 'https://example.com/b'),
      ],
    });

    const toggle = screen.getByRole('button', { name: /Nguồn tham khảo/ });
    toggle.focus();
    expect(toggle).toHaveFocus();

    await user.keyboard('{Enter}');
    expect(toggle).toHaveAttribute('aria-expanded', 'true');

    await user.keyboard(' ');
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
  });

  it('links to the expanded list via aria-controls', async () => {
    const user = userEvent.setup();
    const { container } = renderAnswer({
      sources: [
        makeSource('s1', 'https://example.com/a'),
        makeSource('s2', 'https://example.com/b'),
      ],
    });

    const toggle = screen.getByRole('button', { name: /Nguồn tham khảo/ });
    await user.click(toggle);

    const controlledId = toggle.getAttribute('aria-controls');
    expect(controlledId).toBeTruthy();
    const list = container.querySelector(`#${CSS.escape(controlledId as string)}`);
    expect(list).not.toBeNull();
    expect(within(list as HTMLElement).getAllByRole('link')).toHaveLength(2);
  });
});

/**
 * Typography is asserted against the stylesheet source rather than
 * getComputedStyle: jsdom does not resolve CSS custom properties from an
 * external sheet, so a computed-style assertion here would pass vacuously and
 * prove nothing.
 */
describe('response typography', () => {
  // Imported through Vite's `?raw` loader: this keeps the assertion on the
  // real stylesheet without pulling Node type definitions into the frontend.
  const css = globalsCss;

  function token(name: string): number {
    const match = new RegExp(`--answer-${name}:\\s*([0-9.]+)px`).exec(css);
    expect(match, `--answer-${name} must be declared`).not.toBeNull();
    return Number.parseFloat((match as RegExpExecArray)[1]);
  }

  it('declares one controlled type scale', () => {
    expect(token('text')).toBe(16);
    expect(token('supporting')).toBe(14);
    expect(token('heading')).toBe(18);
  });

  it('keeps a deliberate hierarchy instead of one flat size', () => {
    expect(token('heading')).toBeGreaterThan(token('text'));
    expect(token('text')).toBeGreaterThan(token('supporting'));
  });

  it('scopes the scale to responses, not to page chrome', () => {
    const scopeMatch = /\.structured-answer\s*\{[^}]*--answer-text/s.exec(css);
    expect(scopeMatch, 'tokens must be declared on .structured-answer').not.toBeNull();
    // The composer, Send button and navigation must not be restyled here.
    expect(/\.(composer|send-button|sidebar|new-chat-button)[^{]*\{[^}]*--answer-/s.test(css)).toBe(false);
  });

  it('leaves no drifted per-component font sizes inside responses', () => {
    // These previously ranged from 11px to 0.9rem and are what made responses
    // look inconsistent; they must all derive from the tokens now.
    const answerScopedRules = [
      '.answer-summary',
      '.answer-section h3',
      '.source-cta',
      '.known-facts-toggle',
      '.known-facts-list',
      '.uncertainty-notice',
      '.draft-copy-button',
      '.safety-notice p',
    ];

    for (const selector of answerScopedRules) {
      const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
      const rule = new RegExp(`${escaped}\\s*(,[^{]*)?\\{([^}]*)\\}`, 's').exec(css);
      expect(rule, `${selector} rule must exist`).not.toBeNull();
      const body = (rule as RegExpExecArray)[2];
      const fontSize = /font-size:\s*([^;]+);/.exec(body);
      if (fontSize) {
        expect(fontSize[1].trim(), `${selector} must use a token`).toContain('var(--answer-');
      }
    }
  });

  it('sets one inherited font family at the root only', () => {
    const familyDeclarations = css.match(/font-family:/g) ?? [];
    expect(familyDeclarations).toHaveLength(1);
    expect(/:root\s*\{[^}]*font-family:/s.test(css)).toBe(true);
  });

  it('uses a consistent body line height', () => {
    const leading = /--answer-leading:\s*([0-9.]+)/.exec(css);
    expect(leading).not.toBeNull();
    const value = Number.parseFloat((leading as RegExpExecArray)[1]);
    expect(value).toBeGreaterThanOrEqual(1.6);
    expect(value).toBeLessThanOrEqual(1.7);
  });
});
