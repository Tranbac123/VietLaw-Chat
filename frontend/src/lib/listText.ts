/**
 * Ordered-list ordinal de-duplication.
 *
 * The model frequently writes "1. ..." inside an item that the UI then renders
 * inside an `<ol>`, so the browser's own marker and the model's ordinal both
 * appear: "1. 1. ...". This strips the model's copy, but only at the ordered
 * list rendering boundary and only when it is provably redundant.
 *
 * Deliberately narrow, because the alternative -- a broad regex over answer
 * text -- corrupts ordinary Vietnamese legal prose such as "Điều 2. Nội dung",
 * "Khoản 2 của hợp đồng", "20.000.000 đồng" and "1 tháng tiền thuê".
 *
 * Two conditions must both hold before anything is removed:
 *   1. the leading number equals this item's own 1-based position, so a
 *      mismatched ordinal is left alone as real content; and
 *   2. the number is followed by "." or ")" and then whitespace, so a bare
 *      quantity such as "1 tháng tiền thuê" is never touched.
 */

const LEADING_ORDINAL_RE = /^\s*(\d{1,3})[.)]\s+(?=\S)/;

/**
 * Removes a leading ordinal from `text` when it duplicates the rendered marker
 * for position `index` (0-based). Returns `text` unchanged otherwise.
 */
export function stripRedundantOrdinal(text: string, index: number): string {
  if (typeof text !== 'string') return text;

  const match = LEADING_ORDINAL_RE.exec(text);
  if (!match) return text;

  // Only the item's own number is redundant with the marker the browser draws.
  if (Number(match[1]) !== index + 1) return text;

  const remainder = text.slice(match[0].length);
  // Never blank out an item: if the ordinal was the entire content, keep it.
  return remainder.trim() ? remainder : text;
}
