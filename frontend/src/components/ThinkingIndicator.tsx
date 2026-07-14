interface ThinkingIndicatorProps {
  label?: string;
}

export function ThinkingIndicator({ label = 'Đang suy nghĩ…' }: ThinkingIndicatorProps) {
  return (
    <div
      className="thinking-indicator"
      role="status"
      aria-live="polite"
      aria-label="Trợ lý đang xử lý câu hỏi"
    >
      {label}
    </div>
  );
}
