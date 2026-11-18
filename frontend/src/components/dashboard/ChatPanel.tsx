import { createContext, useContext, useEffect, useRef, useState } from 'react';
import ReactMarkdown, { defaultUrlTransform, type Components } from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Check, Copy, Scale, Send, Square } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { ScrollArea } from '@/components/ui/scroll-area';

import { citationsIn, linkCitations, parseCitation, type Citation } from '../../lib/citations';
import type { ChatMessage } from '../../types';
import SourcePanel, { type OpenCitation } from './SourcePanel';

const PROMPT_SUGGESTIONS = [
  'Summarize the key indemnification obligations in the documents',
  'What are the termination notice periods and conditions?',
  'List all governing law and dispute resolution clauses',
  'Are there any liability caps or exclusion of consequential damages?',
];

// Each asks about a contract backend/seed_demo.py puts in the demo, and has an
// annotated answer in evals/datasets/gold.jsonl: a date, a supported "no", a
// clause the contract lacks, and a list.
const DEMO_SUGGESTIONS = [
  'When does the Scoutcam agreement become effective?',
  'Does anyone outside the Ofgban agreement have rights under it?',
  'What happens to the Transmontaigne Partners agreement if one side is acquired?',
  'What insurance must be carried under the Merit Life Insurance agreement?',
];

// A context, not a closure, keeps AnswerLink one stable component; a new one
// per render would remount every chip on every streamed token.
const CitationContext = createContext<{
  open: Citation | null;
  onOpen: (citation: Citation, chip: HTMLElement) => void;
}>({ open: null, onOpen: () => undefined });

function CitationChip({ citation: c }: { citation: Citation }) {
  const { open, onOpen } = useContext(CitationContext);
  const isOpen = open?.filename === c.filename && open.page === c.page && open.claim === c.claim;
  return (
    <button
      type="button"
      onClick={(e) => onOpen(c, e.currentTarget)}
      aria-pressed={isOpen}
      aria-label={`Open page ${c.page} of ${c.filename}`}
      title={`${c.filename}, page ${c.page}`}
      className={`inline-flex items-baseline gap-1 max-w-[18rem] mx-0.5 px-1.5 rounded-md border text-xs font-medium align-baseline cursor-pointer transition-colors ${
        isOpen
          ? 'bg-primary text-primary-foreground border-primary'
          : 'bg-primary/10 text-primary border-primary/30 hover:bg-primary/20'
      }`}
    >
      <span className="shrink-0">p.&nbsp;{c.page}</span>
      <span className="truncate opacity-80">{c.filename.replace(/\.[^.]+$/, '')}</span>
    </button>
  );
}

function AnswerLink({ href, children }: { href?: string; children?: React.ReactNode }) {
  const c = href ? parseCitation(href) : null;
  if (c) return <CitationChip citation={c} />;
  return (
    <a href={href} target="_blank" rel="noreferrer" className="underline">
      {children}
    </a>
  );
}

const answerComponents: Components = { a: AnswerLink };
const answerUrlTransform = (url: string) => (url.startsWith('cite:') ? url : defaultUrlTransform(url));

interface Props {
  messages: ChatMessage[];
  isGenerating: boolean;
  copiedMessageId: string | null;
  documents: string[];
  selectedCount: number;
  isDemo: boolean;
  onSend: (text: string) => void;
  onStop: () => void;
  onClear: () => void;
  onCopy: (id: string, content: string) => void;
}

export default function ChatPanel({
  messages,
  isGenerating,
  copiedMessageId,
  documents,
  selectedCount,
  isDemo,
  onSend,
  onStop,
  onClear,
  onCopy,
}: Props) {
  const [input, setInput] = useState('');
  const bottomRef = useRef<HTMLDivElement | null>(null);
  const [source, setSource] = useState<OpenCitation | null>(null);
  const sourceCache = useRef(new Map()).current;
  const sourceOpener = useRef<HTMLElement | null>(null);
  const closeSource = () => {
    setSource(null);
    sourceOpener.current?.focus();
  };
  const documentCount = documents.length;

  const exchanges: { question?: ChatMessage; answer?: ChatMessage }[] = [];
  for (const m of messages) {
    const last = exchanges[exchanges.length - 1];
    if (m.role === 'user') exchanges.push({ question: m });
    else if (last && !last.answer) last.answer = m;
    else exchanges.push({ answer: m });
  }

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isGenerating]);

  const submit = (text: string) => {
    if (!text.trim()) return;
    setInput('');
    onSend(text);
  };

  return (
    <div className="flex-1 flex min-h-0">
      <main className="flex-1 flex flex-col min-h-0 min-w-0 relative">
        <ScrollArea className="flex-1 px-3 py-4 sm:px-6 sm:py-6">
          <div className="max-w-3xl mx-auto">
            {messages.length === 0 ? (
              <div className="py-12 px-4 text-center max-w-xl mx-auto">
                <div className="w-16 h-16 rounded-2xl bg-primary/10 border border-primary/25 flex items-center justify-center text-primary mx-auto mb-4 shadow-sm">
                  <Scale className="w-8 h-8" />
                </div>
                <h2 className="text-xl font-bold tracking-tight text-foreground">
                  {isDemo ? 'Ask about the demo contracts' : 'Ask about your documents'}
                </h2>
                <p className="text-sm text-muted-foreground mt-2 leading-relaxed">
                  Every answer cites the file and page it came from, and each citation opens
                  the passage.
                </p>

                <div className="mt-8 text-left">
                  <div className="text-xs font-medium text-muted-foreground mb-3">
                    Try one of these
                  </div>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                    {(isDemo ? DEMO_SUGGESTIONS : PROMPT_SUGGESTIONS).map((prompt) => (
                      <button
                        key={prompt}
                        type="button"
                        onClick={() => submit(prompt)}
                        className="p-3 rounded-lg border border-border/80 bg-card/60 hover:bg-accent/40 hover:border-primary/40 text-left transition-all group cursor-pointer"
                      >
                        <p className="text-xs font-medium text-foreground group-hover:text-primary transition-colors">
                          {prompt}
                        </p>
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            ) : (
              exchanges.map(({ question, answer }, n) => {
                const streaming = isGenerating && n === exchanges.length - 1;
                const linked = answer?.content ? linkCitations(answer.content, documents) : '';
                const sources = streaming ? [] : citationsIn(linked);
                const copied = answer && copiedMessageId === answer.id;
                return (
                  <article
                    key={(question ?? answer)!.id}
                    className={n > 0 ? 'mt-8 pt-8 border-t border-border' : ''}
                  >
                    {question && (
                      <h2 className="text-[17px] leading-snug font-semibold text-foreground whitespace-pre-wrap">
                        {question.content}
                      </h2>
                    )}

                    {answer && (
                      <CitationContext.Provider
                        value={{
                          open: source,
                          onOpen: (c, chip) => {
                            sourceOpener.current = chip;
                            setSource({ ...c, question: question?.content ?? '' });
                          },
                        }}
                      >
                        {answer.content ? (
                          <div className="answer mt-3 max-w-[70ch] text-[15px] leading-[1.65] text-foreground/90">
                            <ReactMarkdown
                              remarkPlugins={[remarkGfm]}
                              urlTransform={answerUrlTransform}
                              components={answerComponents}
                            >
                              {linked}
                            </ReactMarkdown>
                          </div>
                        ) : (
                          <p className={`mt-3 text-sm text-muted-foreground ${streaming ? 'animate-pulse' : ''}`}>
                            {streaming ? 'Reading the contracts…' : 'Stopped before an answer arrived.'}
                          </p>
                        )}

                        {answer.content && !streaming && (
                          <div className="mt-5 flex flex-wrap items-end gap-x-6 gap-y-3">
                            {sources.length > 0 && (
                              <div className="min-w-0 flex-1">
                                <h3 className="text-xs font-medium text-muted-foreground">Sources</h3>
                                <ul className="mt-1.5 flex flex-wrap gap-1.5 -mx-0.5">
                                  {sources.map((c) => (
                                    <li key={`${c.filename}/${c.page}`} className="min-w-0">
                                      <CitationChip citation={c} />
                                    </li>
                                  ))}
                                </ul>
                              </div>
                            )}
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => onCopy(answer.id, answer.content)}
                              className="ml-auto h-8 gap-1.5 text-xs text-muted-foreground hover:text-foreground"
                            >
                              {copied ? <Check className="w-3.5 h-3.5 text-primary" /> : <Copy className="w-3.5 h-3.5" />}
                              {copied ? 'Copied' : 'Copy answer'}
                            </Button>
                          </div>
                        )}
                      </CitationContext.Provider>
                    )}
                  </article>
                );
              })
            )}
            <div ref={bottomRef} />
          </div>
        </ScrollArea>

        <div className="p-3 sm:p-4 border-t border-border bg-card/40 backdrop-blur-md">
          <div className="max-w-3xl mx-auto">
            <form
              onSubmit={(e) => {
                e.preventDefault();
                submit(input);
              }}
              className="relative flex items-center"
            >
              <Input
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder={
                  documentCount === 0
                    ? 'Upload a document to start asking'
                    : selectedCount > 0
                      ? `Ask about the ${selectedCount} selected ${selectedCount === 1 ? 'document' : 'documents'}`
                      : 'Ask a question about your documents'
                }
                disabled={isGenerating}
                className="pr-24 py-6 rounded-xl bg-card border-border shadow-inner text-sm focus-visible:ring-primary"
              />

              <div className="absolute right-2 flex items-center gap-1.5">
                {isGenerating ? (
                  <Button
                    type="button"
                    variant="destructive"
                    size="sm"
                    onClick={onStop}
                    className="h-8 gap-1 text-xs font-medium"
                  >
                    <Square className="w-3.5 h-3.5 fill-current" />
                    Stop
                  </Button>
                ) : (
                  <Button type="submit" aria-label="Send question" disabled={!input.trim()} size="sm" className="h-8 w-9 p-0 font-medium">
                    <Send className="w-4 h-4" />
                  </Button>
                )}
              </div>
            </form>

            <div className="flex items-center justify-between text-[11px] text-muted-foreground mt-2 px-1">
              <span>Answers cite the file and page they came from</span>
              {messages.length > 0 && (
                <button
                  type="button"
                  onClick={() => {
                    setSource(null);
                    onClear();
                  }}
                  className="hover:text-destructive underline decoration-dotted transition-colors cursor-pointer"
                >
                  Clear conversation
                </button>
              )}
            </div>
          </div>
        </div>
      </main>

      {source && <SourcePanel citation={source} cache={sourceCache} onClose={closeSource} />}
    </div>
  );
}
