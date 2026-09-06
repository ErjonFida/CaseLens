/**
 * Composition and the wiring between panels.
 *
 * Feature state lives in hooks (`useDocuments`, `useChat`, `useSemanticSearch`)
 * and rendering lives in the panels. What is left here is what genuinely spans
 * features: which tab is showing, who is signed in, and the two places a panel
 * needs to hand work to another one - analysing a search result in chat, and
 * jumping from the vault to a search.
 */

import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';

import * as api from '../api/client';
import { removeStoredToken } from '../auth';
import { useChat } from '../hooks/useChat';
import { useDocuments } from '../hooks/useDocuments';
import { useSemanticSearch } from '../hooks/useSemanticSearch';
import type { SearchContext } from '../types';

import ChatPanel from './dashboard/ChatPanel';
import DashboardHeader, { type DashboardTab } from './dashboard/DashboardHeader';
import DeleteDocumentDialog from './dashboard/DeleteDocumentDialog';
import DocumentSidebar from './dashboard/DocumentSidebar';
import SearchPanel from './dashboard/SearchPanel';
import VaultPanel from './dashboard/VaultPanel';

export default function Dashboard() {
  const navigate = useNavigate();
  const [userEmail, setUserEmail] = useState('');
  const [activeTab, setActiveTab] = useState<DashboardTab>('chat');
  const [docToDelete, setDocToDelete] = useState<string | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);

  const docs = useDocuments();
  const chat = useChat();
  const search = useSemanticSearch();

  const { load: loadDocuments } = docs;

  useEffect(() => {
    let cancelled = false;

    (async () => {
      try {
        const me = await api.getCurrentUser();
        if (cancelled) return;
        setUserEmail(me.email || '');
        await loadDocuments();
      } catch (err: any) {
        if (cancelled) return;
        if (err?.status === 401) {
          removeStoredToken();
          navigate('/login');
          return;
        }
        // A network failure is not an auth failure: keep the session and say the
        // backend is unreachable, rather than bouncing to /login where signing
        // in cannot work either.
        console.error('Failed to load user data:', err);
        toast.error('Cannot reach the backend API. Is the server running on port 8000?');
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [loadDocuments, navigate]);

  const handleSignOut = useCallback(async () => {
    await api.logout();
    removeStoredToken();
    toast.info('Signed out successfully');
    navigate('/login');
  }, [navigate]);

  const handleConfirmDelete = useCallback(async () => {
    if (!docToDelete) return;
    setIsDeleting(true);
    try {
      await docs.remove(docToDelete);
    } catch (err: any) {
      toast.error(err?.message || 'Error deleting document');
    } finally {
      setIsDeleting(false);
      setDocToDelete(null);
    }
  }, [docToDelete, docs]);

  // Cross-panel: send a retrieved passage to the assistant and follow it there.
  const handleAnalyse = useCallback(
    (result: SearchContext) => {
      setActiveTab('chat');
      chat.send(
        `Based on "${result.metadata?.filename}" (Page ${result.metadata?.page}):\n\n"${result.text.slice(0, 200)}..."\n\nPlease analyze this clause in detail.`
      );
    },
    [chat]
  );

  // Cross-panel: look up a document's segments from the vault.
  const handleFindSegments = useCallback(
    (filename: string) => {
      search.setQuery(filename);
      setActiveTab('search');
    },
    [search]
  );

  return (
    <div className="flex h-screen w-full bg-background overflow-hidden text-foreground antialiased select-none">
      <DocumentSidebar
        documents={docs.documents}
        statuses={docs.statuses}
        uploading={docs.uploading}
        refreshing={docs.refreshing}
        onUpload={docs.upload}
        onRefresh={docs.refresh}
        onRequestDelete={setDocToDelete}
      />

      <div className="flex-1 flex flex-col bg-background min-w-0">
        <DashboardHeader
          userEmail={userEmail}
          activeTab={activeTab}
          onTabChange={setActiveTab}
          onSignOut={handleSignOut}
        />

        {activeTab === 'chat' && (
          <ChatPanel
            messages={chat.messages}
            isGenerating={chat.isGenerating}
            copiedMessageId={chat.copiedMessageId}
            userEmail={userEmail}
            documentCount={docs.documents.length}
            onSend={chat.send}
            onStop={chat.stop}
            onClear={chat.clear}
            onCopy={chat.copyMessage}
          />
        )}

        {activeTab === 'search' && (
          <SearchPanel
            query={search.query}
            onQueryChange={search.setQuery}
            results={search.results}
            isSearching={search.isSearching}
            hasRun={search.hasRun}
            onSearch={search.run}
            onAnalyse={handleAnalyse}
          />
        )}

        {activeTab === 'vault' && (
          <VaultPanel
            documents={docs.documents}
            statuses={docs.statuses}
            uploading={docs.uploading}
            onUpload={docs.upload}
            onFindSegments={handleFindSegments}
            onRequestDelete={setDocToDelete}
          />
        )}
      </div>

      <DeleteDocumentDialog
        filename={docToDelete}
        isDeleting={isDeleting}
        onCancel={() => setDocToDelete(null)}
        onConfirm={handleConfirmDelete}
      />
    </div>
  );
}
