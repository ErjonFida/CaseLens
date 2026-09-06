import { useEffect, useRef, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Check, Copy, Scale, Send, Sparkles, Square } from 'lucide-react';

import { Avatar, AvatarFallback } from '@/components/ui/avatar';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { ScrollArea } from '@/components/ui/scroll-area';

import type { ChatMessage } from '../../types';

const PROMPT_SUGGESTIONS = [
  'Summarize the key indemnification obligations in the documents',
  'What are the termination notice periods and conditions?',
  'List all governing law and dispute resolution clauses',
  'Are there any liability caps or exclusion of consequential damages?',
];

interface Props {
  messages: ChatMessage[];
  isGenerating: boolean;
  copiedMessageId: string | null;
  userEmail: string;
  documentCount: number;
  onSend: (text: string) => void;
  onStop: () => void;
  onClear: () => void;
  onCopy: (id: string, content: string) => void;
}

export default function ChatPanel({
  messages,
  isGenerating,
  copiedMessageId,
  userEmail,
  documentCount,
  onSend,
  onStop,
  onClear,
  onCopy,
}: Props) {
  const [input, setInput] = useState('');
  const bottomRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isGenerating]);

  const submit = (text: string) => {
    if (!text.trim()) return;
    setInput('');
    onSend(text);
  };

  return (
    <main className="flex-1 flex flex-col min-h-0 relative">
      <ScrollArea className="flex-1 px-6 py-6">
        <div className="max-w-4xl mx-auto space-y-6">
          {messages.length === 0 ? (
            <div className="py-12 px-4 text-center max-w-xl mx-auto">
              <div className="w-16 h-16 rounded-2xl bg-primary/10 border border-primary/25 flex items-center justify-center text-primary mx-auto mb-4 shadow-sm">
                <Scale className="w-8 h-8" />
              </div>
              <h2 className="text-xl font-bold tracking-tight text-foreground">Welcome to CaseLens</h2>
              <p className="text-sm text-muted-foreground mt-2 leading-relaxed">
                Ask complex legal questions across your uploaded agreements, court briefs, and
                statutory files. All answers strictly cite matching context and page numbers.
              </p>

              <div className="mt-8 text-left">
                <div className="flex items-center gap-1.5 text-xs font-semibold text-muted-foreground mb-3 uppercase tracking-wider">
                  <Sparkles className="w-3.5 h-3.5 text-primary" /> Suggested Inquiries
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                  {PROMPT_SUGGESTIONS.map((prompt) => (
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
            messages.map((m) => {
              const isUser = m.role === 'user';
              return (
                <div
                  key={m.id}
                  className={`flex gap-3.5 select-text ${isUser ? 'justify-end' : 'justify-start'}`}
                >
                  {!isUser && (
                    <Avatar className="h-8 w-8 mt-1 shrink-0 border border-primary/20">
                      <AvatarFallback className="bg-primary/10 text-primary text-xs font-bold">
                        <Scale className="w-4 h-4" />
                      </AvatarFallback>
                    </Avatar>
                  )}

                  <div className="max-w-[82%] group relative space-y-1">
                    <div
                      className={`p-4 rounded-2xl text-sm leading-relaxed shadow-sm ${
                        isUser
                          ? 'bg-primary text-primary-foreground rounded-tr-none'
                          : 'bg-card border border-border text-card-foreground rounded-tl-none'
                      }`}
                    >
                      {isUser ? (
                        <p className="whitespace-pre-wrap">{m.content}</p>
                      ) : (
                        <div className="prose prose-invert prose-sm max-w-none prose-p:leading-relaxed prose-pre:bg-background/80 prose-pre:border prose-pre:border-border">
                          {m.content ? (
                            <ReactMarkdown remarkPlugins={[remarkGfm]}>{m.content}</ReactMarkdown>
                          ) : (
                            <div className="flex items-center gap-2 text-muted-foreground py-1">
                              <Sparkles className="w-4 h-4 animate-spin text-primary" />
                              <span className="text-xs">
                                Analyzing case context and formulating legal response...
                              </span>
                            </div>
                          )}
                        </div>
                      )}
                    </div>

                    {!isUser && m.content && (
                      <div className="flex items-center gap-2 px-1 pt-1 opacity-0 group-hover:opacity-100 transition-opacity">
                        <Button
                          variant="ghost"
                          size="icon-sm"
                          onClick={() => onCopy(m.id, m.content)}
                          className="h-6 w-6 text-muted-foreground hover:text-foreground"
                        >
                          {copiedMessageId === m.id ? (
                            <Check className="w-3 h-3 text-emerald-400" />
                          ) : (
                            <Copy className="w-3 h-3" />
                          )}
                        </Button>
                        <span className="text-[10px] text-muted-foreground">
                          {copiedMessageId === m.id ? 'Copied' : 'Copy'}
                        </span>
                      </div>
                    )}
                  </div>

                  {isUser && (
                    <Avatar className="h-8 w-8 mt-1 shrink-0 border border-border">
                      <AvatarFallback className="bg-secondary text-secondary-foreground text-xs font-bold">
                        {userEmail ? userEmail.slice(0, 1).toUpperCase() : 'U'}
                      </AvatarFallback>
                    </Avatar>
                  )}
                </div>
              );
            })
          )}
          <div ref={bottomRef} />
        </div>
      </ScrollArea>

      <div className="p-4 border-t border-border bg-card/40 backdrop-blur-md">
        <div className="max-w-4xl mx-auto">
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
                  ? 'Upload a document first, then ask questions...'
                  : 'Ask any legal question based on your uploaded case files...'
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
                <Button type="submit" disabled={!input.trim()} size="sm" className="h-8 w-9 p-0 font-medium">
                  <Send className="w-4 h-4" />
                </Button>
              )}
            </div>
          </form>

          <div className="flex items-center justify-between text-[11px] text-muted-foreground mt-2 px-1">
            <span>Powered by Google Gemini • Responses cite source files &amp; pages</span>
            {messages.length > 0 && (
              <button
                type="button"
                onClick={onClear}
                className="hover:text-destructive underline decoration-dotted transition-colors cursor-pointer"
              >
                Clear Conversation
              </button>
            )}
          </div>
        </div>
      </div>
    </main>
  );
}
