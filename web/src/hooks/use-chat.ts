import { useCallback, useState } from "react";
import { streamChat } from "@/lib/api";

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

export function useChat(sessionId: string | null) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [streaming, setStreaming] = useState(false);

  const send = useCallback(
    async (text: string) => {
      if (!sessionId || streaming) return;

      setMessages((prev) => [...prev, { role: "user", content: text }]);
      setStreaming(true);

      let full = "";
      setMessages((prev) => [...prev, { role: "assistant", content: "" }]);

      try {
        for await (const chunk of streamChat(sessionId, text)) {
          full += chunk;
          setMessages((prev) => {
            const updated = [...prev];
            updated[updated.length - 1] = { role: "assistant", content: full };
            return updated;
          });
        }
      } catch (e) {
        setMessages((prev) => {
          const updated = [...prev];
          updated[updated.length - 1] = {
            role: "assistant",
            content: full + `\n\n[Error: ${e}]`,
          };
          return updated;
        });
      } finally {
        setStreaming(false);
      }
    },
    [sessionId, streaming],
  );

  const clear = useCallback(() => setMessages([]), []);

  return { messages, streaming, send, clear };
}
