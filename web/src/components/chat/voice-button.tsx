import { Loader2, Mic, MicOff } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useVoiceRecorder, type VoiceState } from "@/hooks/use-voice-recorder";

interface VoiceButtonProps {
  onTranscript: (text: string) => void;
  disabled: boolean;
}

function formatElapsed(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

export function VoiceButton({ onTranscript, disabled }: VoiceButtonProps) {
  const { state, error, elapsed, toggle } = useVoiceRecorder(onTranscript);

  const icon: Record<VoiceState, React.ReactNode> = {
    idle: <Mic className="h-4 w-4" />,
    recording: <MicOff className="h-4 w-4" />,
    transcribing: <Loader2 className="h-4 w-4 animate-spin" />,
  };

  return (
    <div className="flex items-center gap-1">
      {state === "recording" && (
        <span className="text-xs tabular-nums text-destructive">
          {formatElapsed(elapsed)}
        </span>
      )}
      <Button
        size="icon"
        variant={state === "recording" ? "destructive" : "ghost"}
        onClick={toggle}
        disabled={disabled || state === "transcribing"}
        className="shrink-0"
        title={
          state === "recording"
            ? "Stop recording"
            : state === "transcribing"
              ? "Transcribing..."
              : "Start voice recording"
        }
      >
        {icon[state]}
      </Button>
      {error && <span className="text-xs text-destructive">{error}</span>}
    </div>
  );
}
