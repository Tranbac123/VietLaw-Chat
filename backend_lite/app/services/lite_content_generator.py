from __future__ import annotations

from ..constants import LITE_MODEL_NAME
from ..runtime.agent_state import AgentState
from ..schemas.content import GeneratedContent
from .deposit_case_facts import (
    classify_follow_up_intent,
    extract_facts,
    extract_facts_from_text,
    known_facts_summary_fragments,
    select_clarifying_questions,
)
from .input_normalizer import InputNormalizer

_DEPOSIT_CHECKLIST = [
    "Hợp đồng thuê nhà hoặc giấy đặt cọc/giấy viết tay",
    "Chứng từ chuyển khoản hoặc biên nhận",
    "Tin nhắn/email trao đổi với chủ nhà",
    "Timeline sự việc",
]
_DEPOSIT_NEXT_STEPS = [
    "Gửi yêu cầu hoàn cọc bằng văn bản (tin nhắn/email) và nêu rõ mốc thời gian phản hồi.",
    "Lưu giữ toàn bộ giấy tờ, chứng từ, tin nhắn liên quan đến việc đặt cọc và thuê nhà.",
    "Nếu chủ nhà tiếp tục không hoàn cọc, tham khảo luật sư hoặc cơ quan chức năng để được hỗ trợ giải quyết tranh chấp.",
]


class LiteContentGenerator:
    model_name = LITE_MODEL_NAME
    used_llm = False

    def __init__(self) -> None:
        self._normalizer = InputNormalizer()

    def _generate_deposit_case(self, state: AgentState, used: list[str]) -> GeneratedContent:
        normalizer = self._normalizer
        prior_user_texts = [
            message.content_text
            for message in state.chat.history_messages
            if message.role == "user" and message.content_text
        ]
        current_text = state.request.question

        prior_facts = extract_facts(prior_user_texts, normalizer)
        current_facts = extract_facts_from_text(current_text, normalizer)
        facts = prior_facts.merge(current_facts)

        already_asked: set[str] = set()
        for message in state.chat.history_messages:
            if message.role == "assistant" and message.content_json is not None:
                ids = message.content_json.metadata.get("asked_question_ids")
                if ids:
                    already_asked.update(ids)

        acknowledgment_fragments = known_facts_summary_fragments(facts)
        acknowledgment = (
            "Đã ghi nhận: " + "; ".join(acknowledgment_fragments) + ". " if acknowledgment_fragments else ""
        )

        if not state.chat.used_current_chat_history:
            selected = select_clarifying_questions(facts, already_asked)
            new_asked = sorted(already_asked | {question_id for question_id, _ in selected})
            summary = (
                acknowledgment
                + "Đây là tranh chấp tiền đặt cọc thuê nhà; hướng xử lý cụ thể còn phụ thuộc vào thỏa thuận, "
                "chứng từ và diễn biến thực tế giữa hai bên."
            )
            return GeneratedContent(
                summary=summary,
                clarifying_questions=[text for _, text in selected],
                checklist=list(_DEPOSIT_CHECKLIST),
                next_steps=list(_DEPOSIT_NEXT_STEPS),
                used_source_ids=used,
                asked_question_ids=new_asked,
            )

        intent = classify_follow_up_intent(current_text, current_facts, normalizer)

        if intent == "risk_concern":
            summary = (
                "Có một số dấu hiệu rủi ro vì nhà chưa được bàn giao và tiền cọc chưa được hoàn trả, nhưng hệ "
                "thống không thể kết luận đây là lừa đảo hình sự hay khẳng định chắc chắn bạn sẽ mất tiền. Khả "
                "năng lấy lại tiền phụ thuộc vào thỏa thuận đặt cọc, chữ ký, chứng từ giao tiền và các trao đổi "
                "giữa hai bên."
            )
            return GeneratedContent(
                summary=summary,
                clarifying_questions=[],
                checklist=[],
                next_steps=[
                    "Tiếp tục thu thập chứng từ, tin nhắn và giấy tờ liên quan đến việc đặt cọc.",
                    "Gửi yêu cầu hoàn cọc bằng văn bản; nếu chủ nhà vẫn từ chối, tham khảo luật sư hoặc cơ quan "
                    "chức năng.",
                ],
                used_source_ids=used,
                asked_question_ids=sorted(already_asked),
            )

        selected = select_clarifying_questions(facts, already_asked)
        new_asked = sorted(already_asked | {question_id for question_id, _ in selected})
        if intent == "fact_update":
            update_fragments = known_facts_summary_fragments(current_facts)
            lead = "Đã cập nhật thông tin: " + ("; ".join(update_fragments) if update_fragments else "thông tin mới") + ". "
        else:
            lead = acknowledgment
        summary = lead + "Dựa trên thông tin hiện có, bạn nên thực hiện các bước sau để yêu cầu hoàn lại tiền cọc."
        return GeneratedContent(
            summary=summary,
            clarifying_questions=[text for _, text in selected],
            checklist=[],
            next_steps=list(_DEPOSIT_NEXT_STEPS),
            used_source_ids=used,
            asked_question_ids=new_asked,
        )

    async def generate(self, state: AgentState) -> GeneratedContent:
        topic = state.classification.detected_topic
        used = list(state.retrieval.retrieved_source_ids)

        if state.classification.decision == "unsupported":
            if topic == "unsupported_language":
                return GeneratedContent(
                    summary="Câu hỏi này nằm ngoài phạm vi ngôn ngữ của bản demo; VietLaw-Chat hiện hỗ trợ định hướng pháp lý bằng tiếng Việt.",
                    clarifying_questions=[],
                    checklist=[],
                    next_steps=["Vui lòng nhập câu hỏi pháp lý bằng tiếng Việt để bản demo có thể hỗ trợ."],
                    used_source_ids=[],
                )
            return GeneratedContent(
                summary="Câu hỏi này nằm ngoài phạm vi pháp lý của bản demo VietLaw-Chat.",
                clarifying_questions=[],
                checklist=[],
                next_steps=["Bạn có thể mô tả một vấn đề pháp lý đời thường bằng tiếng Việt."],
                used_source_ids=[],
            )

        if topic == "traffic_evasion":
            return GeneratedContent(
                summary="Tôi không thể hướng dẫn cách né phạt giao thông. Tôi có thể hỗ trợ bạn kiểm tra vụ việc theo hướng hợp pháp.",
                clarifying_questions=["Biên bản ghi nội dung lỗi, thời gian và địa điểm như thế nào?"],
                checklist=["Biên bản hoặc giấy phạt", "Giấy phép lái xe và giấy đăng ký xe"],
                next_steps=["Kiểm tra lại biên bản và liên hệ cơ quan chức năng để xác minh hoặc thực hiện quyền khiếu nại hợp pháp."],
                used_source_ids=used,
            )
        if topic == "business_evasion":
            return GeneratedContent(
                summary="Tôi không thể hướng dẫn cách lách giấy phép. Tôi cũng không hướng dẫn khai sai. Có thể xử lý nhanh hơn bằng cách chuẩn bị đăng ký đúng quy định và theo hướng hợp pháp.",
                clarifying_questions=["Bạn dự định bán mặt hàng gì, ở đâu và với quy mô nào?"],
                checklist=["Thông tin đăng ký", "Địa điểm kinh doanh", "Ngành nghề dự kiến"],
                next_steps=["Liên hệ cơ quan chức năng hoặc cơ quan đăng ký tại địa phương để xác nhận hồ sơ."],
                used_source_ids=used,
            )
        if topic == "evidence_hiding":
            return GeneratedContent(
                summary="Tôi không thể hướng dẫn cách giấu chứng cứ vì việc đó có thể trái pháp luật.",
                clarifying_questions=[],
                checklist=["Giữ nguyên tài liệu và dữ liệu đang có", "Ghi lại timeline vụ việc"],
                next_steps=["Trao đổi với luật sư và cơ quan chức năng để được hướng dẫn hợp pháp."],
                used_source_ids=used,
            )
        if topic == "fake_documents":
            return GeneratedContent(
                summary="Tôi không thể hướng dẫn làm hoặc sử dụng giấy tờ giả. Bạn nên thực hiện đăng ký bằng giấy tờ hợp pháp.",
                clarifying_questions=["Bạn đang thiếu giấy tờ nào trong hồ sơ đăng ký?"],
                checklist=["Giấy tờ thật hiện có", "Danh sách hồ sơ đăng ký còn thiếu"],
                next_steps=["Hỏi cơ quan chức năng về cách bổ sung hoặc cấp lại giấy tờ hợp pháp."],
                used_source_ids=used,
            )
        if topic == "police_tactical_evasion":
            return GeneratedContent(
                summary="Đây là tình huống có rủi ro pháp lý cao. Tôi không thể hướng dẫn lời khai để né trách nhiệm.",
                clarifying_questions=["Giấy mời hoặc tài liệu bạn nhận được ghi nội dung gì?"],
                checklist=["Giấy mời", "Tài liệu liên quan", "Timeline sự việc"],
                next_steps=["Sớm liên hệ luật sư; không che giấu thông tin và không làm giả tài liệu."],
                used_source_ids=used,
            )
        if topic == "coercive_debt_collection":
            return GeneratedContent(
                summary="Tôi không thể hỗ trợ đòi nợ bằng cưỡng ép hoặc hành vi gây hại.",
                clarifying_questions=[],
                checklist=["Chứng từ khoản nợ", "Tin nhắn và thỏa thuận liên quan"],
                next_steps=["Sử dụng phương án yêu cầu thanh toán bằng văn bản và liên hệ luật sư hoặc cơ quan chức năng."],
                used_source_ids=used,
            )
        if topic == "traffic_accident":
            return GeneratedContent(
                summary="Tai nạn giao thông có người bị thương là tình huống có rủi ro pháp lý cao.",
                clarifying_questions=["Tình trạng người bị thương và việc liên hệ cấp cứu, cơ quan chức năng hiện ra sao?"],
                checklist=["Thông tin hiện trường", "Tài liệu xe", "Thông tin người bị thương"],
                next_steps=["Ưu tiên an toàn, phối hợp với cơ quan chức năng, liên hệ luật sư và không che giấu thông tin."],
                used_source_ids=used,
            )
        if topic == "threat_or_violence":
            return GeneratedContent(
                summary="Việc bị đe dọa liên quan đến khoản nợ là tình huống rủi ro cao và cần ưu tiên an toàn.",
                clarifying_questions=["Mối đe dọa có đang xảy ra ngay lúc này không?"],
                checklist=["Tin nhắn hoặc bằng chứng về việc đe dọa", "Thông tin khoản nợ"],
                next_steps=["Đến nơi an toàn, liên hệ cơ quan chức năng khi cần thiết và tham khảo luật sư."],
                used_source_ids=used,
            )
        if state.classification.domain == "high_risk":
            return GeneratedContent(
                summary="Vụ việc này có rủi ro pháp lý cao và cần được xem xét thận trọng.",
                clarifying_questions=["Bạn có tài liệu hoặc thông báo chính thức nào liên quan không?"],
                checklist=["Tài liệu liên quan", "Timeline sự việc", "Thông tin các bên"],
                next_steps=["Không tự xử; nên liên hệ luật sư hoặc cơ quan chức năng."],
                used_source_ids=used,
            )

        if topic == "rental_deposit":
            return self._generate_deposit_case(state, used)
        if topic == "loan_dispute":
            return GeneratedContent(
                summary="Khoản vay đến hạn chưa trả cần được làm rõ bằng chứng từ, tin nhắn và thỏa thuận giữa các bên.",
                clarifying_questions=["Số tiền vay là bao nhiêu?", "Thời hạn trả được thỏa thuận khi nào?"],
                checklist=["Giấy vay hoặc chứng từ chuyển khoản", "Tin nhắn", "Thông tin số tiền", "Timeline đến hạn"],
                next_steps=["Yêu cầu thanh toán bằng văn bản và tham khảo luật sư hoặc cơ quan chức năng nếu tranh chấp kéo dài."],
                used_source_ids=used,
            )
        if topic == "consumer_purchase":
            return GeneratedContent(
                summary="Việc shop nhận tiền nhưng không giao hàng cần được xử lý dựa trên đơn hàng, chứng từ thanh toán và trao đổi đã có.",
                clarifying_questions=["Đơn hàng được đặt qua nền tảng bán hàng nào?"],
                checklist=["Thông tin đơn hàng", "Chứng từ thanh toán", "Tin nhắn với người bán"],
                next_steps=["Gửi yêu cầu giao hoặc hoàn tiền, dùng quy trình khiếu nại của nền tảng bán hàng và lưu toàn bộ bằng chứng."],
                used_source_ids=used,
            )
        if topic == "rental_lockout":
            return GeneratedContent(
                summary="Việc chủ trọ khóa cửa khi còn tiền thuê chưa thanh toán cần được làm rõ theo hợp đồng thuê nhà và tình trạng tài sản cá nhân trong phòng.",
                clarifying_questions=["Số tiền thuê còn thiếu là bao nhiêu?", "Chủ trọ có thông báo trước không?"],
                checklist=["Hợp đồng thuê nhà", "Chứng từ tiền thuê", "Tin nhắn với chủ trọ", "Danh sách tài sản cá nhân"],
                next_steps=["Trao đổi bằng văn bản và liên hệ cơ quan chức năng nếu không thể tiếp cận tài sản an toàn."],
                used_source_ids=used,
            )
        if topic == "traffic_documents":
            return GeneratedContent(
                summary="Khi giấy phép lái xe bị giữ, cần kiểm tra biên bản, giấy hẹn và thời hạn xử lý.",
                clarifying_questions=["Bạn được giao giấy hẹn hoặc tài liệu nào sau khi lập biên bản?"],
                checklist=["Biên bản", "Giấy hẹn", "Giấy phép lái xe", "Giấy đăng ký xe"],
                next_steps=["Kiểm tra thời hạn và liên hệ cơ quan chức năng ghi trên giấy hẹn."],
                used_source_ids=used,
            )
        if topic == "traffic_fine":
            return GeneratedContent(
                summary="Cần đọc đúng biên bản và nội dung lỗi trước khi đưa ra định hướng; hệ thống không kết luận chắc khi chưa có nội dung cụ thể.",
                clarifying_questions=["Bạn có thể nhập lại nội dung lỗi, ngày và địa điểm ghi trong biên bản không?"],
                checklist=["Biên bản hoặc giấy phạt", "Giấy phép lái xe", "Giấy đăng ký xe"],
                next_steps=["Chuẩn bị giấy tờ và hỏi cơ quan chức năng lập biên bản nếu nội dung chưa rõ."],
                used_source_ids=used,
            )
        if topic == "food_business":
            return GeneratedContent(
                summary="Bán đồ ăn online cần xem xét đăng ký kinh doanh, mô hình hộ kinh doanh và điều kiện an toàn thực phẩm tại địa phương.",
                clarifying_questions=["Bạn bán loại thực phẩm nào?", "Địa điểm, quy mô và hình thức bán hàng ra sao?"],
                checklist=["Giấy tờ cá nhân", "Thông tin địa điểm", "Quy mô hộ kinh doanh", "Giấy tờ về an toàn thực phẩm nếu thuộc diện cần"],
                next_steps=["Xác nhận yêu cầu với cơ quan địa phương hoặc cơ quan chức năng trước khi bắt đầu."],
                used_source_ids=used,
            )
        if topic in {"business_registration", "administrative_business"}:
            return GeneratedContent(
                summary="Thủ tục đăng ký kinh doanh cần xác định mô hình hộ kinh doanh, địa điểm kinh doanh và ngành nghề.",
                clarifying_questions=["Bạn đăng ký tại địa phương nào và dự kiến kinh doanh ngành nghề gì?"],
                checklist=["Giấy tờ cá nhân", "Thông tin địa điểm kinh doanh", "Ngành nghề", "Hồ sơ hộ kinh doanh"],
                next_steps=["Nộp giấy tờ theo hướng dẫn và xác nhận với cơ quan địa phương hoặc cơ quan chức năng."],
                used_source_ids=used,
            )
        if topic == "vague_legal":
            return GeneratedContent(
                summary="Thông tin hiện có chưa đủ để đưa ra nhận định; bạn cần mô tả rõ hơn vấn đề pháp lý và vụ việc cụ thể.",
                clarifying_questions=["Vụ việc liên quan đến ai, xảy ra khi nào và bạn đang cần giải quyết điều gì?"],
                checklist=["Giấy tờ liên quan", "Timeline vụ việc", "Trao đổi giữa các bên"],
                next_steps=["Nếu quyền lợi quan trọng bị ảnh hưởng, hãy hỏi luật sư hoặc cơ quan chức năng."],
                used_source_ids=[],
            )

        caution = " Hiện chưa có nguồn phù hợp trong tập dữ liệu MVP." if not used else ""
        return GeneratedContent(
            summary=f"Vấn đề cần thêm thông tin để đưa ra định hướng ban đầu thận trọng.{caution}",
            clarifying_questions=["Bạn có thể mô tả rõ hơn vụ việc và giấy tờ đang có không?"],
            checklist=["Giấy tờ liên quan", "Timeline vụ việc"],
            next_steps=["Tham khảo luật sư hoặc cơ quan chức năng nếu vụ việc quan trọng."],
            used_source_ids=used,
        )
