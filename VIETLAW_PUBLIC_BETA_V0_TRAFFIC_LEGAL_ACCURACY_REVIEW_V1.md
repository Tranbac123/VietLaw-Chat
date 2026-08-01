# VIETLAW PUBLIC BETA V0 — TARGETED TRAFFIC LEGAL ACCURACY REVIEW V1

```text
INDEPENDENT_LEGAL_REVIEWER=CODEX_GPT_5_6_SOL_HIGH
REVIEW_DATE=2026-07-31
VERDICT=VIETLAW_TRAFFIC_LEGAL_ACCURACY_REVIEW_BLOCKED

HEAD=5079454d90730ac9f7fb23d18fe6b8a5578229a4
BRANCH=feature/conversational-rental-deposit-demo-v2
INDEX_EMPTY=yes

HIGH_FINDINGS=10
MEDIUM_FINDINGS=1
LOW_FINDINGS=0

DECREE_168_CURRENTLY_EFFECTIVE=yes
RELEVANT_LATER_AMENDMENTS=1
REPLACED_RULES=0
CURRENT_EFFECT_CONFIRMED=yes
PRIMARY_OFFICIAL_TEXT_VERIFIED=yes

TOTAL_TRAFFIC_RULES=11
VERIFIED_RULES=0
RULES_WITH_WORDING_CORRECTIONS=0
RULES_WITH_MISSING_QUALIFIERS=5
INCORRECT_RULES=6
OUTDATED_RULES=0
RULES_PRIMARY_SOURCE_NOT_VERIFIABLE=0
RULES_TO_DISABLE=11
RULES_TO_CORRECT=11

ARTICLE_LEVEL_CITATIONS_CAN_BE_ADDED=yes
ARTICLE_CLAUSE_MAPPING_COMPLETE=partially

RED_LIGHT_VERIFIED=no
HELMET_VERIFIED=no
ALCOHOL_VERIFIED=no
SPEEDING_VERIFIED=no
DRIVER_LICENSE_VERIFIED=no
PHONE_USE_VERIFIED=no
PASSENGER_LIMIT_VERIFIED=no
VEHICLE_MODIFICATION_VERIFIED=no

VEHICLE_MODIFICATION_TOPIC_SAFE_AS_ONE_RULE=no
PASSENGER_COUNT_SEMANTICS_CORRECT=no
LICENSE_STATUS_DISTINCTIONS_CORRECT=no
ALCOHOL_THRESHOLD_BOUNDARIES_CORRECT=no
SPEED_THRESHOLD_BOUNDARIES_CORRECT=no

CURATED_VERIFIED_JUSTIFIED_FOR_ALL_RULES=no
CURATED_VERIFIED_TRUST_LEVEL_JUSTIFIED=no
ALL_ENABLED_TRAFFIC_RULES_PRIMARY_SOURCE_VERIFIED=no
RUNTIME_RULE_SELECTION_CORRECT=no

REQUIRED_DATA_CORRECTIONS=11
REQUIRED_WORDING_CORRECTIONS=11
REQUIRED_RULES_TO_DISABLE=all_11_until_corrected_and_reverified
READY_FOR_TRAFFIC_CORRECTION_TASK=yes
READY_FOR_DEPLOYMENT_READINESS_TASK=no
READY_FOR_LIMITED_DEMO_DEPLOYMENT=no

TRACKED_FILES_MODIFIED_BY_REVIEWER=0
TEST_FILES_MODIFIED_BY_REVIEWER=0
EXISTING_REPORTS_MODIFIED_BY_REVIEWER=0
COMMITS_CREATED=0
STAGED_FILES=0
PUSH_PERFORMED=no
DEPLOY_PERFORMED=no
```

## Kết luận

Không thể tiếp tục gắn nhãn `CURATED_VERIFIED` / “Đã kiểm chứng trong dữ liệu
VietLaw” cho 11 quy tắc đang bật. Văn bản nguồn là văn bản chính thức và hiện
còn hiệu lực, nhưng không có dòng dữ liệu nào hiện mô tả đầy đủ một kết quả
pháp lý an toàn để phát công khai. Mười dòng có sai lệch mức HIGH; dòng mũ bảo
hiểm còn lại thiếu phân biệt chủ thể và ngoại lệ ở mức MEDIUM.

Quan trọng hơn, runtime chỉ dùng các trường `speed_excess_kmh`,
`alcohol_level`, `license_status`, `passenger_count` và `modification_type`
như cổng “đã có giá trị”, không dùng giá trị đó để chọn nhánh pháp lý. Sau khi
trường khác `unknown`/`None`, runtime luôn phát nguyên văn duy nhất của
`(topic_id, vehicle_type)`. Vì vậy dữ liệu dù được sửa câu chữ vẫn chưa đủ:
những chủ đề nhiều ngưỡng hoặc nhiều tình trạng cần tách thành quy tắc có điều
kiện và runtime phải chọn đúng quy tắc.

Đếm finding trong báo cáo này theo một finding chính trên mỗi dòng dữ liệu,
không cộng lặp các biểu hiện cùng nguyên nhân. Vì vậy có 10 HIGH và 1 MEDIUM.

## Nguồn chính thức và hiệu lực thời gian

Nguồn chính được kiểm tra trực tiếp:

- [Nghị định 168/2024/NĐ-CP — Cổng TTĐT Chính phủ](https://vanban.chinhphu.vn/?classid=1&docid=212167&orggroupid=2&pageid=27160)
- [Toàn văn Nghị định 168/2024/NĐ-CP — CSDL quốc gia về VBPL](https://vbpl.vn/TW/Pages/vbpq-toanvan.aspx?ItemID=173920&Keyword=)
- [Công báo Nghị định 168/2024/NĐ-CP](https://congbao.chinhphu.vn/van-ban/nghi-dinh-so-168-2024-nd-cp-43733.htm)
- [Luật Trật tự, an toàn giao thông đường bộ 36/2024/QH15](https://vbpl.vn/TW/Pages/vbpq-toanvan.aspx?ItemID=170620)
- [Nghị định 238/2026/NĐ-CP — Cổng TTĐT Chính phủ](https://vanban.chinhphu.vn/?classid=0&docid=218613&pageid=27160)
- [Công báo Nghị định 238/2026/NĐ-CP](https://congbao.chinhphu.vn/van-ban/nghi-dinh-so-238-2026-nd-cp-469913/66580.htm)
- [Thông tư 12/2025/TT-BCA về GPLX, gồm GPLX điện tử](https://vbpl.vn/TW/Pages/vbpq-toanvan.aspx?ItemID=175618)

Nghị định 168/2024/NĐ-CP do Chính phủ ban hành ngày 26/12/2024, có hiệu lực
từ 01/01/2025 và được CSDL VBPL ghi là còn hiệu lực tại ngày review.
Nghị định 238/2026/NĐ-CP sửa đổi Nghị định 168 đã được ban hành ngày
26/06/2026 nhưng chỉ có hiệu lực từ 15/08/2026. Toàn văn sửa đổi đã được
kiểm tra: không sửa các điểm/khoản làm căn cứ cho 11 quy tắc này. Do đó:

```text
DECREE_168_CURRENTLY_EFFECTIVE=yes
RELEVANT_LATER_AMENDMENTS=1
TARGET_PROVISIONS_CHANGED_AS_OF_REVIEW_DATE=0
TARGET_PROVISIONS_CHANGED_ON_2026_08_15=0
REPLACED_RULES=0
```

Nghị định 238 vẫn phải được theo dõi vì là một văn bản sửa đổi trực tiếp đã
ban hành; việc ghi `RELEVANT_LATER_AMENDMENTS=1` không có nghĩa nó đã có hiệu
lực ngày 31/07/2026.

## Bảng kiểm tra 11 quy tắc

`data/traffic_rules.json` không có trường `rule_id`; cột `rule_id` dưới đây
là định danh review ổn định được tạo từ `(topic_id, vehicle_type)`.
“Hành vi hiện tại” mô tả cả dữ liệu và cách runtime thực sự dùng dữ liệu.
Mọi URL trong cột nguồn là URL toàn văn chính thức đã được kiểm tra.

| rule_id | topic_id | vehicle_type | Hành vi hiện tại | Penalty text hiện tại | Văn bản | Điều; khoản/điểm đã kiểm tra | Hiệu lực | URL chính thức | Kết quả | Severity | Sửa bắt buộc |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `traffic_red_light__motorcycle` | `traffic_red_light` | motorcycle | Lookup chính xác theo xe rồi phát một excerpt chung; không xét màu vàng, hiệu lệnh CSGT hay hậu quả tai nạn | 4–6 triệu; chỉ nói tai nạn có mức cao hơn | NĐ 168/2024/NĐ-CP; Luật 36/2024/QH15 | NĐ 168 Điều 7(7)(c), 7(13)(b); nếu gây TNGT: 7(10)(b), 7(13)(d). Luật Điều 11 về thứ tự hiệu lực và tín hiệu đèn | 01/01/2025 | [VBPL NĐ 168](https://vbpl.vn/TW/Pages/vbpq-toanvan.aspx?ItemID=173920&Keyword=) | VERIFIED_WITH_MISSING_QUALIFIER | HIGH | Thêm trừ 4 điểm; tách nhánh gây tai nạn 10–14 triệu và trừ 10 điểm; chỉ áp dụng khi thật sự không chấp hành đèn sau khi xét hiệu lệnh người điều khiển giao thông và quy tắc đèn vàng |
| `traffic_red_light__car` | `traffic_red_light` | car | Như trên, một excerpt cho mọi tình huống đèn | 18–20 triệu | NĐ 168/2024/NĐ-CP; Luật 36/2024/QH15 | NĐ 168 Điều 6(9)(b), 6(16)(b); nếu gây TNGT: 6(10)(b), 6(16)(d). Luật Điều 11 | 01/01/2025 | [VBPL NĐ 168](https://vbpl.vn/TW/Pages/vbpq-toanvan.aspx?ItemID=173920&Keyword=) | VERIFIED_WITH_MISSING_QUALIFIER | HIGH | Thêm trừ 4 điểm; tách nhánh gây tai nạn 20–22 triệu và trừ 10 điểm; thêm các điều kiện về đèn vàng/hiệu lệnh CSGT |
| `traffic_no_helmet__motorcycle` | `traffic_no_helmet` | motorcycle | Sau khi biết xe máy, phát một câu gộp người lái và người được chở; không hỏi ai không đội mũ | 400–600 nghìn cho người điều khiển/người được chở | NĐ 168/2024/NĐ-CP | Người lái: Điều 7(2)(h); người lái chở người vi phạm: 7(2)(i); chính hành khách: 12(5)(b) | 01/01/2025 | [VBPL NĐ 168](https://vbpl.vn/TW/Pages/vbpq-toanvan.aspx?ItemID=173920&Keyword=) | VERIFIED_WITH_MISSING_QUALIFIER | MEDIUM | Tách ba căn cứ/chủ thể; ghi ngoại lệ tại 7(2)(i) (cấp cứu, trẻ dưới 6 tuổi, áp giải); giải thích người lái và hành khách có thể chịu hai hành vi riêng |
| `traffic_alcohol__motorcycle` | `traffic_alcohol` | motorcycle | `alcohol_level` chỉ là cổng hiện diện; mọi số đo đều nhận cùng excerpt từ mức thấp nhất đến cao nhất | 2–3 triệu đến 8–10 triệu, “kèm tước GPLX” | NĐ 168/2024/NĐ-CP | Thấp: 7(6)(a), 7(13)(b); giữa: 7(8)(b), 7(13)(d); cao/từ chối: 7(9)(d)/(đ), 7(12)(c) | 01/01/2025 | [VBPL NĐ 168](https://vbpl.vn/TW/Pages/vbpq-toanvan.aspx?ItemID=173920&Keyword=) | INCORRECT_PENALTY | HIGH | Tạo ba band và nhánh từ chối; thấp `<=50 mg/100 ml` hoặc `<=0,25 mg/L`: 2–3 triệu + trừ 4 điểm; giữa `>50..80` hoặc `>0,25..0,4`: 6–8 triệu + trừ 10 điểm; cao `>80` hoặc `>0,4` và từ chối: 8–10 triệu + tước 22–24 tháng |
| `traffic_alcohol__car` | `traffic_alcohol` | car | `alcohol_level` chỉ là cổng hiện diện; không phân band | 6–8 triệu đến 30–40 triệu, “kèm tước GPLX” | NĐ 168/2024/NĐ-CP | Thấp: 6(6)(c), 6(16)(b); giữa: 6(9)(a), 6(16)(d); cao/từ chối: 6(11)(a)/(b), 6(15)(c) | 01/01/2025 | [VBPL NĐ 168](https://vbpl.vn/TW/Pages/vbpq-toanvan.aspx?ItemID=173920&Keyword=) | INCORRECT_PENALTY | HIGH | Tạo ba band và nhánh từ chối; thấp: 6–8 triệu + trừ 4 điểm; giữa: 18–20 triệu + trừ 10 điểm; cao/từ chối: 30–40 triệu + tước 22–24 tháng. Không nói mọi band đều tước GPLX |
| `traffic_speeding__motorcycle` | `traffic_speeding` | motorcycle | `speed_excess_kmh` chỉ là cổng hiện diện; 5, 10 hay 20 đều nhận cùng excerpt | 400–600 nghìn “5–10”; 800 nghìn–1 triệu “10–20”; trên 20 chỉ nói cao hơn | NĐ 168/2024/NĐ-CP | Điều 7(2)(b): 5 đến dưới 10; 7(4)(a): 10 đến 20; 7(8)(a): trên 20; 7(13)(b): trên 20 trừ 4 điểm | 01/01/2025 | [VBPL NĐ 168](https://vbpl.vn/TW/Pages/vbpq-toanvan.aspx?ItemID=173920&Keyword=) | INCORRECT_PENALTY | HIGH | Sửa biên `5 <= x < 10`, `10 <= x <= 20`, `x > 20`; band cuối 6–8 triệu + trừ 4 điểm; `x < 5` không thuộc ba hành vi này; runtime phải dùng **mức vượt**, không dùng tốc độ thực tế hay tốc độ giới hạn |
| `traffic_driver_license__motorcycle` | `traffic_driver_license` | motorcycle | Mọi `license_status` và mọi xe máy đều nhận band xe đến 125 cm³/11 kW | 2–4 triệu nếu không có GPLX đến 125 cm³/11 kW; nói “quên mang” thấp hơn | NĐ 168/2024/NĐ-CP | Không có/không hiệu lực đến 125 cm³/11 kW: 18(5)(a); trên 125 cm³/11 kW hoặc mô tô ba bánh: 18(7)(a)/(b); không mang khi **kinh doanh vận tải**: 18(2)(d) | 01/01/2025 | [VBPL NĐ 168](https://vbpl.vn/TW/Pages/vbpq-toanvan.aspx?ItemID=173920&Keyword=) | INCORRECT_VEHICLE_SCOPE | HIGH | Bổ sung dung tích/công suất và loại mô tô; tách không có, sai hạng, hết/không còn hiệu lực, hết điểm, giấy giả/không hợp lệ, đang bị tước và không mang; không khẳng định chung rằng quên bản vật lý luôn bị phạt |
| `traffic_driver_license__car` | `traffic_driver_license` | car | Mọi `license_status` (`forgot`, `expired`, `revoked`...) đều nhận 18–20 triệu | 18–20 triệu nếu không có GPLX; nói “quên mang” thấp hơn | NĐ 168/2024/NĐ-CP | Không mang khi kinh doanh vận tải: 18(3)(a); hết hạn dưới 1 năm: 18(8)(a); sai hạng/hết hạn từ 1 năm: 18(9)(a); không có/hết điểm/không hiệu lực: 18(9)(b) | 01/01/2025 | [VBPL NĐ 168](https://vbpl.vn/TW/Pages/vbpq-toanvan.aspx?ItemID=173920&Keyword=) | INCORRECT_PENALTY | HIGH | Tách đầy đủ tình trạng, thời gian hết hạn và phạm vi kinh doanh vận tải; kiểm tra GPLX điện tử/tài khoản định danh trước khi coi “không xuất trình bản vật lý” là “không mang”; không dùng 18–20 triệu cho `forgot` hay hết hạn dưới 1 năm |
| `traffic_phone_use__motorcycle` | `traffic_phone_use` | motorcycle | Matcher rộng nhận “dùng/nghe điện thoại khi chạy”; rule chỉ cần xe, không xác minh dùng tay | 800 nghìn–1 triệu khi dùng tay sử dụng điện thoại | NĐ 168/2024/NĐ-CP | Điều 7(4)(đ), 7(13)(b) | 01/01/2025 | [VBPL NĐ 168](https://vbpl.vn/TW/Pages/vbpq-toanvan.aspx?ItemID=173920&Keyword=) | VERIFIED_WITH_MISSING_QUALIFIER | HIGH | Bắt buộc xác minh dùng tay cầm và sử dụng điện thoại/thiết bị; thêm trừ 4 điểm; không mở rộng sang mọi hình thức rảnh tay. Nếu thêm ô tô phải dùng 6(5)(h), 6(16)(b), có điều kiện phương tiện đang di chuyển |
| `traffic_passenger_limit__motorcycle` | `traffic_passenger_limit` | motorcycle | Parser lưu con số đứng trước “người”; câu hỏi lại định nghĩa là tổng số người kể cả lái xe; giá trị không chọn band | 400–600 nghìn khi chở vượt 1 người; số lớn hơn chỉ nói “cao hơn” | NĐ 168/2024/NĐ-CP | Chở 2 hành khách: 7(2)(g); chở từ 3 hành khách: 7(3)(b), 7(13)(a) | 01/01/2025 | [VBPL NĐ 168](https://vbpl.vn/TW/Pages/vbpq-toanvan.aspx?ItemID=173920&Keyword=) | VERIFIED_WITH_MISSING_QUALIFIER | HIGH | Chuẩn hóa `passenger_count` là số người **được chở, không gồm người lái**; tách 2 hành khách: 400–600 nghìn và các ngoại lệ; từ 3 hành khách: 600–800 nghìn + trừ 2 điểm |
| `traffic_vehicle_modification__motorcycle` | `traffic_vehicle_modification` | motorcycle | Một rule cho lốp, pô, khung, đèn, biển số; `modification_type` chỉ là cổng hiện diện | Cá nhân 4–6 triệu/tổ chức 8–12 triệu và “buộc khôi phục tình trạng ban đầu” | NĐ 168/2024/NĐ-CP và văn bản kỹ thuật/đăng ký tương ứng từng loại | Kết cấu: 32(8)(b). Âm thanh/ánh sáng gây mất ATGT: 32(3)(c), khắc phục tại 32(19)(h). Biển số: 32(4), 32(8)(g)/(h), chế tài bổ sung 32(18)(a). `32(19)` không áp dụng “khôi phục ban đầu” cho 32(8)(b) | 01/01/2025 | [VBPL NĐ 168](https://vbpl.vn/TW/Pages/vbpq-toanvan.aspx?ItemID=173920&Keyword=) | INCORRECT_VEHICLE_SCOPE | HIGH | Tắt rule chung; tách cấu trúc/khung/máy, kích thước lốp sai thiết kế, thay lốp tương đương, pô/tiếng ồn, ánh sáng và biển số; bỏ biện pháp khắc phục không có căn cứ cho 32(8)(b); kiểm tra quy chuẩn kỹ thuật/đăng ký trước khi kết luận lốp hoặc pô |

Không dòng nào bị đánh dấu `VERIFIED` vì “đúng một phần mức tiền” không đủ để
chứng nhận một câu trả lời pháp lý khi chế tài điểm GPLX, chủ thể, điều kiện
hoặc nhánh mức phạt còn thiếu/sai.

## Các mốc pháp lý đã kiểm tra

### Đèn tín hiệu

Luật 36/2024/QH15 Điều 11 quy định hiệu lệnh người điều khiển giao thông có
thứ tự ưu tiên cao hơn đèn tín hiệu. Đèn vàng phải dừng trước vạch; nếu đang
trên hoặc đã qua vạch khi tín hiệu chuyển vàng thì được đi tiếp; đèn vàng
nhấp nháy cho phép đi nhưng phải quan sát, giảm tốc hoặc dừng nhường đường.
Do đó “mọi tình huống đèn” không thể được suy thành cùng một vi phạm.

### Nồng độ cồn

Biên pháp lý dùng `miligam/100 mililít máu` và `miligam/1 lít khí thở`.
Giá trị đúng bằng 50 mg/100 ml hoặc 0,25 mg/L thuộc band thấp; đúng bằng
80 mg/100 ml hoặc 0,4 mg/L thuộc band giữa. Chỉ giá trị **vượt quá** các mốc
trên mới sang band kế tiếp. Dấu phẩy thập phân trong văn bản Việt Nam và dấu
chấm trong input (`0,2`/`0.2`) phải được chuẩn hóa thành cùng giá trị số.
Hiện runtime giữ chuỗi, không phân tích band.

### Tốc độ xe máy

| Mức vượt | Kết quả theo NĐ 168 |
|---|---|
| 4 km/h | Không thuộc ba band tại Điều 7(2)(b), 7(4)(a), 7(8)(a) |
| 5–9 km/h | 400–600 nghìn |
| 10–20 km/h, gồm cả 10 và 20 | 800 nghìn–1 triệu |
| Trên 20 km/h, gồm 34 và 35 | 6–8 triệu + trừ 4 điểm |

Dataset viết “5–10” và “10–20”, tạo chồng lấn tại 10 km/h. Không có quy tắc
ô tô trong pack; không được dùng quy tắc xe máy làm fallback cho ô tô.

### GPLX

NĐ 168 Điều 18 phân biệt loại xe, công suất/dung tích, sai hạng, hết hạn dưới
hay từ một năm, hết điểm, không còn hiệu lực, giấy không hợp lệ và không có
GPLX. Hành vi “không mang theo” tại Điều 18(2)(d), 18(3)(a) có phạm vi người
điều khiển phương tiện **kinh doanh vận tải**, không phải một mức thấp hơn
chung cho mọi người lái. Thông tư 12/2025/TT-BCA công nhận GPLX điện tử được
tích hợp trên hệ thống/tài khoản định danh điện tử. Vì vậy không thể suy từ
“quên bản vật lý” sang “không có GPLX”.

## Vehicle-modification

```text
VEHICLE_MODIFICATION_TOPIC_SAFE_AS_ONE_RULE=no
SUBTOPICS_REQUIRING_SEPARATION=tire_dimension_or_equivalent_replacement,frame_or_engine_or_structural_change,exhaust_or_noise,lighting,license_plate
DECREE_168_ALONE_SUFFICIENT_FOR_ALL_MODIFICATION_FACTS=no
```

Thay lốp mới cùng kích thước/đặc tính được duyệt không tự động là hành vi
“tự ý thay đổi khung, máy, hình dáng, kích thước, đặc tính” tại Điều
32(8)(b). “Đổi pô”, lắp ánh sáng gây mất an toàn và hành vi về biển số có
căn cứ, đối tượng, mức phạt và biện pháp khác nhau. Riêng tuyên bố hiện tại
“buộc khôi phục lại tình trạng ban đầu” cho Điều 32(8)(b) không được Điều
32(19) dẫn chiếu. Chủ đề phải bị tắt cho đến khi được tách và đối chiếu thêm
quy chuẩn kỹ thuật, hồ sơ thiết kế/đăng ký và tình trạng thực tế.

## Adversarial legal probes

Nguồn viết tắt trong bảng: `NĐ168` là [toàn văn chính thức](https://vbpl.vn/TW/Pages/vbpq-toanvan.aspx?ItemID=173920&Keyword=);
`Luật36` là [toàn văn Luật 36/2024/QH15](https://vbpl.vn/TW/Pages/vbpq-toanvan.aspx?ItemID=170620).

| Probe | Diễn giải pháp lý mong đợi | Cần hỏi thêm | Nguồn đúng | Curated rule hiện tại an toàn? |
|---|---|---|---|---|
| Tôi đi xe máy vượt đèn đỏ. | Không chấp hành đèn: 4–6 triệu + trừ 4 điểm | Có theo hiệu lệnh CSGT? đèn đỏ hay vàng? có TNGT? | NĐ168 7(7)(c), 7(13)(b); Luật36 Điều 11 | Không — thiếu điểm và qualifiers |
| Tôi lái ô tô vượt đèn đỏ. | 18–20 triệu + trừ 4 điểm | Như trên | NĐ168 6(9)(b), 6(16)(b); Luật36 Điều 11 | Không |
| Tôi không đội mũ bảo hiểm. | Phải xác định người lái hay hành khách và xe thuộc phạm vi | Vai trò, loại xe, ngoại lệ | NĐ168 7(2)(h)/(i), 12(5)(b) | Không — gộp chủ thể |
| Người ngồi sau không đội mũ bảo hiểm. | Người lái có thể vi phạm 7(2)(i), hành khách vi phạm 12(5)(b), mỗi hành vi 400–600 nghìn; xét ngoại lệ | Có phải cấp cứu, trẻ dưới 6, áp giải? | NĐ168 7(2)(i), 12(5)(b) | Không |
| Tôi đo được 0.2 mg/l khí thở. | Chuẩn hóa 0,2 mg/L; band thấp: xe máy 2–3 triệu + 4 điểm, ô tô 6–8 triệu + 4 điểm | Loại xe; xác nhận đơn vị/kết quả chính thức | NĐ168 7(6)(a), 7(13)(b); 6(6)(c), 6(16)(b) | Không — không chọn band |
| Tôi có 50 mg/100 ml máu. | Đúng bằng 50 thuộc band thấp | Loại xe; kết quả chính thức | Cùng các điều trên | Không |
| Tôi vượt tốc độ 5 km/h. | Xe máy: 400–600 nghìn | Loại xe; đây là mức vượt hay tốc độ thực tế? | NĐ168 7(2)(b) | Không — runtime không chọn band |
| Tôi vượt tốc độ 10 km/h. | Xe máy: 800 nghìn–1 triệu | Như trên | NĐ168 7(4)(a) | Không — dataset chồng biên |
| Tôi vượt tốc độ 20 km/h. | Xe máy: 800 nghìn–1 triệu; chỉ **trên** 20 mới vào band 6–8 triệu + 4 điểm | Như trên | NĐ168 7(4)(a), 7(8)(a), 7(13)(b) | Không |
| Tôi quên mang bằng lái. | Không đồng nghĩa không có GPLX; kiểm tra phương tiện kinh doanh vận tải và GPLX điện tử | Loại xe; kinh doanh vận tải? GPLX hợp lệ/điện tử? | NĐ168 18(2)(d), 18(3)(a); TT12/2025 | Không — có thể phát band “không có” |
| Tôi chưa từng có bằng lái. | Chọn theo loại xe; xe máy còn cần dung tích/công suất; ô tô 18–20 triệu | Loại xe; dung tích/công suất xe máy | NĐ168 18(5), 18(7), 18(9)(b) | Không — thiếu nhánh xe máy |
| Tôi dùng điện thoại khi đang chạy xe máy. | Chỉ áp dụng 800 nghìn–1 triệu + 4 điểm khi dùng tay cầm và sử dụng | Có dùng tay cầm? loại thiết bị? | NĐ168 7(4)(đ), 7(13)(b) | Không — matcher rộng, thiếu điểm |
| Tôi dùng điện thoại rảnh tay trong ô tô. | Không tự động thỏa hành vi “dùng tay cầm và sử dụng” khi xe đang di chuyển | Có cầm thiết bị? xe có đang di chuyển? | NĐ168 6(5)(h), 6(16)(b) | Có ở mức fail-closed: pack không có rule ô tô; không được thêm một mức phạt curated |
| Tôi chở 3 người trên xe máy. | Cách nói tự nhiên là 3 hành khách: 600–800 nghìn + trừ 2 điểm | Xác nhận là 3 người được chở, không gồm lái | NĐ168 7(3)(b), 7(13)(a) | Không |
| Tổng cộng có 3 người trên xe, tính cả tôi. | Có 2 hành khách: 400–600 nghìn, trừ khi thuộc ngoại lệ | Có thuộc cấp cứu/trẻ dưới 12/người già yếu hoặc khuyết tật/áp giải? | NĐ168 7(2)(g) | Không — stored count không cùng nghĩa với luật |
| Tôi thay lốp nhỏ hơn lốp nguyên bản. | Chỉ áp dụng 32(8)(b) nếu việc thay thực sự tự ý làm thay đổi kích thước/đặc tính so với thiết kế hợp lệ | Thông số thiết kế/đăng ký, kích thước cũ/mới, chủ xe cá nhân/tổ chức | NĐ168 32(8)(b) và hồ sơ/quy chuẩn kỹ thuật | Không — kết luận quá sớm và thêm sai biện pháp khắc phục |
| Tôi thay lốp mới cùng kích thước. | Không tự động cấu thành 32(8)(b) | Có cùng đặc tính/thông số được duyệt? | NĐ168 32(8)(b) và hồ sơ/quy chuẩn kỹ thuật | Có cho standalone vì classifier không chọn curated rule; không an toàn nếu đây là câu trả lời cho pending modification |
| Tôi thay pô xe máy. | Không thể tự động dùng mức 32(8)(b); cần phân biệt thay kết cấu, tiếng ồn/nẹt pô, thiết bị gây mất ATGT | Loại pô, thông số, tiếng ồn, cách sử dụng, chủ xe | NĐ168 32(8)(b), 32(3)(c), 7(9)(k), quy chuẩn kỹ thuật liên quan | Có cho standalone vì classifier hiện không nhận riêng câu này là topic; không an toàn nếu đi qua pending modification |

Hai probe “thay lốp cùng kích thước” và “thay pô” không chứng minh topic an
toàn: việc standalone không vào curated route chỉ là khoảng trống classifier.
Nếu một pending `modification_type` đã tồn tại, parser nhận `tire`/`exhaust`
và vẫn phát rule chung sai phạm vi.

## Runtime-to-data consistency

```text
EXACT_TOPIC_VEHICLE_LOOKUP=yes
CROSS_VEHICLE_FALLBACK=no
THRESHOLD_RULE_SELECTION=no
ALCOHOL_NUMERIC_CANONICALIZATION=no
SPEED_BAND_SELECTION=no
LICENSE_STATUS_BRANCHING=no
PASSENGER_COUNT_BRANCHING=no
MODIFICATION_TYPE_BRANCHING=no
UNKNOWN_AFTER_ONE_QUESTION_CAN_RECEIVE_GENERIC_RANGE=yes
DUPLICATE_KEY_REJECTION=no
RUNTIME_RULE_SELECTION_CORRECT=no
```

Điểm tích cực là `TrafficSourcePack.find()` chỉ lookup chính xác
`(topic_id, vehicle_type)` nên không lấy rule xe máy cho ô tô. Tuy nhiên:

1. `missing_blocking_fact()` chỉ kiểm tra giá trị khác `None`/`unknown`.
2. `_resolve_traffic_topic()` sau đó truyền nguyên một `TrafficRuleRecord`
   vào `_build_curated_traffic_response()`.
3. Builder luôn phát `rule.source_excerpt`, không có nhánh theo giá trị.
4. `alcohol_level` là chuỗi thô; các dấu `0.2`/`0,2`, đơn vị và hai loại mẫu
   không được chuyển thành một đại lượng/band pháp lý.
5. `LicenseStatus` có nhiều trạng thái nhưng không có loại xe chi tiết, công
   suất/dung tích hay thời gian hết hạn.
6. `passenger_count` không biểu đạt nhất quán “hành khách” hay “tổng người”.
7. `modification_type` phân loại từ nhưng không đổi rule.
8. Loader ghi đè im lặng nếu sau này có hai row cùng key; cấu trúc hiện tại
   chưa thể chứa nhiều band cho cùng topic/vehicle một cách an toàn.

## Findings

### HIGH-01 đến HIGH-10

| ID | Rule | Finding |
|---|---|---|
| HIGH-01 | red light motorcycle | Thiếu trừ 4 điểm và nhánh tai nạn/điều kiện tín hiệu |
| HIGH-02 | red light car | Thiếu trừ 4 điểm và nhánh tai nạn/điều kiện tín hiệu |
| HIGH-03 | alcohol motorcycle | Sai khi nói mọi band “kèm tước GPLX”; runtime không chọn band |
| HIGH-04 | alcohol car | Sai khi nói mọi band “kèm tước GPLX”; runtime không chọn band |
| HIGH-05 | speeding motorcycle | Biên 10 km/h chồng lấn, thiếu band trên 20 và trừ 4 điểm; runtime bỏ qua giá trị |
| HIGH-06 | driver licence motorcycle | Một band đến 125 cm³/11 kW được dùng cho mọi xe máy và mọi trạng thái GPLX |
| HIGH-07 | driver licence car | `forgot`, hết hạn dưới 1 năm, không có và bị tước có thể nhận cùng 18–20 triệu |
| HIGH-08 | phone motorcycle | Matcher rộng hơn hành vi dùng tay; thiếu trừ 4 điểm |
| HIGH-09 | passenger motorcycle | Semantics số người không thống nhất, runtime không chọn band, thiếu trừ 2 điểm ở từ 3 hành khách |
| HIGH-10 | vehicle modification | Một rule áp cho các hành vi pháp lý khác nhau; có thể phạt thay thế tương đương; biện pháp khắc phục được nêu không có dẫn chiếu |

### MEDIUM-01

`traffic_no_helmet__motorcycle` gộp người lái, người lái chở hành khách vi
phạm và chính hành khách thành một câu, đồng thời bỏ ngoại lệ. Mức tiền trùng
nhau nhưng căn cứ/chủ thể và khả năng có hai quyết định xử phạt riêng là thông
tin vật chất.

## Trust level và phạm vi pack

```text
CURATED_VERIFIED_JUSTIFIED_FOR_ALL_RULES=no
VERIFIED_RULE_COUNT=0
SAFE_ENABLED_SUBSET_WITHOUT_CHANGES=0
RULES_TO_DISABLE=11
RULES_TO_CORRECT=11
```

Không nên chỉ hạ nhãn tin cậy rồi giữ nguyên nội dung: các HIGH finding vẫn
có thể đưa ra kết quả sai. Phương án an toàn cho demo giới hạn là tắt cả 11
rule hiện tại, sau đó chỉ bật lại từng rule đã:

1. có article/clause/point chính xác;
2. chứa đủ hình thức phạt và trừ điểm/tước GPLX;
3. có schema cho facts pháp lý bắt buộc;
4. có selector chọn đúng band;
5. có boundary tests và adversarial tests;
6. được review lại trên văn bản có hiệu lực tại ngày triển khai.

## Recommended article/clause citations

```text
traffic_red_light/motorcycle=NĐ168 Điều 7 khoản 7 điểm c; khoản 13 điểm b; accident khoản 10 điểm b và khoản 13 điểm d; Luật36 Điều 11
traffic_red_light/car=NĐ168 Điều 6 khoản 9 điểm b; khoản 16 điểm b; accident khoản 10 điểm b và khoản 16 điểm d; Luật36 Điều 11
traffic_no_helmet/motorcycle=NĐ168 Điều 7 khoản 2 điểm h, i; Điều 12 khoản 5 điểm b
traffic_alcohol/motorcycle=NĐ168 Điều 7 khoản 6 điểm a; khoản 8 điểm b; khoản 9 điểm d, đ; khoản 12 điểm c; khoản 13 điểm b, d
traffic_alcohol/car=NĐ168 Điều 6 khoản 6 điểm c; khoản 9 điểm a; khoản 11 điểm a, b; khoản 15 điểm c; khoản 16 điểm b, d
traffic_speeding/motorcycle=NĐ168 Điều 7 khoản 2 điểm b; khoản 4 điểm a; khoản 8 điểm a; khoản 13 điểm b
traffic_driver_license/motorcycle=NĐ168 Điều 18 khoản 2 điểm d; khoản 5; khoản 7; khoản 10-12 khi tương ứng
traffic_driver_license/car=NĐ168 Điều 18 khoản 3 điểm a; khoản 8; khoản 9; khoản 10-12 khi tương ứng
traffic_phone_use/motorcycle=NĐ168 Điều 7 khoản 4 điểm đ; khoản 13 điểm b
traffic_passenger_limit/motorcycle=NĐ168 Điều 7 khoản 2 điểm g; khoản 3 điểm b; khoản 13 điểm a
traffic_vehicle_modification/motorcycle=NĐ168 Điều 32 khoản 8 điểm b only for matching structural conduct; other subtopics require their own provisions
```

`ARTICLE_CLAUSE_MAPPING_COMPLETE=partially` vì các hành vi mức phạt hiện có
đã được định vị, nhưng topic modification bao trùm những câu hỏi cần quy
chuẩn kỹ thuật/hồ sơ đăng ký và không thể hoàn tất bằng một điểm của NĐ 168.

## Narrow regression

Chạy tại HEAD nêu trên, không gọi provider và không sửa source/test:

```text
FOCUSED_MODE_2D_TESTS=256 passed
PUBLIC_BETA_TRAFFIC_SOURCE_PACK_TESTS=202 passed
GIT_DIFF_CHECK=clean
AUTOMATED_PROVIDER_CALLS=0
LIVE_PROVIDER_CALLS_USED=0
```

Nhóm 202 test gồm:

```text
backend_lite/tests/unit/test_traffic_source_pack.py
backend_lite/tests/unit/test_traffic_classifier.py
backend_lite/tests/unit/test_legal_fallback_orchestrator.py
backend_lite/tests/integration/test_public_beta_v0_legal_fallback_e2e.py
```

`git diff --check` không báo lỗi whitespace. Worktree đã có nhiều thay đổi
tracked/untracked của người dùng trước review; chúng được giữ nguyên. “Clean”
ở đây chỉ có nghĩa `git diff --check` thành công, không có nghĩa worktree
sạch.

## Verdict

```text
VIETLAW_TRAFFIC_LEGAL_ACCURACY_REVIEW_BLOCKED
```

Lý do chặn: `HIGH_FINDINGS=10`, lựa chọn band runtime sai/thiếu, chế tài GPLX
bị mô tả sai hoặc bỏ sót, và nhãn `CURATED_VERIFIED` vượt quá mức chứng cứ
thực tế. Chưa sẵn sàng cho deployment-readiness task hoặc limited public
demo. Rate limiting vẫn là điều kiện độc lập phải hoàn tất sau khi legal pack
đã qua correction và re-review.
