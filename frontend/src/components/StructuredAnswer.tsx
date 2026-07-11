import type { AnalyzeContent } from '../api/types';
import { formatDomain } from '../lib/format';
import { DecisionBadge } from './DecisionBadge';
import { RiskBadge } from './RiskBadge';
import { SafetyNotice } from './SafetyNotice';
import { SourcePanel } from './SourcePanel';

interface StructuredAnswerProps {
  content: AnalyzeContent;
}

function AnswerList({ title, items }: { title: string; items: string[] }) {
  if (items.length === 0) return null;

  return (
    <section className="answer-section">
      <h3>{title}</h3>
      <ul>
        {items.map((item, index) => <li key={`${title}-${index}`}>{item}</li>)}
      </ul>
    </section>
  );
}

export function StructuredAnswer({ content }: StructuredAnswerProps) {
  return (
    <div className="structured-answer">
      <div className="answer-badges" aria-label="Phân loại phản hồi">
        <span className={`badge domain-badge domain-${content.domain}`}>{formatDomain(content.domain)}</span>
        <RiskBadge level={content.risk_level} />
        <DecisionBadge decision={content.decision} />
      </div>

      <section className="answer-summary">
        <h2>Tóm tắt ban đầu</h2>
        <p>{content.summary}</p>
      </section>

      <AnswerList title="Câu hỏi cần làm rõ" items={content.clarifying_questions} />
      <AnswerList title="Checklist giấy tờ" items={content.checklist} />
      <AnswerList title="Bước tiếp theo an toàn" items={content.next_steps} />
      <SourcePanel sources={content.sources} />
      <SafetyNotice notice={content.safety_notice} />
    </div>
  );
}
