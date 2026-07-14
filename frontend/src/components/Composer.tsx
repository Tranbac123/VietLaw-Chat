import { useLayoutEffect, useRef, useState, type FormEvent, type KeyboardEvent } from 'react';

interface ComposerProps {
  inputDisabled: boolean;
  submitDisabled: boolean;
  isEmptyChat: boolean;
  onSend: (question: string) => Promise<boolean>;
}

const MAX_ROWS = 10;

export function Composer({ inputDisabled, submitDisabled, isEmptyChat, onSend }: ComposerProps) {
  const [draft, setDraft] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const isInputDisabled = inputDisabled || submitting;
  const isSubmitDisabled = submitDisabled || submitting;

  function resizeTextarea() {
    const textarea = textareaRef.current;
    if (!textarea) return;

    textarea.style.height = 'auto';
    const styles = window.getComputedStyle(textarea);
    const parsedLineHeight = Number.parseFloat(styles.lineHeight);
    const lineHeight = Number.isFinite(parsedLineHeight)
      ? parsedLineHeight
      : Number.parseFloat(styles.fontSize) * 1.5;
    const maxHeight = (lineHeight * MAX_ROWS)
      + Number.parseFloat(styles.paddingTop)
      + Number.parseFloat(styles.paddingBottom);
    const nextHeight = Math.min(textarea.scrollHeight, maxHeight);

    textarea.style.height = `${nextHeight}px`;
    textarea.style.overflowY = textarea.scrollHeight > maxHeight ? 'auto' : 'hidden';
  }

  useLayoutEffect(() => {
    resizeTextarea();
  }, [draft]);

  async function submit() {
    const question = draft.trim();
    if (!question || isSubmitDisabled) return;

    setSubmitting(true);
    try {
      const sent = await onSend(question);
      if (sent) setDraft('');
    } finally {
      setSubmitting(false);
    }
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void submit();
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      void submit();
    }
  }

  return (
    <form className={`composer ${isEmptyChat ? 'composer--landing' : 'composer--chat'}`} onSubmit={handleSubmit}>
      <div className="composer-inner">
        <div className="composer-input-shell">
          <textarea
            ref={textareaRef}
            className="composer-input"
            value={draft}
            rows={1}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={handleKeyDown}
            disabled={isInputDisabled}
            placeholder={'Nhập câu hỏi pháp lý của bạn, ví dụ: "Tôi thuê nhà, chủ nhà giữ tiền cọc không trả..."'}
            aria-label="Câu hỏi pháp lý"
          />
          <button
            className="send-button"
            type="submit"
            disabled={isSubmitDisabled || !draft.trim()}
            aria-label="Gửi câu hỏi"
            title="Gửi câu hỏi"
          >
            <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
              <path d="M12 19V5m0 0-5 5m5-5 5 5" />
            </svg>
          </button>
        </div>
        <div className="composer-notices">
          <p className="composer-privacy">Không nhập số CCCD, tài khoản ngân hàng, địa chỉ cụ thể hoặc thông tin nhạy cảm.</p>
          {isEmptyChat && (
            <p className="composer-legal-reference">
              Thông tin chỉ mang tính tham khảo, không thay thế tư vấn của luật sư hoặc hướng dẫn của cơ quan pháp lý có thẩm quyền.
            </p>
          )}
        </div>
      </div>
    </form>
  );
}
