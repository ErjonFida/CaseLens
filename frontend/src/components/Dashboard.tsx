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
import * as Sheet from '@radix-ui/react-dialog';

import { DialogOverlay } from '@/components/ui/dialog';
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
  const [isDemo, setIsDemo] = useState(false);
  const [activeTab, setActiveTab] = useState<DashboardTab>('chat');
  const [docToDelete, setDocToDelete] = useState<string | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);
  const [docsOpen, setDocsOpen] = useState(false);
  // Documents the user chose to ask about; empty means all of them. Filtered
  // against the live list, so a document deleted anywhere drops out.
  const [selected, setSelected] = useState<string[]>([]);

  const docs = useDocuments();
  const chat = useChat();
  const search = useSemanticSearch();

  const { load: loadDocuments } = docs;
  const selection = selected.filter((d) => docs.documents.includes(d));

  const toggleSelected = useCallback(
    (filename: string) =>
      setSelected((prev) => (prev.includes(filename) ? prev.filter((d) => d !== filename) : [...prev, filename])),
    []
  );

  useEffect(() => {
    let cancelled = false;

    (async () => {
      try {
        const me = await api.getCurrentUser();
        if (cancelled) return;
        setUserEmail(me.email || '');
        setIsDemo(Boolean(me.is_demo));
        await loadDocuments();
      } catch (err: any) {
        if (cancelled || err?.status === 401) return; // fetchWithAuth is already on its way to /login
        // A network failure is not an auth failure: keep the session and say the
        // server is unreachable, rather than bouncing to /login where signing
        // in cannot work either.
        console.error('Failed to load user data:', err);
        toast.error("Couldn't reach the server. Try again in a moment.");
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [loadDocuments, navigate]);

  const handleSignOut = useCallback(async () => {
    await api.logout();
    removeStoredToken();
    toast.info('Signed out');
    navigate('/login');
  }, [navigate]);

  const handleConfirmDelete = useCallback(async () => {
    if (!docToDelete) return;
    setIsDeleting(true);
    try {
      await docs.remove(docToDelete);
      setSelected((prev) => prev.filter((d) => d !== docToDelete));
    } catch (err: any) {
      toast.error(err?.message || `Couldn't delete ${docToDelete}. Try again.`);
    } finally {
      setIsDeleting(false);
      setDocToDelete(null);
    }
  }, [docToDelete, docs]);

  const handleAnalyse = useCallback(
    (result: SearchContext) => {
      setActiveTab('chat');
      chat.send(
        `Explain this passage from ${result.metadata?.filename}, page ${result.metadata?.page}:\n\n"${result.text.slice(0, 200)}…"`,
        [result.metadata.filename]
      );
    },
    [chat]
  );

  const handleFindSegments = useCallback(
    (filename: string) => {
      search.setQuery(filename);
      setActiveTab('search');
    },
    [search]
  );

  const sidebar = (
    <DocumentSidebar
      documents={docs.documents}
      statuses={docs.statuses}
      uploading={docs.uploading}
      refreshing={docs.refreshing}
      onUpload={docs.upload}
      onRefresh={docs.refresh}
      onRequestDelete={setDocToDelete}
      selected={selection}
      onToggleSelect={toggleSelected}
      onClearSelection={() => setSelected([])}
      readOnly={isDemo}
    />
  );

  return (
    <div className="flex h-screen w-full bg-background overflow-hidden text-foreground antialiased">
      <div className="hidden md:flex">{sidebar}</div>

      <Sheet.Root open={docsOpen} onOpenChange={setDocsOpen}>
        <Sheet.Portal>
          <DialogOverlay className="md:hidden" />
          <Sheet.Content aria-describedby={undefined} className="fixed inset-y-0 left-0 z-50 flex md:hidden">
            <Sheet.Title className="sr-only">Documents</Sheet.Title>
            {sidebar}
          </Sheet.Content>
        </Sheet.Portal>
      </Sheet.Root>

      <div className="flex-1 flex flex-col bg-background min-w-0">
        <DashboardHeader
          userEmail={userEmail}
          activeTab={activeTab}
          onTabChange={setActiveTab}
          onSignOut={handleSignOut}
          onOpenDocuments={() => setDocsOpen(true)}
        />

        {activeTab === 'chat' && (
          <ChatPanel
            messages={chat.messages}
            isGenerating={chat.isGenerating}
            copiedMessageId={chat.copiedMessageId}
            documents={docs.documents}
            selectedCount={selection.length}
            isDemo={isDemo}
            onSend={(text) => chat.send(text, selection)}
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
            onSearch={() => search.run(selection)}
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
            readOnly={isDemo}
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
