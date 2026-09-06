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
const POLL_MAX_ATTEMPTS = 30;

export function useDocuments() {
  const [documents, setDocuments] = useState<string[]>([]);
  const [statuses, setStatuses] = useState<DocumentStatusMap>({});
  const [uploading, setUploading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

  // Polling runs for up to a minute. Without this, navigating away mid-upload
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
      for (let attempt = 0; attempt < POLL_MAX_ATTEMPTS; attempt++) {
        await new Promise((r) => setTimeout(r, POLL_INTERVAL_MS));
        if (!mounted.current) return;

        try {
          const status = await api.getDocumentStatus(filename);
          if (!mounted.current) return;

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
        } catch {
          return;
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
