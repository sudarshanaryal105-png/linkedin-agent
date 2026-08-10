export type PostStatus =
  | "DRAFT"
  | "EDITED"
  | "APPROVED"
  | "PUBLISHING"
  | "PUBLISHED"
  | "FAILED"
  | "CANCELLED";

export type JobStatus = "PENDING" | "RUNNING" | "SUCCEEDED" | "FAILED";

export interface UploadedImageOut {
  id: string;
  storage_path: string;
  mime_type: string;
  size_bytes: number;
  width: number | null;
  height: number | null;
}

export interface GenerationJobOut {
  job_id: string;
  status: JobStatus;
  generated_post_id?: string | null;
  error_message?: string | null;
}

export interface GeneratedPostOut {
  id: string;
  prompt_id: string;
  post_text: string;
  hashtags: string[];
  status: PostStatus;
  version: number;
  image_ids: string[];
  image_urls: string[];
  created_at: string;
  updated_at: string;
  linkedin_permalink: string | null;
}

export interface PublishResult {
  post_id: string;
  linkedin_post_urn: string;
  linkedin_permalink: string;
}
