export type AIProvider = "claude" | "openai" | "ollama";
export type JobType = "design" | "development";

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
}

export interface GenerateResult {
  output_folder: string;
  resume_docx: string;
  resume_pdf?: string;
  cover_letter_docx: string;
  cover_letter_pdf?: string;
  notion_page_url?: string;
  message: string;
}

export interface ModelFilesStatus {
  design_resume: boolean;
  dev_resume: boolean;
  instructions_prompt: boolean;
  writing_examples: boolean;
  sait_transcript: boolean;
}
