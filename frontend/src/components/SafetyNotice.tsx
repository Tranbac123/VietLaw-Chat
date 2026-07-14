import { useId } from 'react';
import { SAFETY_NOTICE_FALLBACK } from '../lib/constants';

export function SafetyNotice({ notice }: { notice?: string | null }) {
  const headingId = useId();

  return (
    <section className="safety-notice" aria-labelledby={headingId}>
      <h3 id={headingId}>Lưu ý an toàn</h3>
      <p>{notice?.trim() || SAFETY_NOTICE_FALLBACK}</p>
    </section>
  );
}
