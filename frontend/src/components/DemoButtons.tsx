interface DemoCase {
  label: string;
  question: string;
  userType: 'citizen' | 'household_business' | 'foreign_visitor';
}

const DEMO_CASES: DemoCase[] = [
  {
    label: 'Tiền cọc thuê nhà',
    question: 'Tôi thuê nhà, chủ nhà giữ tiền cọc 2 tháng không trả, tôi phải làm gì?',
    userType: 'citizen',
  },
  {
    label: 'Giấy phạt giao thông',
    question: 'Tôi bị phạt giao thông nhưng không hiểu lỗi ghi trong biên bản.',
    userType: 'citizen',
  },
  {
    label: 'Bán đồ ăn online',
    question: 'Tôi muốn bán đồ ăn online ở quê thì cần giấy tờ gì?',
    userType: 'household_business',
  },
  {
    label: 'Safety demo: né phạt',
    question: 'Làm sao để né phạt giao thông?',
    userType: 'citizen',
  },
  {
    label: 'English unsupported',
    question: 'What documents do I need to open a small food business in Vietnam?',
    userType: 'foreign_visitor',
  },
];

interface DemoButtonsProps {
  disabled: boolean;
  onSubmit: (question: string, userType: DemoCase['userType']) => void;
}

export function DemoButtons({ disabled, onSubmit }: DemoButtonsProps) {
  return (
    <div className="demo-section">
      <p className="demo-heading">Chọn tình huống minh họa</p>
      <div className="demo-buttons">
        {DEMO_CASES.map((demo) => (
          <button
            key={demo.label}
            className="demo-button"
            type="button"
            disabled={disabled}
            onClick={() => onSubmit(demo.question, demo.userType)}
          >
            {demo.label}
          </button>
        ))}
      </div>
    </div>
  );
}
