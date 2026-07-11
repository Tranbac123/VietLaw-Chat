interface ErrorBannerProps {
  message: string;
  onDismiss?: () => void;
}

export function ErrorBanner({ message, onDismiss }: ErrorBannerProps) {
  return (
    <div className="error-banner" role="alert">
      <span className="error-banner-mark" aria-hidden="true">!</span>
      <p>{message}</p>
      {onDismiss && (
        <button type="button" onClick={onDismiss} aria-label="Đóng thông báo lỗi">×</button>
      )}
    </div>
  );
}
