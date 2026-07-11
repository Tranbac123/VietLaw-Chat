import { SAFETY_NOTICE_FALLBACK } from '../lib/constants';

export function SafetyNotice({ notice }: { notice?: string | null }) {
  return (
    <section className="safety-notice" aria-labelledby="safety-notice-heading">
      <h3 id="safety-notice-heading">Lưu ý an toàn</h3>
      <p>{notice?.trim() || SAFETY_NOTICE_FALLBACK}</p>
    </section>
  );
}
