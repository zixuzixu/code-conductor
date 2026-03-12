interface QuotaBannerProps {
  onResume: () => void;
}

export function QuotaBanner({ onResume }: QuotaBannerProps) {
  return (
    <div className="flex items-center justify-between gap-3 border-b border-orange-500/30 bg-orange-500/10 px-4 py-2 text-sm text-orange-400">
      <span>API quota exhausted — dispatch paused</span>
      <button
        onClick={onResume}
        className="shrink-0 rounded bg-orange-500/20 px-3 py-1 text-xs font-medium hover:bg-orange-500/30"
      >
        Resume
      </button>
    </div>
  );
}
