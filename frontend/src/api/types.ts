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
  /** Article-level legal citation metadata (MODE_2D). Present only for the
   * bounded Civil Code sources with curated article-level data; absent/null
   * for every other source, which falls back to the generic display. */
  document_title?: string | null;
  document_number?: string | null;
  article_number?: string | null;
  article_title?: string | null;
  clause_numbers?: number[];
  applicable_clause?: number | null;
  relevance_note?: string | null;
  /** Public Beta V0: when this source was retrieved live (official-source
   * search). Absent for curated static content, which already carries
   * `last_checked` for that purpose. */
  retrieved_at?: string | null;
  /** Legal Correction Round 1 (Traffic Safe Subset V1): present only for a
   * curated traffic rule's individual legal-citation sources -- absent for
   * every other source. `clause_number` is the exact source string (e.g.
   * "1-4"), distinct from the integer-only `applicable_clause` above, which
   * cannot represent a khoản range. */
  clause_number?: string | null;
  point_number?: string | null;
  citation_role?: string | null;
}

/** Public Beta V0 trust-level contract (see `contracts/legal_trust.py`). */
export type TrustLevel = 'curated_verified' | 'official_source_search' | 'general_guidance';

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
  /**
   * Stable per-submission idempotency key. Created once when the user submits
   * and reused for transport retries of that same submission, so a retry can
   * neither spend a second provider call nor re-apply fact updates.
   */
  client_request_id?: string;
}

export type ResponseKind = 'legal' | 'social' | 'capability' | 'scope';

/** FAST DEMO V2 copyable draft message. */
export interface DraftBlock {
  title: string;
  body: string;
}

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
  /** FAST DEMO V2 optional blocks (absent on baseline responses). */
  analysis?: string | null;
  draft?: DraftBlock | null;
  known_facts?: string[];
  uncertainty_notice?: string | null;
  /** Public Beta V0 trust-level contract (absent on baseline responses). */
  trust_level?: TrustLevel | null;
  trust_label?: string | null;
  trust_explanation?: string | null;
  source_checked_at?: string | null;
}

export interface LegalAnalyzeResponse extends AnalyzeResponseCommon {
  response_kind: 'legal';
  domain: Domain;
  risk_level: RiskLevel;
  decision: Decision;
  confidence: Confidence;
}

interface NonLegalResponseFields extends AnalyzeResponseCommon {
  domain: null;
  risk_level: null;
  decision: null;
  confidence: null;
}

/** Each non-legal kind is its own single-literal member so TypeScript can
 *  discriminate the union exactly. */
export interface SocialAnalyzeResponse extends NonLegalResponseFields {
  response_kind: 'social';
}

export interface CapabilityAnalyzeResponse extends NonLegalResponseFields {
  response_kind: 'capability';
}

export interface ScopeAnalyzeResponse extends NonLegalResponseFields {
  response_kind: 'scope';
}

export type AnalyzeResponse =
  | LegalAnalyzeResponse
  | SocialAnalyzeResponse
  | CapabilityAnalyzeResponse
  | ScopeAnalyzeResponse;

interface AnalyzeContentCommon {
  summary: string;
  clarifying_questions: string[];
  checklist: string[];
  next_steps: string[];
  sources: SourceObject[];
  safety_notice: string;
  metadata: Record<string, unknown>;
  /** FAST DEMO V2 optional blocks (absent on baseline responses). */
  analysis?: string | null;
  draft?: DraftBlock | null;
  known_facts?: string[];
  uncertainty_notice?: string | null;
  /** Public Beta V0 trust-level contract (absent on baseline responses). */
  trust_level?: TrustLevel | null;
  trust_label?: string | null;
  trust_explanation?: string | null;
  source_checked_at?: string | null;
}

export interface LegalAnalyzeContent extends AnalyzeContentCommon {
  response_kind: 'legal';
  domain: Domain;
  risk_level: RiskLevel;
  decision: Decision;
  confidence: Confidence;
}

interface NonLegalContentFields extends AnalyzeContentCommon {
  domain: null;
  risk_level: null;
  decision: null;
  confidence: null;
}

export interface SocialAnalyzeContent extends NonLegalContentFields {
  response_kind: 'social';
}

export interface CapabilityAnalyzeContent extends NonLegalContentFields {
  response_kind: 'capability';
}

export interface ScopeAnalyzeContent extends NonLegalContentFields {
  response_kind: 'scope';
}

export type AnalyzeContent =
  | LegalAnalyzeContent
  | SocialAnalyzeContent
  | CapabilityAnalyzeContent
  | ScopeAnalyzeContent;

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
