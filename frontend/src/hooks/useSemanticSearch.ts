/**
 * Direct retrieval, without the model in the way.
 *
 * This is the same search the chat endpoint runs before generating, exposed on
 * its own so a user can see which passages were matched and on what page - the
 * difference between an answer you can check and one you have to trust.
 */

import { useCallback, useState } from 'react';
import { toast } from 'sonner';

import * as api from '../api/client';
import type { SearchContext } from '../types';

export function useSemanticSearch() {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<SearchContext[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const [hasRun, setHasRun] = useState(false);

  const run = useCallback(async () => {
    const q = query.trim();
    if (!q || isSearching) return;

    setIsSearching(true);
    setHasRun(true);
    try {
      setResults(await api.searchDocuments(q));
    } catch (err: any) {
      toast.error(err?.message || 'Search failed');
      setResults([]);
    } finally {
      setIsSearching(false);
    }
  }, [query, isSearching]);

  return { query, setQuery, results, isSearching, hasRun, run };
}
