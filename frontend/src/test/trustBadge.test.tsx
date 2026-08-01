/**
 * Public Beta V0: the trust badge (task §10/§13.5). Three trust levels must
 * never render with the same visual appearance, and each must expose its
 * exact required Vietnamese short label and an expandable explanation.
 */
import { afterEach, describe, expect, it } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { TrustBadge } from '../components/TrustBadge';

afterEach(() => {
  cleanup();
});

describe('TrustBadge', () => {
  it('renders the exact required short label for curated_verified', () => {
    render(<TrustBadge trustLevel="curated_verified" />);
    expect(screen.getByText('Đã kiểm chứng')).toBeInTheDocument();
  });

  it('renders the exact required short label for official_source_search', () => {
    render(<TrustBadge trustLevel="official_source_search" />);
    expect(screen.getByText('Nguồn chính thức')).toBeInTheDocument();
  });

  it('renders the exact required short label for general_guidance', () => {
    render(<TrustBadge trustLevel="general_guidance" />);
    expect(screen.getByText('Hướng dẫn chung')).toBeInTheDocument();
  });

  it('the three trust levels render with distinct CSS classes (never the same appearance)', () => {
    const { container: curated } = render(<TrustBadge trustLevel="curated_verified" />);
    const { container: official } = render(<TrustBadge trustLevel="official_source_search" />);
    const { container: general } = render(<TrustBadge trustLevel="general_guidance" />);

    const classOf = (el: HTMLElement) => el.querySelector('.trust-badge')?.className;
    const classes = new Set([classOf(curated), classOf(official), classOf(general)]);
    expect(classes.size).toBe(3);
  });

  it('the explanation is collapsed by default and expands on click', async () => {
    const user = userEvent.setup();
    render(
      <TrustBadge
        trustLevel="general_guidance"
        trustExplanation="Đây là hướng dẫn chung, không phải kết luận pháp lý."
      />,
    );

    expect(screen.queryByText(/Đây là hướng dẫn chung/)).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /Hướng dẫn chung/ }));
    expect(screen.getByText(/Đây là hướng dẫn chung/)).toBeInTheDocument();
  });

  it('falls back to the short label when no backend explanation is provided', async () => {
    const user = userEvent.setup();
    render(<TrustBadge trustLevel="curated_verified" />);
    await user.click(screen.getByRole('button', { name: /Đã kiểm chứng/ }));
    expect(screen.getAllByText('Đã kiểm chứng')).toHaveLength(2);
  });
});
