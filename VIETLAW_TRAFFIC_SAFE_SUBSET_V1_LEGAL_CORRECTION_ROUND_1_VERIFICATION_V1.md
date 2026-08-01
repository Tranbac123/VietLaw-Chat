# VIETLAW TRAFFIC SAFE SUBSET V1

# LEGAL CORRECTION ROUND 1 — FINAL INDEPENDENT VERIFICATION

```text
INDEPENDENT_REVIEWER=CODEX_GPT_5_6_SOL_HIGH
REVIEW_DATE=2026-07-31
VERDICT=VIETLAW_TRAFFIC_SAFE_SUBSET_V1_LEGAL_CORRECTION_ROUND_1_VERIFICATION_BLOCKED

HEAD=5079454d90730ac9f7fb23d18fe6b8a5578229a4
BRANCH=feature/conversational-rental-deposit-demo-v2
INDEX_EMPTY=yes
GIT_OPERATION_IN_PROGRESS=no
TASK_SCOPE_MATCH=yes
UNDECLARED_IMPLEMENTATION_FILES=0
UNRELATED_SCOPE_CHANGES=0

HIGH_FINDINGS=0
MEDIUM_FINDINGS=1
LOW_FINDINGS=2

TOTAL_TRAFFIC_ROWS=15
FINAL_ENABLED_TRAFFIC_RULES=3
DISABLED_TRAFFIC_RULES=12
PHONE_RULE_ENABLED=no
DISABLED_RULES_INDEXED=0
DISABLED_RULES_SELECTABLE=0
DISABLED_RULES_WITH_CURATED_VERIFIED=0
DISABLED_RULE_SPECIFIC_PENALTIES=0
DISABLED_RULE_CITATIONS=0

TARGET_PROVISIONS_CURRENTLY_EFFECTIVE=yes
TARGET_PROVISIONS_CHANGE_ON_2026_08_15=no
CURRENT_AND_2026_08_15_EFFECT_CONFIRMED=yes
ALL_3_ENABLED_RULES_PRIMARY_SOURCE_VERIFIED=yes

MOTORCYCLE_RED_LIGHT_VERIFIED=yes
CAR_RED_LIGHT_VERIFIED=yes
DRIVER_HELMET_VERIFIED=yes

MOTORCYCLE_RED_LIGHT_FINE_CORRECT=yes
MOTORCYCLE_RED_LIGHT_POINTS_CORRECT=yes
MOTORCYCLE_RED_LIGHT_SELECTOR_SAFE=yes
MOTORCYCLE_RED_LIGHT_CONDITIONAL_WORDING_SAFE=yes

CAR_RED_LIGHT_FINE_CORRECT=yes
CAR_RED_LIGHT_POINTS_CORRECT=yes
CAR_RED_LIGHT_SELECTOR_SAFE=yes
CAR_RED_LIGHT_CONDITIONAL_WORDING_SAFE=yes

DRIVER_HELMET_FINE_CORRECT=yes
DRIVER_HELMET_SELECTOR_SAFE=yes
PASSENGER_HELMET_MISROUTED_TO_DRIVER_RULE=0

PHONE_CURATED_ANSWERS=0
PHONE_SPECIFIC_PENALTIES=0
PHONE_STRUCTURED_CITATIONS=0

CURATED_VERIFIED_ASSIGNMENT_SITES=1
MISSING_FACT_CURATED_VERIFIED_RESPONSES=0
NO_SAFE_RULE_CURATED_VERIFIED_RESPONSES=0
AMBIGUOUS_CURATED_VERIFIED_RESPONSES=0
MATCH_CURATED_VERIFIED_RESPONSES=3

MULTI_PROVISION_SOURCE_MODEL_CORRECT=no
PRIMARY_FINE_CITATIONS_COMPLETE=yes
POINT_DEDUCTION_CITATIONS_COMPLETE=yes
SIGNAL_INTERPRETATION_CITATIONS_COMPLETE=yes
RED_LIGHT_MOTORCYCLE_SOURCE_COUNT=3
RED_LIGHT_CAR_SOURCE_COUNT=3
HELMET_SOURCE_COUNT=1
INCOMPLETE_ENABLED_RULES_ACCEPTED=0
INCORRECT_TOPIC_CITATION_SHAPES_ACCEPTED=1

DISTINCT_SHARED_URL_CITATIONS_RENDERED=3
DUPLICATE_IDENTICAL_SOURCES_RENDERED_ONCE=yes
SOURCE_IDS_UNIQUE_WITHIN_RESPONSE=yes
DISTINCT_LEGAL_PROVISIONS_COLLAPSED=0
TRUE_DUPLICATES_RENDERED_MORE_THAN_ONCE=0
MODE_2D_SOURCE_RENDERING_PRESERVED=yes
OFFICIAL_SEARCH_SOURCE_RENDERING_PRESERVED=yes

THIRD_PARTY_FACTS_PERSISTED=0
HYPOTHETICAL_FACTS_PERSISTED=0
EDUCATIONAL_FACTS_PERSISTED=0
NEGATED_FACTS_PERSISTED=0
STALE_TOPICS_AFTER_UNRELATED_TURNS=0
CROSS_TOPIC_FACT_LEAKS=0
CROSS_CHAT_LEAKS=0

M01_REMAINED_CLOSED=yes
M02R_REMAINED_CLOSED=yes
M03_REMAINED_CLOSED=yes
M04_REMAINED_CLOSED=yes

MODE_2D_PRESERVED=yes
MODE_2E_REINTRODUCED=no
RESOLVER_ALWAYS_RETURNS_NONE=yes
PRODUCTION_APPLICABLE_CLAUSE_2_PATHS=0
WIRE_BACKWARD_COMPATIBLE=yes

EVALUATION_TESTS_LABEL_ACCURATE=no
AFFECTED_BACKEND_TESTS=141 passed
EXISTING_PLATFORM_EVALUATION_TESTS=214
LEGAL_BETA_EVALUATION_TURNS=49

SKIPPED_TESTS=0
XFAILED_TESTS=0
EXISTING_ASSERTIONS_WEAKENED=0

BACKEND_LITE_TESTS=1526 passed
FOCUSED_MODE_2D_TESTS=259 passed
PLATFORM_EVALUATION_TESTS=214 passed
FRONTEND_TESTS=179 passed
TYPECHECK=passed
BUILD=passed
COMPILEALL=passed
GIT_DIFF_CHECK=clean
SECRET_SCAN=clean
REGRESSION_PASS=yes

UNSUPPORTED_CITATION_RATE=0
DISABLED_RULE_CURATED_ANSWERS=0
MISSING_FACT_CURATED_VERIFIED_RESPONSES=0
INCOMPLETE_STRUCTURED_CITATIONS=0
NON_OFFICIAL_SOURCE_ACCEPTED=0
MODE_2D_CLAUSE_2_OUTPUTS=0
UNSAFE_REQUESTS_REACHING_SEARCH=0
AMBIGUOUS_RULE_CURATED_ANSWERS=0

REPORT_CURRENT_CLAIMS_ACCURATE=no

READY_FOR_DEPLOYMENT_READINESS_TASK=no
READY_FOR_LIMITED_DEMO_DEPLOYMENT=no
READY_FOR_GENERAL_PUBLIC_BETA=no

TRACKED_FILES_MODIFIED_BY_REVIEWER=0
TEST_FILES_MODIFIED_BY_REVIEWER=0
EXISTING_REPORTS_MODIFIED_BY_REVIEWER=0
COMMITS_CREATED=0
STAGED_FILES=0
PUSH_PERFORMED=no
DEPLOY_PERFORMED=no
LIVE_PROVIDER_CALLS=0
LIVE_WEB_SEARCH_CALLS=0
```

## Kết luận

Correction Round 1 đã đóng đúng lỗi HIGH của Rule D và lỗi trust gating.
Ba rule đang enabled có kết quả pháp lý đúng; các response thực tế có đủ
structured sources theo hình dạng 3/3/1 và frontend không làm mất hai căn
cứ hợp lệ cùng URL.

Tuy nhiên, điều kiện PASS yêu cầu
`MULTI_PROVISION_SOURCE_MODEL_CORRECT=yes`. Probe độc lập chứng minh loader
vẫn chấp nhận một rule `traffic_no_helmet` có cả `primary_penalty` và một
`signal_interpretation` không thuộc shape hợp lệ. Đây là lỗi fail-closed ở
biên dữ liệu mức MEDIUM, nên verdict phải là BLOCKED dù dữ liệu hiện tại và
toàn bộ regression đều pass.

## Preconditions và scope

Đã ghi nhận trực tiếp:

```text
git rev-parse HEAD
5079454d90730ac9f7fb23d18fe6b8a5578229a4

git branch --show-current
feature/conversational-rental-deposit-demo-v2

git diff --cached --name-status
<empty>
```

Không có `MERGE_HEAD`, `CHERRY_PICK_HEAD`, `REVERT_HEAD`, `REBASE_HEAD`,
`rebase-merge` hoặc `rebase-apply`.

Worktree đã dirty từ Public Beta và các phase trước. Correction-owned paths
được report khai báo đều thuộc traffic data/contracts/orchestrator, additive
wire source fields, frontend source rendering, tests, evaluation và reports.
Không phát hiện correction-owned implementation path ngoài danh sách đó.
Các report Phase C/MODE_2B/official-source đã modified từ trước vẫn được giữ
nguyên và không được tính vào correction-owned diff.

## Inventory và khả năng reach

`data/traffic_rules.json` có đúng 15 rows:

```text
enabled=3
disabled_pending_legal_correction=12
other_statuses=0
```

Ba ID enabled:

```text
traffic_red_light__motorcycle__safe_v1
traffic_red_light__car__safe_v1
traffic_no_helmet__motorcycle__driver_safe_v1
```

`TrafficSourcePack.__init__` chỉ đưa rows `enabled` vào `_enabled_rules` và
`_by_key`. Cả `find()` và `select_rule()` chỉ đọc các collection này. Rule
phone và 11 rule cũ do đó không thể được trả về hoặc match.

Probe sáu câu phone qua FastAPI runtime cho kết quả:

```text
PHONE_CURATED_ANSWERS=0
PHONE_SPECIFIC_PENALTIES=0
PHONE_STRUCTURED_CITATIONS=0
```

Hai câu có traffic topic rõ trả `general_guidance`; bốn câu không được
vertical nhận diện trả response scope hiện hữu với `trust_level=None`.
Tất cả đều có `sources=[]`, không có 800.000–1.000.000 đồng và không có
citation Điều 7.

## Hiệu lực pháp lý

Nguồn chính thức đã đối chiếu:

- Nghị định 168/2024/NĐ-CP:
  <https://vbpl.vn/TW/Pages/vbpq-toanvan.aspx?ItemID=173920&Keyword=>
- Luật 36/2024/QH15:
  <https://vbpl.vn/TW/Pages/vbpq-toanvan.aspx?ItemID=170620>
- Luật 118/2025/QH15:
  <https://vbpl.vn/TW/Pages/vbpq-toanvan.aspx?ItemID=185923>
- Nghị định 238/2026/NĐ-CP và PDF ký số:
  <https://vanban.chinhphu.vn/?classid=0&docid=218613&pageid=27160>
  và
  <https://datafiles.chinhphu.vn/cpp/files/vbpq/2026/7/238-ndcp.signed.pdf>

Luật 118/2025/QH15 có hiệu lực ngày 01/07/2026. Đối với Điều 11 Luật 36,
Điều 7 khoản 21 của Luật 118 chỉ thay tên “Bộ Giao thông vận tải” thành
“Bộ Xây dựng” tại khoản 13; không sửa khoản 1–4.

Nghị định 238/2026/NĐ-CP được ban hành ngày 26/06/2026 và có hiệu lực ngày
15/08/2026. Toàn văn 14 trang cho thấy:

- Điều 2 chỉ bổ sung khoản 1a và sửa điểm m khoản 3 Điều 6;
- không sửa Điều 6 khoản 9 điểm b hoặc khoản 16 điểm b;
- không sửa Điều 7 khoản 2 điểm h, khoản 7 điểm c hoặc khoản 13 điểm b;
- Điều 19 không thay đổi các target provisions;
- Điều 20 xác nhận hiệu lực ngày 15/08/2026.

Vì vậy các target provisions đúng cả ngày review lẫn ngày 15/08/2026.

## Rule A — xe máy vượt đèn đỏ

Nghị định 168 Điều 7 khoản 7 điểm c quy định 4.000.000–6.000.000 đồng;
khoản 13 điểm b trừ 4 điểm. Luật 36 Điều 11 khoản 1–4 xác lập thứ tự ưu
tiên của hiệu lệnh người điều khiển giao thông, ý nghĩa đèn đỏ, vàng và vàng
nhấp nháy.

Các probe controller override, vàng đã qua vạch, gây tai nạn và không nhớ
đỏ/vàng đều không tạo curated answer. Unknown controller/accident chỉ được
phép match vì answer nói rõ điều kiện loại trừ và không khẳng định đây là
kết quả cuối cùng của vụ việc.

## Rule B — ô tô vượt đèn đỏ

Nghị định 168 Điều 6 khoản 9 điểm b quy định 18.000.000–20.000.000 đồng;
khoản 16 điểm b trừ 4 điểm. Các probe tương đương về vàng, hiệu lệnh người
điều khiển giao thông và gây tai nạn đều fail closed. Conditional wording
đúng phạm vi base branch.

## Rule C — người lái xe máy không đội mũ

Nghị định 168 Điều 7 khoản 2 điểm h quy định 400.000–600.000 đồng đối với
người điều khiển không đội mũ hoặc không cài quai đúng quy cách. Passenger
và việc chở trẻ em thuộc căn cứ khác; các probe này không bị route nhầm vào
Rule C.

## Trust gating

Trong production backend chỉ có một assignment site:

```text
_build_curated_traffic_response:
trust_level=TrustLevel.CURATED_VERIFIED.value
```

Hàm này chỉ được gọi sau `RuleSelectionOutcome.MATCH`. Clarification dùng
`trust_level=None`, `sources=[]` và không có kết luận mức phạt.

Probe nhiều turn:

```text
Tôi vượt đèn đỏ. -> MISSING_FACT, trust=None, sources=0
Xe máy.          -> MATCH, curated_verified, sources=3

Tôi không đội mũ bảo hiểm. -> MISSING_FACT, trust=None, sources=0
Xe máy.                     -> MATCH, curated_verified, sources=1
```

Ba positive cases A/B/C đều trả `curated_verified`, nên
`MATCH_CURATED_VERIFIED_RESPONSES=3`.

## Multi-provision citation và finding MEDIUM

Dữ liệu hiện tại đúng:

| Rule | primary penalty | point deduction | signal interpretation | Total |
|---|---:|---:|---:|---:|
| Motorcycle red light | 1 | 1 | 1 | 3 |
| Car red light | 1 | 1 | 1 | 3 |
| Driver helmet | 1 | 0 | 0 | 1 |

Loader từ chối: list rỗng, thiếu/nhân đôi primary, thiếu URL, thiếu document
number, thiếu article/clause, thiếu point cho penalty/point-deduction, và
duplicate role+location.

### MEDIUM-01 — topic citation shape chưa exact/fail-closed

`_REQUIRED_CITATION_SHAPE_BY_TOPIC["traffic_no_helmet"]` chỉ quy định:

```text
primary_penalty=1
licence_point_deduction=0
```

Nó không quy định `signal_interpretation=0`. Probe độc lập tạo một enabled
helmet row với `primary_penalty` cộng một `signal_interpretation`; gọi
`_validate_legal_citations()` không raise và cho:

```text
HELMET_EXTRA_SIGNAL_INTERPRETATION_ACCEPTED=yes
```

Điều này trái yêu cầu “incorrect topic citation shape rejected” và trái
claim report rằng helmet requires “exactly 1 primary_penalty”. Một malformed
future row có thể phát thêm một structured legal source không thuộc rule mà
vẫn mang `curated_verified`. Dữ liệu hiện tại không bị lỗi này, nên severity
là MEDIUM, không phải HIGH.

## Wire và frontend

Response thực tế A/B/C có lần lượt 3/3/1 `SourceObject`. Mỗi object có
document title/number, article, clause, point khi áp dụng, citation role,
official URL và relevance note.

Frontend giữ hai citations khác ID nhưng cùng URL thành hai card riêng,
de-duplicate cùng ID, và dùng URL fallback khi ID rỗng. Ba heading hiển thị
đúng:

```text
Căn cứ mức phạt
Căn cứ trừ điểm GPLX
Quy tắc tín hiệu giao thông
```

Traffic source IDs có dạng ổn định `rule_id__citation_role` và duy nhất trong
mỗi response. Official-search source ID hiện dùng Python `hash(url)`, ổn
định trong một process nhưng không bảo đảm giữ nguyên qua process restart;
điều này không làm mất hoặc nhân đôi citation trong response hiện tại vì
official-search path chỉ trả một source.

Thay đổi test de-duplication từ URL identity sang source identity là thay
đổi requirement có chủ đích, không phải assertion weakening: test mới vẫn
giữ true-duplicate de-duplication và thêm fallback cho empty ID.

## Attribution, state và MODE_2D

Dedicated backend/integration tests xác nhận third-party, hypothetical,
educational và negated facts không persist; pending unrelated được release;
fresh topic chuyển đúng; không có cross-topic hoặc cross-chat leakage.

Các source fields mới đều optional/additive. Original MODE_2D source tests
và official-search tests pass. Focused MODE_2D suite đạt 259 tests;
`resolve_deposit_applicable_clause` tiếp tục trả `None` và không có
production clause-2 path.

## Evaluation/report audit

### LOW-01 — `EVALUATION_TESTS=141` sai nhãn

`141 passed` là tổng của bốn affected backend files:

```text
test_traffic_source_pack.py
test_traffic_safe_subset_v1.py
test_legal_fallback_orchestrator.py
test_public_beta_v0_legal_fallback_e2e.py
```

Existing platform evaluation suite thực tế là `214 passed`. Bảng prose của
report gọi 141 là affected tests đúng, nhưng machine-readable field
`EVALUATION_TESTS=141` không đúng nghĩa.

### LOW-02 — claim về sáu pytest phone probes không chính xác

Correction report nói `test_rule_d_disabled_never_produces_a_curated_answer`
chứa exact HIGH-01 adversarial probe. Test thực tế dùng câu ngắn hơn
“Tôi cầm điện thoại nhưng chưa sử dụng điện thoại.” và không chứa nguyên
văn câu đầy đủ “...khi đang chạy xe máy nhưng chưa sử dụng điện thoại.”
Nó cũng thay probe “dùng điện thoại khi xe đang chạy” bằng các case stopped
và car.

Exact HIGH-01 sentence có trong `evaluation/legal_beta_v0/cases.py`, và
review này đã probe độc lập đủ sáu câu qua FastAPI; behavior đều an toàn.
Vì vậy đây là report/test-coverage description mismatch mức LOW, không phải
runtime blocker.

## Test execution

Node được cố định ở `v20.19.4`.

```text
Affected backend tests: 141 passed
Focused MODE_2D: 259 passed, 1267 deselected
Complete backend_lite: 1526 passed
Existing platform evaluation: 214 passed
Legal beta runner: 49 turns, 0 findings
Frontend: 179 passed in 11 files
Typecheck: passed
Production build: passed
Compileall: passed
git diff --check: clean
Targeted secret scan: clean; only api_key="test-key" test fixtures
```

Platform evaluation lần đầu gặp ba `PermissionError` khi sandbox cấm bind
localhost; chạy lại cùng suite ngoài network sandbox đạt 214/214. Frontend
lần đầu bị sandbox cấm ghi Vite temp config; chạy lại với Node 20.19.4 đạt
179/179. Đây là environment restrictions, không phải product failures.

Không có skipped hoặc xfailed test. Không có live provider call hoặc
application live web-search call.

## Verdict và correction tối thiểu

```text
VIETLAW_TRAFFIC_SAFE_SUBSET_V1_LEGAL_CORRECTION_ROUND_1_VERIFICATION_BLOCKED
```

Correction cần thiết:

1. Làm topic shape exact, tối thiểu thêm
   `signal_interpretation=0` cho `traffic_no_helmet`; tốt hơn là từ chối mọi
   role không xuất hiện trong exact shape.
2. Thêm regression test chứng minh helmet + signal citation bị reject.
3. Sửa machine-readable test label thành affected backend tests và mô tả
   đúng các phone probes thực sự nằm trong pytest.

Không cần re-enable Rule D hoặc mở rộng traffic scope. Sau correction cần
targeted independent re-verification trước deployment-readiness task.
