import { useId, useState } from 'react';
import type { TrustLevel } from '../api/types';

const TRUST_BADGE_SHORT_LABELS: Record<TrustLevel, string> = {
  curated_verified: 'Đã kiểm chứng',
  official_source_search: 'Nguồn chính thức',
  general_guidance: 'Hướng dẫn chung',
};

/** Distinct icon per level so the three trust states never share the same
 * visual appearance, even for a user who cannot rely on color alone. */
const TRUST_BADGE_ICONS: Record<TrustLevel, string> = {
  curated_verified: '✓',
  official_source_search: '§',
  general_guidance: 'ℹ',
};

interface TrustBadgeProps {
  trustLevel: TrustLevel;
  /** Backend-provided label/explanation (see `contracts/legal_trust.py`).
   * Falls back to the fixed short label only if the backend omitted it. */
  trustLabel?: string | null;
  trustExplanation?: string | null;
}

/**
 * Compact badge shown near a legal answer's source section (task §10). Each
 * trust level has its own color class and icon -- never the same visual
 * appearance across levels -- and an expandable explanation so the
 * distinction is legible to assistive tech, not just color.
 */
export function TrustBadge({ trustLevel, trustLabel, trustExplanation }: TrustBadgeProps) {
  const [expanded, setExpanded] = useState(false);
  const detailId = useId();
  const label = TRUST_BADGE_SHORT_LABELS[trustLevel];
  const explanation = trustExplanation || trustLabel || label;

  return (
    <div className={`trust-badge trust-badge--${trustLevel}`}>
      <button
        type="button"
        className="trust-badge-toggle"
        aria-expanded={expanded}
        aria-controls={detailId}
        onClick={() => setExpanded((value) => !value)}
      >
        <span className="trust-badge-icon" aria-hidden="true">{TRUST_BADGE_ICONS[trustLevel]}</span>
        <span className="trust-badge-label">{label}</span>
      </button>
      {expanded && (
        <p className="trust-badge-explanation" id={detailId}>{explanation}</p>
      )}
    </div>
  );
}
