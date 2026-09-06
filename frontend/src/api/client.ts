/**
 * Every call to the backend, in one place.
 *
 * Components and hooks describe *what* they want, not which URL serves it or
 * how a FastAPI error is shaped. That keeps endpoint changes to this file, and
 * it means one consistent story for failures: the server's `detail` message is
 * surfaced when there is one, so a misconfigured backend says so instead of
 * collapsing into "something went wrong".
 */

import { fetchWithAuth } from '../auth';
import type { SearchContext } from '../types';

/** An error carrying whatever the backend was willing to explain. */
export class ApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
    this.name = 'ApiError';
  }
}

async function detailOf(res: Response, fallback: string): Promise<string> {
  const body = await res.json().catch(() => ({}));
  return body?.detail || fallback;
}

async function expectOk(res: Response, fallback: string): Promise<Response> {
  if (!res.ok) {
    throw new ApiError(await detailOf(res, fallback), res.status);
  }
  return res;
}

export async function getCurrentUser(): Promise<{ email: string }> {
  const res = await fetchWithAuth('/api/me');
  await expectOk(res, 'Could not load your account');
  return res.json();
}

export async function listDocuments(): Promise<string[]> {
  const res = await fetchWithAuth('/api/documents');
  await expectOk(res, 'Could not load documents');
  const data = await res.json();
  return data.documents || [];
}

export async function uploadDocument(file: File): Promise<{ filename: string }> {
  const body = new FormData();
  body.append('file', file);
  const res = await fetchWithAuth('/api/upload', { method: 'POST', body });
  await expectOk(res, 'Upload failed');
  return res.json();
}

export async function getDocumentStatus(filename: string): Promise<string> {
  const res = await fetchWithAuth(`/api/status/${encodeURIComponent(filename)}`);
  await expectOk(res, 'Could not read processing status');
  const data = await res.json();
  return data.status || 'unknown';
}

export async function deleteDocument(filename: string): Promise<void> {
  const res = await fetchWithAuth(`/api/documents/${encodeURIComponent(filename)}`, {
    method: 'DELETE',
  });
  await expectOk(res, 'Failed to delete document');
}

export async function searchDocuments(query: string): Promise<SearchContext[]> {
  const res = await fetchWithAuth('/api/search', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query }),
  });
  await expectOk(res, 'Search failed');
  const data = await res.json();
  return data.contexts || [];
}

/**
 * Open the chat stream. The caller reads the body; this only gets as far as
 * confirming the server accepted the request, so a failure is reported before
 * any partial answer reaches the screen.
 */
export async function openChatStream(
  messages: { role: string; content: string }[],
  signal: AbortSignal
): Promise<ReadableStreamDefaultReader<Uint8Array>> {
  const res = await fetchWithAuth('/api/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ messages }),
    signal,
  });
  await expectOk(res, `Backend returned ${res.status} ${res.statusText}`);
  if (!res.body) {
    throw new ApiError('Streaming is not supported by this browser', 0);
  }
  return res.body.getReader();
}

export async function logout(): Promise<void> {
  // Uses the authenticated helper like every other call: logout currently only
  // clears a cookie, but an endpoint that later needs the bearer token should
  // not be the one place that does not send it.
  await fetchWithAuth('/api/logout', { method: 'POST' }).catch(() => undefined);
}
