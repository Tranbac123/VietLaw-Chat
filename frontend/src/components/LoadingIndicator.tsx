export function LoadingIndicator({ label = 'Đang phân tích câu hỏi...' }: { label?: string }) {
  return (
    <div className="loading-indicator" role="status" aria-live="polite">
      <span className="loading-dots" aria-hidden="true"><i /><i /><i /></span>
      {label}
    </div>
  );
}
