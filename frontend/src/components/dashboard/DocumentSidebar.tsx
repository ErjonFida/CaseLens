import { useState } from 'react';
import { FileText, FolderOpen, RefreshCw, Search, ShieldCheck, Trash2, Upload } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';

import { DocumentIcon, DocumentStatusBadge } from './DocumentMeta';
import type { DocumentStatusMap } from '../../types';

const ACCEPTED_FILES = '.pdf,.txt,.png,.jpg,.jpeg,.tiff';

interface Props {
  documents: string[];
  statuses: DocumentStatusMap;
  uploading: boolean;
  refreshing: boolean;
  onUpload: (file: File) => void;
  onRefresh: () => void;
  onRequestDelete: (filename: string) => void;
}

export default function DocumentSidebar({
  documents,
  statuses,
  uploading,
  refreshing,
  onUpload,
  onRefresh,
  onRequestDelete,
}: Props) {
  // The filter is nobody else's business, so it stays here rather than being
  // lifted into the dashboard's state.
  const [filter, setFilter] = useState('');
  const visible = documents.filter((d) => d.toLowerCase().includes(filter.toLowerCase()));

  return (
    <aside className="w-80 border-r border-border bg-card/60 flex flex-col shrink-0">
      <div className="p-4 border-b border-border flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <div className="w-9 h-9 rounded-lg bg-primary/10 border border-primary/20 flex items-center justify-center text-primary shadow-sm">
            <FolderOpen className="w-5 h-5" />
          </div>
          <div>
            <h2 className="text-sm font-semibold text-foreground tracking-tight">Case Files Vault</h2>
            <p className="text-xs text-muted-foreground">
              {documents.length} {documents.length === 1 ? 'document' : 'documents'} indexed
            </p>
          </div>
        </div>

        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="ghost"
              size="icon-sm"
              onClick={onRefresh}
              disabled={refreshing}
              className="text-muted-foreground hover:text-foreground"
            >
              <RefreshCw className={`w-4 h-4 ${refreshing ? 'animate-spin' : ''}`} />
            </Button>
          </TooltipTrigger>
          <TooltipContent>Refresh Document List</TooltipContent>
        </Tooltip>
      </div>

      <div className="p-3 border-b border-border/80">
        <label className="cursor-pointer block">
          <div
            className={`flex items-center justify-center gap-2 w-full py-2.5 px-3 rounded-lg border border-dashed border-primary/40 bg-primary/5 hover:bg-primary/10 transition-all text-primary text-xs font-medium ${
              uploading ? 'opacity-60 pointer-events-none' : ''
            }`}
          >
            <Upload className={`w-4 h-4 ${uploading ? 'animate-bounce' : ''}`} />
            <span>{uploading ? 'Uploading Document...' : 'Upload Legal Document'}</span>
          </div>
          <input
            type="file"
            className="hidden"
            accept={ACCEPTED_FILES}
            disabled={uploading}
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) onUpload(file);
              e.target.value = '';
            }}
          />
        </label>
        <div className="flex justify-between items-center text-[10px] text-muted-foreground mt-1.5 px-1">
          <span>Supported: PDF, TXT, OCR Images</span>
          <span>Max 25MB</span>
        </div>
      </div>

      <div className="p-3 border-b border-border/60">
        <div className="relative">
          <Search className="w-3.5 h-3.5 absolute left-2.5 top-2.5 text-muted-foreground" />
          <Input
            placeholder="Filter indexed documents..."
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            className="pl-8 h-8 text-xs bg-background/50"
          />
        </div>
      </div>

      <ScrollArea className="flex-1 p-3">
        <div className="space-y-1.5">
          {visible.map((doc) => (
            <div
              key={doc}
              className="group relative flex items-center justify-between p-2.5 rounded-lg border border-border/40 bg-card/40 hover:bg-accent/40 hover:border-border transition-all"
            >
              <div className="flex items-center gap-2.5 min-w-0 pr-2">
                <div className="shrink-0">
                  <DocumentIcon filename={doc} />
                </div>
                <div className="min-w-0">
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <p className="text-xs font-medium text-foreground truncate cursor-default">{doc}</p>
                    </TooltipTrigger>
                    <TooltipContent>{doc}</TooltipContent>
                  </Tooltip>
                  <div className="mt-0.5">
                    <DocumentStatusBadge status={statuses[doc] || 'completed'} />
                  </div>
                </div>
              </div>

              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    onClick={() => onRequestDelete(doc)}
                    className="opacity-0 group-hover:opacity-100 text-muted-foreground hover:text-destructive hover:bg-destructive/10 transition-all shrink-0 h-7 w-7"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </Button>
                </TooltipTrigger>
                <TooltipContent>Delete Document</TooltipContent>
              </Tooltip>
            </div>
          ))}

          {visible.length === 0 && !uploading && (
            <div className="text-center py-8 px-4 text-muted-foreground">
              <FileText className="w-8 h-8 mx-auto mb-2 opacity-30" />
              <p className="text-xs font-medium">No documents found</p>
              <p className="text-[11px] mt-0.5">
                {filter
                  ? 'No matching files for your query'
                  : 'Upload contracts, briefs, or evidence files to get started'}
              </p>
            </div>
          )}
        </div>
      </ScrollArea>

      <div className="p-3 border-t border-border bg-background/50 flex items-center gap-2 text-[11px] text-muted-foreground">
        <ShieldCheck className="w-4 h-4 text-primary shrink-0" />
        <span className="truncate">Client-Isolated Vector Store</span>
      </div>
    </aside>
  );
}
