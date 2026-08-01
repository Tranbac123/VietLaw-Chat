/**
 * Correction Round 1 (M-03): the previous wording claimed VietLaw Beta
 * "có thể tra cứu nguồn pháp luật chính thức cho các câu hỏi khác" (can
 * look up official legal sources), but no search provider is wired in this
 * build (`VIETLAW_OFFICIAL_LEGAL_SEARCH_ENABLED` is off by default and no
 * concrete provider exists yet -- see `official_legal_search.py`'s module
 * docstring). Static, conservative copy: no backend capability-contract
 * endpoint exists to derive this text from without a broader refactor, so
 * this string must be kept in sync by hand with the actual deployed
 * capability until one exists.
 */
const BETA_SCOPE_TEXT =
  'VietLaw Beta hỗ trợ chuyên sâu tình huống đặt cọc thuê nhà, một số vi phạm giao thông phổ biến '
  + 'và cung cấp hướng dẫn chung cho các vấn đề pháp luật khác. '
  + 'Tính năng tra cứu nguồn pháp luật chính thức đang trong quá trình hoàn thiện. '
  + 'Nội dung chỉ mang tính tham khảo, không thay thế tư vấn pháp lý chuyên nghiệp.';

interface SamplePromptGroup {
  title: string;
  prompts: string[];
}

/** Task §10.1: samples are grouped so a user can see the difference between
 * curated-verified scope, curated-traffic scope, and the general
 * official-source/general-guidance fallback -- never presented as if the
 * third group were curated. */
const SAMPLE_PROMPT_GROUPS: SamplePromptGroup[] = [
  {
    title: 'Đặt cọc thuê nhà',
    prompts: ['Tôi đặt cọc thuê nhà nhưng chủ nhà không cho vào ở thì phải làm sao?'],
  },
  {
    title: 'Giao thông',
    prompts: ['Tôi vượt đèn đỏ khi đi xe máy thì bị phạt bao nhiêu?'],
  },
  {
    title: 'Câu hỏi pháp luật khác',
    prompts: [
      'Công ty giữ lương của tôi không trả thì tôi nên làm gì?',
      'Hàng xóm lấn chiếm đất của gia đình tôi thì phải làm sao?',
    ],
  },
];

interface LandingChatStateProps {
  /** Optional: clicking a sample prompt fills the composer with its text. */
  onSelectPrompt?: (prompt: string) => void;
}

export function LandingChatState({ onSelectPrompt }: LandingChatStateProps = {}) {
  return (
    <section className="landing-chat-state" aria-labelledby="landing-heading">
      <h1 id="landing-heading">Xin chào, hôm nay tôi có thể giúp gì cho bạn?</h1>
      <p className="landing-beta-scope">{BETA_SCOPE_TEXT}</p>
      <div className="landing-sample-prompts">
        {SAMPLE_PROMPT_GROUPS.map((group) => (
          <div className="landing-sample-group" key={group.title}>
            <h2 className="landing-sample-group-title">{group.title}</h2>
            <ul className="landing-sample-group-list">
              {group.prompts.map((prompt) => (
                <li key={prompt}>
                  {onSelectPrompt ? (
                    <button
                      type="button"
                      className="landing-sample-prompt"
                      onClick={() => onSelectPrompt(prompt)}
                    >
                      {prompt}
                    </button>
                  ) : (
                    <span className="landing-sample-prompt">{prompt}</span>
                  )}
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
    </section>
  );
}
