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
    <main className="flex-1 flex flex-col min-h-0 p-4 sm:p-6 overflow-y-auto">
      <div className="max-w-4xl w-full mx-auto space-y-6">
        <div>
          <h2 className="text-xl font-bold tracking-tight text-foreground">Search</h2>
          <p className="text-xs text-muted-foreground mt-1">
            Find passages in your documents without asking for an answer. Each result shows
            its file and page.
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
                  placeholder="A clause, term or party, e.g. termination notice"
                  className="pl-9 h-10 bg-background"
                />
              </div>
              <Button type="submit" loading={isSearching} disabled={!query.trim()}>
                Search
              </Button>
            </form>
          </CardContent>
        </Card>

        <div className="space-y-4">
          {results.map((result, idx) => (
            <Card key={idx} className="border-border/80 bg-card/80 shadow-sm">
              <CardHeader className="p-4 pb-2 flex flex-row flex-wrap items-center justify-between gap-2 space-y-0">
                <div className="flex items-center gap-2 min-w-0">
                  <span className="text-xs font-semibold text-foreground truncate">
                    {result.metadata?.filename || 'Document'}
                  </span>
                  {result.metadata?.page && (
                    <Badge variant="outline" className="text-[10px] shrink-0">
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
                  <MessageSquare className="w-3 h-3" /> Ask about this passage
                </Button>
              </CardHeader>
              <CardContent className="p-4 pt-2">
                <p className="contract text-foreground/90 whitespace-pre-wrap bg-background/50 p-4 rounded-lg border border-border/50">
                  {result.text}
                </p>
              </CardContent>
            </Card>
          ))}

          {hasRun && results.length === 0 && !isSearching && (
            <div className="text-center py-12 text-muted-foreground">
              <Search className="w-8 h-8 mx-auto mb-2 opacity-30" />
              <p className="text-sm font-medium">No passages matched</p>
              <p className="text-xs mt-1">
                Try different words, or check that the document has finished indexing.
              </p>
            </div>
          )}
        </div>
      </div>
    </main>
  );
}
