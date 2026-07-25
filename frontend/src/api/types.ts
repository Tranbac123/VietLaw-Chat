export type Domain =
  | 'civil_dispute'
  | 'traffic'
  | 'household_business'
  | 'administrative'
  | 'high_risk'
  | 'unknown';

export type RiskLevel = 'low' | 'medium' | 'high';

export type Decision =
  | 'answer_with_guidance'
  | 'ask_clarifying_questions'
  | 'recommend_professional_help'
  | 'refuse_unsafe_request'
  | 'unsupported';

export type SourceType =
  | 'official_source'
  | 'procedure'
  | 'legal_snippet'
  | 'curated_note'
  | 'demo_only'
  | 'safety_policy';

export type UserType = 'citizen' | 'household_business' | 'foreign_visitor' | 'unknown';

export interface SourceObject {
  id: string;
  title: string;
  source_name: string;
  url?: string | null;
  snippet: string;
  source_type: SourceType;
  last_checked: string;
}

export interface Confidence {
  domain: number;
  risk: number;
  answer: number;
}

export interface AnalyzeRequest {
  session_id: string;
  chat_id?: string;
  question: string;
  user_type?: UserType;
  language?: 'vi';
}

export type ResponseKind = 'legal' | 'social';

interface AnalyzeResponseCommon {
  contract_version: string;
  request_id: string;
  chat_id: string;
  user_message_id: string;
  assistant_message_id: string;
  summary: string;
  clarifying_questions: string[];
  checklist: string[];
  next_steps: string[];
  sources: SourceObject[];
  safety_notice: string;
  metadata: Record<string, unknown>;
}

export interface LegalAnalyzeResponse extends AnalyzeResponseCommon {
  response_kind: 'legal';
  domain: Domain;
  risk_level: RiskLevel;
  decision: Decision;
  confidence: Confidence;
}

export interface SocialAnalyzeResponse extends AnalyzeResponseCommon {
  response_kind: 'social';
  domain: null;
  risk_level: null;
  decision: null;
  confidence: null;
}

export type AnalyzeResponse = LegalAnalyzeResponse | SocialAnalyzeResponse;

interface AnalyzeContentCommon {
  summary: string;
  clarifying_questions: string[];
  checklist: string[];
  next_steps: string[];
  sources: SourceObject[];
  safety_notice: string;
  metadata: Record<string, unknown>;
}

export interface LegalAnalyzeContent extends AnalyzeContentCommon {
  response_kind: 'legal';
  domain: Domain;
  risk_level: RiskLevel;
  decision: Decision;
  confidence: Confidence;
}

export interface SocialAnalyzeContent extends AnalyzeContentCommon {
  response_kind: 'social';
  domain: null;
  risk_level: null;
  decision: null;
  confidence: null;
}

export type AnalyzeContent = LegalAnalyzeContent | SocialAnalyzeContent;

export type MessageRole = 'user' | 'assistant';
export type ContentType = 'text' | 'structured';

export interface ChatMessage {
  message_id: string;
  chat_id: string;
  role: MessageRole;
  content_type: ContentType;
  content_text?: string | null;
  content_json?: AnalyzeContent | null;
  created_at: string;
}

export interface ChatListItem {
  chat_id: string;
  title: string;
  created_at: string;
  updated_at: string;
}

export interface ChatListResponse {
  chats: ChatListItem[];
}

export interface ChatCreateResponse {
  chat_id: string;
  session_id: string;
  title: string;
  created_at: string;
  updated_at: string;
}

export interface ChatDetailResponse {
  chat_id: string;
  session_id: string;
  title: string;
  created_at: string;
  updated_at: string;
  messages: ChatMessage[];
}

export interface DeleteChatResponse {
  deleted: boolean;
  chat_id: string;
}

export interface ApiErrorResponse {
  error: {
    code: string;
    message: string;
    details?: unknown;
  };
}
