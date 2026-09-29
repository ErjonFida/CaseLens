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

export interface SearchContext {
  text: string;
  metadata: {
    filename: string;
    page?: number;
    [key: string]: any;
  };
}
