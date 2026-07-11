import type { Decision, Domain, SourceType } from '../api/types';

const domainLabels: Record<Domain, string> = {
  civil_dispute: 'Tranh chấp dân sự',
  traffic: 'Giao thông / xử phạt',
  household_business: 'Hộ kinh doanh',
  administrative: 'Thủ tục hành chính',
  high_risk: 'Rủi ro cao',
  unknown: 'Chưa xác định',
};

const decisionLabels: Record<Decision, string> = {
  answer_with_guidance: 'Định hướng ban đầu',
  ask_clarifying_questions: 'Cần thêm thông tin',
  recommend_professional_help: 'Nên hỏi chuyên gia/cơ quan chức năng',
  refuse_unsafe_request: 'Không thể hỗ trợ yêu cầu này',
  unsupported: 'Ngoài phạm vi MVP',
};

const sourceTypeLabels: Record<SourceType, string> = {
  official_source: 'Nguồn chính thức',
  procedure: 'Thủ tục hành chính',
  legal_snippet: 'Trích đoạn pháp lý',
  curated_note: 'Ghi chú được biên tập',
  demo_only: 'Nguồn demo',
  safety_policy: 'Quy tắc an toàn',
};

export function formatDomain(domain: Domain): string {
  return domainLabels[domain];
}

export function formatDecision(decision: Decision): string {
  return decisionLabels[decision];
}

export function formatSourceType(sourceType: SourceType): string {
  return sourceTypeLabels[sourceType];
}

export function formatDate(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;

  return new Intl.DateTimeFormat('vi-VN', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date);
}
