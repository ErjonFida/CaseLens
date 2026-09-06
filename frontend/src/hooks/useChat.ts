/**
 * The streamed conversation: sending, accumulating tokens, stopping.
 *
 * The answer arrives a chunk at a time, so the assistant message is appended
 * empty and rewritten as text lands. A failure replaces that placeholder with
 * the reason rather than leaving a blank bubble, because a silent empty answer
 * is indistinguishable from the model having nothing to say.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { toast } from 'sonner';

import * as api from '../api/client';
import type { ChatMessage } from '../types';

const timestamp = () =>
  new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

export function useChat() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isGenerating, setIsGenerating] = useState(false);
  const [copiedMessageId, setCopiedMessageId] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  // Abort an in-flight stream if the screen goes away mid-answer.
  useEffect(() => () => abortRef.current?.abort(), []);

  const stop = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    setIsGenerating(false);
    toast.info('Response generation stopped');
  }, []);

  const clear = useCallback(() => setMessages([]), []);

  const send = useCallback(
    async (text: string) => {
      const query = text.trim();
      if (!query || isGenerating) return;

      const userMessage: ChatMessage = {
        id: `user-${Date.now()}`,
        role: 'user',
        content: query,
        timestamp: timestamp(),
      };
      const assistantId = `assistant-${Date.now()}`;

      const history = [...messages, userMessage];
      setMessages([
        ...history,
        { id: assistantId, role: 'assistant', content: '', timestamp: timestamp() },
      ]);
      setIsGenerating(true);

      const controller = new AbortController();
      abortRef.current = controller;

      const rewrite = (content: string) =>
        setMessages((prev) => prev.map((m) => (m.id === assistantId ? { ...m, content } : m)));

      try {
        const reader = await api.openChatStream(
          history.map((m) => ({ role: m.role, content: m.content })),
          controller.signal
        );
        const decoder = new TextDecoder();
        let accumulated = '';

        for (;;) {
          const { value, done } = await reader.read();
          if (done) break;
          accumulated += decoder.decode(value, { stream: true });
          rewrite(accumulated);
        }
      } catch (err: any) {
        if (err?.name === 'AbortError') return;
        const reason = err?.message || 'Unable to reach the backend API.';
        toast.error(reason);
        rewrite(
          `**Request failed**\n\n${reason}\n\nNo answer was generated. Check that the FastAPI server is running on port 8000 and that its logs show no errors.`
        );
      } finally {
        setIsGenerating(false);
        abortRef.current = null;
      }
    },
    [messages, isGenerating]
  );

  const copyMessage = useCallback((id: string, content: string) => {
    navigator.clipboard.writeText(content);
    setCopiedMessageId(id);
    toast.success('Copied to clipboard');
    setTimeout(() => setCopiedMessageId(null), 2000);
  }, []);

  return { messages, isGenerating, copiedMessageId, send, stop, clear, copyMessage };
}
