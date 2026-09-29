/**
 * The document vault: listing, upload, indexing status, deletion.
 *
 * Indexing is asynchronous on the server, so the client polls. That polling is
 * the reason this is a hook rather than inline state - a poll can outlive the
 * screen that started it, and it needs somewhere to be cancelled.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { toast } from 'sonner';

import * as api from '../api/client';
import type { DocumentStatusMap } from '../types';

const POLL_INTERVAL_MS = 2000;
// Scanned documents are OCR'd page by page and uploads wait their turn, so a
// job can take many minutes. The server forgets a status an hour after its
// last update (_STATUS_TTL in backend/legal_api/api.py), which bounds the wait.
const POLL_GIVE_UP_MS = 60 * 60 * 1000;
const POLL_MAX_FAILURES = 5;

export function useDocuments() {
  const [documents, setDocuments] = useState<string[]>([]);
  const [statuses, setStatuses] = useState<DocumentStatusMap>({});
  const [uploading, setUploading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

  // Polling can run for many minutes. Without this, navigating away mid-upload
  // leaves the loop running, updating state and firing toasts for a screen that
  // is gone. React 18 no longer warns about that, so it fails silently.
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  const refresh = useCallback(async () => {
    setRefreshing(true);
    try {
      const docs = await api.listDocuments();
      if (mounted.current) setDocuments(docs);
    } catch (err) {
      console.error('Failed to refresh documents:', err);
    } finally {
      if (mounted.current) setRefreshing(false);
    }
  }, []);

  const load = useCallback(async () => {
    const docs = await api.listDocuments();
    if (!mounted.current) return;
    setDocuments(docs);
    setStatuses(Object.fromEntries(docs.map((d) => [d, 'completed' as const])));
  }, []);

  const forget = useCallback((filename: string) => {
    setStatuses((prev) => {
      const next = { ...prev };
      delete next[filename];
      return next;
    });
  }, []);

  const poll = useCallback(
    async (filename: string) => {
      const deadline = Date.now() + POLL_GIVE_UP_MS;
      let failures = 0;
      while (Date.now() < deadline) {
        await new Promise((r) => setTimeout(r, POLL_INTERVAL_MS));
        if (!mounted.current) return;

        try {
          const status = await api.getDocumentStatus(filename);
          if (!mounted.current) return;
          failures = 0;

          setStatuses((prev) => ({ ...prev, [filename]: status }));

          if (status === 'completed') {
            toast.success(`"${filename}" successfully indexed for AI analysis`);
            await refresh();
            return;
          }
          if (status.startsWith('error')) {
            toast.error(`Indexing failed for "${filename}": ${status}`);
            return;
          }
          if (status === 'unknown') return; // deleted meanwhile, or forgotten by the server
        } catch {
          // One dropped request is not a failed upload; several in a row is an outage.
          if (++failures >= POLL_MAX_FAILURES) {
            if (mounted.current) toast.error(`Lost track of "${filename}". Refresh the list to see if it finished.`);
            return;
          }
        }
      }
    },
    [refresh]
  );

  const upload = useCallback(
    async (file: File) => {
      setUploading(true);
      setStatuses((prev) => ({ ...prev, [file.name]: 'queued' }));
      try {
        const { filename } = await api.uploadDocument(file);
        toast.info(`Uploaded "${filename}". Processing & indexing...`);
        void poll(filename);
      } catch (err: any) {
        toast.error(err?.message || 'Upload failed');
        forget(file.name);
      } finally {
        if (mounted.current) setUploading(false);
      }
    },
    [poll, forget]
  );

  const remove = useCallback(
    async (filename: string) => {
      await api.deleteDocument(filename);
      if (!mounted.current) return;
      setDocuments((prev) => prev.filter((d) => d !== filename));
      forget(filename);
      toast.success(`Removed "${filename}" from document vault`);
    },
    [forget]
  );

  return { documents, statuses, uploading, refreshing, load, refresh, upload, remove };
}
