/**
 * How a document presents itself: its type icon and its indexing state.
 *
 * Shared because the sidebar and the vault must agree - the same file showing
 * "Indexing" in one panel and "Indexed" in the other would be a bug the user
 * sees before anyone else does.
 */

import {
  AlertCircle,
  FileCheck2,
  FileClock,
  FileCode,
  FileQuestion,
  FileText,
  RefreshCw,
} from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import type { DocumentStatus } from '../../types';

const IMAGE_EXTENSIONS = ['png', 'jpg', 'jpeg', 'tiff', 'bmp'];

export function DocumentIcon({ filename }: { filename: string }) {
  const ext = filename.split('.').pop()?.toLowerCase();
  if (ext === 'pdf') return <FileText className="w-4 h-4 text-red-400" />;
  if (IMAGE_EXTENSIONS.includes(ext || '')) return <FileText className="w-4 h-4 text-emerald-400" />;
  if (ext === 'txt') return <FileCode className="w-4 h-4 text-blue-400" />;
  return <FileQuestion className="w-4 h-4 text-muted-foreground" />;
}

export function DocumentStatusBadge({ status }: { status?: DocumentStatus }) {
  switch (status) {
    case 'completed':
      return (
        <Badge variant="success" className="gap-1 text-[11px] py-0">
          <FileCheck2 className="w-3 h-3" /> Indexed
        </Badge>
      );
    case 'indexing':
      return (
        <Badge variant="warning" className="gap-1 text-[11px] py-0 animate-pulse">
          <FileClock className="w-3 h-3" /> Indexing
        </Badge>
      );
    case 'extracting_text':
      return (
        <Badge variant="info" className="gap-1 text-[11px] py-0 animate-pulse">
          <RefreshCw className="w-3 h-3 animate-spin" /> OCR/Text
        </Badge>
      );
    case 'queued':
      return (
        <Badge variant="secondary" className="gap-1 text-[11px] py-0">
          <FileClock className="w-3 h-3" /> Queued
        </Badge>
      );
    default:
      if (status?.startsWith('error')) {
        return (
          <Badge variant="destructive" className="gap-1 text-[11px] py-0">
            <AlertCircle className="w-3 h-3" /> Error
          </Badge>
        );
      }
      return (
        <Badge variant="outline" className="text-[11px] py-0">
          Ready
        </Badge>
      );
  }
}
