export type AIProvider = "claude" | "openai" | "ollama";
export type JobType = "design" | "development";
export type GenerationStageId =
  | "validate_request"
  | "load_model_files"
  | "call_ai_provider"
  | "build_documents"
  | "log_notion"
  | "complete";
export type GenerationStageStatus = "pending" | "active" | "done" | "failed";

export interface GeneratePayload {
  job_description: string;
  ai_provider: AIProvider;
  job_type: JobType;
  position: string;
  company: string;
  location?: string;
  salary_annual?: number;
  salary_hourly?: number;
  date_job_posted?: string;
  contact_email?: string;
  company_context?: string;
}

export interface JobMeta {
  position: string;
  company: string;
  location: string;
  salary_annual: string;
  salary_hourly: string;
  date_job_posted: string;
  contact_email: string;
}

export interface ExtractJobMetaResult {
  position?: string | null;
  company?: string | null;
  location?: string | null;
  salary_annual?: number | null;
  salary_hourly?: number | null;
  date_job_posted?: string | null;
  contact_email?: string | null;
}

export interface ApiErrorPayload {
  status_code?: number;
  stage?: GenerationStageId;
  code?: string;
  message?: string;
  detail?: string | null;
  hint?: string | null;
  retryable?: boolean;
}

export interface GenerationFeedItem {
  id: GenerationStageId;
  label: string;
  status: GenerationStageStatus;
  description: string;
  detail?: string;
}

export interface GenerateResult {
  output_folder: string;
  resume_docx: string;
  resume_pdf?: string;
  cover_letter_docx: string;
  cover_letter_pdf?: string;
  notion_page_url?: string;
  notion_error?: string;
  analysis?: string;
  message: string;
}

export interface ModelFilesStatus {
  design_resume: boolean;
  dev_resume: boolean;
  instructions_prompt: boolean;
  writing_examples: boolean;
  sait_transcript: boolean;
}
