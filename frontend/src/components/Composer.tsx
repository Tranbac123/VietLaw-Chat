import { useState, type FormEvent, type KeyboardEvent } from 'react';
import type { UserType } from '../api/types';

interface ComposerProps {
  disabled: boolean;
  userType: UserType;
  onUserTypeChange: (userType: UserType) => void;
  onSend: (question: string) => void;
}

export function Composer({ disabled, userType, onUserTypeChange, onSend }: ComposerProps) {
  const [draft, setDraft] = useState('');

  function submit() {
    const question = draft.trim();
    if (!question || disabled) return;

    onSend(question);
    setDraft('');
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    submit();
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      submit();
    }
  }

  return (
    <form className="composer" onSubmit={handleSubmit}>
      <div className="composer-inner">
        <div className="composer-fields">
          <textarea
            className="composer-input"
            value={draft}
            rows={2}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={handleKeyDown}
            disabled={disabled}
            placeholder={'Nhập câu hỏi pháp lý của bạn, ví dụ: "Tôi thuê nhà, chủ nhà giữ tiền cọc không trả..."'}
            aria-label="Câu hỏi pháp lý"
          />
          <div className="composer-options">
            <label>
              Nhóm người dùng
              <select
                value={userType}
                disabled={disabled}
                onChange={(event) => onUserTypeChange(event.target.value as UserType)}
              >
                <option value="citizen">Người dân</option>
                <option value="household_business">Hộ kinh doanh</option>
                <option value="foreign_visitor">Khách nước ngoài</option>
                <option value="unknown">Chưa xác định</option>
              </select>
            </label>
            <p>Không nhập số CCCD, tài khoản ngân hàng, địa chỉ cụ thể hoặc thông tin nhạy cảm.</p>
          </div>
        </div>
        <button className="send-button" type="submit" disabled={disabled || !draft.trim()}>
          {disabled ? 'Đang phân tích' : 'Gửi'}
        </button>
      </div>
    </form>
  );
}
