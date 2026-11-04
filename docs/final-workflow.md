# 최종 흐름 워크플로우 (`final_imask_workflow`)

Upstage Studio 팀 프로젝트의 `final_imask_workflow`(설정 번호 1)는 팀 워크플로우를 하나로 합친 것입니다: **예시 워크플로우 #3**(지금 웹이 쓰는 것) + **승환 워크플로우의 서류_대조(Match)** + **팀원 서식 분류**. 저장소 정의는 `workflows/final_imask_workflow.json` 입니다.

## 노드 그래프

```
step_1_parse → step_2_classify (서류마다 나눔)
  ├ 신청서 7종 → Information Extract - 추출_신청서 ┐
  ├ 확인서 3종 → Information Extract - 추출_확인서 │
  ├ 증빙 2종   → Information Extract - 추출_증빙   ├→ 병합-1 → Match - 서류_대조 → Validate - 묶음_검증
  ├ 위임장     → Information Extract - 추출_위임장 ┘        → Instruct - 위험도_판정 ─┬ 상·중·하 → Instruct - 권장_조치
  └ Other      → Instruct - 기타_서류_안내 (끝)                                       └ 검토 필요 → Instruct - 검토_안내
```

| 추출 노드 | 분류 코드 |
|---|---|
| `추출_신청서` | `loan_application` `payment_guarantee_application` `consumer_compensation_claim` `debit_card_application` `auto_transfer_application` `dormant_deposit_claim` `retirement_pension_application` |
| `추출_확인서` | `consent_form` `fatca_crs_certification` `foreign_household_confirmation` |
| `추출_증빙` | `income_proof` `debt_transaction` |
| `추출_위임장` | `power_of_attorney` (위임인 = `applicant_*`, 대리인 = `other_person_*`) |
| (`기타_서류_안내`) | `Other` |

- 추출 4개는 같은 17키 스키마입니다(`docs/field-mapping.md` 의 표 그대로). 노드마다 '신청인이 누구인지' 안내 문구만 다릅니다.
- **서류_대조**: 기준 = `추출_신청서`의 `applicant_name`. 대상 = 확인서(exact) · 증빙(fuzzy) · 위임장(exact)의 `applicant_name`. 일치하지 않은 서류는 결과 목록에 없습니다.
- **묶음_검증**(묶음 하나에 한 번, green·yellow·red): `신청서_신청인_성명`(error) · `확인서_신청인_성명` · `증빙_신청인_성명` · `위임장_위임인_성명` · `위임장_대리인_성명`(warning). `left.value` 가 `null` 이면 **그 종류 서류가 묶음에 없음**입니다(필수 항목 누락이 아님).
- Studio 규칙: Match 의 기준·대상은 Merge 로 바로 들어가는 Extract 여야 합니다(아니면 400 `config_graph_rule_violation`). 그래서 검증이 서류_대조 뒤에 있습니다.

## 위험도_판정 출력 = 미션 2 정답지 키

판정 노드는 `Instruct - 위험도_판정` 입니다. 글은 `키: 값` 다섯 줄 + 마지막 줄 등급이고, 등급은 `additional_values.enum` 에도 있습니다.

| 키 | 값 |
|---|---|
| `risk_level` | `상` · `중` · `하` · `검토 필요` |
| `document_types` | 분류 코드 목록. `Other` 는 이 노드로 오지 않아 빠집니다 |
| `sensitive_categories` | `고유식별정보` · `신용도판단정보` · `신용거래정보` · `신용능력정보` · `일반개인정보` 중 값이 있는 것 |
| `review_reasons` | `검토 필요`일 때만: `판독 불가` · `정보 주체 불명` · `필수 항목 누락` · `서류 간 불일치` |
| `reason` | 판정 근거 1~2문장(원문 값 없이) |

예시 정답지(시험 묶음 4개, 원문 값 없음):

```json
{
  "task": "iMASK — 은행 창구 서류 묶음의 민감정보 위험도 판정 (합성 시험 묶음)",
  "unit": "고객 1명 = 파일 1개(서류 묶음 PDF) = 판정 1건",
  "output_keys": ["risk_level", "document_types", "sensitive_categories", "review_reasons", "reason"],
  "decision_values": ["상", "중", "하", "검토 필요"],
  "cases": [
    {
      "case_id": "A",
      "file": "iMASK_smoke_bundle.pdf",
      "documents": ["대출 신청서", "개인(신용)정보 동의서", "소득금액증명", "위임장", "채무 내역", "기타"],
      "answer": {
        "risk_level": "상",
        "document_types": ["loan_application", "consent_form", "income_proof", "power_of_attorney", "debt_transaction"],
        "sensitive_categories": ["고유식별정보", "신용도판단정보", "신용거래정보", "신용능력정보", "일반개인정보"],
        "review_reasons": [],
        "reason": "주민등록번호와 신용도판단정보가 있고 모든 서류의 신청인이 같다."
      }
    },
    {
      "case_id": "B",
      "file": "ff-mismatch.pdf",
      "documents": ["대출 신청서", "개인(신용)정보 동의서", "소득금액증명"],
      "answer": {
        "risk_level": "검토 필요",
        "document_types": ["loan_application", "consent_form", "income_proof"],
        "sensitive_categories": ["고유식별정보", "신용거래정보", "신용능력정보", "일반개인정보"],
        "review_reasons": ["서류 간 불일치"],
        "reason": "동의서의 동의자가 대출 신청서의 신청인과 다르다."
      }
    },
    {
      "case_id": "C",
      "file": "ff-blank-applicant.pdf",
      "documents": ["대출 신청서(신청인 칸 빔)", "개인(신용)정보 동의서"],
      "answer": {
        "risk_level": "검토 필요",
        "document_types": ["loan_application", "consent_form"],
        "sensitive_categories": ["신용거래정보", "신용능력정보", "일반개인정보"],
        "review_reasons": ["필수 항목 누락"],
        "reason": "대출 신청서의 신청인 성명이 비어 있어 묶음_검증이 red다."
      }
    },
    {
      "case_id": "D",
      "file": "ff-team-forms.pdf",
      "documents": ["체크카드 가입신청서", "FATCA/CRS 본인확인서", "위임장", "지점 방문 안내문"],
      "answer": {
        "risk_level": "상",
        "document_types": ["debit_card_application", "fatca_crs_certification", "power_of_attorney"],
        "sensitive_categories": ["고유식별정보", "신용거래정보", "신용능력정보", "일반개인정보"],
        "review_reasons": [],
        "reason": "위임장에 주민등록번호가 있고 확인서·위임장의 신청인이 신청서와 같다."
      }
    }
  ]
}
```

## 시험 묶음

`testdocs/final-flow/*.html` 을 고친 뒤 `python scripts/make_testdocs.py` 로 PDF 를 다시 만듭니다(Chrome·Edge 헤드리스). 모든 값은 지어낸 것입니다. 아래는 모두 실측입니다.

| 묶음 | 쪽 | 분류 | 묶음_검증 | 서류_대조 | 위험도 | 마지막 단계 |
|---|---|---|---|---|---|---|
| `testdocs/iMASK_smoke_bundle.pdf` (정상) | 6 | 대출·동의서·소득·위임장·채무 + Other | green | 확인서·증빙 2·위임장 연결 | 상 | 권장_조치 (+ 기타_서류_안내) |
| `ff-mismatch.pdf` | 3 | 대출·동의서·소득 | yellow (위임장 없음) | 증빙 연결, 확인서 연결 안 됨 | 검토 필요 (서류 간 불일치) | 검토_안내 |
| `ff-blank-applicant.pdf` | 2 | 대출·동의서 | red (신청인 성명 없음, 증빙·위임장 없음) | 확인서 근거 부족(기준 성명 빔) | 검토 필요 (필수 항목 누락) | 검토_안내 |
| `ff-team-forms.pdf` | 4 | 체크카드·FATCA/CRS·위임장 + Other | yellow (증빙 없음) | 확인서·위임장 연결 | 상 | 권장_조치 (+ 기타_서류_안내) |

Upstage 결과는 실행마다 조금 다를 수 있습니다(예: 빈 신청인 묶음의 검토 사유에 한 실행에서 '서류 간 불일치'가 함께 나옴).

## 다시 만들기·비교

- 미션 2 제출 JSON 은 Studio 화면의 워크플로우 ⋯ → **워크플로우 설정 내보내기** 로 받습니다. 저장소 JSON 은 Studio API 의 step 형식이라 화면 내보내기와 꼴이 다릅니다.
- 같은 조직에서 **가져오기** 를 하면 지금 워크플로우를 덮어씁니다(버전 기록은 남습니다).
- 저장소 JSON 은 실제 Studio 설정(번호 1)과 같습니다. 비교·다시 만들기는 `scripts/studio_workflow.py`(키는 `.env`, 출력에 키·전체 id 없음, `diff` 는 같으면 0, `create` 는 `--yes` 가 없으면 할 일만 출력):

```
python scripts/studio_workflow.py diff --agent final_imask_workflow --config 1 workflows/final_imask_workflow.json
python scripts/studio_workflow.py show --agent final_imask_workflow
python scripts/studio_workflow.py create workflows/final_imask_workflow.json --agent <새 이름> --yes
```

## 알려진 한계

- 서류_대조는 **빈 값끼리도 일치**로 냅니다(기준·대상 성명이 둘 다 비면 연결됨) — 화면에서 근거 부족으로 다룹니다.
- 신청서가 둘 이상이거나 없는 묶음의 서류_대조 모양은 아직 확인하지 않았습니다.
- API 로 설정을 넣으면 고쳐 쓰지 않고 늘 새 설정 번호가 생기며 그 번호가 기본 설정이 됩니다(웹은 `.env` 의 번호를 씁니다).
