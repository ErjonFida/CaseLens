import { MessageSquare, Search } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader } from '@/components/ui/card';
import { Input } from '@/components/ui/input';

import type { SearchContext } from '../../types';

interface Props {
  query: string;
  onQueryChange: (value: string) => void;
  results: SearchContext[];
  isSearching: boolean;
  hasRun: boolean;
  onSearch: () => void;
  /** Hand a passage to the assistant. The dashboard owns the tab switch. */
  onAnalyse: (result: SearchContext) => void;
}

export default function SearchPanel({
  query,
  onQueryChange,
  results,
  isSearching,
  hasRun,
  onSearch,
  onAnalyse,
}: Props) {
  return (
    <main className="flex-1 flex flex-col min-h-0 p-6 overflow-y-auto">
      <div className="max-w-4xl w-full mx-auto space-y-6">
        <div>
          <h2 className="text-xl font-bold tracking-tight text-foreground">Document Explorer</h2>
          <p className="text-xs text-muted-foreground mt-1">
            Search the knowledge base directly to inspect relevant text segments, page numbers, and
            exact citations.
          </p>
        </div>

        <Card className="border-border/80 bg-card/60">
          <CardContent className="p-4">
            <form
              onSubmit={(e) => {
                e.preventDefault();
                onSearch();
              }}
              className="flex gap-2"
            >
              <div className="relative flex-1">
                <Search className="w-4 h-4 absolute left-3 top-3 text-muted-foreground" />
                <Input
                  value={query}
                  onChange={(e) => onQueryChange(e.target.value)}
                  placeholder="Search for legal terms, clauses (e.g. relevant parties, supposed breaches, relevant laws)..."
                  className="pl-9 h-10 bg-background"
                />
              </div>
              <Button type="submit" loading={isSearching} disabled={!query.trim()}>
                Search Segments
              </Button>
            </form>
          </CardContent>
        </Card>

        <div className="space-y-4">
          {results.map((result, idx) => (
            <Card key={idx} className="border-border/80 bg-card/80 shadow-sm">
              <CardHeader className="p-4 pb-2 flex flex-row items-center justify-between space-y-0">
                <div className="flex items-center gap-2">
                  <Badge variant="info" className="text-xs">
                    Match #{idx + 1}
                  </Badge>
                  <span className="text-xs font-semibold text-foreground">
                    {result.metadata?.filename || 'Document'}
                  </span>
                  {result.metadata?.page && (
                    <Badge variant="outline" className="text-[10px]">
                      Page {result.metadata.page}
                    </Badge>
                  )}
                </div>

                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => onAnalyse(result)}
                  className="text-xs gap-1 h-7 text-primary hover:text-primary"
                >
                  <MessageSquare className="w-3 h-3" /> Analyze in Chat
                </Button>
              </CardHeader>
              <CardContent className="p-4 pt-2">
                <p className="text-xs text-muted-foreground whitespace-pre-wrap leading-relaxed bg-background/50 p-3 rounded-lg border border-border/50 font-mono">
                  {result.text}
                </p>
              </CardContent>
            </Card>
          ))}

          {hasRun && results.length === 0 && !isSearching && (
            <div className="text-center py-12 text-muted-foreground">
              <Search className="w-8 h-8 mx-auto mb-2 opacity-30" />
              <p className="text-sm font-medium">No semantic matches found</p>
              <p className="text-xs mt-1">
                Try broadening your search query or uploading additional documents.
              </p>
            </div>
          )}
        </div>
      </div>
    </main>
  );
}
