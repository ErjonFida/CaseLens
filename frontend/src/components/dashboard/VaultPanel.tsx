import { FolderOpen, Search, Trash2, Upload } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';

import { DocumentIcon, DocumentStatusBadge } from './DocumentMeta';
import type { DocumentStatusMap } from '../../types';

const ACCEPTED_FILES = '.pdf,.txt,.png,.jpg,.jpeg,.tiff';

interface Props {
  documents: string[];
  statuses: DocumentStatusMap;
  uploading: boolean;
  onUpload: (file: File) => void;
  onFindSegments: (filename: string) => void;
  onRequestDelete: (filename: string) => void;
}

export default function VaultPanel({
  documents,
  statuses,
  uploading,
  onUpload,
  onFindSegments,
  onRequestDelete,
}: Props) {
  return (
    <main className="flex-1 flex flex-col min-h-0 p-6 overflow-y-auto">
      <div className="max-w-4xl w-full mx-auto space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-xl font-bold tracking-tight text-foreground">
              Document Vault &amp; Status
            </h2>
            <p className="text-xs text-muted-foreground mt-1">
              Manage case files and verify proper document uploads
            </p>
          </div>

          <label className="cursor-pointer">
            <Button size="sm" className="gap-2 pointer-events-none">
              <Upload className="w-4 h-4" /> Upload New File
            </Button>
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
        </div>

        <Card className="border-border/80">
          <CardContent className="p-0">
            <div className="divide-y divide-border">
              {documents.map((doc) => (
                <div
                  key={doc}
                  className="p-4 flex items-center justify-between hover:bg-card/80 transition-colors"
                >
                  <div className="flex items-center gap-3">
                    <div className="p-2 rounded-lg bg-secondary/80">
                      <DocumentIcon filename={doc} />
                    </div>
                    <div>
                      <p className="text-sm font-medium text-foreground">{doc}</p>
                      <div className="flex items-center gap-2 mt-1">
                        <DocumentStatusBadge status={statuses[doc] || 'completed'} />
                        <span className="text-xs text-muted-foreground">
                          Upload and synchronisation successful
                        </span>
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => onFindSegments(doc)}
                      className="text-xs gap-1.5"
                    >
                      <Search className="w-3.5 h-3.5" /> Find Segments
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => onRequestDelete(doc)}
                      className="text-xs text-destructive hover:bg-destructive/10"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </Button>
                  </div>
                </div>
              ))}

              {documents.length === 0 && (
                <div className="text-center py-12 text-muted-foreground">
                  <FolderOpen className="w-10 h-10 mx-auto mb-2 opacity-30" />
                  <p className="text-sm font-medium">Vault is currently empty</p>
                  <p className="text-xs mt-1">Upload legal documents for processing.</p>
                </div>
              )}
            </div>
          </CardContent>
        </Card>
      </div>
    </main>
  );
}
