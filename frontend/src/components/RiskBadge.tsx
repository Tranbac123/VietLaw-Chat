import type { RiskLevel } from '../api/types';

const labels: Record<RiskLevel, string> = {
  low: 'Rủi ro thấp',
  medium: 'Rủi ro trung bình',
  high: 'Rủi ro cao',
};

export function RiskBadge({ level }: { level: RiskLevel }) {
  return <span className={`badge risk-badge risk-${level}`}>{labels[level]}</span>;
}
