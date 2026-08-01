/**
 * Public Beta V0 (task §10.1): the landing page must disclose the beta's
 * actual scope (not "supports all Vietnamese law") and group sample prompts
 * by curated-deposit / curated-traffic / other-legal-questions, without
 * implying the third group is itself curated.
 */
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { LandingChatState } from '../components/LandingChatState';

afterEach(() => {
  cleanup();
});

describe('LandingChatState', () => {
  it('discloses the beta scope and does not claim to support all Vietnamese law', () => {
    render(<LandingChatState />);
    const scopeText = screen.getByText(/VietLaw Beta hỗ trợ/);
    expect(scopeText.textContent).toContain('đặt cọc thuê nhà');
    expect(scopeText.textContent).toContain('vi phạm giao thông');
    expect(scopeText.textContent).not.toMatch(/tất cả|mọi vấn đề pháp luật/);
  });

  it('does not claim official-source search currently works (Correction Round 1, M-03)', () => {
    render(<LandingChatState />);
    const scopeText = screen.getByText(/VietLaw Beta hỗ trợ/);
    // The old wording ("có thể tra cứu nguồn pháp luật chính thức cho các
    // câu hỏi khác") claimed a working capability with no provider wired.
    expect(scopeText.textContent).not.toMatch(/có thể tra cứu nguồn pháp luật chính thức/);
    expect(scopeText.textContent).toMatch(/đang trong quá trình hoàn thiện/);
  });

  it('discloses general-guidance wording for questions outside curated scope', () => {
    render(<LandingChatState />);
    const scopeText = screen.getByText(/VietLaw Beta hỗ trợ/);
    expect(scopeText.textContent).toMatch(/hướng dẫn chung/);
  });

  it('presents the beta disclaimer (reference only, not professional advice)', () => {
    render(<LandingChatState />);
    const scopeText = screen.getByText(/VietLaw Beta hỗ trợ/);
    expect(scopeText.textContent).toMatch(/không thay thế tư vấn pháp lý chuyên nghiệp/);
  });

  it('groups sample prompts under the three required category headings', () => {
    render(<LandingChatState />);
    expect(screen.getByRole('heading', { name: 'Đặt cọc thuê nhà' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Giao thông' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Câu hỏi pháp luật khác' })).toBeInTheDocument();
  });

  it('renders sample prompts as plain text when no selection handler is given', () => {
    render(<LandingChatState />);
    expect(screen.queryByRole('button', { name: /vượt đèn đỏ/ })).not.toBeInTheDocument();
  });

  it('invokes the selection handler with the prompt text when clicked', async () => {
    const user = userEvent.setup();
    const onSelectPrompt = vi.fn();
    render(<LandingChatState onSelectPrompt={onSelectPrompt} />);

    const trafficPrompt = screen.getByRole('button', { name: /vượt đèn đỏ/ });
    await user.click(trafficPrompt);

    expect(onSelectPrompt).toHaveBeenCalledTimes(1);
    expect(onSelectPrompt.mock.calls[0][0]).toContain('vượt đèn đỏ');
  });
});
