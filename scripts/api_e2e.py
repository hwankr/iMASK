# ==========================================================================
#  FastAPI 백엔드 끝까지 확인 스크립트 (로컬 uvicorn · 배포 사이트 공용)
#  브라우저가 할 일을 그대로 한다: health → 분석 만들기 → 서명 URL 로 Storage 에 올리기 → 시작
#  → 3초마다 조회(상태가 바뀔 때만 한 줄) → 결과 요약 또는 오류 → Upstage 파일 삭제 확인.
#
#  실행(저장소 루트에서, 먼저 uvicorn 을 띄운다):
#    .venv\Scripts\python.exe scripts\api_e2e.py [--base-url http://127.0.0.1:8000]
#        [--file testdocs/iMASK_smoke_bundle.pdf] [--name 분석명] [--interval 3] [--timeout 600]
#        [--skip-upload] [--content-file <올릴 실제 내용>] [--no-start] [--expect done|failed]
#        [--analysis-id <이미 있는 분석 id>] [--no-review] [--retry-flow | --fail-with-original] [--keep]
#    --skip-upload   : 올리지 않고 시작 → '업로드된 파일을 찾을 수 없습니다' 실패 경로(Upstage 호출 없음)
#    --content-file  : 이름·형식은 --file 로 알리고 내용은 이 파일로 올린다 → 형식 불일치 실패 경로
#    --no-start      : 만들기·올리기까지만(한글 파일 이름이 Storage 에 올라가는지 확인할 때)
#    --analysis-id   : 만들기·올리기·시작 없이(**Upstage 작업을 만들지 않음**) 그 분석을 조회해 아래 done 확인과
#                      원본 파일 확인, 검토 기록 모양 확인만 한다(**읽기만 — 검토 동작을 보내지 않음**).
#                      비교할 원본은 --file(기본 합성 묶음). 코드를 고친 뒤 재확인용.
#    --no-review     : 검토 동작 확인(아래)을 끈다(--analysis-id 에서는 검토 기록 모양 확인을 끈다).
#  done 확인(T1 findings-api): 요약(서류·추출 = 알려진 모양 6·5 또는 5·4 · 상) + 화면용 결과 — 알려진 모양 둘 중 하나와
#    정확히 같은 수(위임장 따로: documents 6(extracted 5·other 1)·findings 29·boxes 있는 항목 28 / 위임장 합침:
#    documents 5(extracted 4·other 1)·findings 26·boxes 26 — 모양을 섞지 않음, EXPECTED_SHAPES),
#    other 에 other_guide·extracted 에 validation(옛 워크플로우만 — 최종 흐름은 아래 bundle_check verdict), overall 상/권장_조치·
#    risk 분포(허용 값·risk_source 와 맞는지만 — unrated 를 강제하지 않음)·계약 키·id 중복·document_index·
#    boxes 0~1, 기본 응답에 stages·response 없음, 응답 크기(기본 GET vs ?include=stages GET 바이트 — 기본이 작아야 함).
#    검토사항(result.items, review-items BRIEF §5.3): 계약 모양(키·순서·타입·R-nn 1부터 연속·id 중복 없음·보이는 서류·쪽 범위·
#    그 서류의 탐지 항목 참조 — 실패하면 'items[n].키' 위치만 출력) + 이 스크립트가 응답의 documents·findings 로 **따로 계산한
#    기대값**과 정확히 같음(nolocation = 위치 없는 보이는 탐지 항목 · lowconf = 서류마다 신뢰도 low 묶음·NUMS · other = 기타 서류,
#    id·number·type·document_index·page·finding_id·고정 글·근거 label·page·finding_ids·finding_id). 검증 checks 는 응답에 없어
#    missing 항목은 계산할 수 없다 — 보이는 서류의 validation 이 모두 green(또는 null)일 때만 missing 0개를 기대하고, 아니면
#    '새 모양'으로 실패를 알린다(숫자를 느슨하게 하지 않는다 — _expected_items). 검토사항 키 맨 뒤 link_id(연결 종류 mismatch·
#    weaklink 만 그 서류를 대상으로 하는 links[] id, 그 밖 null).
#  최종 흐름 워크플로우(final_imask_workflow — final-flow T3 A, _print_final): 결과 키 links·decision·bundle_check 가 있는지(없음 ≠ null)와 계약 모양
#    (키·순서·허용 값·L-nn 연속·link:<기준>:<대상>·연결 서류가 보이는 서류·쪽·탐지 항목·fields 80자·글 = state 고정 문구 + 이름표·
#    조사, decision 키 5개, bundle_check {verdict, checks[키 7개]}). bundle_check 가 객체면 최종 흐름 — 서류 validation 은 null 이어도
#    되고 대신 verdict(green·yellow·red)가 있어야 하며, 알려진 모양(위임장 따로 + 연결 4개 모두 linked · verdict green)과 같아야 한다.
#    검토사항 기대값은 verdict green 이고 모든 연결이 linked 일 때만 묶음·연결 항목(missing·bundle·absent·mismatch·weaklink) 0개,
#    아니면 '새 모양'. bundle_check 가 null 이면 옛 워크플로우 — links [] · decision null 이어야 한다. 출력은 개수·상태·키 이름만
#    (받은 값은 허용 enum 글자만 그대로, 그 밖 숫자·bool·객체·목록·모르는 글자는 '<int>' 같은 타입 표기 — _kind).
#    원본 파일: GET /analyses/{id}/file 200·키 {url, mime_type, filename} → url 로(사용자 지정 헤더 없이) 받아 올린 내용과
#    sha256 비교. 원문 값(value·masked)·서명 URL 은 출력하지 않는다(개수·분포·바이트 수만).
#  검토 동작 확인(review-actions, 기본 켬): **이번 실행이 만든 분석이 done 이 된 뒤에만** POST /analyses/{id}/review-actions 를
#    차례로 보낸다(actor api_e2e, 글은 이 스크립트가 만든 합성 문구). 처음 조회(needed·version 0·findings {}·이력 S1·S2)
#    → 확인 → 확인 취소 → 2건 한꺼번에 확인 → 같은 항목 다시 확인 409(상태 불일치) → 오탐 표시 → 오탐 취소(→ 미확인)
#    → 분류 수정(정보 종류) → 같은 값 분류 수정(changed false·이력 없음) → 오탐 표시 → 오탐 취소(→ 분류 수정)
#    → 항목 메모 저장·삭제 → 검토 메모
#    → 검토사항(review-items §5.6, 첫 검토사항 R-01): resolve_item(review.items[id] = {resolved true, note, resolved_at = 새 이력
#    at, resolved_by api_e2e} · 이력 resolve · 'R-01 <종류 라벨>' · '미해결 → 해결' · reason = note) → 다시 resolve 409(검토사항 상태
#    바뀜) → reopen_item(resolved false · note·resolved_at·resolved_by 남음 · 이력 reopenItem · '해결 → 미해결' · reason '')
#    → 다시 reopen 409 → 다시 resolve(새 처리 내용) → 없는 item_id 404 → 400 두 가지(reopen_item 에 note · 501자 note).
#    검토사항이 0개면 이 부분은 '건너뜀(검토사항 0개)'. 처음 조회는 review.items {} 여야 한다.
#    검토사항 동작을 보내기 **전에** result.items 전체의 계약 모양(done 확인과 같은 검사)을 본다 — 틀리면 값 없는 실패 위치
#    (items[n].필드)만 적고 보내지 않는다. 출력에 쓰는 번호는 스크립트가 만든 순번(R-{i:02d} — 받은 번호가 같을 때만 대상)이고,
#    받은 id·글은 출력하지 않는다(본문 item_id 에만). review 블록의 status·version·changed 도 계약 값이 아니면 '<타입>' 으로만 적는다.
#    → 검토 완료(남은 미확인 탐지 수 · 미해결 검토사항 수(= 검토사항 수 − 해결한 1개)가 문구에) → 잠김 409·이미 완료 409
#    → 잠긴 채 resolve_item·reopen_item 409(잠김)
#    → 내보내기 기록 log_export(**잠긴 상태에서**): CSV(handed)·JSON(saved) 두 번 — 200·changed true·새 이력 줄
#    (kind export · target = 파일 이름 · change 'CSV · <크기> · 다운로드 요청'/'JSON · <크기> · 저장 완료' · reason
#    '민감한 값 마스킹') · review 의 다른 값(status done·findings·memo·memo_at·reviewer·reviewed_at·completion_note) 그대로,
#    거절 두 가지(이 분석의 이름이 아님 — 서울 날짜 하루 다름 → 400, size 0 → 400) → 다시 열기
#    (reviewer·completion_note 남음, reviewed_at null) → 400 두 가지(모르는 type, 501자 글).
#    log_export 기대값도 계약대로 따로 만든다: 파일 이름 = iMASK_IM-<created_at 의 서울(UTC+9) 날짜 YYYYMMDD>-<id 의 ASCII
#    영숫자 앞 4자 대문자> + '_검토결과_탐지항목.csv' | '_검토결과.json'(화면 analysisCode 와 같은 꼴), 크기 표기 = 화면 fmtSize
#    (1,048,576 미만 max(1, Math.round(b/1024))KB, 아니면 (b/1048576).toFixed(1)MB — JS 처럼 '절반은 올림', _fmt_size).
#    크기는 그럴듯한 값(CSV 6,127 → 6KB · JSON 1,310,720 → 1.3MB — MB 소수 첫째 자리 동점)을 보낸다.
#    단계마다 응답 상태·changed·review 값·새 이력 줄(id H{version}·actor·kind·target·change·reason)을 보고 GET 으로 다시
#    읽어 같은지 확인한다(오류 단계는 다시 읽은 review 가 그대로인지 = 쓰기 없음). 마지막에 이력 id H1…Hn 연속,
#    at 이 줄어들지 않음, 저장 줄 수 = 쓴 동작 수 = version, 분석 created_at·updated_at·started_at 이 처음 조회와 같음(분석 시각·
#    걸린 시간 불변 — 동작 응답마다도), 검토사항 해결 기록이 마지막 해결 값 그대로. 출력은 단계 이름·통과/실패·개수만 — 기대와 다른 이력 줄·검토 값도 필드 이름과 '계약과 다름'만
#    (받은 값·기대 값은 출력하지 않는다 — 서버가 잘못해 원문 값을 담아도 터미널에 나오지 않게).
#    기대 문구는 계약(데모 코어와 같은 전이·문구)을 그대로 적은 것이다.
#    기대값도 계약대로 따로 만든다(백엔드 함수를 쓰지 않음): 표시 이름·위험등급은 JavaScript trim() 공백 집합(_js_trim —
#    U+FEFF 는 지우고 U+0085·U+001C~001F 는 두는 화면 기준), 이력 target 은 저장 안전화(_stored_target — 짝 없는
#    서로게이트·NUL → U+FFFD, 200 코드 포인트 넘으면 앞 199자 + '…'). 검토 동작 본문(_json_body)은 httpx json= 과 같은
#    UTF-8 JSON(같은 크기 — 서버 본문 한도 65,536 바이트 기준)이되 짝 없는 서로게이트만 \udXXX 로 escape 한다
#    (브라우저 JSON.stringify 처럼 — 그런 글자가 든 계약 id 도 보낼 수 있게).
#
#  비밀값(BRIEF §2): 접근 코드는 없다(2026-11-03 없앰). Upstage 키 등은 출력하지 않는다.
#    서명 URL·토큰·키는 출력하지 않는다(모든 출력은 _say() 를 지나며 알려진 값을 가린다).
#    배포 사이트의 Vercel 보호를 넘기려면 선택 환경변수 VERCEL_PROTECTION_BYPASS 를
#    x-vercel-protection-bypass 헤더로 보낸다.
#  올리기: .env 에 NEXT_PUBLIC_SUPABASE_URL·NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY 가 있으면 브라우저와 같이
#    공개 키 클라이언트의 upload_to_signed_url(path, token, …)로, 없으면 서명 URL 에 직접 PUT.
#  Upstage 실행 1번 = 크레딧 사용(BRIEF §3). 합성 자료만 올린다.
#  정리: 시간 초과·Ctrl+C·연결 오류·예상 못 한 예외를 포함한 모든 종료 경로의 finally 에서, 관찰한
#    Upstage file id 를 .env 의 UPSTAGE_API_KEY 로 지운다(404 = 이미 지움 = 성공). 시작한 분석이 끝나지 않았는데
#    file id 를 모르면(시작 응답을 받았어도) 분석을 한 번 다시 읽어 얻는다. /start·/retry(작업을 만들 수 있는 요청)는 보내기
#    전에 '시작 결과 미확인'을 적고 응답(200 분석 건 또는 작업을 만들지 않는 거절 400·404·409·413)을 관찰해야 푼다 — 응답을 잃으면
#    앞에서 끝난 것으로 보았어도·file id 를 모았어도 다시 읽어 새 file id 를 더한다(다시 읽은 행이 끝났거나 file id 가 있어야 확인).
#    그래도 확인할 수 없거나 정리를 못 하면 값 없는 문구로 알리고 종료 코드 1.
#  출력의 오류 문구는 원문 전체를 가린 뒤에 자른다(_short).
#  종료 코드: 기대(--expect, 기본 done)대로면 0 — done 이면 위 done 확인·원본 파일 확인·검토 동작 확인(또는 검토 기록
#    모양 확인)도 모두 맞아야 한다. 하나라도 실패하면 1.
#
#  공유 목록·삭제·다시 분석 확인(shared-analyses). 기대값은 계약(BRIEF §5.2~5.5)대로 따로 만든다(백엔드 함수를 쓰지 않음).
#    목록 확인(done 뒤): GET /api/py/analyses 200 {"analyses": [...]} — 모든 항목 키가 계약 10개(result 없음)·문서 키 3개·
#      created_at desc, id desc 순서, 이 분석이 정확히 한 번 있고 값이 조회 응답에서 계약대로 만든 기대값(_list_expected —
#      risk_level = summary.risk_level 문자열, review = done + 서류 수 ≥ 1 이면 검토 상태(done 아니면 needed), 그 밖 none,
#      문서 = 올린 파일 행 filename·size_bytes·mime_type)과 같음. 응답 바이트 수를 출력한다(다른 분석의 값은 출력하지 않음).
#    삭제 확인(기본, --keep 이면 건너뜀): DELETE 204(본문 없음) → GET 404 → GET …/file 404 → 목록에 없음
#      → 지운 분석 다시 분석 404 → 두 번째 DELETE 404(문구 '분석 건을 찾을 수 없습니다.'). 첫 DELETE 가 204·빈 본문이 아니거나
#      (연결 오류 포함) 그 뒤 GET·/file·목록이 아직 있음을 보이면 다시 분석·두 번째 DELETE 를 보내지 않고 실패로 끝낸다(남은 분석에
#      작업을 만들지 않게). 지웠다는 표식은 없음을 확인한 뒤에만 단다 — 아니면 finally 가 다시 지운다.
#    documents 모양: 목록 항목·다시 분석 응답·조회 응답의 documents 가 목록이 아니거나 객체가 아닌 항목이 있으면 그 확인의 실패로
#      적는다(예외 없이 — 정리용 file id 는 정상 항목에서만 모은다).
#    --retry-flow   : 올리지 않고 시작('업로드된 파일을 찾을 수 없습니다' 실패, Upstage 없음) → 목록에 failed → 원본 없이
#                     다시 분석(같은 이유로 다시 실패, 작업·file id 없음, 조회와 같은 값) → 만들 때 받은 같은 서명 업로드
#                     주소로 원본을 올림 → 다시 분석(running, 새 작업 — Upstage 1번) → 분석 중 다시 분석 409 '이미 분석하고
#                     있습니다.'(작업·started_at 그대로) → done. 다시 분석마다 started_at 이 앞 시작보다 뒤, created_at 그대로,
#                     완료 행의 created_at = 처음 · started_at = 마지막 다시 분석 때 값(다르면 '다시 분석' 확인 실패).
#                     done 뒤: done 확인·원본 파일 확인, 검토 이력 [S1, retry 줄(H1·H2 — 사유 = 앞 실패 이유), S2] · at 이
#                     줄지 않음 · 각 retry 줄 at 이 앞 시작 뒤 · 새 시작 이전, 검토 동작 하나(확인) 뒤 [S1, H1, H2, S2, H3]
#                     (--no-review 면 이 동작을 보내지 않음), 목록 확인, 삭제 확인.
#    --fail-with-original : 올리지 않고 시작해 실패시킨 뒤 같은 서명 주소로 원본을 올리고(원본 파일 확인) **다시 분석하지 않고
#                     남긴다**(화면에서 다시 분석을 눌러 볼 실패 분석 — Upstage 0번). 만든 분석 id 를 출력한다. --keep 과 같다.
#    --keep         : 이번 실행이 만든 분석을 지우지 않는다. 기본은 어떻게 끝나든(시간 초과·Ctrl+C·연결 오류 포함) finally 에서
#                     Upstage 파일 정리 뒤 이번 실행이 만든 분석을 DELETE 로 지운다(삭제 확인에서 이미 지웠으면 그대로).
#                     204 뒤 다시 읽어 404 = 지움, DELETE 404 = 이미 없음(출력), 그 밖·연결 오류·204 인데 아직 있음은 정리 실패
#                     (분석 id 출력, 종료 코드 1). 정리 중 Ctrl+C 면 지우지 않는다.
#                     --analysis-id 로 읽은 기존 분석은 지우지 않는다(만든 것이 아니므로).
#  확인 요약: 끝에 확인 묶음마다 통과/실패를 한 줄씩 내고, 새 확인(목록·다시 분석·삭제)만 따로 모아 판정한다 — done 확인의
#    고정 기대값(서류 6·탐지 29 등)이 실제 Upstage 결과와 어긋나는 문제와 섞이지 않게. 종료 코드는 모든 확인이 맞아야 0.
#  설정 60(v2_full) 응답(_is_v2 — decision 에 high_risk_items 키가 있음): 합성 묶음의 고정 기대값(EXPECTED_SHAPES·EXPECTED_RISK)을 보지 않고
#    계약 모양만 본다 — 옛 모양 경로의 출력·판정은 그대로다. 전환 뒤에 --file <임의 PDF> 로 돌렸을 때 '새 모양' 실패가 나오지 않게 하려는 것이다.
#    판정 8키 순서·타입, bundle_check(fail·unknown 만), links, items 계약 모양, 기대 검토사항은 nolocation·lowconf·other 만 따로 계산해
#    비교(번호는 전체 순서라 비교하지 않음)하고 나머지 종류는 계약 모양만 본다. 검토 가능 항목이 3개보다 적으면(빈 서식·대상 외 등) 검토 동작 확인을
#    건너뛴다. mismatch 는 id 꼴이 mismatch:<정수>:<정수> 인 것만 연결 항목이다(그 밖 link_id null). 출력은 값 없이 개수·이름만이다.
# ==========================================================================

from __future__ import annotations

import argparse
import hashlib
import json
import math
import mimetypes
import os
import re
import sys
import time
from collections import Counter
from collections.abc import Callable, Mapping
from datetime import datetime, timedelta, timezone
from fractions import Fraction
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from imask_backend.fields import CATS, EXPOSURES, SUBJECTS  # noqa: E402
from imask_backend.redaction import redact  # noqa: E402
from imask_backend.upstage import UpstageClient, UpstageError  # noqa: E402

DEFAULT_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_FILE = "testdocs/iMASK_smoke_bundle.pdf"
TERMINAL = {"done", "partial", "failed"}
WITHIN_SECONDS = 180  # queued → running → done 기대 시간(3분)

# 합성 묶음의 알려진 결과 모양(BRIEF §3). Upstage 워크플로우가 4쪽 위임장을 따로 나누거나(서류 6) 소득 증빙(3–4쪽)에
# 합친다(서류 5) — 2026-11-03~04 실제 실행에서 두 모양이 모두 나왔다. 수는 둘 중 한 모양과 **정확히** 같아야 한다
# (느슨하게 보지 않는다 — 새 모양이 나오면 실패로 보이고, 확인한 뒤 이 표에 더한다).
EXPECTED_SHAPES: tuple[dict[str, Any], ...] = (
    # 3쪽 소득 정보 하나는 위치(page)를 못 찾아 좌표가 없다(boxes 28). 최종 흐름 워크플로우(final_imask_workflow — 2026-11-04
    # 실제 응답 A_smoke)도 이 모양이고, 그때는 연결 4개 모두 linked · 묶음 검증 green(final)
    {
        "name": "위임장 따로",
        "documents": 6,
        "kinds": {"extracted": 5, "other": 1},
        "findings": 29,
        "boxed": 28,
        "final": {"links": 4, "verdict": "green"},
    },
    # 최종 흐름에서는 아직 보지 못한 모양(final 없음 — 나오면 '새 모양'으로 실패)
    {"name": "위임장 합침", "documents": 5, "kinds": {"extracted": 4, "other": 1}, "findings": 26, "boxed": 26},
)
EXPECTED_RISK = "상"
EXPECTED_NEXT_STAGE = "권장_조치"

# 공통 계약(BRIEF §5)
DOCUMENT_KEYS = {"index", "type", "page_start", "page_end", "kind", "other_guide", "validation"}
FINDING_KEYS = {
    "id",
    "document_index",
    "field",
    "category",
    "label",
    "subject",
    "mapping_status",
    "value",
    "masked",
    "exposure",
    "risk",
    "risk_source",
    "risk_reason",
    "page",
    "boxes",
    "confidence",
}
OVERALL_KEYS = {"level", "text", "next_stage", "next_text"}
FILE_KEYS = {"url", "mime_type", "filename"}
RISKS = ("high", "medium", "low", "unrated")

# 검토 동작 계약(review-actions — 조회 응답의 review 블록·POST /analyses/{id}/review-actions)
REVIEW_KEYS = {"status", "memo", "memo_at", "reviewer", "reviewed_at", "completion_note", "findings", "items", "history", "version"}
REVIEW_FINDING_KEYS = {"status", "category", "subject", "exposure", "fp_type", "fp_note", "reclass_note", "memo", "updated_at"}
HISTORY_KEYS = {"id", "at", "actor", "kind", "target", "change", "reason"}
REVIEW_ACTOR = "api_e2e"  # 이 스크립트가 보내는 처리자 이름
SYSTEM_ACTOR = "시스템"
ANALYSIS_TARGET = "분석 건"
UNNAMED_FINDING = "이름 없는 항목"
RISK_LABELS = {"상": "상", "중": "중", "하": "하", "검토 필요": "검토 필요"}
FP_REASON = "개인정보가 아닌 번호·문구"  # 오탐 사유 목록(FP_REASONS)의 첫 값
MSG_REVIEW_BAD_REQUEST = "요청 형식이 올바르지 않습니다."
MSG_REVIEW_TEXT_TOO_LONG = "메모·사유는 500자 이하로 적어 주세요."
MSG_REVIEW_LOCKED = "검토를 완료한 분석은 바꿀 수 없습니다."
MSG_REVIEW_STATE_CHANGED = "탐지 항목 상태가 바뀌었습니다. 새로 고친 뒤 다시 시도해 주세요."
MSG_REVIEW_ALREADY_DONE = "이미 검토를 완료했습니다."
# 이 스크립트가 만든 합성 문구(메모·사유)
TEXT_CONFIRM = "api_e2e 확인"
TEXT_UNCONFIRM = "api_e2e 확인 취소"
TEXT_FP = "api_e2e 오탐 표시"
TEXT_RESTORE = "api_e2e 오탐 취소"
TEXT_RECLASS = "api_e2e 분류 수정"
TEXT_FINDING_MEMO = "api_e2e 항목 메모"
TEXT_MEMO = "api_e2e 검토 메모"
TEXT_COMPLETE = "api_e2e 검토 완료"
TEXT_REOPEN = "api_e2e 다시 열기"
TEXT_ITEM_RESOLVE = "api_e2e 검토사항 해결"
TEXT_ITEM_RESOLVE_AGAIN = "api_e2e 검토사항 다시 해결"

# 검토사항 계약(review-items BRIEF §5.2·§5.3·§5.5·§5.6). 백엔드 imask_backend.items·reviews 를 쓰지 않고 따로 적는다.
ITEM_KEYS = ("id", "number", "type", "document_index", "page", "finding_id", "title", "desc", "next", "evidence", "link_id")
ITEM_EVIDENCE_KEYS = ("label", "page", "finding_ids", "finding_id")
ITEM_TYPES = {  # 화면 src/display/rules.ts RTYPE 의 키 → 라벨(이력 target '{번호} {라벨}')
    "unreadable": "판독 불가",
    "cutoff": "페이지 잘림",
    "mismatch": "값 불일치",
    "weaklink": "연결 근거 부족",
    "nolocation": "위치 확인 필요",
    "failed": "분석 실패",
    "format": "형식 오류",
    "duplicate": "같은 서식 여러 건",
    "missing": "필수 항목 없음",
    "lowconf": "인식 확인 필요",
    "other": "기타 서류",
    "maskscope": "가림 범위 확인",
    "linkage": "서류 간 정보 결합",
    "reident": "재식별 위험",
}
REVIEW_ITEM_KEYS = {"resolved", "note", "resolved_at", "resolved_by"}
ITEM_MAX_EVIDENCE = 20  # 검토사항 하나의 근거 수(lowconf 는 앞 20쪽)
ITEM_MAX_NAME = 40  # 글에 넣는 표시 이름(코드 포인트) — 넘으면 앞 39자 + '…'
ITEM_MAX_NUMS = 5  # lowconf 설명의 표시 번호 수
ITEM_NOLOCATION = ("원문 위치가 없는 탐지 항목", "{num} {name} — 원문 좌표가 없어 강조할 수 없습니다.", "원본에서 직접 찾아 확인해 주세요.")
ITEM_LOWCONF = ("인식 신뢰도가 낮은 항목 {n}건", "{nums}의 값이 틀렸을 수 있습니다.", "원본과 값을 비교해 확인해 주세요.")
ITEM_OTHER = (
    "기타 서류로 분류된 문서",
    "워크플로우가 지원 서류 종류에 해당하지 않는 기타 서류로 분류했습니다.",
    "원본에 개인정보가 있는지 직접 확인해 주세요.",
)
ITEM_OPEN_LABEL = "{p}쪽 열기"
ITEM_VALUES_LABEL = "{p}쪽 값 보기"
MSG_ITEM_NOT_FOUND = "검토사항을 찾을 수 없습니다."
MSG_ITEM_STATE_CHANGED = "검토사항 상태가 바뀌었습니다. 새로 고친 뒤 다시 시도해 주세요."
LINK_MISMATCH_ID = re.compile(r"mismatch:[0-9]+:[0-9]+")  # 연결 항목인 mismatch 의 id 꼴(설정 60 의 규칙 mismatch 는 연결이 아니다)
V2_OWN_ITEMS = ("nolocation:", "lowconf:", "other:")  # 설정 60 에서 기대값을 따로 계산해 비교하는 항목의 id 머리

# 최종 흐름 워크플로우 결과 계약(final-flow T3 A — links·decision·bundle_check). 백엔드 함수를 쓰지 않고 따로 적는다.
# 옛 워크플로우(묶음_검증 없음)는 links [] · decision null · bundle_check null.
LINK_KEYS = ("id", "number", "status", "state", "title", "field", "label", "docs", "basis", "missing", "check")
LINK_DOC_KEYS = ("document_index", "page", "fields", "finding_ids")
LINK_STATUS = {"linked": "confirmed", "unmatched": "check", "insufficient": "check"}  # state → status
LINK_STATES = tuple(LINK_STATUS)
LINK_MAX_FIELDS = 80  # docs[].fields(코드 포인트)
LINK_NEXT = "같은 고객의 서류인지 원본에서 확인해 주세요."
LINK_TEXT = {  # state → (basis, missing, check) — {label}{p} = 이름표(40 코드 포인트)·주격 조사
    "linked": (("두 서류의 {label}{p} 같습니다.",), "", "두 서류를 함께 보관·전달할 때 열람 권한을 확인해 주세요."),
    "unmatched": ((), "두 서류의 {label}{p} 다릅니다.", LINK_NEXT),
    "insufficient": ((), "비교할 {label}{p} 없습니다.", LINK_NEXT),
}
# 설정 60 지급보증거래 신청서 쌍(대상 서류 분류 코드 — 신청인 성명에 본인 성명이 들어 있는지로 비교)의 linked·unmatched 글
LINK_GUARANTEE_TYPE = "지급보증거래_신청서"
LINK_GUARANTEE_TEXT = {
    "linked": (("신청인 성명에 본인 성명이 들어 있습니다.",), "", LINK_TEXT["linked"][2]),
    "unmatched": ((), "신청인 성명에 본인 성명이 들어 있지 않습니다.", LINK_NEXT),
}
# 가린 이름이라 비교하지 않은 쌍(insufficient)의 글. 백엔드 계약(items.link_pairs·bundle_parts): links[] 의 insufficient 쌍 중 가린 이름이 아닌
# 쌍은 늘 검토사항 weaklink:<기준>:<대상> 을 만들고 가린 이름 쌍은 만들지 않는다 — 그래서 weaklink 가 있는 쌍·대상이 위임장_상속 인 쌍은 기본 글만,
# weaklink 가 없는 insufficient 쌍은 이 글만 받는다. result.items 가 목록이 아니면(가를 근거가 없다) 둘 다 받는다.
LINK_MASKED_TEXT = ((), "이름이 가려져 있어 비교할 수 없습니다.", LINK_NEXT)
LINK_ATTORNEY_TYPE = "위임장_상속"  # 비교할 본인 칸이 없어 늘 기본 근거 부족(가린 이름일 수 없다)
# v6 결합_확인 두 규칙 → bundle_check label(칸 이름이 아니라 사유 이름 — field 는 null). 이 정확한 대응만 'field null → label null' 의 예외다
LINKAGE_RULE_LABELS = {"가린이름_연락처_결합_없음": "서류 간 정보 결합", "가린이름_식별정보_없음": "재식별 위험"}
DECISION_KEYS = ("risk_level", "document_types", "sensitive_categories", "review_reasons", "reason")
DECISION_LIST_KEYS = ("document_types", "sensitive_categories", "review_reasons")
DECISION_RISKS = ("상", "중", "하", "검토 필요")
V2_DECISION_KEYS = (
    "risk_level",
    "document_types",
    "high_risk_items",
    "medium_risk_items",
    "low_risk_items",
    "review_reasons",
    "recommended_action",
    "reason",
)
V2_DECISION_LIST_KEYS = ("document_types", "high_risk_items", "medium_risk_items", "low_risk_items", "review_reasons")
BUNDLE_KEYS = ("verdict", "checks")
BUNDLE_CHECK_KEYS = ("id", "name", "severity", "status", "field", "label", "group")
BUNDLE_VERDICTS = ("green", "yellow", "red")
BUNDLE_SEVERITIES = ("error", "warning")
BUNDLE_STATUSES = ("pass", "fail", "absent", "unknown")

# 내보내기 기록 계약(log_export — live-report BRIEF §5.6·§5.8 백엔드 문구). 백엔드 함수를 쓰지 않고 따로 적는다.
EXPORT_KIND = "export"
EXPORT_REASON = "민감한 값 마스킹"
EXPORT_SUFFIXES = {"csv": "_검토결과_탐지항목.csv", "json": "_검토결과.json"}
EXPORT_STATES = {"handed": "다운로드 요청", "saved": "저장 완료"}
EXPORT_CSV_SIZE = 6_127  # 그럴듯한 CSV 크기 → '6KB'
EXPORT_JSON_SIZE = 1_310_720  # MB 소수 첫째 자리 동점(1.25) → JS toFixed '1.3MB'(파이썬 round·format 이면 '1.2MB')
SEOUL = timezone(timedelta(hours=9))  # 분석 번호의 날짜 기준(서울 = UTC+9 고정)

# 공유 목록·삭제·다시 분석 계약(shared-analyses — BRIEF §5.2~5.5, §5.8 백엔드 문구)
LIST_PATH = "/api/py/analyses"
LIST_ITEM_KEYS = {"id", "name", "status", "error", "created_at", "updated_at", "started_at", "documents", "risk_level", "review", "document_count"}
LIST_DOC_KEYS = {"filename", "size_bytes", "mime_type"}
MSG_NOT_FOUND = "분석 건을 찾을 수 없습니다."
MSG_FILE_MISSING = "업로드된 파일을 찾을 수 없습니다. 파일을 다시 올려 주세요."
MSG_BUSY = "이미 분석하고 있습니다."
RETRY_KIND = "retry"
RETRY_CHANGE = "같은 파일로 다시 분석 요청"
REASON_MAX = 500  # 이력 reason 저장 한도(코드 포인트)
NO_JOB_STATUSES = {400, 404, 409, 413}  # /start·/retry 가 작업을 만들지 않고 거절하는 상태(BRIEF §5.4 — Upstage 를 부르지 않음)

EXIT_OK = 0
EXIT_FAIL = 1

_SECRETS: dict[str, str] = {}


def _setup_console() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace", line_buffering=True)


def _say(text: str = "") -> None:
    """모든 출력의 유일한 길 — 알려진 비밀값·서명 토큰·인증 문구를 가린다."""
    print(redact(text, _SECRETS))


def _hide(value: str | None, placeholder: str) -> None:
    if isinstance(value, str) and len(value) >= 4:
        _SECRETS[value] = placeholder


def _read_env() -> dict[str, str]:
    """루트 .env(있으면)를 읽는다. 값은 출력하지 않는다."""
    path = ROOT / ".env"
    if not path.is_file():
        return {}
    try:
        from dotenv import dotenv_values
    except ImportError:  # pragma: no cover - requirements-dev.txt 에 있다
        return {}
    return {k: v for k, v in dotenv_values(path).items() if isinstance(v, str)}


class Run:
    """한 번 실행의 상태. 정리(finally)에 쓰도록 분석 id·관찰한 Upstage file id 를 모은다."""

    def __init__(self, args: argparse.Namespace, env: Mapping[str, str], transport: httpx.BaseTransport | None = None):
        self.args = args
        self.env = env
        self.transport = transport  # 원본 파일 받기(사용자 지정 헤더 없는 클라이언트)도 같은 전송층을 쓴다(테스트)
        self.start = time.monotonic()
        headers: dict[str, str] = {}
        bypass = os.environ.get("VERCEL_PROTECTION_BYPASS")
        if bypass:
            _hide(bypass, "<VERCEL_PROTECTION_BYPASS>")
            headers["x-vercel-protection-bypass"] = bypass
        for name in ("UPSTAGE_API_KEY", "SUPABASE_SECRET_KEY", "NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY"):
            _hide(env.get(name), f"<{name}>")
        _hide(os.environ.get("UPSTAGE_API_KEY"), "<UPSTAGE_API_KEY>")
        _hide(env.get("UPSTAGE_AGENT_ID"), "<UPSTAGE_AGENT_ID>")
        self.http = httpx.Client(
            base_url=args.base_url.rstrip("/"),
            headers=headers,
            timeout=httpx.Timeout(90.0, connect=10.0),
            transport=transport,
        )
        # 정리용 실행 상태
        self.analysis_id: str | None = None
        self.start_requested = False
        self.start_row_received = False
        self.start_pending = False  # /start·/retry 를 보냈는데 응답을 아직 관찰하지 못함(작업이 생겼을 수 있음)
        self.terminal = False
        self.file_ids: dict[str, None] = {}  # 순서 있는 집합
        # 끝에 지울 분석(이번 실행이 만든 것만) — --keep·--fail-with-original 이면 남긴다
        self.created = False
        self.deleted = False
        self.keep = bool(getattr(args, "keep", False) or getattr(args, "fail_with_original", False))
        self.verdicts: list[tuple[str, bool, bool]] = []  # (확인 묶음 이름, 통과, 새 확인인지)

    def verdict(self, name: str, passed: bool, *, new: bool = False) -> bool:
        self.verdicts.append((name, passed, new))
        return passed

    def log(self, message: str) -> None:
        _say(f"[{time.monotonic() - self.start:6.1f}s] {message}")

    def call(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        response = self.http.request(method, path, **kwargs)
        return response

    def observe(self, row: Mapping[str, Any]) -> None:
        """응답의 분석 건에서 Upstage file id 와 끝났는지를 기억한다(documents 모양이 틀려도 정상 항목의 file id 만 모은다)."""
        for doc in _documents(row):
            file_id = doc.get("upstage_file_id")
            if isinstance(file_id, str) and file_id:
                self.file_ids[file_id] = None
        self.terminal = row.get("status") in TERMINAL

    def begin_start(self) -> None:
        """작업을 만들 수 있는 요청(/start · /retry)을 보내기 직전 — 응답을 관찰하기 전에는 앞의 끝남 값을 믿지 않는다.

        응답을 잃으면(시간 초과·연결 오류·Ctrl+C·5xx) 정리 단계가 그 분석을 다시 읽어 새 file id 를 모은다(모은 것은 유지)."""
        self.start_requested = True
        self.start_pending = True

    def settle_start(self, status_code: int, body: Any) -> None:
        """/start · /retry 응답을 받은 뒤: 200 분석 건이면 관찰, 작업을 만들지 않는 거절(400·404·409·413)이면 미확인을 푼다.
        그 밖(5xx·모양이 틀린 200)은 미확인 그대로 둔다 — 서버가 작업을 만들었을 수 있다."""
        if status_code == 200 and isinstance(body, Mapping):
            self.observe(body)
            self.start_pending = False
        elif status_code in NO_JOB_STATUSES:
            self.start_pending = False

    def upstage_key(self) -> str:
        return os.environ.get("UPSTAGE_API_KEY") or self.env.get("UPSTAGE_API_KEY") or ""

    def upstage_base(self) -> str:
        return self.env.get("UPSTAGE_BASE_URL") or "https://api.upstage.ai/v2"

    def upstage_project(self) -> str | None:
        """에이전트가 속한 Upstage 프로젝트(x-project-id) — 서버가 그 프로젝트에 올린 파일을 확인·정리하려면 같아야 한다."""
        value = os.environ.get("UPSTAGE_PROJECT_ID") or self.env.get("UPSTAGE_PROJECT_ID") or ""
        return value.strip() or None


def _short(text: Any) -> str:
    """원문 전체를 가린 **뒤에** 200자로 자른다(잘린 비밀값·토큰 조각이 남지 않게)."""
    return redact(text, _SECRETS, limit=200)


def _detail(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return _short(response.text)
    return _short(body.get("detail") if isinstance(body, dict) else body)


def _upload(run: Run, upload: Mapping[str, str], content: bytes, mime_type: str) -> bool:
    """서명 URL 로 올린다(브라우저 방식). 서명 URL·토큰은 출력하지 않는다."""
    _hide(upload.get("token"), "<SIGNED_TOKEN>")
    _hide(upload.get("signed_url"), "<SIGNED_URL>")
    url = run.env.get("NEXT_PUBLIC_SUPABASE_URL")
    key = run.env.get("NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY")
    try:
        if url and key:
            from supabase import create_client

            client = create_client(url, key)
            client.storage.from_(upload["bucket"]).upload_to_signed_url(
                upload["path"], upload["token"], content, {"content-type": mime_type}
            )
            run.log(f"올리기 완료(공개 키 + 서명 토큰, uploadToSignedUrl 과 같은 방식): {upload['path']}")
        else:
            name = upload["path"].rsplit("/", 1)[-1]
            response = httpx.put(
                upload["signed_url"],
                files={"file": (name, content, mime_type)},
                data={"cacheControl": "3600"},
                timeout=60.0,
            )
            if not response.is_success:
                run.log(f"올리기 실패: HTTP {response.status_code} {_detail(response)}")
                return False
            run.log(f"올리기 완료(서명 URL 에 직접 PUT): {upload['path']}")
        return True
    except Exception as exc:  # 오류 문구는 원문 전체를 가린 뒤 한 줄로
        run.log(f"올리기 실패: {_short(f'{type(exc).__name__}: {exc}')}")
        return False


def _known_shape(documents: Any, kinds: Mapping[str, Any]) -> dict[str, Any] | None:
    """서류 수 · kind 분포가 알려진 모양(EXPECTED_SHAPES) 중 하나와 같으면 그 모양, 아니면 None."""
    for shape in EXPECTED_SHAPES:
        if _is_int(documents) and documents == shape["documents"] and dict(kinds) == shape["kinds"]:
            return shape
    return None


def _summary_ok(summary: Mapping[str, Any]) -> bool:
    count, extracted = summary.get("document_count"), summary.get("extracted_document_count")
    return (
        any(
            _is_int(count) and _is_int(extracted) and (count, extracted) == (s["documents"], s["kinds"]["extracted"])
            for s in EXPECTED_SHAPES
        )
        and summary.get("risk_level") == EXPECTED_RISK
    )


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


REVIEW_STATUSES = ("needed", "done")  # review.status 계약 값(출력해도 되는 받은 글자)


def _shown(value: Any, allowed: tuple[str, ...] = ()) -> str:
    """받은 값을 문제 줄에 적을 때 — None·bool·정수(bool 아님)·허용 목록의 글자만 repr 로, 그 밖은 '<타입 이름>'(값은 넣지 않는다)."""
    if value is None or isinstance(value, bool) or _is_int(value) or (isinstance(value, str) and value in allowed):
        return repr(value)
    return f"<{type(value).__name__}>"


def _plain(value: Any, allowed: tuple[str, ...] = ()) -> str:
    """_shown 과 같되 허용 글자는 따옴표 없이(요약 줄용)."""
    return value if isinstance(value, str) and value in allowed else _shown(value, allowed)


def _box_ok(box: Any) -> bool:
    if not isinstance(box, list) or len(box) != 4:
        return False
    for point in box:
        if not isinstance(point, Mapping) or set(point) != {"x", "y"}:
            return False
        for v in point.values():
            if not isinstance(v, (int, float)) or isinstance(v, bool) or not 0.0 <= v <= 1.0:
                return False
    return True


def _finding_problems(f: Any, doc_indexes: set[Any]) -> list[str]:
    """탐지 항목 하나의 계약 위반(값은 넣지 않고 id·키 이름만)."""
    if not isinstance(f, Mapping):
        return ["finding: 객체가 아님"]
    where = f"finding {str(f.get('id'))[:60]}"
    if set(f) != FINDING_KEYS:
        return [f"{where}: 키가 계약과 다름 {sorted(set(f) ^ FINDING_KEYS)}"]
    value, shown = f["value"], f["masked"]
    checks = [
        (f["id"] == f"{f['document_index']}:{f['field']}", "id 꼴"),
        (f["document_index"] in doc_indexes, "document_index 가 documents 에 없음"),
        (f["category"] in CATS, "category"),
        (f["subject"] in SUBJECTS, "subject"),
        (f["mapping_status"] in ("ok", "needs_review", "unknown"), "mapping_status"),
        (isinstance(value, str) and bool(value.strip()), "value"),
        (isinstance(shown, str) and isinstance(value, str) and len(shown) == len(value), "masked 길이"),
        (f["exposure"] in EXPOSURES, "exposure"),
        (f["risk"] in RISKS, "risk"),
        ((f["risk"] == "unrated") == (f["risk_source"] is None), "risk 와 risk_source"),
        (f["risk_source"] in ("workflow", None), "risk_source"),
        (f["risk_reason"] is None or isinstance(f["risk_reason"], str), "risk_reason"),
        (f["page"] is None or (_is_int(f["page"]) and f["page"] >= 1), "page"),
        (isinstance(f["boxes"], list) and all(_box_ok(b) for b in f["boxes"]), "boxes 0~1"),
        (f["page"] is not None or f["boxes"] == [], "page 없는데 boxes 있음"),
        (f["confidence"] in ("high", "low", None), "confidence"),
    ]
    return [f"{where}: {name}" for passed, name in checks if not passed]


def _document_problems(doc: Any) -> list[str]:
    if not isinstance(doc, Mapping) or set(doc) != DOCUMENT_KEYS:
        diff = sorted(set(doc) ^ DOCUMENT_KEYS) if isinstance(doc, Mapping) else "객체가 아님"
        return [f"document: 키가 계약과 다름 {diff}"]
    where = f"document {str(doc.get('index'))[:20]}"
    start, end = doc["page_start"], doc["page_end"]
    checks = [
        (_is_int(doc["index"]), "index"),
        (doc["kind"] in ("extracted", "other"), "kind"),
        ((start is None and end is None) or (_is_int(start) and _is_int(end) and 1 <= start <= end), "page_start·page_end"),
        (all(doc[k] is None or isinstance(doc[k], str) for k in ("type", "other_guide", "validation")), "type·other_guide·validation"),
    ]
    return [f"{where}: {name}" for passed, name in checks if not passed]


def _view_problems(result: Mapping[str, Any]) -> list[str]:
    """documents·findings·overall 의 계약 위반 목록(값 없이 위치·키 이름만)."""
    documents, findings, overall = result.get("documents"), result.get("findings"), result.get("overall")
    if not isinstance(documents, list) or not isinstance(findings, list) or not isinstance(overall, Mapping):
        return ["documents·findings·overall 모양이 다름"]
    problems = [p for doc in documents for p in _document_problems(doc)]
    indexes = [d.get("index") for d in documents if isinstance(d, Mapping)]
    if len(set(map(str, indexes))) != len(indexes):
        problems.append("document index 가 겹침")
    doc_indexes = {i for i in indexes if _is_int(i)}
    problems += [p for finding in findings for p in _finding_problems(finding, doc_indexes)]
    ids = [str(f.get("id")) for f in findings if isinstance(f, Mapping)]
    if len(set(ids)) != len(ids):
        problems.append("finding id 가 겹침")
    if set(overall) != OVERALL_KEYS:
        problems.append(f"overall: 키가 계약과 다름 {sorted(set(overall) ^ OVERALL_KEYS)}")
        return problems
    if overall["level"] not in ("상", "중", "하", "검토 필요", None):
        problems.append("overall.level")
    if overall["next_stage"] not in ("권장_조치", "검토_안내", None):
        problems.append("overall.next_stage")
    if not isinstance(overall["text"], str) or not isinstance(overall["next_text"], str):
        problems.append("overall.text·next_text")
    return problems


def _mark(passed: bool) -> str:
    return "일치" if passed else "불일치"


def _get(run: Run, analysis_id: str, params: Mapping[str, str] | None = None) -> tuple[httpx.Response, Any]:
    response = run.call("GET", f"/api/py/analyses/{analysis_id}", params=params)
    try:
        body = response.json()
    except ValueError:
        body = None
    return response, body


def _print_summary(result: Mapping[str, Any]) -> bool:
    summary = result.get("summary") if isinstance(result.get("summary"), Mapping) else {}
    no_raw = "response" not in result and "stages" not in result
    _say(f"결과 형식: {result.get('format')} · 키 {sorted(result)}(response·stages 없음: {no_raw})")
    _say(f"  서류 수: {summary.get('document_count')}")
    _say(f"  서류 종류: {summary.get('document_types')}")
    _say(f"  추출된 서류 수: {summary.get('extracted_document_count')}")
    _say(f"  위험도: {summary.get('risk_level')}")
    _say(f"  마지막 단계: {summary.get('final_stage')}")
    _say(f"  기타 서류 수: {summary.get('other_document_count')}")
    _say(f"  단계 이름: {summary.get('stage_names')}")
    if _is_v2(result):
        _say("  설정 60 응답 — 합성 묶음 기대값을 보지 않고 계약 모양만 봄")
        return no_raw
    expected = _summary_ok(summary)
    pairs = " 또는 ".join(f"{s['documents']}·{s['kinds']['extracted']}" for s in EXPECTED_SHAPES)
    _say(f"  기대값(서류·추출 {pairs} · 위험도 {EXPECTED_RISK}): {_mark(expected)}")
    return expected and no_raw


def _print_view(result: Mapping[str, Any]) -> bool:
    """화면용 결과의 개수·분포만 출력한다(value·masked·본문은 출력하지 않음)."""
    if _is_v2(result):
        return _print_view_v2(result)
    documents = [d for d in result.get("documents") or [] if isinstance(d, Mapping)]
    findings = [f for f in result.get("findings") or [] if isinstance(f, Mapping)]
    overall = result.get("overall") if isinstance(result.get("overall"), Mapping) else {}
    others = [d for d in documents if d.get("kind") == "other"]
    extracted = [d for d in documents if d.get("kind") == "extracted"]
    kinds = dict(Counter(str(d.get("kind")) for d in documents))
    guides = sum(1 for d in others if d.get("other_guide"))
    validations = sum(1 for d in extracted if d.get("validation"))
    shape = _known_shape(len(documents), kinds)
    # 추출 서류마다 validation 은 옛 워크플로우(bundle_check null)만 — 최종 흐름은 검증이 묶음 하나(bundle_check verdict, _print_final)
    final = _is_final(result)
    docs_ok = shape is not None and guides == len(others) and (final or validations == len(extracted))
    boxed = sum(1 for f in findings if f.get("boxes"))
    # 탐지 수 · 위치 있는 항목 수는 서류 모양과 **같은 모양**의 값이어야 한다(모양을 섞지 않는다)
    counts_ok = shape is not None and len(findings) == shape["findings"] and boxed == shape["boxed"]
    want = f"{shape['findings']} · {shape['boxed']}" if shape else "알려진 모양 없음"
    overall_ok = overall.get("level") == EXPECTED_RISK and overall.get("next_stage") == EXPECTED_NEXT_STAGE
    text, next_text = overall.get("text"), overall.get("next_text")
    _say("화면용 결과(documents·findings·overall):")
    _say(
        f"  documents: {len(documents)} · kind {kinds} · other_guide 있음 {guides}/{len(others)}"
        f" · validation 있음 {validations}/{len(extracted)}{'(최종 흐름 — 묶음 검증으로 봄)' if final else ''}"
        f" (알려진 모양: {shape['name'] if shape else '없음'}): {_mark(docs_ok)}"
    )
    _say(f"  findings: {len(findings)} · boxes 있는 항목 {boxed} (기대 {want}): {_mark(counts_ok)}")
    _say(f"  risk 분포: {dict(Counter(str(f.get('risk')) for f in findings))}")
    _say(f"  risk_source 분포: {dict(Counter(str(f.get('risk_source')) for f in findings))}")
    _say(f"  exposure 분포: {dict(Counter(str(f.get('exposure')) for f in findings))}")
    _say(f"  mapping_status 분포: {dict(Counter(str(f.get('mapping_status')) for f in findings))}")
    _say(f"  confidence 분포: {dict(Counter(str(f.get('confidence')) for f in findings))}")
    _say(f"  서류별 항목 수: {dict(Counter(f.get('document_index') for f in findings))}")
    _say(
        f"  overall: level={overall.get('level')} · next_stage={overall.get('next_stage')}"
        f" · text {len(text) if isinstance(text, str) else '?'}자 · next_text {len(next_text) if isinstance(next_text, str) else '?'}자"
        f" (기대 {EXPECTED_RISK} · {EXPECTED_NEXT_STAGE}): {_mark(overall_ok)}"
    )
    problems = _view_problems(result)
    _say(f"  계약 모양(키·허용 값·id 중복·document_index·boxes 0~1): {'맞음' if not problems else f'문제 {len(problems)}개'}")
    for problem in problems[:10]:
        _say(f"    - {_short(problem)}")
    return docs_ok and counts_ok and overall_ok and not problems


def _print_view_v2(result: Mapping[str, Any]) -> bool:
    """설정 60 응답의 화면용 결과 — 개수·분포 + 계약 모양(고정 기대값 없음). overall 은 decision 과 같은지 본다."""
    documents = [d for d in result.get("documents") or [] if isinstance(d, Mapping)]
    findings = [f for f in result.get("findings") or [] if isinstance(f, Mapping)]
    overall = result.get("overall") if isinstance(result.get("overall"), Mapping) else {}
    decision = result.get("decision") if isinstance(result.get("decision"), Mapping) else {}
    level = decision.get("risk_level")
    want_next = "검토_안내" if level == "검토 필요" else "권장_조치" if level in DECISION_RISKS else None
    same = overall.get("level") == level and overall.get("next_stage") == want_next
    _say("화면용 결과(documents·findings·overall):")
    _say(f"  documents: {len(documents)} · kind {dict(Counter(str(d.get('kind')) for d in documents))}")
    _say(f"  findings: {len(findings)} · boxes 있는 항목 {sum(1 for f in findings if f.get('boxes'))}")
    _say(f"  risk 분포: {dict(Counter(str(f.get('risk')) for f in findings))}")
    _say(f"  risk_source 분포: {dict(Counter(str(f.get('risk_source')) for f in findings))}")
    _say(f"  exposure 분포: {dict(Counter(str(f.get('exposure')) for f in findings))}")
    _say(f"  mapping_status 분포: {dict(Counter(str(f.get('mapping_status')) for f in findings))}")
    _say(f"  confidence 분포: {dict(Counter(str(f.get('confidence')) for f in findings))}")
    _say(f"  overall: level={_kind(overall.get('level'), DECISION_RISKS)} · next_stage={_kind(overall.get('next_stage'), ('권장_조치', '검토_안내'))} · decision 과 같음: {_mark(same)}")
    problems = _view_problems(result)
    _say(f"  계약 모양(키·허용 값·id 중복·document_index·boxes 0~1): {'맞음' if not problems else f'문제 {len(problems)}개'}")
    for problem in problems[:10]:
        _say(f"    - {_short(problem)}")
    return same and not problems


# --- 최종 흐름 결과(links·decision·bundle_check) 확인 — final-flow T3 A ----------------------------------
# 계약 모양은 따로 적어 확인한다(백엔드 imask_backend.items·findings 를 쓰지 않음). 출력은 개수·상태·키 이름만 —
# 연결 제목·fields·판정 글·규칙 이름 같은 받은 글자는 출력하지 않는다(허용 목록의 상태 글자만).


FINAL_RESULT_KEYS = ("links", "decision", "bundle_check")  # 조회 응답 result 에 늘 있어야 하는 키(값은 null·[] 일 수 있음)
LINK_STATUSES = tuple(dict.fromkeys(LINK_STATUS.values()))  # confirmed · check


def _kind(value: Any, allowed: tuple[str, ...] = ()) -> str:
    """최종 흐름 진단 출력용 — 허용 목록의 enum 글자만 그대로, null 은 'null', 그 밖(숫자·bool·객체·목록·모르는 글자)은
    값 없는 타입 표기 '<int>'·'<bool>'·'<str>' …(받은 값은 어떤 꼴이든 출력하지 않는다)."""
    if isinstance(value, str) and value in allowed:
        return value
    return "null" if value is None else f"<{type(value).__name__}>"


def _is_final(result: Mapping[str, Any]) -> bool:
    """최종 흐름 워크플로우 결과인지 — bundle_check 가 객체(묶음_검증 단계가 있음). 옛 워크플로우는 null."""
    return isinstance(result.get("bundle_check"), Mapping)


def _is_v2(result: Any) -> bool:
    """설정 60(v2_full) 응답인지 — decision 에 high_risk_items 키가 있음. 고정 기대값 대신 계약 모양만 본다."""
    decision = result.get("decision") if isinstance(result, Mapping) else None
    return isinstance(decision, Mapping) and "high_risk_items" in decision


def _result_shape(result: Mapping[str, Any]) -> dict[str, Any] | None:
    """화면용 결과의 서류 수 · kind 분포가 알려진 모양(EXPECTED_SHAPES) 중 하나면 그 모양."""
    documents = [d for d in result.get("documents") or [] if isinstance(d, Mapping)]
    return _known_shape(len(documents), dict(Counter(str(d.get("kind")) for d in documents)))


def _particle(label: str) -> str:
    """주격 조사(T3 글의 {P}) — 마지막 글자가 한글 음절이면 받침 있음 '이'·없음 '가', 그 밖(영문·숫자·'…' 등) '이(가)'."""
    last = ord(label[-1]) if label else 0
    if 0xAC00 <= last <= 0xD7A3:
        return "이" if (last - 0xAC00) % 28 else "가"
    return "이(가)"


def _own_finding_ids(result: Mapping[str, Any], spans: Mapping[int, Any]) -> dict[int, set[str]]:
    """보이는 서류마다 그 서류의 탐지 항목 id(문자열만)."""
    own: dict[int, set[str]] = {index: set() for index in spans}
    findings = result.get("findings")
    for f in findings if isinstance(findings, list) else []:
        index = f.get("document_index") if isinstance(f, Mapping) else None
        if _is_int(index) and index in own and isinstance(f.get("id"), str):
            own[index].add(f["id"])
    return own


def _linkage_rule_label(check: Mapping[str, Any]) -> bool:
    """bundle_check 규칙이 v6 결합_확인 두 규칙 중 하나이고 field null · label 이 그 규칙의 사유 이름인지."""
    name = check.get("name")
    return (
        check.get("group") == "결합_확인"
        and check.get("field") is None
        and isinstance(name, str)
        and name in LINKAGE_RULE_LABELS
        and check.get("label") == LINKAGE_RULE_LABELS[name]
    )


def _link_problems(links: Any, result: Mapping[str, Any]) -> list[str]:
    """result.links 의 계약 모양(값은 출력하지 않고 'links[n].키' 위치만): 키·순서, L-nn 1부터 연속, id 겹치지 않음·
    'link:<기준>:<대상>', state→status, 두 서류가 보이는 서류(기준 서류는 모두 같음)·쪽이 그 서류 범위 안·finding_ids 가 그 서류의
    탐지 항목(0~1개)·fields 1~80 코드 포인트, 글(basis·missing·check)이 state 의 고정 문구 + 이름표(label 40자)·조사와 정확히 같음."""
    if not isinstance(links, list):
        return ["result.links 가 목록이 아님"]
    spans = {d["index"]: (d["page_start"], max(d["page_start"], d["page_end"])) for d in _visible_docs(result.get("documents"))}
    doc_types = {d["index"]: d.get("type") for d in _visible_docs(result.get("documents"))}
    result_items = result.get("items")
    weak_ids = (
        {i.get("id") for i in result_items if isinstance(i, Mapping) and i.get("type") == "weaklink"} if isinstance(result_items, list) else None
    )
    own = _own_finding_ids(result, spans)
    problems: list[str] = []
    anchors: set[int] = set()
    for n, link in enumerate(links):
        where = f"links[{n}]"
        if not isinstance(link, Mapping) or list(link) != list(LINK_KEYS):
            problems.append(f"{where}: 키·순서가 계약과 다름")
            continue
        state, label, basis = link["state"], link["label"], link["basis"]
        known = isinstance(state, str) and state in LINK_STATUS
        checks = [
            (known and link["status"] == LINK_STATUS[state], "state·status"),
            (all(isinstance(link[k], str) and link[k] != "" for k in ("title", "field", "label", "check")), "title·field·label·check"),
            (isinstance(link["missing"], str), "missing"),
            (isinstance(basis, list) and all(isinstance(b, str) for b in basis), "basis"),
        ]
        if known and isinstance(label, str) and label:
            name = _clip_name(label)
            fill = {"label": name, "p": _particle(name)}
            target = link["docs"][1] if isinstance(link["docs"], list) and len(link["docs"]) == 2 else None
            target_index = target.get("document_index") if isinstance(target, Mapping) else None
            guarantee = _is_int(target_index) and doc_types.get(target_index) == LINK_GUARANTEE_TYPE
            wants = [LINK_GUARANTEE_TEXT[state] if guarantee and state in LINK_GUARANTEE_TEXT else LINK_TEXT[state]]
            if state == "insufficient":
                weak = weak_ids is not None and isinstance(link["id"], str) and ("weak" + link["id"]) in weak_ids  # link:<a>:<t> → weaklink:<a>:<t>
                attorney = _is_int(target_index) and doc_types.get(target_index) == LINK_ATTORNEY_TYPE
                if weak_ids is None:
                    wants.append(LINK_MASKED_TEXT)  # items 를 읽을 수 없다 — 가림 여부를 가를 근거가 없어 둘 다
                elif not (weak or attorney):
                    wants = [LINK_MASKED_TEXT]  # weaklink 가 없는 근거 부족 = 가린 이름 쌍
            same = any(
                basis == [b.format(**fill) for b in want_basis]
                and link["missing"] == want_missing.format(**fill)
                and link["check"] == want_check
                for want_basis, want_missing, want_check in wants
            )
            checks.append((same, "글(basis·missing·check)"))
        docs, indexes = link["docs"], []
        if not isinstance(docs, list) or len(docs) != 2:
            checks.append((False, "docs(서류 2개)"))
            docs = []
        for m, doc in enumerate(docs):
            at = f"docs[{m}]"
            if not isinstance(doc, Mapping) or list(doc) != list(LINK_DOC_KEYS):
                checks.append((False, f"{at}: 키·순서"))
                continue
            index, ids, fields = doc["document_index"], doc["finding_ids"], doc["fields"]
            visible = _is_int(index) and index in spans
            span, mine = (spans[index], own[index]) if visible else ((0, -1), set())
            checks += [
                (visible, f"{at}.document_index(보이는 서류)"),
                (_is_int(doc["page"]) and span[0] <= doc["page"] <= span[1], f"{at}.page(서류 쪽 범위)"),
                (isinstance(fields, str) and 0 < len(fields) <= LINK_MAX_FIELDS, f"{at}.fields(1~80자)"),
                (
                    isinstance(ids, list) and len(ids) <= 1 and all(isinstance(i, str) and i in mine for i in ids),
                    f"{at}.finding_ids(그 서류의 탐지 항목)",
                ),
            ]
            if visible:
                indexes.append(index)
        if len(indexes) == 2:
            checks.append((indexes[0] != indexes[1] and link["id"] == f"link:{indexes[0]}:{indexes[1]}", "id(link:<기준>:<대상>)"))
            anchors.add(indexes[0])
        problems += [f"{where}.{name}" for passed, name in checks if not passed]
    numbers = [link.get("number") if isinstance(link, Mapping) else None for link in links]
    if numbers != [f"L-{n:02d}" for n in range(1, len(links) + 1)]:
        problems.append("links number 가 L-01 부터 이어지지 않음")
    ids = [link.get("id") for link in links if isinstance(link, Mapping) and isinstance(link.get("id"), str)]
    if len(set(ids)) != len(ids):
        problems.append("links id 가 겹침")
    if len(anchors) > 1:
        problems.append("links 기준 서류가 둘 이상")
    return problems


def _decision_problems(decision: Any) -> list[str]:
    """result.decision — null 또는 위험도_판정 키 5개(순서 그대로)·설정 60 판정 키 8개: risk_level 허용 값·null, 목록 키는 문자열 목록·null,
    reason·recommended_action 글·null."""
    if decision is None:
        return []
    v2 = isinstance(decision, Mapping) and "high_risk_items" in decision
    if not isinstance(decision, Mapping) or list(decision) != list(V2_DECISION_KEYS if v2 else DECISION_KEYS):
        return ["decision: 키·순서가 계약과 다름"]
    checks = [
        (decision["risk_level"] is None or (isinstance(decision["risk_level"], str) and decision["risk_level"] in DECISION_RISKS), "risk_level"),
        (decision["reason"] is None or isinstance(decision["reason"], str), "reason"),
    ]
    if v2:
        checks.append((decision["recommended_action"] is None or isinstance(decision["recommended_action"], str), "recommended_action"))
    for key in V2_DECISION_LIST_KEYS if v2 else DECISION_LIST_KEYS:
        value = decision[key]
        checks.append((value is None or (isinstance(value, list) and all(isinstance(v, str) for v in value)), key))
    return [f"decision.{name}" for passed, name in checks if not passed]


def _bundle_problems(bundle: Any) -> list[str]:
    """result.bundle_check — null 또는 {verdict, checks[키 7개]}: verdict 허용 값·null, 규칙 id·name 글, severity·status 허용 값,
    field·label·group 글·null(field 가 null 이면 label 도 null), 규칙 id 겹치지 않음. 규칙의 서류별 결과(documents)는 없다."""
    if bundle is None:
        return []
    if not isinstance(bundle, Mapping) or list(bundle) != list(BUNDLE_KEYS):
        return ["bundle_check: 키·순서가 계약과 다름"]
    verdict, checks = bundle["verdict"], bundle["checks"]
    problems = [] if verdict is None or (isinstance(verdict, str) and verdict in BUNDLE_VERDICTS) else ["bundle_check.verdict"]
    if not isinstance(checks, list):
        return [*problems, "bundle_check.checks 가 목록이 아님"]
    for n, check in enumerate(checks):
        where = f"bundle_check.checks[{n}]"
        if not isinstance(check, Mapping) or list(check) != list(BUNDLE_CHECK_KEYS):
            problems.append(f"{where}: 키·순서가 계약과 다름")
            continue
        severity, status = check["severity"], check["status"]
        rows = [
            (all(isinstance(check[k], str) and check[k] != "" for k in ("id", "name")), "id·name"),
            (severity is None or (isinstance(severity, str) and severity in BUNDLE_SEVERITIES), "severity"),
            (isinstance(status, str) and status in BUNDLE_STATUSES, "status"),
            (all(check[k] is None or isinstance(check[k], str) for k in ("field", "label", "group")), "field·label·group"),
            (check["field"] is not None or check["label"] is None or _linkage_rule_label(check), "label(field 가 null 이면 null)"),
        ]
        problems += [f"{where}.{name}" for passed, name in rows if not passed]
    ids = [c.get("id") for c in checks if isinstance(c, Mapping) and isinstance(c.get("id"), str)]
    if len(set(ids)) != len(ids):
        problems.append("bundle_check 규칙 id 가 겹침")
    return problems


def _final_problems(result: Mapping[str, Any]) -> list[str]:
    """세 키가 **있는지**(없음 ≠ null) + 있는 키의 계약 모양 + 옛 워크플로우(bundle_check null)면 links [] · decision null."""
    problems = [f"결과 키 {key} 가 없음(null 과 다름)" for key in FINAL_RESULT_KEYS if key not in result]
    if "links" in result:
        problems += _link_problems(result["links"], result)
    if "decision" in result:
        problems += _decision_problems(result["decision"])
    if "bundle_check" in result:
        problems += _bundle_problems(result["bundle_check"])
    if not _is_final(result):
        if "links" in result and result["links"] != []:
            problems.append("옛 워크플로우(bundle_check null)인데 links 가 [] 가 아님")
        if "decision" in result and result["decision"] is not None:
            problems.append("옛 워크플로우(bundle_check null)인데 decision 이 null 이 아님")
    return problems


def _print_final(result: Mapping[str, Any]) -> bool:
    """links·decision·bundle_check — 계약 모양, 최종 흐름이면 묶음 검증 verdict 가 있고 알려진 모양(연결 수·모두 linked·verdict)과
    같음. 출력은 개수·상태 분포·키 이름만 — 받은 값은 허용 enum 글자만 그대로, 그 밖은 _kind 의 타입 표기(값 없음).
    개수·길이는 목록·문자열임을 확인한 값에서만 센다."""
    links, decision, bundle = result.get("links"), result.get("decision"), result.get("bundle_check")
    final = _is_final(result)
    rows = [link for link in links if isinstance(link, Mapping)] if isinstance(links, list) else []
    _say("최종 흐름 결과(links·decision·bundle_check):")
    _say(f"  워크플로우: {'최종 흐름(bundle_check 있음)' if final else '옛 워크플로우(bundle_check null)'}")
    absent = [key for key in FINAL_RESULT_KEYS if key not in result]
    if absent:
        _say(f"  결과 키 없음: {absent}")
    states = dict(Counter(_kind(link.get("state"), LINK_STATES) for link in rows))
    statuses = dict(Counter(_kind(link.get("status"), LINK_STATUSES) for link in rows))
    _say(f"  links: {len(rows) if isinstance(links, list) else _kind(links)} · state {states} · status {statuses}")
    if isinstance(decision, Mapping):
        reason = decision.get("reason")
        parts = [f"risk_level={_kind(decision.get('risk_level'), DECISION_RISKS)}"]
        for key in V2_DECISION_LIST_KEYS if _is_v2(result) else DECISION_LIST_KEYS:
            value = decision.get(key)
            parts.append(f"{key} {len(value)}개" if isinstance(value, list) else f"{key} {_kind(value)}")
        parts.append(f"reason {len(reason)}자" if isinstance(reason, str) else f"reason {_kind(reason)}")
        _say(f"  decision: {' · '.join(parts)}")
    else:
        _say(f"  decision: {_kind(decision)}")
    verdict = bundle.get("verdict") if isinstance(bundle, Mapping) else None
    if isinstance(bundle, Mapping):
        raw_checks = bundle.get("checks")
        checks = [c for c in raw_checks if isinstance(c, Mapping)] if isinstance(raw_checks, list) else []
        check_states = dict(Counter(_kind(c.get("status"), BUNDLE_STATUSES) for c in checks))
        severities = dict(Counter(_kind(c.get("severity"), BUNDLE_SEVERITIES) for c in checks))
        count = len(checks) if isinstance(raw_checks, list) else _kind(raw_checks)
        _say(f"  bundle_check: verdict={_kind(verdict, BUNDLE_VERDICTS)} · 규칙 {count} · status {check_states} · severity {severities}")
    else:
        _say(f"  bundle_check: {_kind(bundle)}")
    problems = _final_problems(result)
    _say(
        "  계약 모양(키·순서·허용 값·L-nn·연결 서류·쪽·글, 옛 워크플로우면 links []·decision null): "
        f"{'맞음' if not problems else f'문제 {len(problems)}개'}"
    )
    for problem in problems[:10]:
        _say(f"    - {_short(problem)}")
    if not final:
        return not problems
    if _is_v2(result):
        _say("  설정 60 응답 — 알려진 모양(연결 수·verdict) 비교 없이 계약 모양만 봄")
        return not problems
    verdict_ok = isinstance(verdict, str) and verdict in BUNDLE_VERDICTS
    _say(f"  묶음 검증 verdict 있음(서류별 validation 대신): {_mark(verdict_ok)}")
    shape = _result_shape(result)
    want = shape.get("final") if shape else None
    linked = sum(1 for link in rows if link.get("state") == "linked")
    if want is None:
        _say("  알려진 모양(최종 흐름): 없음 — 새 모양: 불일치")
        return False
    shape_ok = len(rows) == want["links"] == linked and verdict == want["verdict"]
    _say(f"  알려진 모양(최종 흐름 — 연결 {want['links']}개 모두 linked · 묶음 검증 {want['verdict']}): {_mark(shape_ok)}")
    return not problems and verdict_ok and shape_ok


# --- 검토사항(result.items) 확인 — review-items BRIEF §5.3 ---------------------------------------
# 기대값은 계약대로 응답의 documents·findings 에서 따로 만든다(백엔드 imask_backend.items 를 쓰지 않음). 검증 checks 는 응답에
# 없으므로 missing(규칙·verdict) 항목은 계산할 수 없다 — 보이는 서류의 validation 이 모두 green(또는 null)일 때만 missing
# 0개를 기대하고, 그 밖이면 '새 모양'으로 실패를 알린다(숫자를 느슨하게 하지 않는다).


def _visible_docs(documents: Any) -> list[Mapping[str, Any]]:
    """보이는 서류(화면 readDocSources 와 같은 기준) — index 가 bool 아닌 정수 ≥ 0, page_start·page_end 가 bool 아닌 정수 ≥ 1.
    index 순, 같은 index 는 처음 것."""
    found: dict[int, Mapping[str, Any]] = {}
    for doc in documents if isinstance(documents, list) else []:
        if not isinstance(doc, Mapping):
            continue
        index, start, end = doc.get("index"), doc.get("page_start"), doc.get("page_end")
        if _is_int(index) and index >= 0 and _is_int(start) and start >= 1 and _is_int(end) and end >= 1 and index not in found:
            found[index] = doc
    return [found[index] for index in sorted(found)]


def _clip_name(text: str) -> str:
    """글에 넣는 표시 이름: 40 코드 포인트를 넘으면 앞 39자 + '…', 그 뒤 NUL·짝 없는 서로게이트 → U+FFFD."""
    short = text if len(text) <= ITEM_MAX_NAME else text[: ITEM_MAX_NAME - 1] + "…"
    return "".join(REPLACEMENT_CHAR if char == "\x00" or 0xD800 <= ord(char) <= 0xDFFF else char for char in short)


def _validation_green(value: Any) -> bool:
    """검증 결과가 없거나(null·빈 글) green(앞뒤 공백·대소문자 무시)인지."""
    return value is None or (isinstance(value, str) and _js_trim(value).strip().lower() in ("", "green"))


def _item_want(
    item_id: str, kind: str, index: int, page: int, finding_id: str | None, text: tuple[str, str, str], evidence: list[dict[str, Any]]
) -> dict[str, Any]:
    title, desc, next_step = text
    return {
        "id": item_id,
        "number": "",
        "type": kind,
        "document_index": index,
        "page": page,
        "finding_id": finding_id,
        "title": title,
        "desc": desc,
        "next": next_step,
        "evidence": evidence[:ITEM_MAX_EVIDENCE],
        "link_id": None,  # 연결 재료(mismatch·weaklink)만 문자열 — 기대값을 계산하는 모양에서는 늘 없다
    }


def _expected_items(result: Mapping[str, Any]) -> tuple[list[dict[str, Any]] | None, str]:
    """계약대로 따로 계산한 result.items 기대값(서류 순서 → nolocation·lowconf·other → 재료 안 순서). 계산할 수 없으면 (None, 이유).

    최종 흐름(bundle_check 있음)의 묶음 재료(missing·bundle·absent — 묶음_검증, mismatch·weaklink — 서류_대조)는 묶음 검증이 green 이고
    모든 연결이 linked 일 때만 0개로 기대한다(그 밖은 규칙별 서류 결과가 응답에 없어 계산할 수 없다 — '새 모양')."""
    visible = _visible_docs(result.get("documents"))
    not_green = sum(1 for doc in visible if not _validation_green(doc.get("validation")))
    if not_green:
        return None, f"새 모양 — 검증 결과가 green 이 아닌 서류 {not_green}개(checks 를 볼 수 없어 missing 항목을 계산할 수 없음)"
    bundle = result.get("bundle_check")
    if isinstance(bundle, Mapping) and not _is_v2(result):  # 설정 60 은 nolocation·lowconf·other 만 비교한다(_print_items)
        links = result.get("links") if isinstance(result.get("links"), list) else []
        unlinked = sum(1 for link in links if not (isinstance(link, Mapping) and link.get("state") == "linked"))
        if bundle.get("verdict") != "green" or unlinked:
            verdict = _kind(bundle.get("verdict"), BUNDLE_VERDICTS)
            return None, (
                f"새 모양 — 최종 흐름 묶음 검증 {verdict} · linked 아닌 연결 {unlinked}개"
                "(missing·bundle·absent·mismatch·weaklink 항목을 계산할 수 없음)"
            )
    spans: dict[int, tuple[int, int, int]] = {}  # index → (서류 순번, page_start, 화면 쪽 범위 끝)
    for number, doc in enumerate(visible, 1):
        start = doc["page_start"]
        spans[doc["index"]] = (number, start, max(start, doc["page_end"]))
    rows: dict[int, list[dict[str, Any]]] = {index: [] for index in spans}
    findings = result.get("findings")
    for finding in findings if isinstance(findings, list) else []:
        if not isinstance(finding, Mapping):
            continue
        index = finding.get("document_index")
        if not _is_int(index) or index not in spans:
            continue
        number, start, end = spans[index]
        page, boxes, label, field, raw_id = (finding.get(k) for k in ("page", "boxes", "label", "field", "id"))
        in_range = _is_int(page) and start <= page <= end
        name = (_js_trim(label) if isinstance(label, str) else "") or (_js_trim(field) if isinstance(field, str) else "")
        rows[index].append(
            {
                "id": raw_id if isinstance(raw_id, str) else None,
                "num": f"D{number}-{len(rows[index]) + 1:02d}",
                "name": name or UNNAMED_FINDING,
                "page": page if in_range else start,  # 파일 쪽(상자와 무관)
                "located": in_range and isinstance(boxes, list) and len(boxes) > 0,
                "low": isinstance(finding.get("confidence"), str) and finding["confidence"] == "low",
            }
        )
    items: list[dict[str, Any]] = []
    for doc in visible:
        index = doc["index"]
        _number, start, _end = spans[index]
        first_page = {"label": ITEM_OPEN_LABEL.format(p=1), "page": start, "finding_ids": [], "finding_id": None}
        for f in rows[index]:  # nolocation — 위치 없는 항목마다
            if f["located"] or f["id"] is None:
                continue
            title, desc, next_step = ITEM_NOLOCATION
            evidence = [{"label": ITEM_OPEN_LABEL.format(p=f["page"] - start + 1), "page": f["page"], "finding_ids": [f["id"]], "finding_id": f["id"]}]
            text = (title, desc.format(num=f["num"], name=_clip_name(f["name"])), next_step)
            items.append(_item_want(f"nolocation:{f['id']}", "nolocation", index, f["page"], f["id"], text, evidence))
        low = [f for f in rows[index] if f["low"]]
        if low:  # lowconf — 서류마다 하나, 근거는 위치 있는 low 항목을 파일 쪽별로(쪽 오름차순 앞 20쪽)
            count = len(low)
            nums = ", ".join(f["num"] for f in low[:ITEM_MAX_NUMS]) + (f" 외 {count - ITEM_MAX_NUMS}건" if count > ITEM_MAX_NUMS else "")
            pages: dict[int, list[str]] = {}
            for f in low:
                if f["located"] and f["id"] is not None:
                    pages.setdefault(f["page"], []).append(f["id"])
            evidence = [
                {"label": ITEM_VALUES_LABEL.format(p=p - start + 1), "page": p, "finding_ids": pages[p], "finding_id": None}
                for p in sorted(pages)[:ITEM_MAX_EVIDENCE]
            ]
            title, desc, next_step = ITEM_LOWCONF
            text = (title.format(n=count), desc.format(nums=nums), next_step)
            items.append(_item_want(f"lowconf:{index}", "lowconf", index, evidence[0]["page"] if evidence else start, None, text, evidence))
        if isinstance(doc.get("kind"), str) and doc["kind"] == "other":
            items.append(_item_want(f"other:{index}", "other", index, start, None, ITEM_OTHER, [first_page]))
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:  # 같은 계약 id 는 처음 것만
        if item["id"] not in seen:
            seen.add(item["id"])
            out.append(item)
    for number, item in enumerate(out, 1):
        item["number"] = f"R-{number:02d}"
    return out, ""


def _link_targets(links: Any) -> dict[str, Any]:
    """result.links 의 연결 id → 대상 서류 index(docs[1].document_index — 모양이 틀린 줄은 None)."""
    out: dict[str, Any] = {}
    for link in links if isinstance(links, list) else []:
        if not isinstance(link, Mapping) or not isinstance(link.get("id"), str):
            continue
        docs = link.get("docs")
        target = docs[1] if isinstance(docs, list) and len(docs) == 2 and isinstance(docs[1], Mapping) else {}
        out.setdefault(link["id"], target.get("document_index"))
    return out


def _is_link_item(item: Mapping[str, Any]) -> bool:
    """연결 항목(link_id 가 있어야 함) — weaklink 와 id 꼴이 mismatch:<정수>:<정수> 인 mismatch."""
    kind, item_id = item.get("type"), item.get("id")
    return kind == "weaklink" or (kind == "mismatch" and isinstance(item_id, str) and LINK_MISMATCH_ID.fullmatch(item_id) is not None)


def _link_id_ok(item: Mapping[str, Any], link_targets: Mapping[str, Any]) -> bool:
    """검토사항의 link_id(final-flow T3 B): 연결 항목(_is_link_item)은 같은 결과 links[] 의 id 이고 그 연결의 대상 서류가 이 항목의 서류,
    그 밖은 null."""
    link_id = item.get("link_id")
    if not _is_link_item(item):
        return link_id is None
    if not isinstance(link_id, str) or link_id not in link_targets:
        return False
    target = link_targets[link_id]
    return _is_int(target) and _is_int(item.get("document_index")) and target == item["document_index"]


def _items_shape_problems(items: Any, result: Mapping[str, Any]) -> list[str]:
    """result.items 의 계약 모양(값은 출력하지 않고 'items[n].키' 위치만): 키·순서·타입, R-nn 1부터 연속, id 겹치지 않음,
    document_index 가 보이는 서류, page·근거 page 가 그 서류 화면 쪽 범위 안, finding_id·finding_ids 가 그 서류의 탐지 항목,
    link_id 가 연결 항목(_is_link_item)만 그 서류를 대상으로 하는 연결 id(그 밖 null)."""
    if not isinstance(items, list):
        return ["result.items 가 목록이 아님"]
    spans = {d["index"]: (d["page_start"], max(d["page_start"], d["page_end"])) for d in _visible_docs(result.get("documents"))}
    own = _own_finding_ids(result, spans)
    link_targets = _link_targets(result.get("links"))
    problems: list[str] = []
    for n, item in enumerate(items):
        where = f"items[{n}]"
        if not isinstance(item, Mapping) or list(item) != list(ITEM_KEYS):
            problems.append(f"{where}: 키·순서가 계약과 다름")
            continue
        index = item["document_index"]
        visible = _is_int(index) and index in spans
        span, mine = (spans[index], own[index]) if visible else ((0, -1), set())
        kind, finding_id = item["type"], item["finding_id"]
        checks = [
            (isinstance(item["id"], str) and item["id"] != "", "id"),
            (isinstance(item["number"], str), "number"),
            (isinstance(kind, str) and kind in ITEM_TYPES, "type"),
            (visible, "document_index(보이는 서류)"),
            (_is_int(item["page"]) and span[0] <= item["page"] <= span[1], "page(서류 쪽 범위)"),
            (finding_id is None or (isinstance(finding_id, str) and finding_id in mine), "finding_id(그 서류의 탐지 항목)"),
            ((kind == "nolocation") == isinstance(finding_id, str), "finding_id(nolocation 만 있음)"),
            (all(isinstance(item[k], str) and item[k] != "" for k in ("title", "desc", "next")), "title·desc·next"),
            (isinstance(item["evidence"], list) and len(item["evidence"]) <= ITEM_MAX_EVIDENCE, "evidence(목록·20개 이하)"),
            (_link_id_ok(item, link_targets), "link_id(연결 종류만 그 서류의 연결 id · 그 밖 null)"),
        ]
        problems += [f"{where}.{name}" for passed, name in checks if not passed]
        for m, ev in enumerate(item["evidence"] if isinstance(item["evidence"], list) else []):
            at = f"{where}.evidence[{m}]"
            if not isinstance(ev, Mapping) or list(ev) != list(ITEM_EVIDENCE_KEYS):
                problems.append(f"{at}: 키·순서가 계약과 다름")
                continue
            ids = ev["finding_ids"]
            ev_checks = [
                (isinstance(ev["label"], str) and ev["label"] != "", "label"),
                (_is_int(ev["page"]) and span[0] <= ev["page"] <= span[1], "page(서류 쪽 범위)"),
                (isinstance(ids, list) and all(isinstance(i, str) and i in mine for i in ids), "finding_ids(그 서류의 탐지 항목)"),
                (ev["finding_id"] is None or (isinstance(ev["finding_id"], str) and ev["finding_id"] in mine), "finding_id"),
            ]
            problems += [f"{at}.{name}" for passed, name in ev_checks if not passed]
    numbers = [item.get("number") if isinstance(item, Mapping) else None for item in items]
    if numbers != [f"R-{n:02d}" for n in range(1, len(items) + 1)]:
        problems.append("number 가 R-01 부터 이어지지 않음")
    ids = [item.get("id") for item in items if isinstance(item, Mapping) and isinstance(item.get("id"), str)]
    if len(set(ids)) != len(ids):
        problems.append("id 가 겹침")
    return problems


def _items_compare(got: list[Any], want: list[dict[str, Any]], *, skip: tuple[str, ...] = ()) -> list[str]:
    """받은 result.items 와 따로 계산한 기대값을 비교 — 다른 자리만('items[n].키' — 값은 출력하지 않는다). skip 의 키는 보지 않는다."""
    problems = [f"개수 {len(got)}(기대 {len(want)})"] if len(got) != len(want) else []
    for n, (item, expected) in enumerate(zip(got, want, strict=False)):
        if not isinstance(item, Mapping):
            problems.append(f"items[{n}]: 객체가 아님")
            continue
        problems += [
            f"items[{n}].{key}: 기대값과 다름" for key in ITEM_KEYS if key != "evidence" and key not in skip and item.get(key) != expected[key]
        ]
        evidence = item.get("evidence")
        if not isinstance(evidence, list) or len(evidence) != len(expected["evidence"]):
            problems.append(f"items[{n}].evidence: 개수가 기대와 다름")
            continue
        for m, (ev, want_ev) in enumerate(zip(evidence, expected["evidence"], strict=True)):
            problems += [
                f"items[{n}].evidence[{m}].{key}: 기대값과 다름"
                for key in ITEM_EVIDENCE_KEYS
                if not isinstance(ev, Mapping) or ev.get(key) != want_ev[key]
            ]
    return problems


def _kinds(items: Any) -> dict[str, int]:
    """종류별 개수(계약 밖 종류는 '계약 밖' — 응답 글자를 그대로 출력하지 않는다)."""
    counts: Counter[str] = Counter()
    for item in items if isinstance(items, list) else []:
        kind = item.get("type") if isinstance(item, Mapping) else None
        counts[kind if isinstance(kind, str) and kind in ITEM_TYPES else "계약 밖"] += 1
    return dict(counts)


def _print_items(result: Mapping[str, Any]) -> bool:
    """result.items — 계약 모양 + 따로 계산한 기대값과 같음. 출력은 개수·종류 분포·문제 위치만(글·id 는 출력하지 않는다)."""
    items = result.get("items")
    got = items if isinstance(items, list) else []
    shape = _items_shape_problems(items, result)
    evidence = sum(len(i["evidence"]) for i in got if isinstance(i, Mapping) and isinstance(i.get("evidence"), list))
    _say("검토사항(result.items):")
    _say(f"  {len(got)}개 · 종류 {_kinds(got)} · 근거 {evidence}개")
    _say(f"  계약 모양(키·순서·타입·R-nn 연속·id 중복 없음·서류·쪽·탐지 항목 참조): {'맞음' if not shape else f'문제 {len(shape)}개'}")
    for problem in shape[:10]:
        _say(f"    - {_short(problem)}")
    want, reason = _expected_items(result)
    if want is None:
        _say(f"  따로 계산한 기대값: 계산할 수 없음 — {reason}: 불일치")
        return False
    if _is_v2(result):
        own = [i for i in got if isinstance(i, Mapping) and isinstance(i.get("id"), str) and i["id"].startswith(V2_OWN_ITEMS)]
        differs = _items_compare(own, want, skip=("number",))  # 번호는 전체 순서라 보지 않는다
        _say(f"  따로 계산한 기대값(nolocation·lowconf·other 만 — 나머지 종류는 계약 모양만): {len(want)}개 · 종류 {_kinds(want)}: {_mark(not differs)}")
        for problem in differs[:10]:
            _say(f"    - {_short(problem)}")
        return not shape and not differs
    differs = _items_compare(got, want)
    _say(
        f"  따로 계산한 기대값(documents·findings → nolocation·lowconf·other, 검증 모두 green·null → missing 0"
        f"{', 최종 흐름 묶음 검증 green·모두 linked → 묶음·연결 항목 0' if _is_final(result) else ''}): "
        f"{len(want)}개 · 종류 {_kinds(want)}: {_mark(not differs)}"
    )
    for problem in differs[:10]:
        _say(f"    - {_short(problem)}")
    return not shape and not differs


def _result_items(row: Any) -> list[Mapping[str, Any]]:
    """조회 응답의 result.items(객체인 항목만 — 모양 판정은 _items_shape_problems)."""
    result = row.get("result") if isinstance(row, Mapping) else None
    items = result.get("items") if isinstance(result, Mapping) else None
    return [i for i in items if isinstance(i, Mapping)] if isinstance(items, list) else []


def _verify_done(run: Run, analysis_id: str) -> bool:
    """done 분석을 다시 읽어(기본·?include=stages) 요약·화면용 결과·응답 크기를 확인한다. done 조회는 Upstage 를 부르지 않는다."""
    plain, row = _get(run, analysis_id)
    if plain.status_code != 200 or not isinstance(row, Mapping):
        run.log(f"done 확인: 조회 실패 HTTP {plain.status_code} {_detail(plain)}")
        return False
    if row.get("status") != "done":
        run.log(f"done 확인: 상태가 done 이 아님({row.get('status')})")
        return False
    result = row.get("result") if isinstance(row.get("result"), Mapping) else {}
    ok = _print_summary(result)
    ok = _print_view(result) and ok
    ok = _print_final(result) and ok
    ok = _print_items(result) and ok

    staged, staged_row = _get(run, analysis_id, {"include": "stages"})
    staged_result = staged_row.get("result") if isinstance(staged_row, Mapping) else None
    has_stages = isinstance(staged_result, Mapping) and isinstance(staged_result.get("stages"), list)
    no_response = isinstance(staged_result, Mapping) and "response" not in staged_result
    small, big = len(plain.content), len(staged.content)
    ratio = f"{small / big:.1%}" if big else "?"
    size_ok = staged.status_code == 200 and has_stages and no_response and small < big
    _say(
        f"응답 크기: 기본 GET {small:,} bytes · ?include=stages GET {big:,} bytes(HTTP {staged.status_code}) · 기본이 {ratio}"
        f" · include=stages 에 stages 있음 {has_stages}·response 없음 {no_response}: {_mark(size_ok)}"
    )
    return ok and size_ok


def _check_file(run: Run, analysis_id: str, content: bytes) -> bool:
    """원본 파일 주소를 받아 그 주소로(사용자 지정 헤더 없이) 내려받고 올린 내용과 sha256 을 비교한다. URL 은 출력하지 않는다."""
    response = run.call("GET", f"/api/py/analyses/{analysis_id}/file")
    if response.status_code != 200:
        run.log(f"원본 파일: HTTP {response.status_code} {_detail(response)}")
        return False
    try:
        body = response.json()
    except ValueError:
        body = None
    if not isinstance(body, Mapping):
        run.log("원본 파일: 응답 모양이 다름")
        return False
    url = body.get("url")
    if isinstance(url, str):
        _hide(url, "<SIGNED_DOWNLOAD_URL>")
    keys_ok = set(body) == FILE_KEYS and isinstance(url, str) and url.startswith(("https://", "http://"))
    no_store = "no-store" in response.headers.get("cache-control", "")
    run.log(
        f"원본 파일: HTTP 200 · 키 {sorted(body)}({_mark(keys_ok)}) · mime_type={body.get('mime_type')}"
        f" · filename={body.get('filename')!r} · Cache-Control no-store: {no_store}"
    )
    if not keys_ok:
        return False
    try:
        with httpx.Client(timeout=httpx.Timeout(60.0, connect=10.0), transport=run.transport) as plain:
            downloaded = plain.get(url)
    except httpx.HTTPError as exc:
        run.log(f"원본 파일 받기 실패: {type(exc).__name__}")
        return False
    if downloaded.status_code != 200:
        run.log(f"원본 파일 받기 실패: HTTP {downloaded.status_code}")
        return False
    same = hashlib.sha256(downloaded.content).digest() == hashlib.sha256(content).digest()
    run.log(f"원본 파일 받기(사용자 지정 헤더 없이): HTTP 200 · {len(downloaded.content):,} bytes · 올린 내용과 sha256 {_mark(same)}")
    return same and no_store


# --- 검토 동작 확인(review-actions) ---------------------------------------------------------
# 기대 문구는 백엔드 코드를 가져다 쓰지 않고 계약(데모 코어 src/services/demo/core.ts 와 같은 전이·문구)을 그대로 적는다.


# JavaScript String.prototype.trim() 이 지우는 글자 = ECMAScript WhiteSpace + LineTerminator(계약 BRIEF §5.1 — 화면 기준).
# Python str.strip() 과 다르다: U+FEFF 는 지우고, U+0085·U+001C~001F 는 지우지 않는다. 백엔드 함수를 쓰지 않고 따로 적는다.
_JS_WHITESPACE = (0x0009, 0x000B, 0x000C, 0x0020, 0x00A0, 0xFEFF)  # TAB VT FF SP NBSP ZWNBSP
_JS_ZS = (0x0020, 0x00A0, 0x1680, *range(0x2000, 0x200B), 0x202F, 0x205F, 0x3000)  # 유니코드 Zs 전체
_JS_LINE_TERMINATORS = (0x000A, 0x000D, 0x2028, 0x2029)  # LF CR LS PS
JS_TRIM_CHARS = "".join(chr(c) for c in sorted({*_JS_WHITESPACE, *_JS_ZS, *_JS_LINE_TERMINATORS}))
TARGET_MAX = 200  # 이력 target 저장 한도(코드 포인트, BRIEF §5.5)
REPLACEMENT_CHAR = chr(0xFFFD)  # 저장할 수 없는 글자(짝 없는 서로게이트·NUL)를 바꿀 글자


_JSON_U_ESCAPE = chr(92) + "u"  # JSON 문자열의 \uXXXX escape 머리


def _json_body(value: Any) -> bytes:
    """검토 동작 본문 JSON 바이트 — httpx `json=` 과 같은 모양(ensure_ascii=False · 구분자 , : · NaN 금지 · UTF-8)이되,
    UTF-8 로 인코딩할 수 없는 **짝 없는 서로게이트만** `\\udXXX` 로 escape 한다(브라우저 JSON.stringify 와 같은 값).
    정상 유니코드(한글 등)는 UTF-8 그대로라 본문 크기가 httpx `json=` 과 같다(서버 본문 한도 65,536 바이트 기준).
    서로게이트는 JSON 문자열 안에만 나오므로 그 자리의 escape 는 늘 올바른 JSON 이고, 결과는 늘 유효한 UTF-8 이다.
    (json.loads 로 만든 문자열에는 상위·하위 서로게이트가 따로 붙어 있는 경우가 없다 — 있다면 서버가 한 글자로 합쳐 읽는다.)"""
    text = json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    escaped = "".join(f"{_JSON_U_ESCAPE}{ord(char):04x}" if 0xD800 <= ord(char) <= 0xDFFF else char for char in text)
    return escaped.encode("utf-8")


def _js_trim(text: str) -> str:
    """JavaScript `text.trim()` 과 같은 결과(앞뒤의 JS_TRIM_CHARS 만 지운다)."""
    return text.strip(JS_TRIM_CHARS)


def _stored_text(text: str, limit: int) -> str:
    """이력 글이 저장되는 모양: 짝 없는 서로게이트·NUL → U+FFFD, limit 코드 포인트를 넘으면 앞 limit-1 자 + '…'."""
    cleaned = "".join(REPLACEMENT_CHAR if char == "\x00" or 0xD800 <= ord(char) <= 0xDFFF else char for char in text)
    return cleaned if len(cleaned) <= limit else cleaned[: limit - 1] + "…"


def _stored_target(text: str) -> str:
    """이력 target 이 저장되는 모양(BRIEF §5.5): 짝 없는 서로게이트·NUL → U+FFFD, 200 코드 포인트를 넘으면 앞 199자 + '…'."""
    return _stored_text(text, TARGET_MAX)


def _when(value: Any) -> datetime | None:
    """ISO 8601(시간대 포함) → datetime. 못 읽으면 None. DB 시각(timestamptz)과 이력 문자열을 같은 기준으로 비교한다."""
    if not isinstance(value, str) or not value:
        return None
    try:
        moment = datetime.fromisoformat(value)
    except ValueError:
        return None
    return moment if moment.tzinfo is not None else None


def _fmt_size(size: int) -> str:
    """화면 src/lib/format.ts fmtSize 와 같은 글자(계약대로 따로 — 백엔드 함수를 쓰지 않음).
    1,048,576 미만이면 max(1, Math.round(b/1024)) + 'KB', 아니면 (b/1048576).toFixed(1) + 'MB'.
    b/1024·b/1048576 은 정확한 이진 소수라 JS Math.round·toFixed 는 양수에서 '절반은 올림'이다 — 정확한 분수로 계산한다
    (파이썬 round()·format(.1f) 는 동점에서 짝수 쪽이라 2,560 B·1,310,720 B 에서 다르다)."""
    if size < 1_048_576:
        return f"{max(1, math.floor(Fraction(size, 1024) + Fraction(1, 2)))}KB"
    tenths = math.floor(Fraction(size * 10, 1_048_576) + Fraction(1, 2))
    return f"{tenths // 10}.{tenths % 10}MB"


def _export_name(row: Mapping[str, Any], fmt: str, *, shift_days: int = 0) -> str | None:
    """이 분석의 내보내기 파일 이름(화면 analysisCode 와 같은 꼴): iMASK_IM-<created_at 의 서울 날짜 YYYYMMDD>-<id 의 ASCII
    영숫자 앞 4자 대문자> + 형식별 꼬리. shift_days 는 거절 확인용(날짜만 다른 이름). created_at 을 읽지 못하면 None."""
    moment = _when(row.get("created_at"))
    if moment is None:
        return None
    day = moment.astimezone(SEOUL) + timedelta(days=shift_days)
    head = "".join(c for c in str(row.get("id")) if c.isascii() and c.isalnum())[:4].upper()
    return f"iMASK_IM-{day:%Y%m%d}-{head}{EXPORT_SUFFIXES[fmt]}"


def _review_targets(result: Any) -> list[dict[str, str]]:
    """검토할 수 있는 탐지 항목(화면에 보이는 항목) — 표시 번호·표시 이름·AI 값. 화면 toLiveFindings 와 같은 순서."""
    if not isinstance(result, Mapping):
        return []
    documents = result.get("documents") if isinstance(result.get("documents"), list) else []
    findings = result.get("findings") if isinstance(result.get("findings"), list) else []
    seen: list[int] = []
    for doc in documents:
        if not isinstance(doc, Mapping):
            continue
        index, start, end = doc.get("index"), doc.get("page_start"), doc.get("page_end")
        if _is_int(index) and index >= 0 and _is_int(start) and start >= 1 and _is_int(end) and end >= 1 and index not in seen:
            seen.append(index)
    numbers = {index: number for number, index in enumerate(sorted(seen), 1)}
    seq: dict[int, int] = {}
    targets: list[dict[str, str]] = []
    for finding in findings:
        if not isinstance(finding, Mapping):
            continue
        index = finding.get("document_index")
        if not _is_int(index) or index not in numbers:
            continue
        number = numbers[index]
        seq[number] = seq.get(number, 0) + 1
        label, field = finding.get("label"), finding.get("field")
        # 표시 이름: label → field → '이름 없는 항목'(화면 toLiveFindings 처럼 JavaScript trim 기준)
        name = (_js_trim(label) if isinstance(label, str) else "") or (_js_trim(field) if isinstance(field, str) else "")
        category, subject, exposure = finding.get("category"), finding.get("subject"), finding.get("exposure")
        targets.append(
            {
                "id": str(finding.get("id")),
                "num": f"D{number}-{seq[number]:02d}",
                "label": name or UNNAMED_FINDING,
                "category": category if category in CATS else "기타 개인정보",
                "subject": subject if subject in SUBJECTS else "기타",
                "exposure": exposure if exposure in EXPOSURES else "전체 노출",
            }
        )
    return targets


def _risk_label(result: Mapping[str, Any]) -> str:
    """S2 의 위험등급 — overall.level(비면 summary.risk_level) 상·중·하·검토 필요 → 상·중·하·검토 필요, 그 밖 미평가."""
    overall = result.get("overall") if isinstance(result.get("overall"), Mapping) else {}
    level = overall.get("level")
    if not (isinstance(level, str) and _js_trim(level)):
        summary = result.get("summary") if isinstance(result.get("summary"), Mapping) else {}
        level = summary.get("risk_level")
    return RISK_LABELS.get(_js_trim(level) if isinstance(level, str) else "", "미평가")


def _system_lines(row: Mapping[str, Any], targets: list[dict[str, str]]) -> list[dict[str, str]]:
    """조회할 때 만드는 이력 두 줄(S1 분석 요청 · S2 최초 AI 결과)의 기대값."""
    result = row.get("result") if isinstance(row.get("result"), Mapping) else {}
    files = len(_documents(row))
    items = result.get("items") if isinstance(result.get("items"), list) else []  # 검토사항 수(review-items §5.5)
    base = {"actor": SYSTEM_ACTOR, "target": ANALYSIS_TARGET, "reason": ""}
    return [
        {"id": "S1", "at": row.get("created_at"), "kind": "request", "change": f"파일 {files}개 분석 요청", **base},
        {
            "id": "S2",
            "at": row.get("updated_at"),
            "kind": "ai",
            "change": f"분석 완료 · 탐지 {len(targets)}건 · 위험등급 {_risk_label(result)} · 검토사항 {len(items)}건",
            **base,
        },
    ]


def _line_problems(line: Any, want: Mapping[str, Any], where: str) -> list[str]:
    if not isinstance(line, Mapping) or set(line) != HISTORY_KEYS:
        return [f"{where}: 이력 줄 모양이 다름"]
    return [f"{where} {key}: 계약과 다름" for key, value in want.items() if line.get(key) != value]


def _review_shape_problems(row: Mapping[str, Any], targets: list[dict[str, str]]) -> list[str]:
    """review 블록의 모양(값은 보지 않음): 키·status·findings·items·history S1·S2·version."""
    review = row.get("review")
    if not isinstance(review, Mapping):
        return ["review 가 객체가 아님(검토 기록을 읽지 못함)"]
    if set(review) != REVIEW_KEYS:
        return [f"review 키가 계약과 다름 {sorted(set(review) ^ REVIEW_KEYS)}"]
    problems: list[str] = []
    if review["status"] not in ("needed", "done"):
        problems.append(f"status {_shown(review['status'], REVIEW_STATUSES)}")
    version = review["version"]
    if not (_is_int(version) and version >= 0):
        problems.append("version 이 0 이상 정수가 아님")
    findings = review["findings"]
    ids = {t["id"] for t in targets}
    if not isinstance(findings, Mapping):
        problems.append("findings 가 객체가 아님")
    else:
        # 받은 키(id)는 출력하지 않는다 — 개수만(V-T3-1 M1 과 같은 기준)
        strangers = sum(1 for k in findings if k not in ids)
        if strangers:
            problems.append(f"findings: 검토 가능 항목이 아닌 id {strangers}개")
        bad_values = sum(1 for v in findings.values() if not (isinstance(v, Mapping) and set(v) == REVIEW_FINDING_KEYS))
        if bad_values:
            problems.append(f"findings: 키가 계약과 다른 값 {bad_values}개")
    # 검토사항 해결 기록(review-items §5.5): 지금 결과의 검토사항 id 만, 값은 정규화한 4키(id·처리 내용은 출력하지 않는다)
    items = review["items"]
    item_ids = {i["id"] for i in _result_items(row) if isinstance(i.get("id"), str)}
    if not isinstance(items, Mapping):
        problems.append("items 가 객체가 아님")
    else:
        strangers = sum(1 for k in items if k not in item_ids)
        if strangers:
            problems.append(f"items: 지금 결과의 검토사항이 아닌 id {strangers}개")
        bad = sum(1 for v in items.values() if not _review_item_ok(v))
        if bad:
            problems.append(f"items: 값 모양(resolved·note·resolved_at·resolved_by)이 계약과 다른 것 {bad}개")
    history = review["history"]
    if not isinstance(history, list) or len(history) < 2:
        problems.append("history 에 S1·S2 두 줄이 없음")
        return problems
    for line, want in zip(history[:2], _system_lines(row, targets), strict=True):
        problems += _line_problems(line, want, str(want["id"]))
    stored = history[2:]
    if any(not isinstance(line, Mapping) or set(line) != HISTORY_KEYS or not str(line.get("id")).startswith("H") for line in stored):
        problems.append("저장된 이력 줄 모양이 다름")
    if _is_int(version) and len(stored) > version:
        problems.append(f"저장된 이력 {len(stored)}줄이 version {version} 보다 많음")
    return problems


def _review_item_ok(value: Any) -> bool:
    """review.items 값 하나가 정규화한 모양인지: 정확히 4키, resolved bool · note str · resolved_at str|null · resolved_by str."""
    return (
        isinstance(value, Mapping)
        and set(value) == REVIEW_ITEM_KEYS
        and isinstance(value["resolved"], bool)
        and isinstance(value["note"], str)
        and (value["resolved_at"] is None or isinstance(value["resolved_at"], str))
        and isinstance(value["resolved_by"], str)
    )


def _first_review_problems(row: Mapping[str, Any], targets: list[dict[str, str]]) -> list[str]:
    """새 분석의 처음 review: needed·빈 값·findings {}·items {}·S1·S2 만·version 0."""
    problems = _review_shape_problems(row, targets)
    review = row.get("review")
    if problems or not isinstance(review, Mapping):
        return problems
    want = {
        "status": "needed",
        "memo": "",
        "memo_at": None,
        "reviewer": "",
        "reviewed_at": None,
        "completion_note": "",
        "findings": {},
        "items": {},
        "version": 0,
    }
    problems += [f"{key}: 계약과 다름" for key, value in want.items() if review.get(key) != value]
    if len(review["history"]) != 2:
        problems.append(f"history {len(review['history'])}줄(기대 S1·S2 2줄)")
    return problems


class _Checklist:
    """번호를 매긴 단계별 통과/실패 출력(단계 이름·개수·문제 줄만 — 값은 넣지 않는다)."""

    def __init__(self) -> None:
        self.steps = 0
        self.failed = 0

    def report(self, name: str, problems: list[str], note: str = "") -> bool:
        self.steps += 1
        ok = not problems
        if not ok:
            self.failed += 1
        _say(f"  [{'통과' if ok else '실패'}] {self.steps:02d}. {name}" + (f" — {note}" if note else ""))
        for problem in problems[:6]:
            _say(f"      - {_short(problem)}")
        return ok

    @property
    def ok(self) -> bool:
        return self.failed == 0

    def summary(self, title: str) -> bool:
        _say(f"{title}: {self.steps - self.failed}/{self.steps} 통과 — {'기대대로' if self.ok else '기대와 다름'}")
        return self.ok


class _ReviewFlow:
    """검토 동작을 차례로 보내고, 응답과 다시 읽은 값을 확인한다. 이번 실행이 만든 분석에만 쓴다.

    checks 를 주면 그 체크리스트에 이어서 번호를 매긴다(다시 분석 확인 안에서 검토 동작 하나를 볼 때)."""

    def __init__(self, run: Run, analysis_id: str, first: Mapping[str, Any], checks: _Checklist | None = None) -> None:
        self.run = run
        self.analysis_id = analysis_id
        self.first = first
        review = first.get("review")
        self.review: Mapping[str, Any] = review if isinstance(review, Mapping) else {}
        self.checks = checks if checks is not None else _Checklist()
        self.expected_writes = 0  # 이력 한 줄을 남겨야 하는 동작 수
        self.writes = 0  # 실제로 changed true 였던 동작 수

    @property
    def steps(self) -> int:
        return self.checks.steps

    @property
    def failed(self) -> int:
        return self.checks.failed

    def report(self, name: str, problems: list[str], note: str = "") -> bool:
        return self.checks.report(name, problems, note)

    def finding(self, target: Mapping[str, str]) -> Mapping[str, Any]:
        found = self.review.get("findings", {}).get(target["id"]) if isinstance(self.review.get("findings"), Mapping) else None
        return found if isinstance(found, Mapping) else {}

    def _post(self, body: Mapping[str, Any]) -> tuple[httpx.Response, Any]:
        # 본문은 _json_body 로 직접 만든다 — httpx json= 와 같은 UTF-8 바이트(같은 크기)이되, 짝 없는 서로게이트가 든
        # 계약 id 도 보낼 수 있게 그 글자만 escape(httpx json= 는 UTF-8 로 인코딩하다 실패한다). 서버가 읽는 값은 같다.
        content = _json_body({"actor": REVIEW_ACTOR, **body})
        response = self.run.call(
            "POST",
            f"/api/py/analyses/{self.analysis_id}/review-actions",
            content=content,
            headers={"content-type": "application/json"},
        )
        try:
            data = response.json()
        except ValueError:
            data = None
        return response, data

    def _reread(self, expected: Mapping[str, Any] | None) -> tuple[Mapping[str, Any] | None, list[str]]:
        """GET 으로 다시 읽는다. expected 가 있으면 분석 전체가 같아야 하고, 없으면 review 가 지금 값과 같아야 한다."""
        response, row = _get(self.run, self.analysis_id)
        if response.status_code != 200 or not isinstance(row, Mapping):
            return None, [f"다시 읽기: HTTP {response.status_code}"]
        if expected is not None and row != expected:
            keys = sorted(k for k in set(row) | set(expected) if row.get(k) != expected.get(k))
            return row, [f"다시 읽은 값이 응답과 다름 {keys}"]
        if expected is None and row.get("review") != self.review:
            return row, ["다시 읽은 review 가 바뀜(쓰기가 있었음)"]
        return row, []

    def write(
        self,
        name: str,
        body: Mapping[str, Any],
        line: tuple[str, str, str, str] | None,
        check: Callable[[Mapping[str, Any], Mapping[str, Any]], list[str]] | None = None,
    ) -> bool:
        """200 을 기대하는 동작. line = 새 이력 줄(kind, target, change, reason), None 이면 changed false(쓰기 없음)."""
        before = self.review
        if line is not None:
            self.expected_writes += 1
        response, data = self._post(body)
        if response.status_code != 200 or not isinstance(data, Mapping) or set(data) != {"analysis", "changed"}:
            return self.report(name, [f"HTTP {response.status_code} {_detail(response)}(기대 200 · analysis·changed)"])
        analysis = data["analysis"]
        review = analysis.get("review") if isinstance(analysis, Mapping) else None
        if not isinstance(review, Mapping) or not isinstance(review.get("history"), list):
            return self.report(name, ["응답의 review 가 객체가 아님"])
        problems: list[str] = []
        if analysis.get("upstage_status") is not None or analysis.get("poll_error") is not None:
            problems.append("응답의 upstage_status·poll_error 가 null 이 아님")
        if isinstance(analysis.get("result"), Mapping) and "stages" in analysis["result"]:
            problems.append("응답 result 에 stages 가 있음")
        for key in ("created_at", "updated_at", "started_at"):  # 분석 행은 쓰지 않는다(분석 시각·걸린 시간 불변)
            if analysis.get(key) != self.first.get(key):
                problems.append(f"분석 {key} 가 바뀜")
        changed = data["changed"]
        history, old = review["history"], before["history"]
        if changed is True:
            self.writes += 1
        if line is None:
            if changed is not False:
                problems.append(f"changed {_shown(changed)}(기대 false)")
            if review != before:
                problems.append("바뀐 것이 없는데 review 가 바뀜")
        else:
            version = before["version"] + 1
            if changed is not True:
                problems.append(f"changed {_shown(changed)}(기대 true)")
            if review.get("version") != version:
                problems.append(f"version {_shown(review.get('version'))}(기대 {version})")
            if len(history) != len(old) + 1 or history[:-1] != old:
                problems.append(f"이력 {len(history)}줄(기대 앞 {len(old)}줄 그대로 + 1줄)")
            else:
                kind, target, change, reason = line
                # target 은 저장 안전화를 거친 모양이어야 한다(안전화하지 않은 응답은 여기서 불일치로 잡힌다)
                want = {"id": f"H{version}", "actor": REVIEW_ACTOR, "kind": kind, "target": _stored_target(target), "change": change, "reason": reason}
                problems += _line_problems(history[-1], want, "새 이력")
                if _when(history[-1].get("at")) is None:
                    problems.append("새 이력 at 을 읽을 수 없음")
        if check is not None:
            problems += check(review, before)
        _, reread = self._reread(analysis)
        problems += reread
        self.review = review  # 실패해도 서버의 지금 값을 기준으로 다음 단계를 본다
        note = f"이력 {len(history)}줄 · version {_shown(review.get('version'))}" + ("" if changed else " · changed false")
        return self.report(name, problems, note)

    def refuse(self, name: str, body: Mapping[str, Any], status: int, detail: str) -> bool:
        """오류를 기대하는 동작 — 상태 코드·문구, 그리고 다시 읽어도 review 가 그대로(쓰기 없음)."""
        response, data = self._post(body)
        problems: list[str] = []
        got = data.get("detail") if isinstance(data, Mapping) else None
        if response.status_code != status or got != detail:
            problems.append(f"HTTP {response.status_code} {_detail(response)}(기대 {status} {detail})")
        _, reread = self._reread(None)
        problems += reread
        return self.report(name, problems, f"HTTP {response.status_code} · 쓰기 없음" if not problems else "")

    # --- 항목 값 확인 도우미 -------------------------------------------------------------

    def last_at(self, review: Mapping[str, Any]) -> datetime | None:
        return _when(review["history"][-1].get("at")) if review.get("history") else None

    def expect_finding(self, review: Mapping[str, Any], target: Mapping[str, str], **want: Any) -> list[str]:
        findings = review.get("findings") if isinstance(review.get("findings"), Mapping) else {}
        value = findings.get(target["id"])
        if not isinstance(value, Mapping) or set(value) != REVIEW_FINDING_KEYS:
            return [f"{target['num']}: 저장 값 모양이 다름"]
        return [f"{target['num']} {key}: 계약과 다름" for key, expected in want.items() if value.get(key) != expected]

    def touched_now(self, review: Mapping[str, Any], target: Mapping[str, str]) -> list[str]:
        """그 항목의 updated_at = 이번 동작 시각(새 이력 at)."""
        value = (review.get("findings") or {}).get(target["id"]) or {}
        if _when(value.get("updated_at")) is None or _when(value.get("updated_at")) != self.last_at(review):
            return [f"{target['num']} updated_at 이 이번 동작 시각이 아님"]
        return []


# --- 검토사항 해결·다시 열기(review-items BRIEF §5.6) --------------------------------------------------
# 기대 문구·값은 계약(데모 코어 resolveItem·reopenItem 과 같은 전이·문구)을 그대로 적는다(백엔드 함수를 쓰지 않음).


def _item_target(item: Any, position: int) -> dict[str, str] | None:
    """검토사항 하나(목록의 position 번째, 1부터) → 동작 대상(계약 id·화면 번호·이력 target '{번호} {종류 라벨}').

    출력·기대 이력에 쓰는 번호는 이 스크립트가 만든 순번 R-{position:02d} 이고, 받은 number 가 그것과 **같을 때만** 대상으로
    삼는다 — 받은 문자열은 출력에 넣지 않는다(V-T3-1 M1). id 는 본문(item_id)에만 쓰고 출력하지 않는다. 모양이 틀리면 None."""
    if not isinstance(item, Mapping):
        return None
    local = f"R-{position:02d}"
    item_id, number, kind = item.get("id"), item.get("number"), item.get("type")
    if not (isinstance(item_id, str) and item_id and number == local and isinstance(kind, str) and kind in ITEM_TYPES):
        return None
    return {"id": item_id, "num": local, "target": f"{local} {ITEM_TYPES[kind]}"}


def _item_checks(x: Mapping[str, str]) -> tuple[Callable[..., list[str]], Callable[[Mapping[str, Any], Mapping[str, Any]], list[str]]]:
    """검토사항 x 의 응답 review 저장 값 확인(value)과 '다른 것은 그대로' 확인(kept — 다른 검토사항·탐지 항목·메모 등)."""

    def value(review: Mapping[str, Any], **want: Any) -> list[str]:
        items = review.get("items") if isinstance(review.get("items"), Mapping) else {}
        saved = items.get(x["id"])
        if not _review_item_ok(saved):
            return [f"{x['num']}: review.items 저장 값 모양이 다름"]
        return [f"{x['num']} {key}: 계약과 다름" for key, expected in want.items() if saved.get(key) != expected]

    def kept(review: Mapping[str, Any], before: Mapping[str, Any]) -> list[str]:
        problems = [f"review {key} 가 바뀜" for key in sorted(REVIEW_KEYS - {"items", "history", "version"}) if review.get(key) != before.get(key)]
        now = review.get("items") if isinstance(review.get("items"), Mapping) else {}
        old = before.get("items") if isinstance(before.get("items"), Mapping) else {}
        if {k: v for k, v in now.items() if k != x["id"]} != {k: v for k, v in old.items() if k != x["id"]}:
            problems.append("다른 검토사항의 저장 값이 바뀜")
        return problems

    return value, kept


def _history_at(review: Mapping[str, Any]) -> Any:
    history = review.get("history")
    return history[-1].get("at") if isinstance(history, list) and history and isinstance(history[-1], Mapping) else None


def _check_item_actions(flow: _ReviewFlow, result: Any) -> dict[str, str] | None:
    """첫 검토사항(R-01)으로 해결 → 다시 해결 409 → 다시 열기 → 다시 열기 409 → 다시 해결, 없는 id 404, 400 두 가지.
    끝에 해결된 검토사항(대상)을 돌려준다.

    동작을 보내기 **전에** result.items 전체가 계약 모양인지(done 확인과 같은 _items_shape_problems — 키·순서·타입·R-nn 1부터
    연속·id 중복 없음·서류·쪽·참조) 본다. 하나라도 틀리면 값 없는 실패 위치(items[n].필드)만 적고 검토사항 동작을 보내지 않는다
    (None — 받은 번호·id·글을 단계 이름·문제 줄에 넣지 않게, V-T3-1 M1). 모양은 맞고 done 기대값만 다른 결과(검증 실패 서류 등)는
    그대로 확인한다. 검토사항이 0개면 건너뛰고 None."""
    view = result if isinstance(result, Mapping) else {}
    raw = view.get("items")
    shape = _items_shape_problems(raw, view)
    if shape:
        flow.report("검토사항 모양 — 계약과 달라 해결·다시 열기를 보내지 않음", shape, f"문제 {len(shape)}개")
        return None
    items: list[Mapping[str, Any]] = list(raw)  # 모양 검사를 지나 모두 객체
    if not items:
        _say("  검토사항 해결·다시 열기 확인 건너뜀(검토사항 0개)")
        return None
    x = _item_target(items[0], 1)
    if x is None:  # 모양 검사를 지났으면 생기지 않는다
        flow.report("검토사항 해결·다시 열기 — 첫 검토사항", ["items[0]: id·number·type 이 계약과 다름"])
        return None
    value, kept = _item_checks(x)
    resolve = {"type": "resolve_item", "item_id": x["id"], "note": TEXT_ITEM_RESOLVE}
    reopen = {"type": "reopen_item", "item_id": x["id"]}

    flow.write(
        f"resolve_item({x['num']})",
        resolve,
        ("resolve", x["target"], "미해결 → 해결", TEXT_ITEM_RESOLVE),
        lambda r, b: value(r, resolved=True, note=TEXT_ITEM_RESOLVE, resolved_at=_history_at(r), resolved_by=REVIEW_ACTOR) + kept(r, b),
    )
    flow.refuse(f"resolve_item 다시({x['num']}) → 409 검토사항 상태 바뀜", resolve, 409, MSG_ITEM_STATE_CHANGED)

    def reopened(review: Mapping[str, Any], before: Mapping[str, Any]) -> list[str]:
        # 다시 열기는 resolved 만 false — 처리 내용·해결 시각·처리자는 남는다(데모 reopenItem 과 같다)
        old = (before.get("items") or {}).get(x["id"]) if isinstance(before.get("items"), Mapping) else None
        old_at = old.get("resolved_at") if isinstance(old, Mapping) else None
        problems = value(review, resolved=False, note=TEXT_ITEM_RESOLVE, resolved_at=old_at, resolved_by=REVIEW_ACTOR)
        now = (review.get("items") or {}).get(x["id"]) if isinstance(review.get("items"), Mapping) else None
        if not isinstance(now, Mapping) or _when(now.get("resolved_at")) is None:
            problems.append(f"{x['num']} resolved_at 이 남지 않음")
        return problems + kept(review, before)

    flow.write(f"reopen_item({x['num']})", reopen, ("reopenItem", x["target"], "해결 → 미해결", ""), reopened)
    flow.refuse(f"reopen_item 다시({x['num']}) → 409 검토사항 상태 바뀜", reopen, 409, MSG_ITEM_STATE_CHANGED)
    flow.write(
        f"resolve_item 다시 해결({x['num']} · 새 처리 내용)",
        {**resolve, "note": TEXT_ITEM_RESOLVE_AGAIN},
        ("resolve", x["target"], "미해결 → 해결", TEXT_ITEM_RESOLVE_AGAIN),
        lambda r, b: value(r, resolved=True, note=TEXT_ITEM_RESOLVE_AGAIN, resolved_at=_history_at(r), resolved_by=REVIEW_ACTOR)
        + kept(r, b),
    )
    ids = {i.get("id") for i in items if isinstance(i.get("id"), str)}
    unknown = f"{REVIEW_ACTOR}:없는 검토사항"
    while unknown in ids:
        unknown += "_"
    flow.refuse("없는 item_id → 404", {"type": "resolve_item", "item_id": unknown, "note": ""}, 404, MSG_ITEM_NOT_FOUND)
    flow.refuse(f"reopen_item 에 note → 400({x['num']})", {**reopen, "note": ""}, 400, MSG_REVIEW_BAD_REQUEST)
    flow.refuse(f"resolve_item 501자 처리 내용 → 400({x['num']})", {**resolve, "note": "가" * 501}, 400, MSG_REVIEW_TEXT_TOO_LONG)
    return x


def _check_locked_items(flow: _ReviewFlow, items: list[Mapping[str, Any]], resolved: Mapping[str, str] | None) -> None:
    """검토 완료(잠김) 동안 resolve_item·reopen_item → 409 잠김. 해결하지 않은 다른 검토사항이 있으면 그것을 해결하려 한다
    (상태 409 와 섞이지 않게), 다시 열기는 해결한 검토사항으로."""
    if resolved is None:
        return
    targets = (_item_target(item, n) for n, item in enumerate(items, 1) if n > 1)
    other = next((t for t in targets if t is not None and t["id"] != resolved["id"]), None) or resolved
    flow.refuse(
        f"잠김 — resolve_item({other['num']}) → 409",
        {"type": "resolve_item", "item_id": other["id"], "note": TEXT_ITEM_RESOLVE},
        409,
        MSG_REVIEW_LOCKED,
    )
    flow.refuse(f"잠김 — reopen_item({resolved['num']}) → 409", {"type": "reopen_item", "item_id": resolved["id"]}, 409, MSG_REVIEW_LOCKED)


def _check_reviews(run: Run, analysis_id: str) -> bool:
    """새로 만든 분석(done)에 검토 동작을 차례로 보내 확인한다. 기존 분석에는 부르지 않는다(_check_review_shape 만)."""
    _say(f"검토 동작 확인(이번 실행이 만든 분석에만 씀 · actor {REVIEW_ACTOR}):")
    response, first = _get(run, analysis_id)
    if response.status_code != 200 or not isinstance(first, Mapping):
        _say(f"  [실패] 00. 처음 조회 — HTTP {response.status_code}")
        return False
    targets = _review_targets(first.get("result"))
    problems = _first_review_problems(first, targets)
    if len({t["id"] for t in targets}) < 3:
        if _is_v2(first.get("result")) and not problems:  # 빈 서식·대상 외 서류처럼 탐지 항목이 적은 파일 — 보낼 대상이 없다
            _say(f"  검토 동작 확인 건너뜀(설정 60 응답 — 검토 가능 항목 {len(targets)}개)")
            return True
        problems.append(f"검토 가능 항목이 3개보다 적음({len(targets)})")
    items = _result_items(first)  # 서버가 계산한 검토사항(모양·기대값은 done 확인이 본다)
    flow = _ReviewFlow(run, analysis_id, first)
    note = f"검토 가능 항목 {len(targets)} · 검토사항 {len(items)}"
    if not flow.report("처음 조회 — needed·version 0·findings {}·items {}·S1·S2", problems, note):
        _say("검토 동작 확인: 처음 조회가 기대와 달라 동작을 보내지 않습니다")
        return False
    a, b, c = targets[0], targets[1], targets[2]
    cat = a["category"]
    new_cat = next(x for x in CATS if x != cat)
    same = flow.expect_finding
    ai = {"subject": a["subject"], "exposure": a["exposure"]}

    flow.write(
        f"set_status confirmed({a['num']})",
        {"type": "set_status", "finding_id": a["id"], "status": "confirmed", "reason": TEXT_CONFIRM},
        ("confirm", f"{a['num']} {cat}", "미확인 → 확인함", TEXT_CONFIRM),
        lambda r, _: same(r, a, status="confirmed", category=cat, **ai) + flow.touched_now(r, a),
    )
    flow.write(
        f"set_status open({a['num']})",
        {"type": "set_status", "finding_id": a["id"], "status": "open", "reason": TEXT_UNCONFIRM},
        ("unconfirm", f"{a['num']} {cat}", "확인함 → 미확인", TEXT_UNCONFIRM),
        lambda r, _: same(r, a, status="open") + flow.touched_now(r, a),
    )
    flow.write(
        f"confirm_many 2건({b['num']}, {c['num']})",
        {"type": "confirm_many", "finding_ids": [b["id"], c["id"]]},
        ("confirm", "탐지 항목 2건", "미확인 → 확인함", f"{b['num']}, {c['num']}"),
        lambda r, _: same(r, b, status="confirmed") + same(r, c, status="confirmed") + flow.touched_now(r, b) + flow.touched_now(r, c),
    )
    flow.refuse(
        f"set_status confirmed 다시({b['num']}) → 409 상태 불일치",
        {"type": "set_status", "finding_id": b["id"], "status": "confirmed", "reason": ""},
        409,
        MSG_REVIEW_STATE_CHANGED,
    )
    flow.write(
        f"mark_false_positive({a['num']})",
        {"type": "mark_false_positive", "finding_id": a["id"], "reason_type": FP_REASON, "note": TEXT_FP},
        ("fp", f"{a['num']} {a['label']}", f"{cat} → 오탐 ({FP_REASON})", TEXT_FP),
        lambda r, _: same(r, a, status="false_positive", fp_type=FP_REASON, fp_note=TEXT_FP) + flow.touched_now(r, a),
    )
    flow.write(
        f"restore → 미확인({a['num']})",
        {"type": "restore", "finding_id": a["id"], "note": TEXT_RESTORE},
        ("restore", f"{a['num']} {a['label']}", "오탐 → 미확인", TEXT_RESTORE),
        lambda r, _: same(r, a, status="open", fp_type="", fp_note="", category=cat) + flow.touched_now(r, a),
    )
    flow.write(
        f"reclassify 정보 종류({a['num']})",
        {"type": "reclassify", "finding_id": a["id"], "category": new_cat, "reason": TEXT_RECLASS},
        ("reclass", f"{a['num']} {a['label']}", f"정보 종류: {cat} → {new_cat}", TEXT_RECLASS),
        lambda r, _: same(r, a, status="reclassified", category=new_cat, reclass_note=TEXT_RECLASS, **ai) + flow.touched_now(r, a),
    )
    flow.write(
        f"reclassify 같은 값({a['num']}) → changed false",
        {"type": "reclassify", "finding_id": a["id"], "category": new_cat, "subject": a["subject"], "reason": TEXT_RECLASS},
        None,
    )
    flow.write(
        f"mark_false_positive 다시({a['num']})",
        {"type": "mark_false_positive", "finding_id": a["id"], "reason_type": FP_REASON, "note": TEXT_FP},
        ("fp", f"{a['num']} {a['label']}", f"{new_cat} → 오탐 ({FP_REASON})", TEXT_FP),
        lambda r, _: same(r, a, status="false_positive", category=new_cat) + flow.touched_now(r, a),
    )
    flow.write(
        f"restore → 분류 수정({a['num']})",
        {"type": "restore", "finding_id": a["id"], "note": TEXT_RESTORE},
        ("restore", f"{a['num']} {a['label']}", "오탐 → 분류 수정", TEXT_RESTORE),
        lambda r, _: same(r, a, status="reclassified", category=new_cat, fp_type="", fp_note="", reclass_note=TEXT_RECLASS)
        + flow.touched_now(r, a),
    )

    def memo_kept_time(text: str) -> Callable[[Mapping[str, Any], Mapping[str, Any]], list[str]]:
        # 항목 메모는 updated_at 을 바꾸지 않는다(데모와 같다)
        def check(review: Mapping[str, Any], before: Mapping[str, Any]) -> list[str]:
            old = (before.get("findings") or {}).get(a["id"]) or {}
            return same(review, a, memo=text, status="reclassified", updated_at=old.get("updated_at"))

        return check

    flow.write(
        f"save_finding_memo 저장({a['num']})",
        {"type": "save_finding_memo", "finding_id": a["id"], "text": TEXT_FINDING_MEMO},
        ("fmemo", f"{a['num']} {new_cat}", "항목 메모 저장", TEXT_FINDING_MEMO),
        memo_kept_time(TEXT_FINDING_MEMO),
    )
    flow.write(
        f"save_finding_memo 삭제({a['num']})",
        {"type": "save_finding_memo", "finding_id": a["id"], "text": ""},
        ("fmemo", f"{a['num']} {new_cat}", "항목 메모 삭제", ""),
        memo_kept_time(""),
    )

    def memo_check(review: Mapping[str, Any], _before: Mapping[str, Any]) -> list[str]:
        problems = [] if review.get("memo") == TEXT_MEMO else ["memo 가 저장한 글과 다름"]
        if _when(review.get("memo_at")) is None or _when(review.get("memo_at")) != flow.last_at(review):
            problems.append("memo_at 이 이번 동작 시각이 아님")
        return problems

    flow.write(
        "save_memo",
        {"type": "save_memo", "text": TEXT_MEMO},
        ("memo", ANALYSIS_TARGET, "검토 메모 저장", TEXT_MEMO),
        memo_check,
    )

    # 검토사항 해결·다시 열기(review-items §5.6) — 끝에 첫 검토사항 하나가 해결된 상태(검토사항 0개면 건너뜀,
    # result.items 모양이 계약과 다르면 값 없는 실패 위치만 적고 보내지 않음)
    resolved = _check_item_actions(flow, first.get("result"))

    findings_now = flow.review.get("findings") if isinstance(flow.review.get("findings"), Mapping) else {}
    left = sum(1 for t in targets if ((findings_now.get(t["id"]) or {}).get("status") or "open") == "open")
    # 미해결 검토사항(review-items §5.6) = 검토사항 수 − 이 흐름이 해결한 1개(서버 값이 아니라 이 흐름이 보낸 동작으로 센다)
    open_items = len(items) - (1 if resolved is not None else 0)
    rest_parts = ([f"미확인 탐지 {left}건"] if left else []) + ([f"미해결 검토사항 {open_items}건"] if open_items else [])
    rest = f" (남은 항목: {', '.join(rest_parts)})" if rest_parts else ""

    def complete_check(review: Mapping[str, Any], _before: Mapping[str, Any]) -> list[str]:
        problems = [
            f"{key}: 계약과 다름"
            for key, value in {"status": "done", "reviewer": REVIEW_ACTOR, "completion_note": TEXT_COMPLETE}.items()
            if review.get(key) != value
        ]
        if _when(review.get("reviewed_at")) is None or _when(review.get("reviewed_at")) != flow.last_at(review):
            problems.append("reviewed_at 이 이번 동작 시각이 아님")
        return problems

    flow.write(
        f"complete_review(남은 미확인 {left}건 · 미해결 검토사항 {open_items}건)",
        {"type": "complete_review", "note": TEXT_COMPLETE},
        ("complete", ANALYSIS_TARGET, f"검토 대기 → 검토 완료{rest}", TEXT_COMPLETE),
        complete_check,
    )
    flow.refuse(
        f"잠김 — set_status open({b['num']}) → 409",
        {"type": "set_status", "finding_id": b["id"], "status": "open", "reason": ""},
        409,
        MSG_REVIEW_LOCKED,
    )
    flow.refuse("이미 완료 — complete_review → 409", {"type": "complete_review", "note": ""}, 409, MSG_REVIEW_ALREADY_DONE)
    _check_locked_items(flow, items, resolved)  # 잠긴 채 resolve_item·reopen_item → 409 잠김

    # 내보내기 기록(log_export) — 검토 완료로 잠긴 상태에서도 된다. 이력 한 줄 + version 만, review 의 다른 값은 그대로.
    names = {fmt: _export_name(first, fmt) for fmt in EXPORT_SUFFIXES}
    wrong_name = _export_name(first, "csv", shift_days=1)
    csv_name, json_name = names["csv"], names["json"]
    if csv_name is None or json_name is None or wrong_name is None:
        flow.report("log_export — 이 분석의 파일 이름", ["created_at 을 읽을 수 없어 기대 파일 이름을 만들 수 없음"])
    else:

        def export_kept(review: Mapping[str, Any], before: Mapping[str, Any]) -> list[str]:
            # 잠김과 무관: 이력·version 말고는 바뀌지 않는다(검토 상태 done·항목 값·메모·검토자·완료 시각)
            problems = [f"review {key} 가 바뀜" for key in sorted(REVIEW_KEYS - {"history", "version"}) if review.get(key) != before.get(key)]
            if review.get("status") != "done":
                problems.append(f"status {_shown(review.get('status'), REVIEW_STATUSES)}(기대 done — 잠긴 상태 그대로)")
            return problems

        for fmt, size, state in (("csv", EXPORT_CSV_SIZE, "handed"), ("json", EXPORT_JSON_SIZE, "saved")):
            name = names[fmt]
            label = fmt.upper()
            flow.write(
                f"log_export {label}·{state}(잠긴 상태 · {size:,} B → {_fmt_size(size)})",
                {"type": "log_export", "format": fmt, "size": size, "state": state, "file_name": name},
                (EXPORT_KIND, name, f"{label} · {_fmt_size(size)} · {EXPORT_STATES[state]}", EXPORT_REASON),
                export_kept,
            )
        flow.refuse(
            "log_export 이 분석의 이름이 아님(서울 날짜 하루 다름) → 400",
            {"type": "log_export", "format": "csv", "size": EXPORT_CSV_SIZE, "state": "handed", "file_name": wrong_name},
            400,
            MSG_REVIEW_BAD_REQUEST,
        )
        flow.refuse(
            "log_export size 0 → 400",
            {"type": "log_export", "format": "csv", "size": 0, "state": "handed", "file_name": csv_name},
            400,
            MSG_REVIEW_BAD_REQUEST,
        )

    def reopen_check(review: Mapping[str, Any], before: Mapping[str, Any]) -> list[str]:
        want = {"status": "needed", "reviewed_at": None, "reviewer": REVIEW_ACTOR, "completion_note": TEXT_COMPLETE, "memo": TEXT_MEMO}
        problems = [f"{key}: 계약과 다름" for key, value in want.items() if review.get(key) != value]
        if review.get("items") != before.get("items"):  # 다시 열기는 검토사항 해결 기록을 바꾸지 않는다
            problems.append("review items 가 바뀜")
        return problems

    flow.write(
        "reopen_review(reviewer·completion_note 남음, reviewed_at null)",
        {"type": "reopen_review", "reason": TEXT_REOPEN},
        ("reopen", ANALYSIS_TARGET, "검토 완료 → 검토 대기", TEXT_REOPEN),
        reopen_check,
    )
    flow.refuse("모르는 type → 400", {"type": "delete_everything"}, 400, MSG_REVIEW_BAD_REQUEST)
    flow.refuse("501자 글 → 400", {"type": "save_memo", "text": "가" * 501}, 400, MSG_REVIEW_TEXT_TOO_LONG)

    # 마지막: 이력 id 연속·시간 순서·줄 수 = 쓴 동작 수·분석 시각 불변
    response, last = _get(run, analysis_id)
    problems = []
    if response.status_code != 200 or not isinstance(last, Mapping) or not isinstance(last.get("review"), Mapping):
        problems.append(f"마지막 조회: HTTP {response.status_code}")
        history: list[Any] = []
        version: Any = None
    else:
        review = last["review"]
        history = review.get("history") if isinstance(review.get("history"), list) else []
        version = review.get("version")
        stored = history[2:]
        ids = [line.get("id") if isinstance(line, Mapping) else None for line in stored]
        if ids != [f"H{i}" for i in range(1, len(stored) + 1)]:
            problems.append("이력 id 가 H1…Hn 연속이 아님")
        times = [_when(line.get("at")) if isinstance(line, Mapping) else None for line in history]
        if any(t is None for t in times):
            problems.append("이력 at 을 읽을 수 없는 줄이 있음")
        elif any(later < earlier for earlier, later in zip(times, times[1:], strict=False)):
            problems.append("이력 at 이 줄어드는 곳이 있음")
        if not (len(stored) == flow.expected_writes == flow.writes == version):
            problems.append(f"저장 이력 {len(stored)}줄 · 쓴 동작 {flow.writes} · 기대 {flow.expected_writes} · version {_shown(version)}")
        for key in ("created_at", "updated_at", "started_at"):
            if last.get(key) != first.get(key):
                problems.append(f"분석 {key} 가 처음 조회와 다름")
        if review.get("status") != "needed":
            problems.append(f"status {_shown(review.get('status'), REVIEW_STATUSES)}(기대 needed)")
        # 검토사항 해결 기록: 해결한 그 검토사항 하나만, 마지막 해결 값(다시 해결한 처리 내용) 그대로
        saved_items = review.get("items") if isinstance(review.get("items"), Mapping) else None
        want_ids = {resolved["id"]} if resolved is not None else set()
        if saved_items is None or set(saved_items) != want_ids:
            problems.append(f"review items 의 검토사항 수가 {len(saved_items) if saved_items is not None else '?'}개(기대 {len(want_ids)}개)")
        elif resolved is not None:
            value = saved_items[resolved["id"]]
            if not (_review_item_ok(value) and value["resolved"] is True and value["note"] == TEXT_ITEM_RESOLVE_AGAIN and value["resolved_by"] == REVIEW_ACTOR):
                problems.append(f"{resolved['num']}: 마지막 해결 값(해결 · 다시 해결한 처리 내용 · 처리자)이 아님")
    flow.report(
        "마지막 — 이력 H1…Hn 연속·시간 순서·줄 수 = 쓴 동작 수·분석 created_at·updated_at·started_at 그대로·검토사항 해결 기록",
        problems,
        f"이력 {len(history)}줄(S1·S2 포함) · 쓴 동작 {flow.writes} · version {_shown(version)}",
    )
    ok = flow.failed == 0
    _say(f"검토 동작 확인: {flow.steps - flow.failed}/{flow.steps} 통과 · 쓴 동작 {flow.writes}건 — {'기대대로' if ok else '기대와 다름'}")
    return ok


def _check_review_shape(run: Run, analysis_id: str) -> bool:
    """--analysis-id: 기존 분석은 **읽기만** — review 블록 모양(status·findings·items·history S1·S2·version)만 본다(POST 없음)."""
    response, row = _get(run, analysis_id)
    if response.status_code != 200 or not isinstance(row, Mapping):
        run.log(f"검토 기록 모양: 조회 실패 HTTP {response.status_code}")
        return False
    targets = _review_targets(row.get("result"))
    problems = _review_shape_problems(row, targets)
    review = row.get("review") if isinstance(row.get("review"), Mapping) else {}
    history = review.get("history") if isinstance(review.get("history"), list) else []
    findings = review.get("findings") if isinstance(review.get("findings"), Mapping) else {}
    items = review.get("items") if isinstance(review.get("items"), Mapping) else {}
    default = review.get("status") == "needed" and findings == {} and items == {} and len(history) == 2 and review.get("version") == 0
    _say(
        f"검토 기록 모양(읽기만, 동작 보내지 않음): status={_plain(review.get('status'), REVIEW_STATUSES)} · findings {len(findings)}개 · "
        f"검토사항 해결 기록 {len(items)}개 · "
        f"이력 {len(history)}줄(S1·S2 포함) · version {_shown(review.get('version'))} · 기본값(검토 행 없음) {default}: "
        f"{'맞음' if not problems else f'문제 {len(problems)}개'}"
    )
    for problem in problems[:6]:
        _say(f"    - {_short(problem)}")
    return not problems


# --- 공유 목록·삭제·다시 분석 확인(shared-analyses) ---------------------------------------------
# 기대값은 계약(BRIEF §5.2~5.5)을 그대로 적어 조회 응답에서 만든다(백엔드 함수를 가져다 쓰지 않음).


def _after(later: Any, earlier: Any) -> bool:
    """두 ISO 시각을 읽어 later 가 earlier 보다 뒤인지. 하나라도 못 읽으면 False."""
    a, b = _when(later), _when(earlier)
    return a is not None and b is not None and a > b


def _list_expected(row: Mapping[str, Any]) -> dict[str, Any]:
    """조회 응답(AnalysisOut)에서 계약대로 만든 목록 항목 기대값(BRIEF §5.2)."""
    status = row.get("status")
    result = row.get("result") if isinstance(row.get("result"), Mapping) else {}
    summary = result.get("summary") if isinstance(result.get("summary"), Mapping) else {}
    risk = summary.get("risk_level")
    count = summary.get("document_count")
    if status == "done" and _is_int(count) and count >= 1:
        review = row.get("review")
        state = "done" if isinstance(review, Mapping) and review.get("status") == "done" else "needed"
    else:
        state = "none"
    documents = _documents(row)
    documents.sort(key=lambda d: (str(d.get("created_at") or ""), str(d.get("id") or "")))
    return {
        "id": row.get("id"),
        "name": row.get("name"),
        "status": status,
        "error": row.get("error"),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
        "started_at": row.get("started_at"),
        "documents": [{key: d.get(key) for key in ("filename", "size_bytes", "mime_type")} for d in documents],
        "risk_level": risk if isinstance(risk, str) else None,
        "review": state,
        "document_count": count if _is_int(count) and count >= 0 else None,  # 분류한 서류 수(bool 아닌 정수 ≥ 0, 그 밖 null)
    }


def _check_list(run: Run, analysis_id: str, label: str) -> bool:
    """GET /api/py/analyses — 모양(키·result 없음·순서)과 이 분석의 항목 = 조회 응답에서 만든 기대값. 다른 분석의 값은 출력하지 않는다."""
    detail, row = _get(run, analysis_id)
    if detail.status_code != 200 or not isinstance(row, Mapping):
        _say(f"목록 확인({label}): 기대값을 만들 조회 실패 HTTP {detail.status_code}: 실패")
        return False
    expected = _list_expected(row)
    response = run.call("GET", LIST_PATH)
    try:
        body = response.json()
    except ValueError:
        body = None
    problems: list[str] = _documents_problems(row, "기대값을 만든 조회 응답의 documents")
    items: list[Any] = []
    if response.status_code != 200 or not isinstance(body, Mapping) or set(body) != {"analyses"} or not isinstance(body["analyses"], list):
        problems.append(f"HTTP {response.status_code} · 응답 모양이 {{\"analyses\": [...]}} 가 아님")
    else:
        items = body["analyses"]
    with_result = sum(1 for item in items if isinstance(item, Mapping) and "result" in item)
    bad_items = sum(1 for item in items if not (isinstance(item, Mapping) and set(item) == LIST_ITEM_KEYS))
    bad_docs = sum(
        1
        for item in items
        if isinstance(item, Mapping)
        and not (isinstance(item.get("documents"), list) and all(isinstance(d, Mapping) and set(d) == LIST_DOC_KEYS for d in item["documents"]))
    )
    if with_result:
        problems.append(f"result 키가 있는 항목 {with_result}개")
    if bad_items:
        problems.append(f"키가 계약(11개)과 다른 항목 {bad_items}개")
    if bad_docs:
        problems.append(f"문서 키가 계약(filename·size_bytes·mime_type)과 다른 항목 {bad_docs}개")
    order = [(_when(item.get("created_at")), str(item.get("id"))) for item in items if isinstance(item, Mapping)]
    if any(moment is None for moment, _ in order):
        problems.append("created_at 을 읽을 수 없는 항목이 있음")
    elif any(later > earlier for earlier, later in zip(order, order[1:], strict=False)):
        problems.append("created_at desc, id desc 순서가 아님")
    mine = [item for item in items if isinstance(item, Mapping) and item.get("id") == analysis_id]
    if len(mine) != 1:
        problems.append(f"이 분석이 목록에 {len(mine)}번 있음(기대 1번)")
    else:
        differs = sorted(key for key in set(expected) | set(mine[0]) if mine[0].get(key) != expected.get(key))
        if differs:
            problems.append(f"이 분석의 항목이 조회 응답과 다름 {differs}")
    item = mine[0] if len(mine) == 1 else {}
    ok = not problems
    _say(
        f"목록 확인({label}): GET {LIST_PATH} HTTP {response.status_code} · {len(items)}건 · {len(response.content):,} bytes"
        f" · result 키 있는 항목 {with_result} · 이 분석 status={item.get('status')} review={item.get('review')}"
        f" risk_level={item.get('risk_level')} 문서 {len(_documents(item))}개: {'통과' if ok else '실패'}"
    )
    for problem in problems[:6]:
        _say(f"    - {_short(problem)}")
    return ok


def _body(response: httpx.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return None


def _retry(run: Run, analysis_id: str) -> tuple[httpx.Response, Any]:
    """POST …/retry 본문 {"actor": "api_e2e"}(검토 동작과 같은 JSON 직렬화).

    작업을 만들 수 있는 요청이라 보내기 전에 '시작 결과 미확인'을 적고(run.begin_start), 응답을 받으면 관찰한다(settle_start).
    응답을 잃으면(예외가 그대로 올라감) 미확인이 남아 정리 단계가 그 분석을 다시 읽어 새 Upstage 파일까지 지운다."""
    run.begin_start()
    response = run.call(
        "POST",
        f"/api/py/analyses/{analysis_id}/retry",
        content=_json_body({"actor": REVIEW_ACTOR}),
        headers={"content-type": "application/json"},
    )
    body = _body(response)
    run.settle_start(response.status_code, body)
    return response, body


def _refused(response: httpx.Response, status: int, detail: str) -> list[str]:
    body = _body(response)
    got = body.get("detail") if isinstance(body, Mapping) else None
    return [] if response.status_code == status and got == detail else [f"HTTP {response.status_code} {_detail(response)}(기대 {status} {detail})"]


def _documents(row: Any) -> list[Mapping[str, Any]]:
    """응답의 documents 를 정규화 — 목록이 아니면 [], 객체가 아닌 항목은 뺀다(모양 판정은 _documents_problems)."""
    documents = row.get("documents") if isinstance(row, Mapping) else None
    return [d for d in documents if isinstance(d, Mapping)] if isinstance(documents, list) else []


def _documents_problems(row: Any, where: str = "documents") -> list[str]:
    """documents 가 목록이 아니거나 객체가 아닌 항목이 있으면 그 확인의 문제로(예외를 내지 않는다)."""
    documents = row.get("documents") if isinstance(row, Mapping) else None
    if not isinstance(documents, list):
        return [f"{where} 가 목록이 아님({type(documents).__name__})"]
    bad = sum(1 for d in documents if not isinstance(d, Mapping))
    return [f"{where} 에 객체가 아닌 항목 {bad}개"] if bad else []


def _file_ids(row: Mapping[str, Any]) -> list[str]:
    return [str(d["upstage_file_id"]) for d in _documents(row) if d.get("upstage_file_id")]


def _not_started_problems(row: Mapping[str, Any]) -> list[str]:
    """시작하지 못한 실패(원본 없음): failed + 그 이유, Upstage 작업·file id·result 없음, review null."""
    problems: list[str] = _documents_problems(row)
    if row.get("status") != "failed":
        problems.append(f"status {row.get('status')!r}(기대 failed)")
    if row.get("error") != MSG_FILE_MISSING:
        problems.append(f"error {_short(row.get('error'))!r}(기대 {MSG_FILE_MISSING!r})")
    if row.get("upstage_job_id") is not None:
        problems.append("upstage_job_id 가 있음(Upstage 작업을 만듦)")
    if _file_ids(row):
        problems.append("upstage_file_id 가 있음(Upstage 에 올림)")
    if row.get("result") is not None:
        problems.append("result 가 null 이 아님")
    if row.get("review") is not None:
        problems.append("review 가 null 이 아님(실패 분석은 검토 블록 없음)")
    return problems


def _check_delete(run: Run, analysis_id: str) -> bool:
    """이번 실행이 만든 분석을 지우고 그 뒤 모든 경로가 404 인지 본다(BRIEF §5.3·§5.6).

    지운 것이 확인되지 않으면(첫 DELETE 가 204·빈 본문이 아님, 또는 그 뒤 GET·/file·목록이 아직 있음을 보임) 상태를 바꾸는
    확인('지운 분석 다시 분석' · 두 번째 DELETE)을 보내지 않고 실패로 끝낸다 — 남은 분석에 작업(크레딧)을 만들지 않게.
    완료 표식(run.deleted)도 없음을 확인한 뒤에만 단다(아니면 finally 가 다시 지우고 확인한다)."""
    _say("삭제 확인(이번 실행이 만든 분석):")
    checks = _Checklist()
    path = f"/api/py/analyses/{analysis_id}"
    try:
        first = run.call("DELETE", path)
    except httpx.HTTPError as exc:  # 지웠는지 모른다 — 확인 실패로 끝내고 finally 가 다시 지운다
        checks.report("DELETE → 204(본문 없음)", [f"연결 오류 {type(exc).__name__}"])
        _say("  지워지지 않아 나머지 확인(다시 분석 404 등)을 보내지 않습니다")
        return checks.summary("삭제 확인")
    accepted = first.status_code == 204 and first.content == b""
    checks.report("DELETE → 204(본문 없음)", [] if accepted else [f"HTTP {first.status_code} · 본문 {len(first.content)} bytes(기대 204 · 본문 없음)"])
    if not accepted:
        _say("  지워지지 않아 나머지 확인(다시 분석 404 등)을 보내지 않습니다")
        return checks.summary("삭제 확인")
    gone = checks.report("GET → 404", _refused(run.call("GET", path), 404, MSG_NOT_FOUND))
    gone = checks.report("GET …/file → 404", _refused(run.call("GET", f"{path}/file"), 404, MSG_NOT_FOUND)) and gone
    listed = run.call("GET", LIST_PATH)
    body = _body(listed)
    items = body.get("analyses") if isinstance(body, Mapping) else None
    if listed.status_code != 200 or not isinstance(items, list):
        problems = [f"목록 HTTP {listed.status_code}"]
    else:
        problems = [] if not any(isinstance(i, Mapping) and i.get("id") == analysis_id for i in items) else ["목록에 아직 있음"]
    gone = checks.report("목록에 없음", problems, f"{len(items) if isinstance(items, list) else '?'}건") and gone
    if not gone:
        _say("  204 를 받았지만 지워진 것을 확인하지 못해 나머지 확인(다시 분석 404 등)을 보내지 않습니다")
        return checks.summary("삭제 확인")
    run.deleted = True  # 없음을 확인한 뒤에만
    response, _ = _retry(run, analysis_id)
    checks.report("지운 분석 다시 분석 → 404(Upstage 없음)", _refused(response, 404, MSG_NOT_FOUND))
    checks.report("두 번째 DELETE → 404", _refused(run.call("DELETE", path), 404, MSG_NOT_FOUND))
    return checks.summary("삭제 확인")


def _retry_step(
    run: Run,
    checks: _Checklist,
    name: str,
    analysis_id: str,
    created_at: Any,
    previous_start: Any,
    keys: set[str],
    *,
    started: bool,
) -> Mapping[str, Any] | None:
    """다시 분석 한 번. started=True 면 running·새 작업, False 면 원본 없음으로 다시 실패(조회와 같은 값)."""
    response, body = _retry(run, analysis_id)  # 200 분석 건이면 _retry 가 이미 관찰했다(file id · 끝남)
    if response.status_code != 200 or not isinstance(body, Mapping):
        checks.report(name, [f"HTTP {response.status_code} {_detail(response)}(기대 200 분석 건)"])
        return None
    problems: list[str] = []
    if set(body) != keys:
        problems.append(f"응답 키가 시작·조회 응답과 다름 {sorted(set(body) ^ keys)}")
    if body.get("created_at") != created_at:
        problems.append("created_at 이 바뀜(요청 시각·분석 번호·목록 순서 기준)")
    if not _after(body.get("started_at"), previous_start):
        problems.append("started_at 이 앞 시작보다 뒤가 아님")
    if body.get("upstage_status") is not None or body.get("poll_error") is not None:
        problems.append("upstage_status·poll_error 가 null 이 아님")
    if started:
        problems += _documents_problems(body)
        if body.get("status") != "running":
            problems.append(f"status {body.get('status')!r}(기대 running) · error {_short(body.get('error'))!r}")
        if not body.get("upstage_job_id"):
            problems.append("upstage_job_id 없음(작업을 만들지 않음)")
        if not _file_ids(body):
            problems.append("upstage_file_id 없음(Upstage 에 올리지 않음)")
        if body.get("error") is not None or body.get("result") is not None or body.get("review") is not None:
            problems.append("error·result·review 가 null 이 아님")
    else:
        problems += _not_started_problems(body)
        reread, again = _get(run, analysis_id)  # 실패 분석의 조회는 Upstage 를 부르지 않는다
        if reread.status_code != 200 or again != body:
            problems.append("다시 조회한 값이 다시 분석 응답과 다름")
    note = f"status {body.get('status')} · 작업 {'있음' if body.get('upstage_job_id') else '없음'} · created_at 그대로 {body.get('created_at') == created_at}"
    checks.report(name, problems, note)
    return body


def _check_retry_history(
    run: Run, checks: _Checklist, analysis_id: str, reasons: list[Any], marks: list[Any], *, act: bool
) -> None:
    """done 뒤 검토 이력: [S1, retry 줄(사유 = 앞 실패 이유), S2] — 그리고 검토 동작 하나 뒤 [S1, H…, S2, H(n+1)]."""
    response, row = _get(run, analysis_id)
    if response.status_code != 200 or not isinstance(row, Mapping) or not isinstance(row.get("review"), Mapping):
        checks.report("검토 이력 — S1 · 다시 분석 줄 · S2", [f"조회 HTTP {response.status_code} · review 가 객체가 아님"])
        return
    review = row["review"]
    targets = _review_targets(row.get("result"))
    s1, s2 = _system_lines(row, targets)
    documents = _documents(row)
    filename = documents[0].get("filename") if documents else None
    target = _stored_target(filename if isinstance(filename, str) and _js_trim(filename) else ANALYSIS_TARGET)
    retries = [
        {
            "id": f"H{number}",
            "actor": REVIEW_ACTOR,
            "kind": RETRY_KIND,
            "target": target,
            "change": RETRY_CHANGE,
            "reason": _stored_text(reason if isinstance(reason, str) else "", REASON_MAX),
        }
        for number, reason in enumerate(reasons, 1)
    ]
    history = review.get("history") if isinstance(review.get("history"), list) else []
    problems: list[str] = _documents_problems(row)
    wants = [s1, *retries, s2]
    if len(history) != len(wants):
        problems.append(f"이력 {len(history)}줄(기대 S1 · 다시 분석 {len(retries)}줄 · S2 = {len(wants)}줄)")
    else:
        for line, want in zip(history, wants, strict=True):
            problems += _line_problems(line, want, str(want["id"]))
    times = [_when(line.get("at")) if isinstance(line, Mapping) else None for line in history]
    if any(t is None for t in times):
        problems.append("이력 at 을 읽을 수 없는 줄이 있음")
    elif any(later < earlier for earlier, later in zip(times, times[1:], strict=False)):
        problems.append("이력 at 이 줄어드는 곳이 있음")
    for number, line in enumerate(history[1 : 1 + len(retries)], 1):
        at = line.get("at") if isinstance(line, Mapping) else None
        before, after = marks[number - 1], marks[number]
        if not (_after(at, before) and not _after(at, after)):
            problems.append(f"H{number} at 이 그 다시 분석의 앞 시작 뒤 · 새 시작 이전이 아님")
    if review.get("version") != len(retries) or review.get("status") != "needed" or review.get("findings") != {}:
        problems.append(f"version {review.get('version')!r}(기대 {len(retries)}) · status · findings 가 기본값이 아님")
    checks.report(
        f"검토 이력 — [S1, 다시 분석 {len(retries)}줄(사유 = 앞 실패 이유), S2] · at 이 줄지 않음",
        problems,
        f"이력 {len(history)}줄 · version {_shown(review.get('version'))}",
    )
    if not act:
        _say("  검토 동작 하나 뒤 이력 순서 확인 건너뜀(--no-review)")
        return
    if not targets:
        if _is_v2(row.get("result")):  # 설정 60 응답은 탐지 항목이 없는 파일도 있다(빈 서식·대상 외 서류)
            _say("  검토 동작 하나 뒤 이력 순서 확인 건너뜀(설정 60 응답 — 검토 가능 항목 0개)")
            return
        checks.report("검토 동작 하나 뒤 이력 순서", ["검토 가능 항목 없음"])
        return
    flow = _ReviewFlow(run, analysis_id, row, checks)
    a = targets[0]
    flow.write(
        f"set_status confirmed({a['num']}) — 새 줄은 S2 뒤",
        {"type": "set_status", "finding_id": a["id"], "status": "confirmed", "reason": TEXT_CONFIRM},
        ("confirm", f"{a['num']} {a['category']}", "미확인 → 확인함", TEXT_CONFIRM),
        lambda r, _: flow.expect_finding(r, a, status="confirmed") + flow.touched_now(r, a),
    )
    response, last = _get(run, analysis_id)
    last_review = last.get("review") if isinstance(last, Mapping) else None
    lines = last_review.get("history") if isinstance(last_review, Mapping) and isinstance(last_review.get("history"), list) else []
    ids = [line.get("id") if isinstance(line, Mapping) else None for line in lines]
    want_ids = ["S1", *[r["id"] for r in retries], "S2", f"H{len(retries) + 1}"]
    problems = [] if ids == want_ids else [f"이력 id 순서 {ids}(기대 {want_ids})"]
    times = [_when(line.get("at")) if isinstance(line, Mapping) else None for line in lines]
    if any(t is None for t in times) or any(later < earlier for earlier, later in zip(times, times[1:], strict=False)):
        problems.append("이력 at 이 줄어들거나 읽을 수 없음")
    checks.report(f"검토 동작 뒤 이력 — {want_ids} · at 이 줄지 않음", problems)


def _check_upstage_files(run: Run, documents: list[Mapping[str, Any]]) -> bool | None:
    """(정상 종료 때) 서버가 Upstage 파일을 지웠는지(GET /files/{id} 404). 키가 없으면 None(확인 안 함)."""
    key = run.upstage_key()
    file_ids = [d.get("upstage_file_id") for d in documents if d.get("upstage_file_id")]
    if not file_ids:
        run.log("Upstage 파일 확인: 올린 파일 없음")
        return True
    if not key:
        run.log("Upstage 파일 확인: UPSTAGE_API_KEY 가 없어 건너뜀")
        return None
    _hide(key, "<UPSTAGE_API_KEY>")
    ok = True
    with UpstageClient(key, run.upstage_base(), project_id=run.upstage_project()) as client:
        for file_id in file_ids:
            exists = client.file_exists(str(file_id))
            state = {True: "아직 있음", False: "지워짐(404)", None: "확인 실패"}.get(exists, "확인 실패")
            run.log(f"Upstage 파일 {file_id}: {state}")
            ok = ok and exists is False
    return ok


def _reread_for_cleanup(run: Run) -> bool:
    """정리에 필요한 file id 를 얻으려고 분석을 한 번 다시 읽는다. 상태·파일 여부를 확인했으면 True."""
    try:
        response = run.call("GET", f"/api/py/analyses/{run.analysis_id}")
    except httpx.HTTPError as exc:
        run.log(f"정리: 분석을 다시 읽지 못했습니다({type(exc).__name__})")
        return False
    if response.status_code != 200:
        run.log(f"정리: 분석을 다시 읽지 못했습니다(HTTP {response.status_code})")
        return False
    try:
        row = response.json()
    except ValueError:
        run.log("정리: 분석을 다시 읽었지만 응답 모양이 다릅니다")
        return False
    if not isinstance(row, Mapping):
        run.log("정리: 분석을 다시 읽었지만 응답 모양이 다릅니다")
        return False
    run.observe(row)  # 앞에서 모은 file id 는 그대로 두고 더한다
    run.start_pending = False
    # 끝났으면 서버가 정리했고, 지금 행에 file id 가 있으면 여기서 지운다. 둘 다 아니면 시작(다시 분석)이 서버에서 아직
    # 돌거나 응답이 일부만 왔을 수 있어 Upstage 에 파일이 남았는지 알 수 없다(앞 실행의 file id 만으로는 판단하지 않는다).
    return run.terminal or bool(_file_ids(row))


def _cleanup(run: Run) -> bool:
    """모든 종료 경로의 finally — 이번 실행이 Upstage 에 남겼을 수 있는 파일을 지운다(404 = 성공).

    '시작 응답을 받았다'와 '정리에 필요한 file id 를 확보했다'는 다르다: 시작을 요청한 분석이 끝나지 않았고
    file id 도 모르면(응답을 받았더라도) 분석을 한 번 다시 읽어 확보한다. /start·/retry 의 응답을 관찰하지 못했으면
    (start_pending — 앞에서 끝난 것으로 보았어도, file id 를 이미 모았어도) 늘 다시 읽어 새 file id 를 더한다.
    그래도 상태·파일 여부를 확인할 수 없으면 정리 성공으로 치지 않는다(False → 종료 코드 1). 정리를 못 해도 False.
    """
    if run.analysis_id is None or not run.start_requested:
        return True  # 시작하지 않았으면 Upstage 에 올린 것이 없다
    known = True
    if run.start_pending or (not run.terminal and not run.file_ids):
        known = _reread_for_cleanup(run)
        if not known:
            run.log("정리 확인 못 함: 시작한 분석이 Upstage 에 파일을 남겼는지 확인하지 못했습니다")
    if not run.file_ids:
        return known
    key = run.upstage_key()
    count = len(run.file_ids)
    if not key:
        if run.terminal:
            # 끝난 분석의 파일은 서버(조회)가 이미 지웠다
            run.log("정리: UPSTAGE_API_KEY 가 없어 건너뜀(끝난 분석의 파일은 서버가 지움)")
            return known
        run.log(f"정리 못 함: UPSTAGE_API_KEY 가 없어 Upstage 파일 {count}개를 지우지 못했습니다")
        return False
    _hide(key, "<UPSTAGE_API_KEY>")
    ok = True
    with UpstageClient(key, run.upstage_base(), project_id=run.upstage_project()) as client:
        for file_id in run.file_ids:
            try:
                if not client.delete_file(file_id):
                    run.log(f"정리 못 함: Upstage 파일 {file_id} 삭제가 거절됐습니다")
                    ok = False
            except UpstageError as exc:
                # 바깥 문구는 내보내지 않는다(클라이언트가 이미 잘랐을 수 있어서) — 상태 코드만
                shown = f"HTTP {exc.status_code}" if exc.status_code else "연결 오류"
                run.log(f"정리 못 함: Upstage 파일 {file_id}: {shown}")
                ok = False
    if ok:
        run.log(f"정리: Upstage 파일 {count}개 삭제 요청 완료(이미 지워졌으면 404 = 성공)")
    return ok and known


def _remove_created(run: Run) -> bool:
    """finally — 이번 실행이 만든 분석을 지운다(기본). --keep·--fail-with-original 이면 남긴다. 204·404 = 성공."""
    if run.analysis_id is None or not run.created:
        return True
    if run.deleted:
        run.log("정리: 이번 실행이 만든 분석은 삭제 확인에서 지웠습니다(없음 확인)")
        return True
    if run.keep:
        run.log(f"정리: 이번 실행이 만든 분석을 남깁니다: {run.analysis_id}")
        return True
    try:
        response = run.call("DELETE", f"/api/py/analyses/{run.analysis_id}")
    except httpx.HTTPError as exc:
        run.log(f"정리 못 함: 이번 실행이 만든 분석을 지우지 못했습니다({type(exc).__name__}): {run.analysis_id}")
        return False
    if response.status_code == 404:
        run.log("정리: 이번 실행이 만든 분석이 이미 없습니다(DELETE 404)")
        return True
    if response.status_code != 204:
        run.log(f"정리 못 함: 이번 실행이 만든 분석을 지우지 못했습니다(HTTP {response.status_code} {_detail(response)}): {run.analysis_id}")
        return False
    # 204 만으로 지웠다고 적지 않는다 — 다시 읽어 없음(404)을 확인한다
    try:
        check = run.call("GET", f"/api/py/analyses/{run.analysis_id}")
    except httpx.HTTPError as exc:
        run.log(f"정리 못 함: DELETE 204 뒤 지워졌는지 확인하지 못했습니다({type(exc).__name__}): {run.analysis_id}")
        return False
    if check.status_code != 404:
        run.log(f"정리 못 함: DELETE 204 를 받았지만 분석이 아직 있습니다(GET HTTP {check.status_code}): {run.analysis_id}")
        return False
    run.deleted = True
    run.log("정리: 이번 실행이 만든 분석을 지웠습니다(DELETE 204 · 다시 읽어 404)")
    return True


def _poll(run: Run, args: argparse.Namespace, analysis_id: str, row: Any) -> Any:
    """끝날 때까지 interval 마다 조회(상태가 바뀔 때만 한 줄). 시간 초과면 None."""
    seen = (row["status"], row.get("upstage_status"), row.get("poll_error"))
    deadline = time.monotonic() + args.timeout
    while row["status"] not in TERMINAL:
        if time.monotonic() > deadline:
            run.log(f"시간 초과({args.timeout}s) — 마지막 상태 {row['status']}")
            return None
        time.sleep(args.interval)
        polled = run.call("GET", f"/api/py/analyses/{analysis_id}")
        if polled.status_code != 200:
            run.log(f"조회 실패: HTTP {polled.status_code} {_detail(polled)}")
            continue
        row = polled.json()
        run.observe(row)
        state = (row["status"], row.get("upstage_status"), row.get("poll_error"))
        if state != seen:
            extra = f" upstage={row.get('upstage_status')}" if row.get("upstage_status") else ""
            extra += f" poll_error={row['poll_error']!r}" if row.get("poll_error") else ""
            run.log(f"조회: 상태={row['status']}{extra}")
            seen = state
    return row


def _print_verdicts(run: Run) -> None:
    """확인 묶음마다 한 줄 — 새 확인(목록·다시 분석·삭제)은 따로 모아 판정한다(고정 기대값 문제와 섞이지 않게)."""
    if not run.verdicts:
        return
    _say("확인 요약:")
    for name, passed, new in run.verdicts:
        _say(f"  {'[새] ' if new else ''}{name}: {'통과' if passed else '실패'}")
    news = [passed for _, passed, new in run.verdicts if new]
    if news:
        _say(f"새 확인(목록·다시 분석·삭제): {sum(news)}/{len(news)} 통과 — {'기대대로' if all(news) else '기대와 다름'}")


def _delete_or_keep(run: Run, analysis_id: str) -> bool:
    if run.keep:
        _say("삭제 확인 건너뜀(--keep — 이번 실행이 만든 분석을 남김)")
        return True
    return run.verdict("삭제", _check_delete(run, analysis_id), new=True)


def _flow_retry(
    run: Run, args: argparse.Namespace, analysis_id: str, upload: Mapping[str, str], content: bytes, mime_type: str, row: Mapping[str, Any]
) -> int:
    """--retry-flow: 원본 없이 실패 → 원본 없이 다시 분석(다시 실패) → 같은 주소로 올림 → 다시 분석(성공) → done."""
    _say(f"다시 분석 확인(이번 실행이 만든 분석에만 · actor {REVIEW_ACTOR}):")
    checks = _Checklist()
    keys = set(row)
    created_at = row.get("created_at")
    marks: list[Any] = [row.get("started_at")]  # 시작마다 started_at(처음 시작 → 다시 분석 1 → 다시 분석 2)
    reasons: list[Any] = [row.get("error")]  # 다시 분석마다 그 앞 실패 이유
    problems = _not_started_problems(row)
    if _when(row.get("started_at")) is None:
        problems.append("started_at 을 읽을 수 없음(시작 선점이 넣어야 함)")
    checks.report("올리지 않고 시작 → failed '업로드된 파일을 찾을 수 없습니다'(Upstage 작업 없음)", problems)
    run.verdict("목록(실패 분석)", _check_list(run, analysis_id, "실패 분석"), new=True)

    body = _retry_step(run, checks, "원본 없이 다시 분석 → 다시 실패(같은 이유 · 작업 없음 · 조회와 같은 값)", analysis_id, created_at, marks[-1], keys, started=False)
    if body is None or body.get("status") != "failed":
        checks.summary("다시 분석 확인")
        run.verdict("다시 분석", False, new=True)
        _print_verdicts(run)
        return EXIT_FAIL
    marks.append(body.get("started_at"))
    reasons.append(body.get("error"))

    uploaded = _upload(run, upload, content, mime_type)
    checks.report("만들 때 받은 같은 서명 업로드 주소로 원본 올리기", [] if uploaded else ["올리기 실패"])
    body = _retry_step(run, checks, "원본을 올린 뒤 다시 분석 → running(새 작업)", analysis_id, created_at, marks[-1], keys, started=True) if uploaded else None
    if body is None or body.get("status") != "running":
        checks.summary("다시 분석 확인")
        run.verdict("다시 분석", False, new=True)
        _print_verdicts(run)
        return EXIT_FAIL
    marks.append(body.get("started_at"))
    job = body.get("upstage_job_id")
    run.log(f"다시 분석 시작: 상태={body.get('status')} job={job}")

    response, _ = _retry(run, analysis_id)
    problems = _refused(response, 409, MSG_BUSY)
    reread, latest = _get(run, analysis_id)  # 분석 중이면 Upstage 상태를 한 번 확인한다(작업 만들기 아님)
    row = body
    if reread.status_code == 200 and isinstance(latest, Mapping):
        run.observe(latest)
        row = latest
        if latest.get("upstage_job_id") != job or latest.get("started_at") != marks[-1]:
            problems.append("작업 id·started_at 이 바뀜(새 작업을 만듦)")
        if latest.get("status") not in ("running", "done"):
            problems.append(f"status {latest.get('status')!r}(기대 running 또는 done)")
    else:
        problems.append(f"다시 조회 HTTP {reread.status_code}")
    checks.report("분석 중에 다시 분석 → 409 '이미 분석하고 있습니다.'(작업·started_at 그대로)", problems)

    final = _poll(run, args, analysis_id, row)
    if final is None:
        checks.summary("다시 분석 확인")
        run.verdict("다시 분석", False, new=True)
        _print_verdicts(run)
        return EXIT_FAIL
    _say(f"분석 id: {analysis_id}")
    _say(f"job id: {final.get('upstage_job_id')}")
    _say(f"최종 상태: {final['status']}")
    problems = [] if final["status"] == "done" and isinstance(final.get("review"), Mapping) else [f"status {final['status']!r} · review 객체 아님"]
    if final.get("created_at") != created_at:
        problems.append("완료 행의 created_at 이 처음과 다름(요청 시각·분석 번호·목록 순서 기준)")
    if final.get("started_at") != marks[-1]:
        problems.append("완료 행의 started_at 이 마지막 다시 분석 때 값과 다름(경과·걸린 시간 기준)")
    problems += _documents_problems(final)
    checks.report(
        "다시 분석한 분석이 done(검토할 수 있음) · created_at 그대로 · started_at = 마지막 다시 분석",
        problems,
        f"created_at 그대로 {final.get('created_at') == created_at} · started_at = 마지막 다시 분석 {final.get('started_at') == marks[-1]}",
    )
    done = final["status"] == "done"
    ok = done
    if done:
        # 고정 기대값(done 확인)이 어긋나도 아래 새 확인은 따로 돌린다(섞이지 않게)
        ok = run.verdict("done 확인(요약·화면용 결과 고정 기대값·검토사항·응답 크기)", _verify_done(run, analysis_id))
        ok = run.verdict("원본 파일", _check_file(run, analysis_id, content)) and ok
        _check_retry_history(run, checks, analysis_id, reasons, marks, act=not args.no_review)
    retry_ok = run.verdict("다시 분석", checks.summary("다시 분석 확인"), new=True)
    if done:
        ok = run.verdict("목록", _check_list(run, analysis_id, "다시 분석한 완료 분석"), new=True) and ok
    files_ok = _check_upstage_files(run, _documents(final))
    if files_ok is False:
        ok = run.verdict("Upstage 파일 지움", False)
    ok = _delete_or_keep(run, analysis_id) and retry_ok and ok and all(passed for _, passed, _ in run.verdicts)
    _print_verdicts(run)
    _say(f"결과: {'기대대로' if ok else '기대와 다름'} (다시 분석 확인)")
    return EXIT_OK if ok else EXIT_FAIL


def _flow_fail_with_original(
    run: Run, analysis_id: str, upload: Mapping[str, str], content: bytes, mime_type: str, row: Mapping[str, Any]
) -> int:
    """--fail-with-original: 원본 없이 실패시킨 뒤 같은 주소로 원본을 올리고 다시 분석하지 않고 남긴다(Upstage 0번)."""
    _say("실패 분석 만들기(원본은 올려 두고 다시 분석하지 않음 · Upstage 작업 없음 · 지우지 않음):")
    checks = _Checklist()
    checks.report("올리지 않고 시작 → failed '업로드된 파일을 찾을 수 없습니다'(Upstage 작업 없음)", _not_started_problems(row))
    run.verdict("목록(실패 분석)", _check_list(run, analysis_id, "실패 분석"), new=True)
    uploaded = _upload(run, upload, content, mime_type)
    checks.report("만들 때 받은 같은 서명 업로드 주소로 원본 올리기", [] if uploaded else ["올리기 실패"])
    if uploaded:
        run.verdict("원본 파일(올린 뒤)", _check_file(run, analysis_id, content))
    response, latest = _get(run, analysis_id)
    problems = (
        _not_started_problems(latest) if response.status_code == 200 and isinstance(latest, Mapping) else [f"조회 HTTP {response.status_code}"]
    )
    checks.report("다시 분석하지 않고 남김 — failed 그대로(작업 없음)", problems)
    ok = run.verdict("실패 분석 만들기", checks.summary("실패 분석 만들기")) and all(passed for _, passed, _ in run.verdicts)
    _print_verdicts(run)
    _say(f"분석 id: {analysis_id}")
    _say("남김: 화면에서 다시 분석할 실패 분석입니다(목록·상세의 '삭제' 또는 DELETE /api/py/analyses/{id} 로 지움)")
    _say(f"결과: {'기대대로' if ok else '기대와 다름'} (실패 분석 만들기)")
    return EXIT_OK if ok else EXIT_FAIL


def _flow(run: Run, args: argparse.Namespace) -> int:
    file_path = (ROOT / args.file) if not Path(args.file).is_absolute() else Path(args.file)
    filename = file_path.name
    mime_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    content_path = Path(args.content_file) if args.content_file else file_path
    content = content_path.read_bytes()
    role = "비교할 원본" if args.analysis_id else "올릴 내용"
    _say(f"대상: {args.base_url} · 파일 {filename}({mime_type}) · {role} {content_path.name} {len(content):,} bytes")
    if args.analysis_id:
        return _flow_existing(run, args, args.analysis_id, content)
    mode = " · 다시 분석 확인(--retry-flow)" if args.retry_flow else " · 실패 분석 만들기(--fail-with-original)" if args.fail_with_original else ""
    _say(
        f"기대: {'done' if args.retry_flow else 'failed' if args.fail_with_original else args.expect}{mode}"
        + (" · 올리지 않음" if args.skip_upload else "")
        + (" · 시작하지 않음" if args.no_start else "")
        + (" · 끝나도 지우지 않음" if run.keep else "")
    )

    # 1. health
    health = run.call("GET", "/api/py/health")
    run.log(f"health: HTTP {health.status_code} {health.json() if health.is_success else _detail(health)}")
    if not health.is_success:
        return EXIT_FAIL

    # 2. 만들기
    body: dict[str, Any] = {"filename": filename, "size": len(content), "mime_type": mime_type}
    if args.name is not None:
        body["name"] = args.name
    created = run.call("POST", "/api/py/analyses", json=body)
    if created.status_code != 201:
        run.log(f"만들기 실패: HTTP {created.status_code} {_detail(created)}")
        return EXIT_FAIL
    payload = created.json()
    analysis = payload["analysis"]
    upload = payload["upload"]
    analysis_id = analysis["id"]
    run.analysis_id = analysis_id
    run.created = True  # 끝에 지울 대상(--keep 이면 남김)
    t_queued = time.monotonic()
    leaked = [k for k in ("agent_id", "storage_path") if k in created.text]
    run.log(f"만들기: HTTP 201 id={analysis_id} 상태={analysis['status']} 이름={analysis['name']!r}")
    run.log(f"  문서 이름={analysis['documents'][0]['filename']!r} → Storage 경로 {upload['path']}")
    if leaked:
        run.log(f"  응답에 들어가면 안 되는 키: {leaked}")
        return EXIT_FAIL

    # 3. 올리기(--retry-flow·--fail-with-original 은 먼저 올리지 않고 시작해 실패시킨다)
    if args.retry_flow or args.fail_with_original:
        run.log("올리기 건너뜀(원본 없이 먼저 시작 — 같은 서명 주소로 나중에 올린다)")
    elif args.skip_upload:
        run.log("올리기 건너뜀(--skip-upload)")
    elif not _upload(run, upload, content, mime_type):
        return EXIT_FAIL
    if args.no_start:
        run.log("시작하지 않고 끝냄(--no-start)")
        _say(f"분석 id: {analysis_id}")
        return EXIT_OK

    # 4. 시작 — 작업을 만들 수 있는 요청: 응답을 관찰하기 전에는 시작 결과 미확인(잃으면 정리가 다시 읽는다)
    run.begin_start()
    started = run.call("POST", f"/api/py/analyses/{analysis_id}/start")
    run.settle_start(started.status_code, _body(started))
    if started.status_code != 200:
        run.log(f"시작 실패: HTTP {started.status_code} {_detail(started)}")
        return EXIT_FAIL
    row = started.json()
    run.start_row_received = True
    t_running = time.monotonic() if row["status"] == "running" else None
    run.log(f"시작: HTTP 200 상태={row['status']} job={row.get('upstage_job_id')}" + (f" 오류={row['error']!r}" if row.get("error") else ""))
    if args.retry_flow:
        return _flow_retry(run, args, analysis_id, upload, content, mime_type, row)
    if args.fail_with_original:
        return _flow_fail_with_original(run, analysis_id, upload, content, mime_type, row)

    # 5. 조회
    row = _poll(run, args, analysis_id, row)
    if row is None:
        return EXIT_FAIL
    t_end = time.monotonic()

    # 6. 결과
    _say(f"분석 id: {analysis_id}")
    _say(f"job id: {row.get('upstage_job_id')}")
    _say(f"최종 상태: {row['status']}")
    ok = row["status"] == args.expect
    if row["status"] == "done":
        # 끝난 분석을 다시 읽어 확인한다(done 조회는 Upstage 를 부르지 않는다)
        ok = run.verdict("done 확인(요약·화면용 결과 고정 기대값·검토사항·응답 크기)", _verify_done(run, analysis_id)) and ok
        ok = run.verdict("원본 파일", _check_file(run, analysis_id, content)) and ok
        if args.no_review:
            _say("검토 동작 확인 건너뜀(--no-review)")
        else:
            # 이번 실행이 만든 분석이 done 이 된 뒤에만 검토 동작을 보낸다
            ok = run.verdict("검토 동작", _check_reviews(run, analysis_id)) and ok
        ok = run.verdict("목록", _check_list(run, analysis_id, "완료 분석"), new=True) and ok
    else:
        _say(f"오류 문구: {row.get('error')!r}")
        ok = ok and bool(row.get("error"))

    files_ok = _check_upstage_files(run, _documents(row))
    if files_ok is False:
        ok = run.verdict("Upstage 파일 지움", False)
    ok = _delete_or_keep(run, analysis_id) and ok

    if t_running is not None and row["status"] == "done":
        total = t_end - t_queued
        _say(f"queued → running → done: {total:.1f}s ({'3분 안' if total <= WITHIN_SECONDS else '3분 넘음'})")
    _print_verdicts(run)
    _say(f"결과: {'기대대로' if ok else '기대와 다름'} (기대 {args.expect})")
    return EXIT_OK if ok else EXIT_FAIL


def _flow_existing(run: Run, args: argparse.Namespace, analysis_id: str, content: bytes) -> int:
    """--analysis-id: 만들기·올리기·시작 없이 조회·원본 파일 확인만(Upstage 작업을 만들지 않는다).

    start_requested 가 False 라 정리 단계는 아무것도 지우지 않는다.
    """
    run.analysis_id = analysis_id
    _say(f"기존 분석 확인(만들기·올리기·시작 없음, Upstage 작업 없음): {analysis_id}")
    health = run.call("GET", "/api/py/health")
    run.log(f"health: HTTP {health.status_code} {health.json() if health.is_success else _detail(health)}")
    if not health.is_success:
        return EXIT_FAIL
    done_ok = _verify_done(run, analysis_id)
    file_ok = _check_file(run, analysis_id, content)
    ok = done_ok and file_ok
    if args.no_review:
        _say("검토 기록 모양 확인 건너뜀(--no-review)")
    else:
        ok = _check_review_shape(run, analysis_id) and ok  # 읽기만 — 검토 동작은 보내지 않는다
    _say(f"분석 id: {analysis_id}")
    _say(f"결과: {'기대대로' if ok else '기대와 다름'} (기존 분석 확인)")
    return EXIT_OK if ok else EXIT_FAIL


def run_e2e(args: argparse.Namespace, *, transport: httpx.BaseTransport | None = None) -> int:
    """_flow 를 돌리고, 어떻게 끝나든(시간 초과·Ctrl+C·연결 오류·예상 못 한 예외) finally 에서 정리한다."""
    env = _read_env()
    run = Run(args, env, transport=transport)
    code = EXIT_FAIL
    cleaned = False
    removed = False
    try:
        try:
            code = _flow(run, args)
        except KeyboardInterrupt:
            _say("중단됨(Ctrl+C)")
        except httpx.HTTPError as exc:
            _say(f"연결 오류: {type(exc).__name__}")
        except Exception as exc:
            _say(f"예상 못 한 오류: {_short(f'{type(exc).__name__}: {exc}')}")
    finally:
        interrupted = False
        try:
            cleaned = _cleanup(run)
        except KeyboardInterrupt:
            interrupted = True
            _say("정리 중 중단됨(Ctrl+C) — Upstage 파일을 지웠는지 확인하지 못했습니다")
        except Exception as exc:
            _say(f"정리 중 오류: {_short(type(exc).__name__)} — Upstage 파일을 지웠는지 확인하지 못했습니다")
        # 이번 실행이 만든 분석 지우기(기본) — 정리 중 Ctrl+C 면 멈춘다(지우지 않음)
        if interrupted:
            if run.created and not run.deleted and run.analysis_id:
                _say(f"정리 중 중단돼 이번 실행이 만든 분석을 지우지 않았습니다: {run.analysis_id}")
        else:
            try:
                removed = _remove_created(run)
            except KeyboardInterrupt:
                _say("정리 중 중단됨(Ctrl+C) — 이번 실행이 만든 분석을 지웠는지 확인하지 못했습니다")
            except Exception as exc:
                _say(f"정리 중 오류: {_short(type(exc).__name__)} — 이번 실행이 만든 분석을 지웠는지 확인하지 못했습니다")
        run.http.close()
    if not (cleaned and removed):
        _say("정리를 끝내지 못해 실패로 끝냅니다")
        return EXIT_FAIL
    return code


def main(argv: list[str] | None = None, *, transport: httpx.BaseTransport | None = None) -> int:
    _setup_console()
    parser = argparse.ArgumentParser(description="iMASK FastAPI 백엔드 끝까지 확인")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--file", default=DEFAULT_FILE, help="이름·형식을 알릴 파일(기본 합성 묶음)")
    parser.add_argument("--name", default=None, help="분석명(없으면 서버가 파일 이름을 쓴다)")
    parser.add_argument("--interval", type=float, default=3.0)
    parser.add_argument("--timeout", type=float, default=600.0)
    parser.add_argument("--skip-upload", action="store_true", help="올리지 않고 시작(실패 경로)")
    parser.add_argument("--content-file", default=None, help="실제로 올릴 내용(형식 불일치 실패 경로)")
    parser.add_argument("--no-start", action="store_true", help="만들기·올리기까지만")
    parser.add_argument("--expect", choices=("done", "failed"), default="done")
    parser.add_argument(
        "--analysis-id",
        default=None,
        help="이미 있는 분석을 조회하고 원본 파일·검토 기록 모양만 확인(만들기·올리기·시작·검토 동작 없음 — Upstage 작업을 만들지 않음)",
    )
    parser.add_argument(
        "--no-review",
        action="store_true",
        help="검토 동작 확인을 끈다(기본은 새 분석이 done 이 되면 검토 동작을 보내 확인)",
    )
    parser.add_argument(
        "--retry-flow",
        action="store_true",
        help="다시 분석 확인: 원본 없이 시작해 실패 → 원본 없이 다시 분석(다시 실패) → 같은 서명 주소로 올림 → 다시 분석 → done(Upstage 1번)",
    )
    parser.add_argument(
        "--fail-with-original",
        action="store_true",
        help="원본 없이 시작해 실패시킨 뒤 같은 서명 주소로 원본을 올리고 다시 분석하지 않고 남긴다(화면 확인용, Upstage 0번)",
    )
    parser.add_argument("--keep", action="store_true", help="이번 실행이 만든 분석을 끝에 지우지 않는다(기본은 지움)")
    args = parser.parse_args(argv)
    if args.retry_flow and args.fail_with_original:
        parser.error("--retry-flow 와 --fail-with-original 은 함께 쓸 수 없습니다")
    if args.retry_flow or args.fail_with_original:
        flag = "--retry-flow" if args.retry_flow else "--fail-with-original"
        clashes = [
            name
            for name, given in (
                ("--analysis-id", args.analysis_id is not None),
                ("--no-start", args.no_start),
                ("--content-file", args.content_file is not None),
                ("--expect failed", args.expect != "done"),
            )
            if given
        ]
        if clashes:
            parser.error(f"{flag} 는 {', '.join(clashes)} 와 함께 쓸 수 없습니다(--skip-upload 는 같은 뜻이라 무시)")
    try:
        return run_e2e(args, transport=transport)
    except KeyboardInterrupt:  # 정리 바깥(설정 읽기 등)에서의 중단
        _say("중단됨(Ctrl+C)")
        return EXIT_FAIL


if __name__ == "__main__":
    sys.exit(main())
