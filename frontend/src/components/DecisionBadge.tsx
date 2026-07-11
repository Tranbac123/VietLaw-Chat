import type { Decision } from '../api/types';
import { formatDecision } from '../lib/format';

export function DecisionBadge({ decision }: { decision: Decision }) {
  return <span className={`badge decision-badge decision-${decision}`}>{formatDecision(decision)}</span>;
}
