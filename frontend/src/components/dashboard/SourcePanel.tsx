/**
 * The chat stream carries no sources, only the "(file, Page N)" the model
 * wrote, so the passage is found again by a search scoped to the cited file.
 * When the cited page isn't among the hits, the panel says so rather than
 * passing another page off as the source.
 */

import { Fragment, useEffect, useRef, useState } from 'react';
import { FileText, X } from 'lucide-react';

import { Button } from '@/components/ui/button';
import * as api from '../../api/client';
import { quotesIn, type Citation } from '../../lib/citations';
import type { SearchContext } from '../../types';

export interface OpenCitation extends Citation {
  /** The question the answer replied to; searched when the claim is empty. */
  question: string;
}

type Found = { passage: SearchContext | null; onPage: boolean };

interface Props {
  citation: OpenCitation;
  cache: Map<string, Found>;
  onClose: () => void;
}

const keyOf = (c: OpenCitation) => `${c.filename}\n${c.page}\n${c.claim || c.question}`;

/** The passage split into plain runs and runs that match a quote from the claim. */
function highlight(text: string, quotes: string[]) {
  if (quotes.length === 0) return [text];
  // Spacing and quote marks differ between the model's quote and the page.
  const pattern = quotes
    .map((q) => q.split(/\s+/).map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('\\s+'))
    .map((q) => q.replace(/['"‘’“”]/g, `['"‘’“”]`))
    .join('|');
  return text.split(new RegExp(`(${pattern})`, 'gi'));
}

export default function SourcePanel({ citation, cache, onClose }: Props) {
  const [found, setFound] = useState<Found | null>(() => cache.get(keyOf(citation)) ?? null);
  const [error, setError] = useState('');
  const markRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    const key = keyOf(citation);
    const cached = cache.get(key);
    setError('');
    setFound(cached ?? null);
    if (cached) return;

    let cancelled = false;
    api
      .searchDocuments(citation.claim || citation.question, [citation.filename])
      .then((hits) => {
        if (cancelled) return;
        const inFile = hits.filter((h) => h.metadata?.filename === citation.filename);
        const onPage = inFile.filter((h) => Number(h.metadata?.page) === citation.page);
        const quotes = quotesIn(citation.claim);
        const quoted = onPage.find((h) => highlight(h.text, quotes).length > 1);
        const result = { passage: quoted ?? onPage[0] ?? inFile[0] ?? null, onPage: onPage.length > 0 };
        cache.set(key, result);
        setFound(result);
      })
      .catch((err) => !cancelled && setError(err?.message || "Couldn't load the passage. Click the citation to try again."));
    return () => {
      cancelled = true;
    };
  }, [citation, cache]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  useEffect(() => {
    markRef.current?.scrollIntoView({ block: 'center' });
  }, [found]);

  const parts = found?.passage ? highlight(found.passage.text, quotesIn(citation.claim)) : [];
  markRef.current = null;

  return (
    <aside
      aria-label="Source"
      className="fixed inset-0 z-40 flex flex-col bg-card lg:static lg:z-auto lg:w-[26rem] lg:shrink-0 lg:border-l lg:border-border"
    >
      <div className="flex items-start gap-3 p-4 border-b border-border">
        <FileText className="w-4 h-4 mt-0.5 shrink-0 text-red-400" />
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold text-foreground break-words">{citation.filename}</p>
          <p className="text-xs text-muted-foreground mt-0.5">Page {citation.page}</p>
        </div>
        <Button
          variant="ghost"
          size="icon-sm"
          onClick={onClose}
          aria-label="Close source"
          autoFocus
          className="shrink-0 text-muted-foreground hover:text-foreground"
        >
          <X className="w-4 h-4" />
        </Button>
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {citation.claim && (
          <p className="text-xs text-muted-foreground leading-relaxed">
            <span className="font-semibold text-foreground">Cited for: </span>
            {citation.claim}
          </p>
        )}

        {error ? (
          <p className="text-sm text-destructive">{error}</p>
        ) : !found ? (
          <div className="space-y-2" aria-label="Loading the passage">
            {[92, 100, 84, 96, 70].map((w) => (
              <div key={w} className="h-3 rounded bg-muted animate-pulse" style={{ width: `${w}%` }} />
            ))}
          </div>
        ) : !found.passage ? (
          <p className="text-sm text-muted-foreground">No passage from this file matched the cited text.</p>
        ) : (
          <>
            {!found.onPage && (
              <p className="text-xs text-amber-300 leading-relaxed">
                Page {citation.page} wasn't among the closest passages in this file. Nearest match, from page{' '}
                {found.passage.metadata.page}:
              </p>
            )}
            <p className="contract text-foreground whitespace-pre-wrap">
              {parts.map((part, i) =>
                i % 2 === 1 ? (
                  <mark
                    key={i}
                    ref={(el) => {
                      markRef.current ??= el;
                    }}
                    className="bg-primary/30 text-foreground rounded-sm px-0.5"
                  >
                    {part}
                  </mark>
                ) : (
                  <Fragment key={i}>{part}</Fragment>
                )
              )}
            </p>
          </>
        )}
      </div>
    </aside>
  );
}
