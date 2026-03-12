import { Send } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

interface ChatInputProps {
  onSend: (message: string) => void;
  disabled: boolean;
  sessionId: string | null;
}

export function ChatInput({ onSend, disabled, sessionId }: ChatInputProps) {
  const [draft, setDraft] = useState("");

  // Persist draft per session in localStorage
  const storageKey = sessionId ? `draft-${sessionId}` : null;

  const handleChange = (value: string) => {
    setDraft(value);
    if (storageKey) localStorage.setItem(storageKey, value);
  };

  const handleSend = () => {
    if (!draft.trim() || disabled) return;
    onSend(draft.trim());
    setDraft("");
    if (storageKey) localStorage.removeItem(storageKey);
  };

  // Restore draft when session changes
  useState(() => {
    if (storageKey) {
      const saved = localStorage.getItem(storageKey);
      if (saved) setDraft(saved);
    }
  });

  return (
    <div className="flex items-end gap-2 border-t border-border p-4">
      <Textarea
        placeholder={sessionId ? "Type a message... (Ctrl+Enter to send)" : "Select a session first"}
        value={draft}
        onChange={(e) => handleChange(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
            e.preventDefault();
            handleSend();
          }
        }}
        disabled={!sessionId || disabled}
        className="min-h-[60px] max-h-[200px] resize-none text-sm"
        rows={2}
      />
      <Button
        size="icon"
        onClick={handleSend}
        disabled={!draft.trim() || disabled || !sessionId}
        className="shrink-0"
      >
        <Send className="h-4 w-4" />
      </Button>
    </div>
  );
}
