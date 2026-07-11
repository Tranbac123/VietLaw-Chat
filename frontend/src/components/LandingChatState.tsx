import { DemoButtons } from './DemoButtons';

interface LandingChatStateProps {
  disabled: boolean;
  onDemoSubmit: (question: string, userType: 'citizen' | 'household_business' | 'foreign_visitor') => void;
}

export function LandingChatState({ disabled, onDemoSubmit }: LandingChatStateProps) {
  return (
    <section className="landing-chat-state" aria-labelledby="landing-heading">
      <p className="eyebrow">VietLaw-Chat <span>MVP Demo</span></p>
      <h1 id="landing-heading">Trợ lý định hướng pháp lý ban đầu bằng tiếng Việt</h1>
      <p className="landing-description">
        Mô tả vấn đề pháp lý đời thường để xem nhóm rủi ro, thông tin cần làm rõ, giấy tờ cần chuẩn bị và nguồn tham khảo phù hợp.
      </p>
      <DemoButtons disabled={disabled} onSubmit={onDemoSubmit} />
      <p className="landing-privacy">Không nhập thông tin cá nhân nhạy cảm trong bản demo.</p>
    </section>
  );
}
