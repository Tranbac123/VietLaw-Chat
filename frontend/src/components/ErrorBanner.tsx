interface ErrorBannerProps {
  message: string;
  onDismiss?: () => void;
  /**
   * Offered only when a dispatched submission failed. Retry replays that
   * submission's own snapshot, so it works regardless of what the composer
   * currently holds. Absent means there is nothing to replay.
   */
  onRetry?: () => void;
}

export function ErrorBanner({ message, onDismiss, onRetry }: ErrorBannerProps) {
  return (
    <div className="error-banner" role="alert">
      <span className="error-banner-mark" aria-hidden="true">!</span>
      <p>{message}</p>
      {onRetry && (
        <button
          type="button"
          className="error-banner-retry"
          onClick={onRetry}
          aria-label="Thử lại yêu cầu"
        >
          Thử lại
        </button>
      )}
      {onDismiss && (
        <button type="button" onClick={onDismiss} aria-label="Đóng thông báo lỗi">×</button>
      )}
    </div>
  );
}
