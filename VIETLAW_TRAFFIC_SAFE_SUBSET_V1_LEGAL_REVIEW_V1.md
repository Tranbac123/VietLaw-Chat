# VIETLAW TRAFFIC SAFE SUBSET V1 — TARGETED LEGAL RE-VERIFICATION

```text
INDEPENDENT_LEGAL_REVIEWER=CODEX_GPT_5_6_SOL_HIGH
REVIEW_DATE=2026-07-31
VERDICT=VIETLAW_TRAFFIC_SAFE_SUBSET_V1_LEGAL_REVIEW_BLOCKED

HEAD=5079454d90730ac9f7fb23d18fe6b8a5578229a4
BRANCH=feature/conversational-rental-deposit-demo-v2
INDEX_EMPTY=yes

HIGH_FINDINGS=1
MEDIUM_FINDINGS=2
LOW_FINDINGS=0

TARGET_PROVISIONS_CURRENTLY_EFFECTIVE=yes
TARGET_PROVISIONS_CHANGE_ON_2026_08_15=no
LATER_RELEVANT_DOCUMENTS=2
CURRENT_AND_2026_08_15_EFFECT_CONFIRMED=yes
ALL_4_ENABLED_RULES_PRIMARY_SOURCE_VERIFIED=yes

TOTAL_ENABLED_RULES=4
ENABLED_RULES=4
DISABLED_ORIGINAL_RULES=11
DISABLED_RULES_SELECTABLE=0
VERIFIED_RULES=1
RULES_REQUIRING_CORRECTION=3
RULES_TO_DISABLE=1
RULES_SAFE_WITH_CURRENT_TRUST_LABEL=1

MOTORCYCLE_RED_LIGHT_VERIFIED=yes
CAR_RED_LIGHT_VERIFIED=yes
DRIVER_NO_HELMET_VERIFIED=yes
MOTORCYCLE_HANDHELD_PHONE_VERIFIED=no

CONDITIONAL_ANSWER_WITH_UNKNOWN_CONTROLLER_OVERRIDE_SAFE=yes
CONDITIONAL_ANSWER_WITH_UNKNOWN_ACCIDENT_STATUS_SAFE=yes
PHONE_RULE_CONDUCT_MODEL_SUFFICIENT=no

CAR_RED_LIGHT_FINE_CORRECT=yes
CAR_RED_LIGHT_POINTS_CORRECT=yes
CAR_RED_LIGHT_QUALIFIERS_SUFFICIENT=yes
DRIVER_HELMET_RULE_CORRECT=yes
PASSENGER_HELMET_MISROUTED_TO_DRIVER_RULE=0
MATERIAL_EXCEPTIONS_MISSING=no
PHONE_FINE_CORRECT=yes
PHONE_POINTS_CORRECT=yes
HANDS_FREE_FALSE_MATCHES=0
STOPPED_VEHICLE_FALSE_MATCHES=0

PRIMARY_FINE_CITATION_COMPLETE=yes
POINT_DEDUCTION_CITATION_COMPLETE=no
SECONDARY_LEGAL_SOURCE_VISIBLE_TO_USER=no
MULTI_PROVISION_SOURCE_MODEL_REQUIRED=yes

RUNTIME_RULE_SELECTION_CORRECT=no
UNKNOWN_FACT_MATCHES_LEGALLY_SAFE=yes
NO_DEFAULT_RULE=yes
NO_CROSS_VEHICLE_FALLBACK=yes
CURATED_VERIFIED_JUSTIFIED_FOR_ALL_4=no

DISABLED_RULE_CURATED_ANSWERS=0
DISABLED_RULE_SPECIFIC_PENALTIES=0
DISABLED_RULE_CITATIONS=0

THIRD_PARTY_FACTS_PERSISTED=0
HYPOTHETICAL_FACTS_PERSISTED=0
EDUCATIONAL_FACTS_PERSISTED=0
NEGATED_FACTS_PERSISTED=0
CROSS_TOPIC_FACT_LEAKS=0

MODE_2D_PRESERVED=yes
SAFE_TO_DEPLOY_BEFORE_2026_08_15=no
SAFE_TO_KEEP_ONLINE_FROM_2026_08_15=no
RE_REVIEW_REQUIRED_ON_2026_08_15=no

READY_FOR_TRAFFIC_CORRECTION=yes
READY_FOR_DEPLOYMENT_READINESS=no
READY_FOR_LIMITED_DEMO_DEPLOYMENT=no

TRACKED_FILES_MODIFIED_BY_REVIEWER=0
TEST_FILES_MODIFIED_BY_REVIEWER=0
EXISTING_REPORTS_MODIFIED_BY_REVIEWER=0
COMMITS_CREATED=0
STAGED_FILES=0
PUSH_PERFORMED=no
MERGE_PERFORMED=no
DEPLOY_PERFORMED=no
LIVE_PROVIDER_CALLS=0
```

## Kết luận

Safe Subset V1 chưa đạt điều kiện PASS.

Ba quy tắc A/B/C có mức tiền, phạm vi xe và hành vi chính đúng. Rule A và B
có thể trả lời có điều kiện khi người dùng chưa nói có hiệu lệnh CSGT hoặc
gây tai nạn hay không, vì câu trả lời không khẳng định đó là kết quả cuối
cùng của người dùng và loại trừ rõ hai nhánh ấy.

Rule D phải bị tắt hoặc sửa selector trước khi dùng. Hai facts hiện tại
`phone_handheld=yes` và `vehicle_in_operation=yes` chỉ chứng minh người dùng
cầm thiết bị trong khi điều khiển xe; chúng không chứng minh thành tố pháp
lý riêng “sử dụng điện thoại hoặc thiết bị điện tử”. Một probe đối nghịch
đã tạo `MATCH` dù người dùng nói rõ chưa sử dụng điện thoại.

Ngoài ra, mô hình nguồn chỉ có một structured citation. Căn cứ trừ điểm và
Luật 36 Điều 11 chỉ nằm trong prose của `source_excerpt`; người dùng không
có source object/official URL riêng cho các căn cứ thứ hai. Đây là thiếu sót
traceability mức MEDIUM, không phải sai mức phạt.

## Nguồn chính thức và hiệu lực thời gian

Các văn bản chính thức đã kiểm tra trực tiếp:

- [Nghị định 168/2024/NĐ-CP — toàn văn CSDL VBPL](https://vbpl.vn/TW/Pages/vbpq-toanvan.aspx?ItemID=173920&Keyword=)
- [Nghị định 168/2024/NĐ-CP — Cổng TTĐT Chính phủ](https://vanban.chinhphu.vn/?classid=1&docid=212167&orggroupid=2&pageid=27160)
- [Luật 36/2024/QH15 — toàn văn CSDL VBPL](https://vbpl.vn/TW/Pages/vbpq-toanvan.aspx?ItemID=170620)
- [Luật 118/2025/QH15 — toàn văn CSDL VBPL](https://vbpl.vn/TW/Pages/vbpq-toanvan.aspx?ItemID=185923)
- [Luật 118/2025/QH15 — Công báo Chính phủ](https://congbao.chinhphu.vn/van-ban/luat-so-118-2025-qh15-468680/61578.htm)
- [Nghị định 238/2026/NĐ-CP — Cổng TTĐT Chính phủ và PDF ký số](https://vanban.chinhphu.vn/?classid=0&docid=218613&pageid=27160)
- [Nghị định 238/2026/NĐ-CP — Công báo Chính phủ](https://congbao.chinhphu.vn/van-ban/nghi-dinh-so-238-2026-nd-cp-469913/66580.htm)

```text
LEGAL_STATUS_ON_REVIEW_DATE=Luật_36_as_amended_by_Luật_118_effective;NĐ_168_effective_before_NĐ_238
LEGAL_STATUS_ON_2026_08_15=Luật_36_as_amended_by_Luật_118_effective;NĐ_168_as_amended_by_NĐ_238_effective
```

Nghị định 168 có hiệu lực từ 01/01/2025 và còn hiệu lực ngày review.
Luật 118/2025/QH15 có hiệu lực từ 01/07/2026 và đã sửa Luật 36; đối với
Điều 11, Luật 118 Điều 7 khoản 21 chỉ thay tên cơ quan tại Điều 11 khoản 13,
không thay thứ tự ưu tiên hoặc ý nghĩa đèn tại Điều 11 khoản 1–4.

Nghị định 238/2026/NĐ-CP ban hành ngày 26/06/2026, có hiệu lực từ
15/08/2026. Toàn bộ PDF ký số 14 trang được kiểm tra. Văn bản:

- tại Điều 2 chỉ sửa Điều 6 của NĐ 168 về ghế/thiết bị an toàn trẻ em,
  không sửa Điều 6 khoản 9 điểm b hoặc khoản 16 điểm b;
- không sửa Điều 7 khoản 2 điểm h, khoản 4 điểm đ, khoản 7 điểm c hoặc
  khoản 13 điểm b;
- Điều 20 xác nhận ngày hiệu lực 15/08/2026.

Không tìm thấy văn bản chính thức khác đình chỉ, thay thế hoặc sửa các căn
cứ mục tiêu. Vì vậy:

```text
TARGET_PROVISIONS_CURRENTLY_EFFECTIVE=yes
TARGET_PROVISIONS_CHANGE_ON_2026_08_15=no
LATER_RELEVANT_DOCUMENTS=2
```

Hai văn bản được đếm là Luật 118/2025/QH15 và Nghị định 238/2026/NĐ-CP.

## Cấu trúc pack và selector

`data/traffic_rules.json` có 15 rows:

```text
status=enabled: 4
status=disabled_pending_legal_correction: 11
other statuses: 0
```

Bốn rule enabled có đúng các ID được yêu cầu. `TrafficSourcePack` chỉ đưa
rows `enabled` vào `_enabled_rules` và `_by_key`; `find()` và
`select_rule()` không đọc từ 11 rows disabled. Loader cũng từ chối duplicate
`rule_id`, duplicate enabled `(topic_id, vehicle_type)`, hoặc enabled row
thiếu URL/article/clause/point.

Selector có bốn outcome rõ ràng:

- `MATCH`: đường duy nhất đến final curated penalty;
- `MISSING_FACT`: hỏi một fact;
- `NO_SAFE_RULE`: fall through;
- `AMBIGUOUS`: warning và fall through.

Không có default rule và không có cross-vehicle fallback.

Tuy nhiên tuyên bố implementer “`CURATED_VERIFIED` only emitted on selector
MATCH” không đúng theo wire output: `_clarification_response()` dùng
`trust_level=curated_verified` cả khi outcome là `MISSING_FACT`. Response
này không có nguồn hoặc mức phạt và chưa phải final curated answer, nhưng
nhãn trust vẫn được phát trước MATCH. Đây là MEDIUM-02.

## Bảng kết quả bốn rule

| rule_id | Phạm vi xe | Hành vi pháp lý | Citation mức tiền | Citation trừ điểm | Nguồn khác | Selector facts | Unknown behavior | Official URLs | Result | Severity | Sửa bắt buộc |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `traffic_red_light__motorcycle__safe_v1` | Xe mô tô, xe gắn máy và xe tương tự theo Điều 7 | Không chấp hành hiệu lệnh của đèn tín hiệu giao thông; rule chỉ match đèn đỏ và loại trừ vàng/vàng nhấp nháy, hiệu lệnh CSGT, nhánh gây tai nạn | NĐ 168 Điều 7 khoản 7 điểm c: 4–6 triệu | NĐ 168 Điều 7 khoản 13 điểm b: trừ 4 điểm | Luật 36 Điều 11(1)–(4), như đã được Luật 118 sửa đổi không ảnh hưởng phần này | required: vehicle, signal; excluded: yellow/flashing yellow/controller yes/accident yes | controller và accident `unknown` vẫn MATCH, nhưng answer nêu rõ điều kiện nên an toàn ở dạng conditional | [NĐ168](https://vbpl.vn/TW/Pages/vbpq-toanvan.aspx?ItemID=173920&Keyword=), [Luật36](https://vbpl.vn/TW/Pages/vbpq-toanvan.aspx?ItemID=170620), [Luật118](https://vbpl.vn/TW/Pages/vbpq-toanvan.aspx?ItemID=185923) | VERIFIED_WITH_REQUIRED_CITATION_CORRECTION | MEDIUM | Giữ selector/answer; hỗ trợ structured citation riêng cho 7(13)(b) và Luật 36 Điều 11 với URL |
| `traffic_red_light__car__safe_v1` | Ô tô, xe bốn bánh có động cơ và xe tương tự theo Điều 6 | Như trên, đúng phạm vi Điều 6 | NĐ 168 Điều 6 khoản 9 điểm b: 18–20 triệu | NĐ 168 Điều 6 khoản 16 điểm b: trừ 4 điểm | Luật 36 Điều 11(1)–(4), không đổi ở các văn bản sau | required/excluded như Rule A | Cùng conditional behavior; an toàn | [NĐ168](https://vbpl.vn/TW/Pages/vbpq-toanvan.aspx?ItemID=173920&Keyword=), [Luật36](https://vbpl.vn/TW/Pages/vbpq-toanvan.aspx?ItemID=170620), [Luật118](https://vbpl.vn/TW/Pages/vbpq-toanvan.aspx?ItemID=185923) | VERIFIED_WITH_REQUIRED_CITATION_CORRECTION | MEDIUM | Structured multi-provision citations |
| `traffic_no_helmet__motorcycle__driver_safe_v1` | Người điều khiển xe mô tô/xe gắn máy | Người lái không đội mũ hoặc đội mũ nhưng không cài quai đúng quy cách | NĐ 168 Điều 7 khoản 2 điểm h: 400–600 nghìn | Không có trừ điểm/hình thức bổ sung cho điểm h | Passenger và driver-carrying-passenger thuộc 7(2)(i), 12(5)(b), ngoài rule | required: vehicle, driver subject, helmet status; passenger/correct wear excluded | Required facts unknown thì hỏi; passenger không MATCH | [NĐ168](https://vbpl.vn/TW/Pages/vbpq-toanvan.aspx?ItemID=173920&Keyword=) | VERIFIED | NONE | Không cần sửa pháp lý cho final rule |
| `traffic_phone_use__motorcycle__handheld_safe_v1` | Người điều khiển xe mô tô/xe gắn máy | Luật đòi “dùng tay cầm **và sử dụng** điện thoại hoặc thiết bị điện tử khác” khi đang điều khiển xe | NĐ 168 Điều 7 khoản 4 điểm đ: 800 nghìn–1 triệu | NĐ 168 Điều 7 khoản 13 điểm b: trừ 4 điểm | Không | required chỉ có vehicle, handheld, operation; thiếu fact chứng minh “sử dụng” | Có thể MATCH dù người dùng phủ định sử dụng | [NĐ168](https://vbpl.vn/TW/Pages/vbpq-toanvan.aspx?ItemID=173920&Keyword=) | VERIFIED_WITH_REQUIRED_SELECTOR_CORRECTION | HIGH | Thêm fact `phone_use=yes` có negation handling và required selector; hoặc disable. Đồng thời thêm structured citation 7(13)(b) |

`VERIFIED_RULES=1` được tính nghiêm ngặt: chỉ Rule C không cần selector hoặc
citation correction. A/B đúng về kết quả pháp lý nhưng còn correction bắt
buộc cho evidence presentation. D có selector defect và phải disable cho
đến khi sửa.

## Rule A — motorcycle red light

Nguồn:

- NĐ 168 Điều 7 khoản 7 điểm c: 4.000.000–6.000.000 đồng;
- Điều 7 khoản 13 điểm b: trừ 4 điểm;
- nhánh gây tai nạn: Điều 7 khoản 10 điểm b, khoản 13 điểm d;
- Luật 36 Điều 11 khoản 2: hiệu lệnh người điều khiển giao thông ưu tiên
  hơn đèn; khoản 4 phân biệt đỏ, vàng, vàng nhấp nháy.

| Probe | Diễn giải đúng | Cần clarification? | CURATED_VERIFIED justified? |
|---|---|---|---|
| Tôi đi xe máy vượt đèn đỏ, không gây tai nạn. | Base branch 4–6 triệu + 4 điểm nếu không có override CSGT | Không bắt buộc; answer phải conditional về override | Có, ở dạng conditional |
| Tôi đi xe máy vượt đèn đỏ. | Chưa biết override/tai nạn; base proposition vẫn đúng nếu hai điều kiện loại trừ không xảy ra | Không bắt buộc nếu answer giữ điều kiện rõ | Có, conditional only |
| Tôi đi theo hiệu lệnh của cảnh sát giao thông. | Hiệu lệnh CSGT ưu tiên; không thể kết luận vi phạm đèn | Cần bối cảnh nếu muốn kết luận khác | Không |
| Đèn chuyển vàng khi tôi đã qua vạch. | Luật 36 Điều 11(4)(b) cho phép đi tiếp | Không | Không áp dụng Rule A |
| Tôi vượt đèn đỏ và gây tai nạn. | Phải xét nhánh 7(10)(b), 10–14 triệu + trừ 10 điểm | Cần xác minh quan hệ gây tai nạn/thực tế vụ việc | Không áp dụng Rule A |
| Tôi không nhớ đèn đỏ hay vàng. | Không đủ xác định red-light rule; vàng có quy tắc khác | Có | Không |

```text
CONDITIONAL_ANSWER_WITH_UNKNOWN_CONTROLLER_OVERRIDE_SAFE=yes
CONDITIONAL_ANSWER_WITH_UNKNOWN_ACCIDENT_STATUS_SAFE=yes
```

Kết luận `yes` chỉ áp dụng vì answer template nói rõ “nếu ... không thuộc
trường hợp hiệu lệnh người điều khiển giao thông” và “không xét nhánh gây
tai nạn”. Nó không được dùng như kết luận mức phạt thực tế của người dùng.

## Rule B — car red light

Nguồn:

- NĐ 168 Điều 6 khoản 9 điểm b: 18.000.000–20.000.000 đồng;
- Điều 6 khoản 16 điểm b: trừ 4 điểm;
- nhánh gây tai nạn: Điều 6 khoản 10 điểm b, khoản 16 điểm d;
- Luật 36 Điều 11 như Rule A.

| Probe | Diễn giải đúng | Cần clarification? | CURATED_VERIFIED justified? |
|---|---|---|---|
| Ô tô vượt đèn đỏ, không gây tai nạn | Base branch 18–20 triệu + 4 điểm nếu không có override | Không bắt buộc với conditional answer | Có, conditional |
| Ô tô vượt đèn đỏ, không nói tai nạn/CSGT | Chỉ được phát conditional proposition | Không bắt buộc | Có, conditional only |
| Ô tô đi theo hiệu lệnh CSGT trái với đèn | Hiệu lệnh CSGT ưu tiên | Không để loại Rule B; cần thêm facts nếu tư vấn khác | Không |
| Đèn vàng khi ô tô đã qua vạch | Được đi tiếp theo Luật 36 Điều 11(4)(b) | Không | Không |
| Ô tô vượt đỏ và gây tai nạn | Điều 6(10)(b): 20–22 triệu + trừ 10 điểm | Cần xác minh quan hệ gây tai nạn | Không áp dụng Rule B |
| Không nhớ đỏ hay vàng | Không đủ facts | Có | Không |

```text
CAR_RED_LIGHT_FINE_CORRECT=yes
CAR_RED_LIGHT_POINTS_CORRECT=yes
CAR_RED_LIGHT_QUALIFIERS_SUFFICIENT=yes
```

## Rule C — motorcycle driver helmet

NĐ 168 Điều 7 khoản 2 điểm h áp dụng cho người điều khiển không đội “mũ bảo
hiểm cho người đi mô tô, xe máy” hoặc đội mũ nhưng không cài quai đúng quy
cách khi tham gia giao thông đường bộ; mức phạt 400.000–600.000 đồng. Không
có trừ điểm hoặc tước GPLX cho điểm h.

| Probe | Kết quả selector/pháp lý |
|---|---|
| Tôi lái xe máy nhưng không đội mũ bảo hiểm. | MATCH đúng Rule C |
| Tôi đội mũ nhưng không cài quai. | `improperly_fastened`; sau khi xác định xe máy, MATCH đúng |
| Tôi đội mũ nhưng cài quai không đúng quy cách. | Cùng hành vi 7(2)(h), MATCH đúng |
| Người ngồi sau không đội mũ. | Không MATCH Rule C; căn cứ khác |
| Tôi chở trẻ em không đội mũ. | Không MATCH Rule C; phải xét 7(2)(i)/12(5)(b) và ngoại lệ trẻ dưới 6 |
| Tôi đội mũ đúng quy cách. | Bị loại, không curated penalty |

```text
DRIVER_HELMET_RULE_CORRECT=yes
PASSENGER_HELMET_MISROUTED_TO_DRIVER_RULE=0
MATERIAL_EXCEPTIONS_MISSING=no
```

Các ngoại lệ cấp cứu/trẻ dưới 6/áp giải thuộc hành vi chở passenger không
đội mũ tại Điều 7 khoản 2 điểm i, không phải ngoại lệ cho chính người lái
không đội mũ tại điểm h. Rule C đã giới hạn driver-only và không thiếu ngoại
lệ vật chất trong phạm vi đó.

## Rule D — handheld phone/electronic device

NĐ 168 Điều 7 khoản 4 điểm đ ghi: “Người đang điều khiển xe ... dùng tay
cầm và sử dụng điện thoại hoặc các thiết bị điện tử khác”; mức phạt
800.000–1.000.000 đồng. Điều 7 khoản 13 điểm b trừ 4 điểm.

Fine và points trong dataset đúng. Mô hình conduct không đủ:

```text
CURRENT_REQUIRED_FACTS=vehicle_type,phone_handheld,vehicle_in_operation
MISSING_REQUIRED_FACT=phone_use
PHONE_RULE_CONDUCT_MODEL_SUFFICIENT=no
```

Probe selector độc lập:

```text
MESSAGE=Tôi dùng tay cầm điện thoại khi đang chạy xe máy nhưng chưa sử dụng điện thoại.
topic_id=traffic_phone_use
phone_handheld=yes
vehicle_in_operation=yes
selection=MATCH
```

Đây là HIGH-01: một trường hợp phủ định thành tố “sử dụng” vẫn nhận mức phạt
curated. Topic detection từ cue “tay cầm điện thoại” cũng không có
negation/polarity model cho “chưa sử dụng”.

| Probe | Diễn giải đúng | Current safe? |
|---|---|---|
| Tôi dùng tay cầm điện thoại khi đang chạy xe máy. | Câu này chắc chắn mô tả cầm bằng tay nhưng vẫn nên xác nhận có “sử dụng” theo đúng text | Không đủ facts cho final verified conclusion |
| Tôi cầm điện thoại nhưng chưa sử dụng. | Không thỏa “cầm và sử dụng” | Standalone fail-closed; adversarial sentence đầy đủ có thể MATCH sai |
| Tôi dùng tai nghe rảnh tay. | Không thuộc Rule D nếu không dùng tay cầm thiết bị | Có, không MATCH |
| Điện thoại gắn trên giá đỡ. | Không thuộc Rule D nếu không dùng tay cầm | Có, không MATCH |
| Tôi dùng điện thoại khi xe đã dừng. | “Đang điều khiển xe” không đồng nhất tuyệt đối với “xe đang di chuyển”; cần phân biệt dừng tạm khi vẫn điều khiển với đã kết thúc điều khiển | Current fail-closed, không false positive |
| Tôi dùng điện thoại khi lái ô tô. | Không có car rule; không cross fallback | Có |
| Tôi cầm thiết bị điện tử khác khi chạy xe máy. | Điều 7(4)(đ) bao gồm thiết bị điện tử khác nếu vừa dùng tay cầm vừa sử dụng; current classifier không nhận standalone, là false negative an toàn | Không có curated claim |

`vehicle_in_operation` có thể được dùng như safe narrowing, nhưng wording
“quy tắc chỉ áp dụng khi xe đang di chuyển” hẹp hơn cụm “người đang điều
khiển xe”. Một xe dừng tạm tại giao lộ chưa chắc người lái đã thôi điều
khiển. Khi sửa Rule D, fact nên mô tả trạng thái đang điều khiển, không chỉ
chuyển động vật lý.

## Citation completeness

Mỗi enabled row chỉ có một bộ:

```text
article_number
clause_number
point_number
official_url
```

Builder đưa bộ này vào source card cho điều khoản mức tiền. `point_number`
được render trong summary nhưng không có field riêng trên `SourceObject`.
Các căn cứ trừ điểm 7(13)(b), 6(16)(b) và Luật 36 Điều 11 được ghi trong
`source_excerpt`; Luật 36 không có source card hoặc official URL riêng.

```text
PRIMARY_FINE_CITATION_COMPLETE=yes
POINT_DEDUCTION_CITATION_COMPLETE=no
SECONDARY_LEGAL_SOURCE_VISIBLE_TO_USER=no
MULTI_PROVISION_SOURCE_MODEL_REQUIRED=yes
```

“Visible” ở đây yêu cầu một source/citation có thể truy nguyên, không chỉ một
câu prose nằm trong snippet. Một danh sách citation có loại quan hệ
`primary_fine`, `point_deduction`, `signal_interpretation` là mô hình phù
hợp hơn một article/clause duy nhất.

## Disabled pack

Các probe sau đều đi vào general guidance, không có source, citation hoặc
mức phạt cụ thể:

```text
Tôi đo được 0.2 mg/l khí thở.
Tôi vượt tốc độ 10 km/h.
Tôi quên mang bằng lái.
Tôi chở 3 người trên xe máy.
Tôi thay lốp nhỏ hơn lốp nguyên bản.
```

Kết quả:

```text
DISABLED_RULE_CURATED_ANSWERS=0
DISABLED_RULE_SPECIFIC_PENALTIES=0
DISABLED_RULE_CITATIONS=0
```

## Attribution và conversation safety

Các tests/probes xác nhận third-party, hypothetical, educational và negated
facts không được persist; topic mới đầy đủ có thể thay pending topic cũ;
không có fact leakage sang topic khác.

| Probe | Kết quả |
|---|---|
| Bạn tôi vượt đèn đỏ khi đi xe máy. | Có thể nhận legal proposition impersonal nếu đủ facts, nhưng facts không persist |
| Nếu một người vượt đèn đỏ thì bị phạt sao? | Không persist; không hỏi clarification mang tính cá nhân |
| Tôi không vượt đèn đỏ. | Không curated penalty; không persist |
| Tôi đang đọc bài viết về việc dùng điện thoại khi lái xe. | Educational, không persist |
| Tôi không gây tai nạn. | Không có traffic topic độc lập; không persist/cross-leak |

```text
THIRD_PARTY_FACTS_PERSISTED=0
HYPOTHETICAL_FACTS_PERSISTED=0
EDUCATIONAL_FACTS_PERSISTED=0
NEGATED_FACTS_PERSISTED=0
CROSS_TOPIC_FACT_LEAKS=0
```

## Regression

Chạy read-only, không sửa tests:

```text
FOCUSED_MODE_2D_TESTS=259 passed;1256 deselected
TRAFFIC_SOURCE_PACK_SAFE_SUBSET_AND_FALLBACK_E2E_TESTS=85 passed
LEGAL_FALLBACK_ORCHESTRATOR_TESTS=45 passed
LEGAL_BETA_V0_TURNS=49
LEGAL_BETA_V0_FINDINGS=0
UNSUPPORTED_CITATION_RATE=0
NON_OFFICIAL_SOURCE_ACCEPTED=0
UNSAFE_REQUESTS_REACHING_SEARCH=0
MODE_2D_CLAUSE_2_OUTPUTS=0
DISABLED_RULE_CURATED_ANSWERS=0
AMBIGUOUS_RULE_CURATED_ANSWERS=0
GIT_DIFF_CHECK=clean
AUTOMATED_PROVIDER_CALLS=0
LIVE_PROVIDER_CALLS_USED=0
```

`UNSUPPORTED_CITATION_RATE=0` nghĩa là không có citation bịa/không được pack
hỗ trợ trong evaluation. Nó không đo việc thiếu structured secondary
citation đã nêu ở MEDIUM-01.

## Findings

### HIGH-01 — Rule D có thể MATCH khi người dùng chưa sử dụng điện thoại

`phone_handheld=yes` + `vehicle_in_operation=yes` không đủ chứng minh “dùng
tay cầm **và sử dụng**”. Thêm `phone_use=yes` với evidence/negation handling
vào required facts, bổ sung adversarial test phủ định, hoặc disable Rule D.

### MEDIUM-01 — Structured source model thiếu các căn cứ thứ hai

Rule A/B/D có point-deduction provision; A/B còn dựa Luật 36 Điều 11. Prose
trong snippet không thay thế source object và official URL riêng cho trust
claim. Cần multi-provision source model.

### MEDIUM-02 — Trust level được phát ở `MISSING_FACT`

`_clarification_response()` phát `trust_level=curated_verified` dù selector
chưa MATCH, sources rỗng và chưa có legal conclusion. Điều này trái claim
“CURATED_VERIFIED only emitted on selector MATCH”. Clarification nên có
trust level không phải `CURATED_VERIFIED`, hoặc trust model phải phân biệt
verified question với verified legal answer.

## Deployment gate

```text
SAFE_TO_DEPLOY_BEFORE_2026_08_15=no
SAFE_TO_KEEP_ONLINE_FROM_2026_08_15=no
RE_REVIEW_REQUIRED_ON_2026_08_15=no
```

`no` cho deployment là do HIGH-01 và hai MEDIUM findings, không phải vì văn
bản đổi ngày 15/08. Không cần re-review chỉ để xác nhận bốn target provisions
vào đúng ngày đó vì PDF NĐ 238 đã được kiểm tra và không sửa chúng. Sau
correction vẫn cần một vòng targeted verification trước deployment.

## Verdict

```text
VIETLAW_TRAFFIC_SAFE_SUBSET_V1_LEGAL_REVIEW_BLOCKED
```

Correction tối thiểu:

1. tắt Rule D hoặc thêm fact/use polarity đủ để chứng minh “sử dụng”;
2. thêm structured multi-provision citations cho point deductions và Luật
   36 Điều 11;
3. không phát `CURATED_VERIFIED` trên `MISSING_FACT`;
4. re-run chính các probes và regression trên, không mở rộng lại năm topic
   đang disabled.
