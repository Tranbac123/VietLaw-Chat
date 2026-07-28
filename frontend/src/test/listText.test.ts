/**
 * Phase A: ordered-list ordinal de-duplication.
 *
 * The risk here is over-reach, not under-reach: a broad regex would corrupt
 * ordinary Vietnamese legal prose. Most of these cases assert that text is
 * left alone.
 */
import { describe, expect, it } from 'vitest';
import { stripRedundantOrdinal } from '../lib/listText';

describe('stripRedundantOrdinal', () => {
  it('removes an ordinal that matches the item position', () => {
    expect(stripRedundantOrdinal('1. Thu thập bằng chứng', 0)).toBe('Thu thập bằng chứng');
    expect(stripRedundantOrdinal('2. Gửi yêu cầu hoàn trả', 1)).toBe('Gửi yêu cầu hoàn trả');
    expect(stripRedundantOrdinal('3. Khởi kiện nếu cần', 2)).toBe('Khởi kiện nếu cần');
  });

  it('supports the ")" ordinal form', () => {
    expect(stripRedundantOrdinal('1) Thu thập bằng chứng', 0)).toBe('Thu thập bằng chứng');
    expect(stripRedundantOrdinal('2) Gửi yêu cầu', 1)).toBe('Gửi yêu cầu');
  });

  it('tolerates leading whitespace', () => {
    expect(stripRedundantOrdinal('  1.  Thu thập bằng chứng', 0)).toBe('Thu thập bằng chứng');
  });

  it('leaves a mismatched ordinal alone', () => {
    expect(stripRedundantOrdinal('5. Điều khoản thứ năm', 0)).toBe('5. Điều khoản thứ năm');
    expect(stripRedundantOrdinal('1. Mục một', 2)).toBe('1. Mục một');
  });

  it('never corrupts legitimate Vietnamese legal or numeric text', () => {
    const untouched = [
      ['Điều 2. Nội dung hợp đồng', 0],
      ['Điều 2. Nội dung hợp đồng', 1],
      ['Khoản 2 của hợp đồng', 1],
      ['20.000.000 đồng', 0],
      ['20.000.000 đồng tiền cọc', 19],
      ['1 tháng tiền thuê', 0],
      ['2 tháng tiền cọc', 1],
      ['Bước 3 có 2 lựa chọn', 2],
      ['Nghị định 21/2021/NĐ-CP', 0],
    ] as const;

    for (const [text, index] of untouched) {
      expect(stripRedundantOrdinal(text, index), `${text} @${index}`).toBe(text);
    }
  });

  it('requires a separator, so a bare quantity is preserved', () => {
    // "1 tháng" must survive; only "1." or "1)" count as an ordinal.
    expect(stripRedundantOrdinal('1 tháng tiền thuê', 0)).toBe('1 tháng tiền thuê');
  });

  it('does not blank out an item that is only an ordinal', () => {
    expect(stripRedundantOrdinal('1.', 0)).toBe('1.');
    expect(stripRedundantOrdinal('1.   ', 0)).toBe('1.   ');
  });

  it('is idempotent for already-clean text', () => {
    expect(stripRedundantOrdinal('Thu thập bằng chứng', 0)).toBe('Thu thập bằng chứng');
    expect(stripRedundantOrdinal('', 0)).toBe('');
  });
});
