import { cn } from "@/lib/utils";
import type { ChatMessage } from "@/hooks/use-chat";

interface MessageProps {
  message: ChatMessage;
}

export function Message({ message }: MessageProps) {
  const isUser = message.role === "user";

  return (
    <div className={cn("flex", isUser ? "justify-end" : "justify-start")}>
      <div
        className={cn(
          "max-w-[80%] rounded-lg px-4 py-2.5 text-sm leading-relaxed",
          isUser
            ? "bg-primary text-primary-foreground"
            : "bg-muted text-foreground",
        )}
      >
        <pre className="whitespace-pre-wrap break-words font-sans">{message.content}</pre>
      </div>
    </div>
  );
}
