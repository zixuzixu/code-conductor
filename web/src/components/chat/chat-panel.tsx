import { useEffect, useRef } from "react";
import { ScrollArea } from "@/components/ui/scroll-area";
import type { ChatMessage } from "@/hooks/use-chat";
import { ChatInput } from "./chat-input";
import { Message } from "./message";

interface ChatPanelProps {
  messages: ChatMessage[];
  streaming: boolean;
  onSend: (message: string) => void;
  sessionId: string | null;
}

export function ChatPanel({ messages, streaming, onSend, sessionId }: ChatPanelProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  return (
    <div className="flex flex-1 flex-col">
      <ScrollArea className="flex-1 p-4">
        {!sessionId ? (
          <div className="flex h-full items-center justify-center">
            <p className="text-muted-foreground">Select a session to start chatting</p>
          </div>
        ) : messages.length === 0 ? (
          <div className="flex h-full items-center justify-center">
            <p className="text-muted-foreground">Send a message to get started</p>
          </div>
        ) : (
          <div className="space-y-4">
            {messages.map((m, i) => (
              <Message key={i} message={m} />
            ))}
            {streaming && (
              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-primary" />
                Thinking...
              </div>
            )}
            <div ref={bottomRef} />
          </div>
        )}
      </ScrollArea>
      <ChatInput onSend={onSend} disabled={streaming} sessionId={sessionId} />
    </div>
  );
}
