export interface UserProfile {
  email: string;
  first_name?: string;
  last_name?: string;
  company?: string;
  phone_number?: string;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp?: string;
}

/** Known stages, plus `error: ...` and anything else the backend reports. */
export type DocumentStatus =
  | 'queued'
  | 'extracting_text'
  | 'indexing'
  | 'completed'
  | (string & {});

export type DocumentStatusMap = Record<string, DocumentStatus>;

export interface DocumentStatusResponse {
  filename: string;
  status: DocumentStatus;
}

export interface SearchContext {
  text: string;
  metadata: {
    filename: string;
    page?: number;
    [key: string]: any;
  };
}

export interface SearchResponse {
  contexts: SearchContext[];
}
