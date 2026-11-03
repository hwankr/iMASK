# 민감정보_추출 필드 대응표 (스키마 담당 확인용)

Upstage 워크플로우의 `민감정보_추출` 노드가 내는 키를 화면의 **정보 종류**(`category`)·**세부 이름**(`label`)·**정보 주체**(`subject`)로 옮기는 표입니다. 백엔드(`imask_backend/fields.py`)는 이 표대로 이름표만 붙이고, **개인정보인지·위험한지는 판별하지 않습니다**. 위험등급은 `위험도_판정` 노드가 준 값만 옮깁니다.

- 정보 종류는 화면 `src/display/rules.ts` 의 `CATS`, 정보 주체는 `SUBJECTS` 값 중 하나입니다.
- 상태: `ok` = 확정, `needs_review` = **확인 필요**(아래 질문), `unknown` = 표에 없는 키.
- 표를 바꾸면 `imask_backend/fields.py` 도 같이 바꿉니다(테스트 `tests/test_fields.py` 가 둘이 같은지 봅니다).
- 이 문서에는 원문 값을 적지 않습니다. 아래 '값의 모양'은 합성 묶음(`testdocs/iMASK_smoke_bundle.pdf`, 6쪽) 1회 실행에서 본 글자 꼴만 적었습니다.

## 1. 대응표

| 키 | 정보 종류 (category) | 세부 이름 (label) | 정보 주체 (subject) | 가림 규칙 (kind) | 상태 (mapping_status) |
|---|---|---|---|---|---|
| `applicant_name` | 이름 | 신청인 성명 | 신청인 | `name` | `ok` |
| `applicant_rrn` | 고유식별정보 | 주민등록번호 | 신청인 | `rrn` | `ok` |
| `applicant_id_number` | 고유식별정보 | 신분증 번호 | 신청인 | `id_number` | `needs_review` (확인 필요) |
| `applicant_birth_date` | 생년월일 | 생년월일 | 신청인 | `birth_date` | `ok` |
| `applicant_phone` | 연락처·이메일 | 전화번호 | 신청인 | `phone` | `ok` |
| `applicant_email` | 연락처·이메일 | 이메일 주소 | 신청인 | `email` | `ok` |
| `applicant_address` | 주소 | 주소 | 신청인 | `address` | `ok` |
| `employer_info` | 기타 개인정보 | 직장 정보 | 신청인 | `text` | `needs_review` (확인 필요) |
| `account_number` | 계좌번호 | 계좌번호 | 신청인 | `account` | `ok` |
| `card_number` | 기타 개인정보 | 카드번호 | 신청인 | `card` | `needs_review` (확인 필요) |
| `loan_info` | 소득·거래정보 | 대출 정보 | 신청인 | `text` | `needs_review` (확인 필요) |
| `income_info` | 소득·거래정보 | 소득 정보 | 신청인 | `text` | `needs_review` (확인 필요) |
| `credit_negative_info` | 소득·거래정보 | 신용 불이익 정보 | 신청인 | `text` | `needs_review` (확인 필요) |
| `other_person_name` | 이름 | 제3자 성명 | 기타 | `name` | `needs_review` (확인 필요) |
| `other_person_rrn` | 고유식별정보 | 제3자 주민등록번호 | 기타 | `rrn` | `needs_review` (확인 필요) |
| `other_person_contact` | 연락처·이메일 | 제3자 연락처 | 기타 | `text` | `needs_review` (확인 필요) |
| `staff_contact` | 연락처·이메일 | 은행 직원 연락처 | 기타 · 은행 직원 | `text` | `ok` |

**표에 없는 키**(워크플로우에 새 키가 생긴 경우)도 버리지 않습니다: 정보 종류 `기타 개인정보`, 세부 이름 = 키 이름 그대로, 정보 주체 `기타`, 가림 규칙 `text`, 상태 `unknown`.

## 2. 가림 규칙 (화면 미리보기용 — 판별 아님)

값을 `;` 로 나눈 조각마다 적용합니다. 길이는 원문과 같고, 글자는 원문 그대로이거나 `*` 로만 바뀝니다(원문에 이미 있던 가림 문자는 그대로). 규칙을 써도 그대로인 조각(가림 문자가 없는데)은 글자·숫자를 모두 `*` 로 바꿉니다. 예는 모두 지어낸 값입니다.

| 가림 규칙 | 한 줄 설명 | 예 |
|---|---|---|
| `name` | 첫 글자·끝 글자만 남김(2자면 첫 글자만, 1자면 전부 가림) | 홍길동 → 홍\*동 |
| `rrn` | 숫자 앞 7개만 남김 | 800101-1234567 → 800101-1\*\*\*\*\*\* |
| `id_number` | 숫자가 13개면 `rrn`, 아니면 글자·숫자 앞 2·뒤 2만 남김 | A1234567 → A1\*\*\*\*67 |
| `birth_date` | 숫자 앞 4개(연도)만 남김 | 1980년 1월 1일 → 1980년 \*월 \*일 |
| `phone` | 숫자 앞 3·뒤 4개만 남김 | 010-1234-5678 → 010-\*\*\*\*-5678 |
| `email` | `@` 앞만 가림(4자 이상이면 앞 2자, 2~3자면 앞 1자 남김), 도메인은 그대로 | hong@example.com → ho\*\*@example.com |
| `address` | 공백으로 나눈 앞 2토큰만 남김(2토큰 이하면 첫 토큰만) | 가상특별시 모의구 예시대로 77, 9층 → 가상특별시 모의구 \*\*\*\* \*\*, \*\* |
| `account` | 숫자 앞 3·뒤 3개만 남김 | 123-45-678901 → 123-\*\*-\*\*\*901 |
| `card` | 숫자 앞 4·뒤 4개만 남김 | 1234-5678-9012-3456 → 1234-\*\*\*\*-\*\*\*\*-3456 |
| `text` | `@` 가 있으면 `email`, 9~12자리 번호면 `phone`, `이름표:` 가 있으면 이름표는 두고 나머지를, 아니면 공백 토큰마다 첫 글자만 남김 | 연봉: 12,340,000원 → 연봉: 1\*,\*\*\*,\*\*\*\* |

노출 상태(`전체 노출`·`부분 마스킹`·`마스킹됨`)는 값 속 가림 문자(`* ＊ ● ○ ■ □ ◆ ◇ ★ ☆`, 숫자 규칙 종류에서는 `X x ×` 도)로 추정합니다.

## 3. 합성 묶음에서 본 값의 모양 (원문 없이)

합성 묶음은 서류 6개(쪽마다 1개)로 분류됐습니다: `loan_application`(1쪽) · `consent_form`(2) · `income_proof`(3) · `power_of_attorney`(4) · `debt_transaction`(5) · `Other`(6). 추출은 `Other` 를 뺀 5개 서류에서 나왔고 값이 있는 키는 서류마다 10 / 2 / 5 / 7 / 5개(합 29)였습니다. 값은 모두 문자열, 못 찾으면 `""`, 여러 값은 `;` 로 이어 옵니다.

| 키 | 나온 서류 | 모양 |
|---|---|---|
| `applicant_name` | 5개 서류 모두 | 한글 이름 한 개 |
| `applicant_rrn` | loan_application · income_proof · power_of_attorney | `숫자6-숫자7`. income_proof 에서는 뒤 6자리가 이미 `*` 로 가려져 왔다 |
| `applicant_id_number` | (나오지 않음) | — |
| `applicant_birth_date` | consent_form | `연 월 일` 꼴(숫자 + 한글 단위, 공백으로 3토큰) |
| `applicant_phone` | loan_application · power_of_attorney | `숫자-숫자-숫자` |
| `applicant_email` | loan_application | `영문.영문@영문.영문` |
| `applicant_address` | loan_application · income_proof · power_of_attorney | 시·구·도로명·번지·동·호 공백 토큰 6개(단어 좌표도 6개) |
| `employer_info` | loan_application · income_proof | `이름표: 값` 꼴. loan_application 은 `;` 로 4건(직장명·부서 등 이름표가 각각), income_proof 는 1건(`(주)회사명`). 신뢰도 low |
| `account_number` | loan_application · debt_transaction | `숫자-숫자-숫자` |
| `card_number` | debt_transaction | 가운데 8자리가 이미 `*` 로 가려진 `숫자4-****-****-숫자4`. 신뢰도 low |
| `loan_info` | loan_application · debt_transaction | 한글 낱말 + 금액(`9,999,999원`) + 기간·금리(`9.9%`)·상태. debt_transaction 은 `;` 로 2건. 신뢰도 low |
| `income_info` | loan_application · income_proof | `이름표: 금액원`. income_proof 는 `;` 로 2건이고 **page -1·좌표 없음**(위치를 못 찾음). 신뢰도 low |
| `credit_negative_info` | debt_transaction | 한글 낱말 + 횟수. 신뢰도 low |
| `other_person_name` | power_of_attorney | 한글 이름 한 개 |
| `other_person_rrn` | power_of_attorney | `숫자6-숫자7` |
| `other_person_contact` | power_of_attorney | `;` 로 2건 — **전화번호와 주소가 한 값에** 섞여 왔다. 신뢰도 low |
| `staff_contact` | loan_application | `;` 로 4건 — **이름 · 부서와 영문-숫자 코드 · 전화번호 · 이메일이 한 값에** 섞여 왔다. 신뢰도 low |

- `page` 는 값마다 그 서류가 있는 쪽 번호(2쪽 서류의 값이 `page 2`)였습니다 — 파일 전체 기준으로 보입니다. 서류마다 1쪽이라 여러 쪽 서류에서는 확인하지 못했습니다.
- 좌표는 `word_coordinates`(단어별 사각형 1~6개)와 `coordinates`(값 영역 사각형) 둘 다 0~1 비율로 왔습니다. 화면은 단어별 사각형을 먼저 씁니다.
- `Other` 서류(6쪽)는 추출 대신 `기타_서류_안내` 본문(`예상_서류_종류=…, 검토_사유=…, 담당자_조치=…`)이 붙습니다.

## 4. 확인 필요 — 질문

답을 주시면 표의 상태를 `ok` 로 바꾸거나 키를 나눕니다.

1. **`other_person_name`·`other_person_rrn`·`other_person_contact` 는 누구인가요?** 위임장의 대리인, 보증인, 거래 상대방 중 무엇인가요? 서류마다 다르면(예: 위임장은 대리인, 보증 서류는 보증인) 키를 나눠 줄 수 있나요(`agent_*`·`guarantor_*`·`counterparty_*` 등)? 지금은 정보 주체를 `기타` 로 둡니다(화면 목록에는 `보증인`·`기타 · 거래 상대방` 도 있습니다).
2. **`applicant_id_number` 는 어떤 번호인가요?** 운전면허번호·여권번호·외국인등록번호·신분증 발급번호 중 무엇인가요? 주민등록번호와 겹쳐 나오면(같은 번호가 두 키에) 어떻게 할까요? 합성 묶음에서는 한 번도 값이 없었습니다.
3. **`employer_info`·`loan_info`·`income_info`·`credit_negative_info` 의 정보 종류가 맞나요?** 지금은 직장 정보 = `기타 개인정보`, 나머지 = `소득·거래정보` 입니다. 신용정보(연체·불이익)를 따로 둘지 알려 주세요. 또 여러 건이 `;` 로 한 값에 오는데, **한 건씩 나눠(배열 등) 줄 수 있나요?** 지금은 한 값을 한 항목으로 보여 줍니다.
4. **`card_number`**: 화면 정보 종류(`CATS`)에 카드번호가 없습니다. `계좌번호` 에 넣을까요, 새 종류(예: `카드번호`)를 둘까요? 지금은 `기타 개인정보` 입니다.
5. **`staff_contact`·`other_person_contact`**: 이름·부서·전화번호·이메일·주소가 한 값에 섞여 옵니다. 항목별로 나눠(`staff_name`·`staff_phone`·`staff_email` 등) 줄 수 있나요?
6. **`page` 기준**: 여러 쪽 서류에서도 `page` 가 파일 전체 기준 쪽 번호인가요, 서류 안 쪽 번호인가요?(합성 묶음은 서류마다 1쪽이라 확인하지 못했습니다.) 화면은 파일 전체 기준으로 원본 쪽을 엽니다.
7. **항목별 위험등급**: 지금 워크플로우는 전체 위험도(`위험도_판정` 의 `additional_values.enum`)만 내고 항목별 등급은 없어 모든 항목이 `미평가`(unrated)입니다. `위험도_판정` 노드가 `[{branch_key, field, grade, reason}]` 목록을 낸다면 아래 중 어디에 둘지 정해 주세요. 백엔드는 이 순서로 찾습니다.
   1. `data`(노드 출력 본문)가 JSON 배열이면 그 배열, JSON 객체면 그 값 중 배열인 것
   2. `additional_values` 의 값 중 배열인 것(예: `items`)
   3. 본문이 Markdown 이면 그 안의 ```` ```json ```` 코드 블록(언어 표시 없는 ```` ``` ```` 도)
   - `branch_key` 는 병합 단계와 같은 `"<분류 순번>:<분류 코드>"`(예: `0:loan_application`), `field` 는 위 표의 키, `grade` 는 `상`·`중`·`하`, `reason` 은 짧은 문장입니다. 같은 (branch_key, field) 가 여러 번이면 처음 것만 씁니다.
   - **`grade` 에 `검토 필요` 도 쓸 건가요?** 지금은 `상`·`중`·`하` 만 읽고 그 밖(검토 필요·영어 등)은 무시합니다. 본문 Markdown·인용(citations)에서 등급을 추측하지 않습니다.
