# iMASK

은행 여신 담당자가 대출 서류 묶음(PDF·이미지)에서 찾은 민감정보 탐지 결과(위험등급과 판단 근거)를 검토하고, 보고서로 내보내는 웹 서비스 **iMASK**입니다. 1단계 화면 껍데기(데모)에 Upstage 워크플로우로 실제 분석하는 모드를 더했습니다.

- 기본은 브라우저 안의 **데모 서비스**가 샘플 데이터로 응답합니다. 샘플 속 이름·주민등록번호·전화번호·계좌번호·주소·금액은 모두 가상입니다. 화면의 '데모 데이터' 표시도 이 때문에 있습니다.
- `NEXT_PUBLIC_IMASK_SERVICE=api` 로 켜는 **실제 분석 모드**에서는 서류 묶음 하나를 올리면 **FastAPI 백엔드**(`api/`)가 **Upstage Studio 워크플로우**로 분석하고, 화면은 진행 상태를 보여 주고, 끝나면 데모와 같은 상세 검토 화면(올린 PDF·이미지 원문 위의 탐지 위치 상자·마스킹 미리보기·분석 요약)을 **읽기 전용**으로 보여 줍니다([실제 분석 모드](#실제-분석-모드)). 검토 동작(확인·오탐·분류 수정·메모·검토 완료)·보고서는 아직 데모에만 있습니다.
- 모드는 **주소 기준**입니다. **`/demo` 아래는 언제나 데모**이고, 그 밖은 빌드 모드(`NEXT_PUBLIC_IMASK_SERVICE`)를 따릅니다. 그래서 실제 분석 모드로 빌드한 운영 사이트에서도 `/demo` 로 들어가면 데모(샘플 6건·상세 검토·보고서·내보내기)가 그대로 동작합니다. 실제 분석 화면 헤더의 **'데모 체험하기'** 링크가 `/demo` 로 가고, `/demo` 헤더의 **'실제 분석으로'** 링크로 돌아옵니다.
- Next.js 16(App Router), TypeScript strict, CSS Modules와 디자인 토큰(CSS 변수)으로 만들었습니다. Tailwind, CSS-in-JS, UI 라이브러리는 쓰지 않습니다.

## 화면

| 주소 | 화면 | 하는 일 |
|---|---|---|
| `/` | 분석 목록 | 요약 카드, 검색·필터·정렬(URL 검색 파라미터 `q`·`risk`·`status`·`review`·`sort` 와 이어짐), 분석 건 표, 비어 있을 때 안내 |
| `/analyses/new` | 새 분석 | 파일 선택 검사(PDF·PNG·JPG, 파일당 20MB, 최대 10개), 업로드 진행, 분석 요청 |
| `/analyses/[id]` | 상세 검토 | 문서 목록, 원문(샘플 문서 화면)과 하이라이트, 결과 패널(탐지 항목 · 검토 필요 · 문서 간 연결 탭, 필터 칩, '현재 문서만 보기'). 아래 검토 동작을 하고 검토를 완료합니다 |
| `/analyses/[id]/report` | 검토 결과 보고서 | 검토 결과 정리, 내보내기(CSV·JSON 파일을 브라우저 다운로드로 저장) |
| `/demo` · `/demo/analyses/new` · `/demo/analyses/[id]` · `/demo/analyses/[id]/report` | 위 네 화면(데모) | **빌드 모드와 상관없이 언제나 데모 서비스**로 위 네 화면을 그립니다. 화면 안 이동(목록·새 분석·상세·보고서·완료 토스트·헤더 메뉴·로고)은 모두 `/demo` 아래에 머뭅니다 |

위 표의 루트 주소(`/`·`/analyses/…`)는 데모 모드 빌드 기준입니다. 실제 분석 모드로 빌드하면 루트 주소의 새 분석·상세·보고서가 다른 화면으로 바뀌고([화면별 동작](#화면별-동작)), `/demo` 아래는 그대로 데모입니다.

휴대폰(768px 미만), 태블릿(768–1199px), 데스크톱(1200px 이상) 배치가 각각 있습니다. 휴대폰에서는 목록이 카드로 바뀌고, 상세 검토는 원문·탐지 결과·문서 탭으로 나뉘며, 모달은 아래에서 올라오는 시트가 됩니다.

### 상세 검토의 동작

검토 동작은 모두 데모 서비스의 메모리 상태를 바꾸고(실제 저장 없음), 끝나면 토스트로 알립니다. 헤더 '검토 필요' 숫자와 목록 요약도 같은 서비스에서 와서 함께 바뀝니다.

| 대상 | 바로 바뀌는 동작 | 모달로 하는 동작(메모·사유 입력) |
|---|---|---|
| 탐지 항목 | 탐지 내용 확인 · 확인 취소, 원문 확인(원문의 그 위치로 이동) | 오탐으로 표시(사유) · 오탐 표시 취소, 정보 분류 수정(정보 종류 · 정보 주체 · 노출 상태), 항목 메모 |
| 검토사항 | 근거 위치 보기(예: '신청서 값 보기') · 연결 보기, 다시 분석(읽지 못한 문서), 다시 열기 | 해결로 표시 |
| 문서 간 연결 | 근거 문서 열기 | 같은 사람 · 같은 건으로 판단 / 연결 아님으로 판단 |
| 분석 건 | 실패 문서 다시 분석(일부 실패 띠) · 다시 시도(전체 실패) | 검토 메모, 검토 완료(남은 항목이 있으면 요약을 보여 줌), 검토 다시 열기 |

검토를 완료하면 화면이 잠기고(검토 동작 버튼 비활성) '보고서 보기' 토스트가 뜹니다. 분석 중인 건이 끝나면 어느 화면에 있든 '분석이 끝났습니다' 토스트가 한 번 뜹니다.

### 화면 이동과 목록 상태

목록의 검색·필터·정렬은 URL 검색 파라미터에 있고, 목록 화면이 마지막 값을 탭의 `sessionStorage` 에 기억합니다(`src/components/list/listReturn.ts`). 다른 화면에서 목록으로 갈 때는 프로토타입처럼 이 값을 이어 씁니다.

- 기억은 **기준 경로마다 따로**입니다 — 루트(`/`)는 `imask:list-query`, 데모(`/demo`)는 `imask:demo:list-query`. `/demo` 에서 건 필터가 실제 분석 화면의 헤더·'목록으로' 링크로 새지 않습니다(그 반대도).
- 화면 안 이동 주소는 모두 `src/lib/routes.ts` 의 함수(`listHref`·`newAnalysisHref`·`detailHref`·`reportHref`, 기준 경로 붙이기 `withBase`)에 지금 기준 경로(`useRouteBase()` — `''` 또는 `'/demo'`)를 넘겨 만듭니다. `/demo` 아래에서는 아래 이동이 모두 `/demo` 기준입니다(예: 헤더 '검토 필요' → `/demo?review=needed`).

| 이동 | 목록 상태 |
|---|---|
| 상세 검토의 '←'(목록으로), 새 분석의 '취소' | 검색·필터·정렬을 그대로 둡니다 |
| 헤더 '문서 분석' | '검토 필요' 필터만 풉니다 |
| 헤더 '검토 필요' | 검색·위험·상태 필터를 풀고 '검토 필요'만 겁니다(정렬은 그대로) |
| 로고 | 검색·필터를 모두 풉니다(정렬은 그대로) |

---

## 실행 방법

### 필요한 것

- **Node.js 22.12 이상**(24 LTS 권장). Next.js 16.4는 Node 20.9 이상이면 되지만, 테스트 도구 Vitest 5가 `^22.12.0 || ^24.0.0 || >=26.0.0` 을 요구합니다. 이 저장소는 Node 24.19, npm 11.17로 만들었습니다.
- npm(저장소에 `package-lock.json` 이 있습니다).
- **FastAPI 백엔드(`api/`)를 돌릴 때만**: [uv](https://docs.astral.sh/uv/)와 Python 3.12(`.python-version`). Python 이 없으면 uv 가 내려받아 `.venv` 를 만듭니다([아래](#fastapi-백엔드-api) 참고).
- 네트워크: 개발 서버와 빌드가 고정폭 글꼴 IBM Plex Mono를 Google Fonts에서 받습니다(`next/font/google`). Pretendard는 npm 패키지에서 읽습니다.

### 설치와 개발 서버

```bash
npm install
npm run dev          # next dev (Turbopack) → http://localhost:3000
```

포트를 바꾸려면 `npm run dev -- -p 3100` 처럼 넘깁니다.

### 주요 주소

| 주소 | 내용 |
|---|---|
| `/` | 분석 목록 — 샘플 분석 6건(A1~A6) |
| `/analyses/new` | 새 분석 |
| `/analyses/new?sample=1` | 샘플 문서 3개를 담은 채로 새 분석 시작 |
| `/analyses/A1` | 상세 검토 — 샘플 '대출상담 서류 묶음' |
| `/analyses/A1/report` | A1의 검토 결과 보고서 |
| `/analyses/A3` · `/analyses/A4` · `/analyses/A6` | 상세 검토 — 분석 중 · 일부 문서 처리 실패 · 전체 분석 실패 샘플 |
| `/demo` · `/demo/analyses/new?sample=1` · `/demo/analyses/A1` · `/demo/analyses/A1/report` | 위와 같은 데모 화면을 `/demo` 아래에서 — 실제 분석 모드 빌드(운영)에서도 데모입니다. `/demo` 아래의 없는 주소는 404, 없는 분석 ID 는 `/demo` 로 돌아갑니다 |
| `/dev/states` | 개발용 — 화면 상태 23개 목록([아래](#devstates-사용법) 참고) |
| `/dev/components` | 개발용 — 공통 컴포넌트와 디자인 기준 보드 |

데모 데이터는 브라우저 메모리에만 있습니다. 화면을 옮겨 다니는 동안은 상태가 이어지지만(상세에서 검토를 완료하면 목록 숫자에 반영), **새로 고침하면 처음 샘플 상태로 돌아갑니다.**

### 운영 빌드

```bash
npm run build        # next build
npm run start        # next start — 빌드한 뒤에 실행, 기본 포트 3000
```

---

## 확인 명령

| 명령 | 하는 일 |
|---|---|
| `npm run check` | 아래 네 개를 순서대로 실행합니다. 하나라도 실패하면 거기서 멈춥니다. |
| `npm run typecheck` | `tsc --noEmit` — TypeScript strict 타입 검사 |
| `npm run lint` | `eslint` — Next 권장 규칙(core-web-vitals·typescript)과 샘플 데이터 import 금지 규칙(`eslint.config.mjs`) |
| `npm run check:tokens` | `node scripts/check-tokens.mjs` — 색·크기 값이 토큰으로만 쓰였는지 검사([디자인 규칙](#디자인-규칙) 참고). 위반이 있으면 파일:줄과 이유를 출력합니다. |
| `npm test` | `vitest run --passWithNoTests` — `src/**/*.test.{ts,tsx}` 와 `scripts/**/*.test.mjs` 단위 테스트(Node 환경) |
| `.venv\Scripts\python.exe -m pytest -q` | FastAPI 백엔드·Upstage 코드의 Python 테스트(`tests/`, 네트워크 없음). macOS·Linux 는 `.venv/bin/python -m pytest -q`. `npm run check` 에는 들어 있지 않습니다. |

---

## 폴더 구조

프로토타입 로직의 다섯 구역 ① 설정값 ② 표시 규칙 ③ 샘플 데이터 ④ 데이터 서비스 ⑤ 화면 컴포넌트를 폴더로 나눴습니다.

```
src/
├─ config/app.ts            ① 설정값 — 브랜드명·강조색·담당자·업로드 제한·데모 지연 시간(CONFIG)
├─ display/                 ② 표시 규칙
│  ├─ rules.ts              등급·상태 라벨과 색, 정보 종류·정보 주체·노출 상태, 오탐 사유, 규칙 ID 예시, 이력 구분
│  └─ icon-names.ts         아이콘 이름 목록
├─ samples/                 ③ 샘플 데이터(가상) — src/services/demo/ 만 import한다
├─ services/                ④ 데이터 서비스
│  ├─ analysis-service.ts   인터페이스 AnalysisService·DemoControls — 실제 API로 바꾸는 계약
│  ├─ types.ts              도메인 타입(분석 건·문서·탐지 항목·검토사항·문서 간 연결·이력·내보내기 파일)
│  ├─ demo/                 데모 구현 — 동기 코어(core.ts), 비동기 겉면(service.ts),
│  │                        미리 해 둔 검토 동작(seed.ts), /dev/states 상태 준비(scenarios.ts)
│  ├─ api/                  실제 분석 구현 — 백엔드 클라이언트(client.ts), 응답 → 화면 타입(mapping.ts),
│  │                        서명 업로드(upload.ts), 이 탭의 저장소·분석 id(browser-storage.ts·session-list.ts)
│  ├─ mode.ts               서비스 모드 — 빌드 모드 SERVICE_MODE(NEXT_PUBLIC_IMASK_SERVICE — demo | api)와
│  │                        주소 기준 모드 modeForPath(/demo 아래는 언제나 demo)
│  ├─ index.ts              createServiceFor(mode) · createServiceCache() — 모드별 데모·실제 분석 서비스를 만드는 한 곳
│  └─ react.tsx             ServiceProvider(주소 기준 모드 · 기준 경로, 모드별 브라우저 싱글턴)와
│                           훅(useService·useServiceMode·useRouteBase·useBuildMode·useAnalyses·useAnalysis·usePending …)
├─ app/                     ⑤ 라우트 — layout.tsx·providers.tsx·fonts.ts·globals.css,
│                             page.tsx(/), analyses/(새 분석·상세·보고서 — 주소 기준 모드로 데모·실제 분석 화면을 고름),
│                             demo/(/demo 아래 같은 네 화면 — 언제나 데모, [...rest] 는 /demo 아래 404), dev/(states·components)
├─ components/              ⑤ 화면 컴포넌트
│  ├─ ui/                   공통 컴포넌트(버튼·입력·드롭다운·탭·모달·토스트·상태 표기 …)
│  ├─ layout/               헤더(모드 전환 링크 — modeSwitch.ts: '데모 체험하기' · '실제 분석으로'), AppShell(<main>·토스트·알림 영역·
│  │                        아이콘 스프라이트), 데모 표시, ByServiceMode(주소 기준 모드로 두 화면 중 하나를 그림)
│  ├─ list/                 분석 목록
│  ├─ upload/               새 분석
│  ├─ detail/               상세 검토(데모·실제 분석 공용) — 실제 분석 원문은 LivePaper(쪽 · 위치 상자) ·
│  │                        liveFile(원본 파일 한 번 받기) · pdfRuntime(pdf.js, 동적 import)
│  ├─ live/                 실제 분석 모드의 새 분석·상세(진행 상태·옛 형식 결과 JSON·'분석 요약' 탭)·보고서 안내
│  ├─ modals/               상세 검토의 검토 동작 모달
│  └─ report/               보고서와 내보내기
├─ styles/tokens.css        디자인 토큰(CSS 변수) — 색·크기 리터럴은 이 파일에만 있다
├─ lib/                     형식 도우미(format.ts), 브라우저 다운로드(download.ts), 쪽 위 상자 · 캔버스 배율(pageBox.ts),
│                             주소 기준 경로 · 이동 주소(routes.ts), 공통 훅(hooks/),
│                             지킴 테스트(navigation-guard.test.ts — SERVICE_MODE · 환경변수 · 이동 주소 리터럴)
└─ dev/                     /dev/states 상태 정의(states.ts)와 미리보기
scripts/check-tokens.mjs    토큰 규칙 검사기(같은 폴더에 검사기·ESLint 경계 테스트)
scripts/upstage_smoke.py    Upstage 워크플로우 직접 호출 확인 · scripts/api_e2e.py 백엔드 끝까지 확인
api/index.py                FastAPI 백엔드 진입점(Vercel Python 함수) — 아래 'FastAPI 백엔드' 참고
imask_backend/              백엔드 Python 코드(설정·Supabase·Upstage·결과 파싱·화면용 결과 변환·업무 로직)
docs/                       팀원과 맞출 문서 — field-mapping.md(민감정보_추출 키 → 정보 종류·주체 대응표와 확인 질문)
tests/                      백엔드 Python 테스트(pytest)
vercel.json                 Vercel 설정(프레임워크 nextjs 고정, 지역 icn1, Python 함수 maxDuration·묶음 제외)
supabase/                   DB 변경 기록 — migrations/에 적용한 SQL을 순서대로 둔다(아래 'DB 변경 기록' 참고)
.env.example                필요한 환경변수 이름(값은 로컬 .env와 Vercel에만)
```

---

## 실제 분석 모드

기본은 데모 모드입니다. 환경변수 `NEXT_PUBLIC_IMASK_SERVICE` 가 정확히 `api` 이면 루트 주소(`/`·`/analyses/…`·`/dev/…`)의 화면이 데모 서비스 대신 **실제 분석 서비스**(`src/services/api/`)를 씁니다. **`/demo` 아래는 이 값과 상관없이 언제나 데모 서비스**입니다 — 샘플·검토 동작·보고서·내보내기가 그대로 됩니다. 서류 묶음 하나를 올리면 [FastAPI 백엔드](#fastapi-백엔드-api)가 Upstage Studio 워크플로우로 분석하고, 화면은 진행 상태와, 끝나면 데모와 같은 상세 검토 화면(원본 파일 원문 · 탐지 위치 상자 · 마스킹 미리보기 · 분석 요약, 읽기 전용)을 보여 줍니다. **합성 자료만 올립니다** — 실제 고객 서류나 본인 서류는 올리지 않습니다.

### 켜는 법(로컬)

1. 백엔드를 띄웁니다([로컬 실행](#로컬-실행) 참고).
2. 화면을 실제 분석 모드로 띄웁니다. `.env.local` 에 `NEXT_PUBLIC_IMASK_SERVICE=api` 한 줄을 넣고 `npm run dev` 하거나, 셸 환경변수로 넘깁니다.

   ```bash
   NEXT_PUBLIC_IMASK_SERVICE=api npm run dev              # macOS·Linux·Git Bash
   $env:NEXT_PUBLIC_IMASK_SERVICE='api'; npm run dev       # Windows PowerShell
   ```

3. `http://localhost:3000/analyses/new` 에서 파일을 올립니다(접근 코드는 없습니다 — 2026-11-03 없앰).

- 브라우저 업로드에 `NEXT_PUBLIC_SUPABASE_URL`·`NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` 도 필요합니다. Next 는 저장소 루트의 `.env` 도 읽지만, 브라우저 코드에는 `NEXT_PUBLIC_` 이 붙은 값만 들어갑니다.
- `NEXT_PUBLIC_*` 값은 **빌드(또는 `next dev` 시작) 때** 코드에 들어갑니다. 바꾸면 개발 서버를 다시 띄우고, Vercel 에서는 다시 배포합니다.
- 헤더 배지가 '데모 데이터' 대신 **'실제 분석'** 으로 보이면 켜진 것입니다. 실제 분석 화면 헤더에는 배지 앞에 작은 **'데모 체험하기'** 링크(→ `/demo`, 휴대폰 폭에서는 '데모')가, `/demo` 헤더에는 같은 자리에 **'실제 분석으로'** 링크(→ `/`, 휴대폰 폭에서는 '실제' — 이때 배지도 '데모')가 있습니다(`src/components/layout/modeSwitch.ts`). 두 링크는 미리 받지 않으므로(`prefetch={false}`) 한쪽 화면을 열 때 다른 쪽 화면을 받지 않습니다. 데모 빌드(실제 분석 없음)에는 이 링크가 없습니다.

### 흐름

```
새 분석(/analyses/new) — 분석명(선택) · 파일 1개
  ① POST /api/py/analyses             분석 건 + 서명 업로드 URL          '분석 건 만드는 중'
  ② Supabase Storage 서명 업로드       @supabase/supabase-js · 공개 키    '파일 올리는 중'
  ③ POST /api/py/analyses/{id}/start  Upstage 작업 시작                  '분석 시작 중'
상세(/analyses/{id}) — 3초마다 GET /api/py/analyses/{id}(조회마다 백엔드가 Upstage 상태를 한 번 확인)
  queued · running ──▶ done | failed(백엔드 오류 문구 그대로 + '새 분석')
  done + 공통 계약 결과 ──▶ 상세 검토 화면(읽기 전용)
    · 원본 파일   GET /api/py/analyses/{id}/file → 서명 주소에서 한 번 받아 둔다(서류 · 쪽을 바꿔도 다시 받지 않음)
    · 단계별 JSON GET /api/py/analyses/{id}?include=stages — '분석 요약' 탭에서 접은 칸을 처음 펼칠 때 한 번
  done + 옛 형식(서류 0개 등) ──▶ 요약 + 단계별 결과(JSON 나무)
```

- 파일은 **1개**(워크플로우가 묶음 하나를 서류별로 나눕니다), PDF·PNG·JPEG, 20MB 이하입니다. 어기면 고르는 순간 한국어 오류가 보입니다. 분석명은 60자까지, 비우면 파일 이름입니다.
- `@supabase/supabase-js` 는 실제로 올릴 때만 불러옵니다(동적 `import()`) — 첫 화면 묶음과 데모 모드에는 들어가지 않습니다. 서명 토큰이 권한이라 공개 키(publishable key)로 충분합니다.
- PDF 원문은 **`pdfjs-dist`**(버전 고정)로 쪽을 캔버스에만 그립니다(주석·텍스트 레이어·폼·스크립트 없음). 원본이 PDF 일 때만 상세 화면에서 동적 `import()` 하므로(`src/components/detail/liveFile.ts` → `pdfRuntime.ts`) 첫 화면·목록·새 분석 묶음과 데모 빌드에는 들어가지 않습니다. 데모 빌드에서 그 분기가 빠지도록 `next.config.ts` 의 `env` 가 `NEXT_PUBLIC_IMASK_SERVICE` 를 값이 없어도 빈 글자로 넣습니다. 워커는 문서마다 `new Worker(new URL('pdfjs-dist/build/pdf.worker.min.mjs', import.meta.url), { type: 'module' })` 로 만들어 `PDFWorker` 에 넘깁니다 — `next dev`(Turbopack)와 `next build`/`next start` 모두 번들러가 워커를 따로 묶어 같은 출처에서 내보내고, 화면을 떠나면 문서와 워커를 정리합니다. PNG·JPEG 는 object URL 의 `<img>` 로 그립니다.
- 시작이 409(이미 시작)이거나 `failed` 행을 돌려줘도 상세로 갑니다(상세가 상태·오류를 보여 줍니다). 업로드에 실패하면 새 분석 화면 위에 `파일을 올리지 못했습니다. …` 가 보이고, 그 분석 건은 `queued` 로 남습니다(목록에는 보이지 않음).
- 업로드까지 끝낸 뒤 **시작이 5xx·네트워크 오류·시간 초과로 끝나면** 시작이 실제로는 됐을 수 있습니다. 새 분석 화면은 오류와 함께 '분석 건은 만들어졌지만 시작됐는지 확인하지 못했습니다' 와 **'분석 건 확인하기'** 링크(상세 → 실제 상태: 분석 중·실패·대기)를 보여 주고, 그 분석을 이 탭 목록에도 넣습니다. 성공했다고 표시하지 않습니다.
- 요청 하나의 시간 제한은 60초이고 응답 본문을 다 받을 때까지 걸립니다.
- 상세 화면은 `queued`·`running` 인 동안만 조회합니다. 앞 요청이 끝난 뒤 다음을 잡아 겹치지 않고, 탭이 숨겨지면 쉬었다가 다시 보이면 바로 한 번 조회합니다. 끝나거나(`done`·`failed`) 화면을 떠나면 멈춥니다. **백엔드는 조회가 올 때만 상태를 나아가게 하므로 상세 화면이 열려 있어야 끝납니다**(닫았다가 다시 열면 이어서 진행합니다).

### 접근 제한 없음

접근 코드(예전 `X-Demo-Code` · `DEMO_ACCESS_CODE`)는 2026-11-03 없앴습니다 — 팀만 아는 주소이고 Upstage 키가 대회용 무제한이라서입니다. 그래서 **주소를 아는 사람은 누구나 분석을 올리고 돌릴 수 있습니다**(Upstage 크레딧 · Supabase 저장 공간이 쓰입니다). 다른 사람의 분석은 목록 경로가 없고 분석 id(UUID)를 알아야 볼 수 있습니다.

### 화면별 동작

| 주소 | 실제 분석 모드 |
|---|---|
| `/` | 기존 목록 화면 그대로입니다. **이 탭에서 만든 분석만** 보입니다(백엔드에 목록 경로가 없습니다 — 남의 분석이 보이지 않게). id 목록은 sessionStorage `imask:api-analyses`(최신 50개)에 있습니다. 위험등급은 묶음 전체 위험도 판정에서 옵니다 — 공통 계약의 `result.overall.level`, 없으면 `result.summary.risk_level`(상·중·하 → 높음·보통·낮음, 검토 필요·없음 → 미평가). 탐지 항목별 위험등급은 워크플로우가 판정한 항목(`risk_source: "workflow"`)만 받은 값이고 나머지는 미평가입니다. 검토 상태는 늘 미검토입니다. |
| `/analyses/new` | 실제 분석 새 화면(`src/components/live/LiveUploadScreen.tsx`) — 걸리는 시간 안내, 분석명, 파일 1개, 진행 단계 |
| `/analyses/[id]` | 실제 분석 상세(`src/components/live/LiveDetailScreen.tsx`) — 대기·분석 중: 머리(분석명·상태·분석 번호 `DG-YYYYMMDD-XXXX`·요청 시각·파일·경과 시간), 진행 중 안내와 Upstage 상태. 실패: 실패 문구와 '새 분석'. **완료 + 공통 계약 결과**(`raw.detailReady`): 데모와 같은 상세 검토 화면(`DetailView` — 3단 배치·휴대폰 탭)을 새로 고침 없이 바로 그립니다 — 문서 목록(한국어 서류 이름, `1페이지 · 파일 3쪽`), 원문 자리에 올린 파일의 그 서류 쪽(PDF 는 캔버스, PNG·JPEG 는 이미지)과 탐지 위치 상자(위험등급 색 · 누르면 그 항목 · 고르면 강조와 이름표 · 마스킹 미리보기면 검은 상자), 위치 없는 항목은 '위치 확인 필요', 기타 서류는 '기타 서류 안내', 결과 패널은 '탐지 항목'과 '분석 요약'(위험도 판정·다음 단계 문구를 글자 그대로, 결과 요약 줄, 접은 원본 단계별 JSON). 원본 파일을 받지 못하면 이유와 '다시 시도'(결과 패널은 그대로). 검토 동작 버튼은 막혀 있고 '실제 분석에서는 아직 지원하지 않는 기능입니다' 안내가 보입니다. **완료지만 옛 형식**(서류 0개 등): 완료 요약(분류한 서류 수와 종류·정보를 추출한 서류 수·위험도·마지막 단계·기타 서류·걸린 시간·Upstage 작업 번호)과 단계별 결과(단계마다 접고 펴는 JSON — 펼칠 때만 그립니다). 없는 id 면 안내와 '새 분석'(목록으로 보내지 않습니다). |
| `/analyses/[id]/report` | '실제 분석 보고서는 아직 없습니다' 안내와 상세로 가는 링크 |
| `/demo/**` | **데모 그대로** — 헤더 배지 '데모 데이터'와 배지 앞 **'실제 분석으로'** 링크(→ `/`), '검토 필요' 숫자는 데모 목록 기준, 페이지 설명(meta description)은 '(데모 데이터)'가 붙은 문구(`src/app/demo/layout.tsx`), 샘플 6건·상세 검토 동작·보고서·내보내기·`?sample=1`·분석 완료 토스트가 모두 됩니다. 데모 서비스(브라우저 메모리)는 처음 `/demo` 를 열 때 만들어 탭 안에서 이어지고(`/` 로 갔다가 클라이언트 이동으로 돌아와도 검토가 남음), `/demo` 만 다니면 실제 분석 서비스는 만들지 않아 `/api/py` 요청이 없습니다. 새로 고침하면 샘플 상태로 돌아갑니다. |

### 실제 분석 모드에서 안 되는 것

- 검토 동작(탐지 내용 확인·확인 취소·오탐 표시·분류 수정·항목 메모)·검토사항·문서 간 연결·검토 메모·검토 완료·보고서·내보내기. 상세 검토 화면은 읽기 전용이라 그 버튼을 막고 안내를 보입니다. 서비스의 검토·내보내기 메서드는 `실제 분석에서는 아직 지원하지 않는 기능입니다.` 로 거절하고, 다시 분석(`retry`)은 같은 문구의 실패 결과를 돌려줍니다(목록의 '재시도'를 누르면 그 문구가 토스트로 보입니다).
- 루트 주소에서는 샘플 문서(`sampleFiles()` 는 빈 목록, `?sample=1` 은 무시)와 '샘플 분석 건 둘러보기'가 없습니다 — 이것들과 위의 검토 동작·보고서·내보내기는 **`/demo` 아래 데모**에서 됩니다.
- `/dev/**`(`/dev/states` 미리보기 등)는 `/demo` 밖이라 실제 분석 서비스를 쓰므로 여전히 동작하지 않습니다(`DemoControls` 가 없습니다).
- 마스킹한 파일 만들기(마스킹 미리보기는 화면에서만 가립니다), 결과 표·보고서, 다른 탭이나 다른 사람이 만든 분석 목록, 분석 지우기.
- 원본 PDF 에 들어 있지 않은 글꼴(표준 14 글꼴 · CJK 미리 정의 CMap)·JPEG 2000 이미지는 pdf.js 의 글꼴 · wasm 자료를 함께 내보내지 않아 대체 글꼴로 보이거나 빠질 수 있습니다(합성 묶음은 글꼴을 품고 있어 해당 없음).

### Vercel 에 넣을 환경변수

값은 Vercel 프로젝트 설정에만 넣습니다(여기에는 이름만 적습니다).

| 구분 | 이름 |
|---|---|
| 서버 전용 6개 — `NEXT_PUBLIC_` 을 붙이지 않음 | `SUPABASE_URL`, `SUPABASE_SECRET_KEY`, `UPSTAGE_API_KEY`, `UPSTAGE_AGENT_ID`, `UPSTAGE_CONFIG_ID`, `UPSTAGE_PROJECT_ID`(에이전트가 Upstage 프로젝트에 속할 때 — 지금 그렇다) |
| 브라우저 공개 3개 — 빌드 때 들어가므로 바꾸면 다시 배포 | `NEXT_PUBLIC_IMASK_SERVICE`(실제 분석이면 `api`), `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` |

---

## FastAPI 백엔드 (`api/`)

브라우저가 서류 묶음을 올리고 Upstage Studio 워크플로우로 분석하게 하는 서버입니다. Vercel 공식 [nextjs-fastapi 템플릿](https://github.com/digitros/nextjs-fastapi)처럼 **Next.js 와 같은 Vercel 프로젝트**에 Python 함수로 배포하고(지역 `icn1` 서울), 로컬에서는 uvicorn 으로 띄워 Next 개발 서버가 요청을 넘겨 줍니다. 화면은 [실제 분석 모드](#실제-분석-모드)에서 이 백엔드를 부릅니다.

### 구조

| 위치 | 내용 |
|---|---|
| `api/index.py` | FastAPI 앱 진입점. 경로·의존성·오류 모양만 다룹니다. Vercel 은 `api/` 의 `.py` 파일마다 함수를 만들므로 이 폴더에는 이 파일 하나만 둡니다 |
| `imask_backend/settings.py` | 환경변수. 요청 때 읽어서, 값이 빠져도 import 는 실패하지 않고 필요한 순간에 500 으로 이름만 알립니다 |
| `imask_backend/files.py` | 파일 이름·형식·크기 검사, Storage 용 안전한 이름, 내용 첫 바이트 검사 |
| `imask_backend/store.py` | Supabase 테이블·Storage 접근(`supabase==2.33.0`, `create_client(SUPABASE_URL, SUPABASE_SECRET_KEY)`)과 조건부 갱신 |
| `imask_backend/analyses.py` | 만들기·시작·조회·원본 파일 주소 업무 로직(FastAPI 와 무관), 응답 모양(`analysis_out`) |
| `imask_backend/upstage.py` · `results.py` · `redaction.py` · `config.py` | Upstage Agent API 클라이언트, 응답 파싱·요약, 비밀값 가림, Upstage 설정 |
| `imask_backend/findings.py` | 저장된 결과 → 화면용 `documents`·`findings`·`overall`(조회할 때 계산) |
| `imask_backend/fields.py` · `masking.py` | 민감정보_추출 키 대응표(정보 종류·세부 이름·정보 주체), 노출 상태 추정·가림 미리보기(표시용 — 판별 아님) |
| `imask_backend/textsafe.py` | 응답 문자열 안전성 — 짝 없는 서로게이트 검사(`has_unpaired_surrogates`)와 ASCII escape JSON 본문(`escaped_json_bytes` — 이름·값 원문 그대로, NaN·inf 는 null) |
| `docs/field-mapping.md` | 대응표와 스키마 담당 팀원에게 묻는 '확인 필요' 질문(테스트가 `fields.py` 와 같은지 봅니다) |
| `tests/` | pytest. 네트워크를 쓰지 않습니다(저장소는 메모리 가짜, Upstage 는 `httpx.MockTransport`) |
| `scripts/upstage_smoke.py` | Upstage 워크플로우를 직접 한 번 돌려 응답 모양을 확인합니다 |
| `scripts/api_e2e.py` | 로컬·배포 백엔드를 브라우저처럼 끝까지(만들기 → 올리기 → 시작 → 조회 → 원본 파일) 돌려 봅니다 |

### 환경변수

이름과 설명은 `.env.example` 에 있습니다. 값은 로컬 `.env`(커밋 안 됨)와 Vercel 프로젝트 환경변수에만 넣습니다. 백엔드는 `.env` 를 직접 읽지 않고 환경변수로 받습니다(로컬은 `uvicorn --env-file .env`).

| 이름 | 쓰는 곳 |
|---|---|
| `SUPABASE_URL`, `SUPABASE_SECRET_KEY` | DB·Storage. 새 형식 서버 비밀 키(`sb_secret_…`)가 supabase-py 2.33 에서 그대로 동작합니다 |
| `UPSTAGE_API_KEY`, `UPSTAGE_AGENT_ID`, `UPSTAGE_CONFIG_ID` | Upstage 작업. `UPSTAGE_CONFIG_ID` 가 비면 작업을 만들지 않습니다(빼면 Studio 최신 설정이 돌아 결과가 바뀜) |
| `UPSTAGE_PROJECT_ID`(에이전트가 프로젝트에 속하면 필수) | Upstage Studio 코드 패널의 Project ID(`proj_…`). 모든 Upstage 요청(파일 올리기·작업 만들기·조회·지우기)에 `x-project-id` 헤더로 보냅니다. 빠지면 올린 파일이 프로젝트 밖에 저장돼 작업 만들기가 `HTTP 403 — No access to file` 로 실패합니다. 영문·숫자·`_`·`-` 만 받습니다(그 밖은 설정 오류) |
| `UPSTAGE_BASE_URL`(선택) | 기본 `https://api.upstage.ai/v2` |
| `IMASK_API_DEV_URL`(선택, Next 개발 서버만) | `next dev` 가 `/api/py/*` 를 넘길 주소. 기본 `http://127.0.0.1:8000` |

`GET /api/py/health` 의 `configured` 로 값이 들어 있는지(값 없이 참·거짓만 — `supabase`·`upstage`·`upstage_project`) 확인할 수 있습니다.

### 로컬 실행

```bash
# 처음 한 번 — 저장소 루트에서. uv 가 .python-version(3.12)을 보고 .venv 를 만든다
uv venv
uv pip install -r requirements-dev.txt     # 실행용 requirements.txt + uvicorn·pytest

# 백엔드(포트 8000)
.venv\Scripts\python.exe -m uvicorn api.index:app --port 8000 --env-file .env    # Windows
.venv/bin/python -m uvicorn api.index:app --port 8000 --env-file .env            # macOS·Linux

# 다른 터미널에서 화면(포트 3000)
npm run dev
```

`npm run dev` 와 함께 띄우면 `http://localhost:3000/api/py/*` 가 `next.config.ts` 의 rewrites 로 uvicorn 에 연결됩니다(배포에서는 같은 프로젝트의 Python 함수 `/api/` 로 갑니다). 브라우저는 늘 같은 출처의 `/api/py/...` 만 부르므로 CORS 설정이 없습니다. 개발용 API 문서는 `http://127.0.0.1:8000/api/py/docs` 에 있습니다.

끝까지 확인하기(정상 경로는 Upstage 를 실제로 1번 돌립니다 — 크레딧 사용, 합성 묶음만):

```bash
.venv\Scripts\python.exe scripts\api_e2e.py                                           # 정상 경로(기본 testdocs/iMASK_smoke_bundle.pdf, 기대 done)
.venv\Scripts\python.exe scripts\api_e2e.py --skip-upload --expect failed             # 올리지 않고 시작 → 실패 경로
.venv\Scripts\python.exe scripts\api_e2e.py --content-file <가짜 내용> --expect failed  # 형식 불일치 → 실패 경로
.venv\Scripts\python.exe scripts\api_e2e.py --file <파일> --no-start                    # 만들기·올리기까지만
.venv\Scripts\python.exe scripts\api_e2e.py --base-url https://<배포 주소>              # 배포 사이트 확인
.venv\Scripts\python.exe scripts\api_e2e.py --analysis-id <분석 id>                     # 이미 끝난 분석 재확인(Upstage 작업 없음)
```

배포 사이트에 Vercel 보호가 켜져 있으면 `VERCEL_PROTECTION_BYPASS` 환경변수를 `x-vercel-protection-bypass` 헤더로 보냅니다. 종료 코드는 기대대로면 0, 아니면 1 입니다. done 이면 다음이 모두 맞아야 합니다: 요약(서류 6·추출 5·위험도 상), 화면용 결과(`findings` 29·좌표 있는 항목 28·`documents` 6(extracted 5·other 1, other 에 `other_guide`·extracted 에 `validation`)·`overall` 상/권장_조치·계약 키와 허용 값·id 중복 없음·`document_index` 가 `documents` 에 있음·`boxes` 0~1·`risk` 가 `risk_source` 와 맞음), 기본 응답에 `stages`·`response` 없음, 기본 응답이 `?include=stages` 응답보다 작음, `/file` 의 주소로 받은 내용이 올린 파일과 같음(sha256). 출력에는 개수·분포·바이트 수만 나오고 원문 값·가림 미리보기·서명 URL 은 나오지 않습니다. `--analysis-id` 는 만들기·올리기·시작 없이 그 분석을 조회해 위 done 확인과 원본 파일 확인만 합니다(비교할 원본은 `--file`, 기본 합성 묶음). 어떻게 끝나든(시간 초과·Ctrl+C·연결 오류 포함) 마지막에 이번 실행이 Upstage 에 남겼을 수 있는 파일을 `UPSTAGE_API_KEY` 로 지우고(404 = 이미 지움), 정리를 못 하면 종료 코드 1 입니다.

### 경로

모든 요청·응답은 JSON(UTF-8)이고, 오류 본문은 늘 `{"detail": "<짧은 한국어 문장>"}` 입니다.

| 요청 | 하는 일 | 응답 |
|---|---|---|
| `GET /api/py/health` | 설정이 있는지만 | 200 `{"ok": true, "configured": {"supabase", "upstage", "upstage_project"}}` |
| `POST /api/py/analyses` | 본문 `{"name"?, "filename", "size", "mime_type"}`. `analyses`(queued)·`documents` 행과 서명 업로드 URL 을 만든다 | 201 `{"analysis": 분석 건, "upload": {"bucket", "path", "token", "signed_url"}}` · 400 검사 실패 · 502 준비 실패(만든 행은 지움) |
| `POST /api/py/analyses/{id}/start` | 올린 파일을 Upstage 에 넘겨 작업을 만든다(완료를 기다리지 않음) | 200 분석 건(`running`, 선점 뒤 실패면 `failed` + `error`) · 404 · 409 이미 시작함 · 502 실패 기록도 못 함 |
| `GET /api/py/analyses/{id}` | 분석 건 조회. `running` 이면 Upstage 상태를 **한 번** 확인. 쿼리 `include` 에 `stages` 가 있으면(여러 번·쉼표로 줄 수 있음, 모르는 값은 무시) `result.stages` 도 넣는다 | 200 분석 건 · 404 |
| `GET /api/py/analyses/{id}/file` | 원본 파일의 Storage 서명 다운로드 URL(10분 유효)을 만든다. 상태와 상관없이, Upstage 는 부르지 않음 | 200 `{"url", "mime_type", "filename"}`(`filename` 은 원래 이름, 헤더 `Cache-Control: no-store`) · 404 `분석 건을 찾을 수 없습니다.`(uuid 아님·행 없음) · 404 `원본 파일을 찾을 수 없습니다.`(문서 행 없음·경로 빔·객체 없음) · 502 `원본 파일 주소를 만들지 못했습니다. 잠시 후 다시 시도해 주세요.` |

- 검사(400): 형식은 `application/pdf`·`image/png`·`image/jpeg` 이고 확장자가 형식과 맞아야 합니다(pdf, png, jpg·jpeg). 크기는 1바이트~20MB(20,971,520) 정수, 파일 이름은 경로를 뗀 뒤 1~200자, 분석명은 앞뒤 공백을 지운 뒤 60자 이하입니다(비면 파일 이름). 본문이 JSON 이 아니거나 필드 타입이 틀리면 `요청 형식이 올바르지 않습니다.` 입니다(FastAPI 기본 422 대신 400).
- **분석 건**(`AnalysisOut`): `id`, `name`, `status`, `upstage_job_id`, `error`, `result`(아래 [API 응답의 `result`](#api-응답의-result) — 저장 형식에서 `response`·`stages` 를 빼고 화면용 값을 더한 것), `created_at`, `updated_at`(ISO 8601, 시간대 포함), `documents[]`(`id`, `filename`, `size_bytes`, `mime_type`, `upstage_file_id`, `created_at`), `upstage_status`·`poll_error`(GET 에서 이번 조회에 본 Upstage 상태와 확인 실패 문구. DB 에는 저장하지 않음). `agent_id`·`storage_path` 는 응답에 넣지 않습니다.
- **Storage 경로**는 `analyses/{분석 id}/{안전한 이름}` 입니다. Supabase Storage 키는 일부 ASCII 만 받으므로(한글 이름은 'Invalid key') 원래 이름의 줄기에서 `[A-Za-z0-9._-]` 밖 글자 묶음을 `_` 로 바꾸고 앞뒤 `._-` 를 지운 뒤 80자까지, 비면 `document` 로 합니다. 확장자는 소문자입니다. 예: `대출 서류.pdf` → `document.pdf`, `김 2024 묶음.PDF` → `2024.pdf`. 원래 이름은 `documents.filename` 에 남습니다.
- 브라우저는 `@supabase/supabase-js` 의 `storage.from(bucket).uploadToSignedUrl(path, token, file)` 로 올립니다. 공개 키로 충분합니다(서명 토큰이 권한).
- **원본 파일 주소**(`/file`)는 `documents` 행(분석 1건 = 묶음 파일 1개)의 `storage_path` 로 `storage3` 의 `create_signed_url(path, 600)` 을 부릅니다. `supabase==2.33.0`(storage3 2.33)은 `{"signedURL", "signedUrl"}` 에 Storage 기준 주소를 붙인 **절대 주소**를 돌려줍니다(다른 버전이 상대 경로 `/object/sign/…` 를 주면 `storage_url` 에 붙입니다). 없는 객체는 Storage 가 HTTP 400 + 본문 `statusCode "404"` 로 알려 404 로 답합니다. 서명 URL 은 로그에 남기지 않습니다.

### 접근 코드 없음

`/api/py/analyses` 경로는 접근 코드 없이 처리합니다(예전 `X-Demo-Code` 검사 미들웨어 · `DEMO_ACCESS_CODE` 는 2026-11-03 없앰). 헤더를 보내도 무시합니다.

### 상태 흐름

```
queued ──(start: 원자적 선점)──▶ running ──(GET 이 Upstage 완료를 봄)──▶ done
   │                               ├──(Upstage 실패·취소·incomplete)──▶ failed
   │                               ├──(job 404, job id 저장 뒤 2분 지남)─▶ failed
   │                               └──(job id 없이 5분 지남)──────────▶ failed
   └──(start 선점 뒤 실패: 파일 없음·형식 불일치·Upstage 시작 실패)──▶ failed
```

- **선점**: `update analyses set status='running' where id=? and status='queued'`. 바뀐 행이 없으면 409 입니다. 같은 분석을 두 번 시작해 Upstage 작업이 둘 생기지 않습니다.
- **결과 반영**: `where status='running'` 조건부 갱신입니다. 두 조회가 같은 결과를 동시에 처리해도 한 번만 반영되고, 진 쪽은 다시 읽어 돌려줍니다. 진 쪽이 다시 읽기도 실패하면 조회는 조회 전 `running` 행과 `poll_error`(`분석 상태를 다시 읽지 못했습니다…`)를, 시작은 502(`분석 시작 결과를 확인하지 못했습니다…`)를 돌려줘 다시 확인하게 합니다(저장하지 못한 상태를 확정해 보여 주지 않음). 실제 분석 화면은 이 시작 502 를 받으면 오류와 함께 **'분석 건 확인하기'**(그 분석의 상세 — 실제 상태)를 보여 줍니다.
- Upstage 조회가 실패하면(연결·401·403·429·5xx·결과 받기 실패) 상태를 바꾸지 않고 `poll_error` 만 채웁니다. 다음 조회에서 다시 확인합니다(키 같은 설정을 고치면 이어서 진행).
- 단 **404**(작업 없음)는 job id 를 저장한 뒤(`updated_at` 기준) **2분이 지났으면** 없어진 작업으로 보고 `failed`(`Upstage 작업을 찾을 수 없습니다. 새 분석으로 다시 올려 주세요.`)로 바꾸고 파일을 정리합니다. 2분 전이면 만든 직후의 일시적 404 로 보고 다시 시도합니다. `include[]=all` 받기의 404 도 같습니다.
- job id 없이 5분 지난 `running` 을 `failed` 로 바꿀 때는 `upstage_job_id is null` 조건으로 갱신하고, 실제로 바꾼 경우에만 파일을 지웁니다(그 사이 시작 요청이 job id 저장에 성공했으면 실행 중인 작업이므로 건드리지 않음).
- `partial` 은 DB·화면 상태 키로만 있고 백엔드는 아직 쓰지 않습니다(분석 1건 = 묶음 파일 1개 = Upstage 작업 1개).

### Upstage 호출 순서

모든 호출에 `Authorization: Bearer <UPSTAGE_API_KEY>` 와, `UPSTAGE_PROJECT_ID` 가 있으면 `x-project-id: <프로젝트 id>` 헤더를 붙입니다(에이전트가 Studio 프로젝트에 속하면 파일·작업이 그 프로젝트 안에 만들어져야 에이전트가 파일을 읽습니다).

1. 시작: Storage 에서 파일 받기 → 내용 검사(20MB 이하, 첫 바이트: PDF 는 앞 1024바이트 안 `%PDF-`, PNG `\x89PNG\r\n\x1a\n`, JPEG `\xff\xd8\xff`) → `POST /v2/files`(안전한 이름) → `documents.upstage_file_id` 저장 → `POST /v2/responses`(`model` = 에이전트 id, `config_id`, `include: ["all"]`) → `analyses.upstage_job_id`·`agent_id` 저장.
2. 조회(화면이 3초마다 부름): `GET /v2/responses/{job}?include[]=last` 한 번. `completed` 면 `?include[]=all` 로 한 번 더 받아 `analyses.result` 에 저장합니다. 끝나면(완료·실패) `DELETE /v2/files/{id}` 로 Upstage 파일을 지웁니다(404 는 이미 지움). 지우기 실패는 결과를 바꾸지 않습니다(로그만).
3. 바깥에서 온 문구(`analyses.error`·`poll_error`·`upstage_status`·로그)는 `imask_backend.redaction` 으로 서버 비밀값 전체(Upstage 키·에이전트 id·Supabase 비밀 키), 인증 문구, Supabase 서명 URL·`token=` 값·JWT 를 가린 **뒤에** 길이를 자릅니다. 정상 만들기 응답의 `upload.token`·`upload.signed_url` 은 브라우저 업로드에 필요하므로 그대로 줍니다.

### `analyses.result` 형식

```json
{
  "format": "imask-upstage-v1",
  "job": { "id": "job_…", "status": "completed", "config_id": "3", "created_at": 1700000000, "usage": { "input_tokens": 0, "output_tokens": 0, "total_tokens": 0 } },
  "summary": { "stage_names": [], "stage_counts": {}, "document_count": 6, "document_types": ["loan_application", "…"], "extracted_document_count": 5, "risk_level": "상", "final_stage": "권장_조치", "other_document_count": 1 },
  "stages": [ { "name": "Instruct - 위험도_판정", "key": "위험도_판정", "step_type": "instruct", "status": "completed", "data": "…", "additional_values": {}, "contents": [] } ],
  "response": { "…": "include[]=all 원본 응답(최상위 model 만 뺌)" }
}
```

- `summary` 는 `imask_backend.results.summarize`, `stages` 는 `parse_stages` 결과입니다. 요약값을 못 읽으면(모양이 다름) 그 값이 `null` 일 뿐 분석은 `done` 입니다.
- 서류 종류는 영문 분류 코드(`loan_application` 등) 그대로입니다. 한국어 이름은 화면이 붙입니다.
- API 응답의 `result` 에는 `response` 가 없고 `stages` 는 `?include=stages` 일 때만 들어갑니다(아래). 합성 6쪽 묶음 기준으로 DB 의 `result` 는 약 560KB 입니다.

### API 응답의 `result`

조회 응답(`GET /api/py/analyses/{id}`)의 `result` 는 저장된 값에서 `response`·`stages` 를 빼고(`format`·`job`·`summary` 는 그대로) 화면이 바로 쓰는 `documents`·`findings`·`overall` 을 더한 것입니다(값은 지어낸 예).

```json
{
  "format": "imask-upstage-v1", "job": { "…": "…" }, "summary": { "…": "…" },
  "documents": [ { "index": 0, "type": "loan_application", "page_start": 1, "page_end": 1, "kind": "extracted", "other_guide": null, "validation": "green" } ],
  "findings": [ { "id": "0:applicant_rrn", "document_index": 0, "field": "applicant_rrn", "category": "고유식별정보", "label": "주민등록번호",
                  "subject": "신청인", "mapping_status": "ok", "value": "800101-1234567", "masked": "800101-1******", "exposure": "전체 노출",
                  "risk": "unrated", "risk_source": null, "risk_reason": null, "page": 1,
                  "boxes": [[{ "x": 0.1, "y": 0.2 }, { "x": 0.3, "y": 0.2 }, { "x": 0.3, "y": 0.22 }, { "x": 0.1, "y": 0.22 }]], "confidence": "high" } ],
  "overall": { "level": "상", "text": "## 위험도 판정 …【†1】", "next_stage": "권장_조치", "next_text": "## 권장 조치 …" }
}
```

- **조회할 때 계산합니다**(`imask_backend.findings.build_view`). DB 저장 형식은 그대로라 예전 분석에도 적용됩니다. 단계는 저장된 `response` 를 `parse_stages` 로 풀어(없으면 저장된 `stages`) status 가 `completed`(또는 없음)인 것만 씁니다. 바깥 모양이 달라도 예외를 던지지 않습니다. 탐지 항목 하나를 만들다 예외가 나면 **그 항목만** 안전한 값(`masked` 전부 `*`·`exposure` `전체 노출`·`page` null·`boxes` []·`confidence` null, id·대응표·위험등급은 정상 조회값)으로 두고 항목은 버리지 않습니다 — 값 문자열 만들기가 실패해도 `value` 는 원문 문자열 그대로이고, 원문을 문자열로 만들 수 없을 때만 고정 문구 `(값을 읽지 못했습니다)` 입니다(빈 값은 실패가 아니라 원래 항목이 아님). 그래도 예상 못 한 오류가 나면 빈 값(`documents []`·`findings []`·`overall` 빈 값)으로 200 을 돌려줍니다(로그에는 필드 이름·예외 종류만). `?include=stages` 의 `stages` 도 한 경계를 지나, 만들다 예외가 나거나(깊은 JSON 의 `RecursionError` 등) 중첩이 64단을 넘으면(실제 단계는 10단 안쪽, 응답 직렬화기 한도 약 97단) 경고 후 `[]` 입니다. 응답(분석 건 전체 — 만들기 201·시작·조회와 `/file`)은 `api/index.py` 의 응답 도우미 한 곳(`_json_out`)을 지납니다. 응답 안의 문자열·dict 키에 **짝 없는 서로게이트(U+D800~U+DFFF)가 하나라도 있을 때만** 그 응답을 `json.dumps(…, ensure_ascii=True)` 로 만든 ASCII 본문(서로게이트·비 ASCII 는 `\uXXXX` escape)으로 보냅니다(올바른 유니코드 글자가 아니라 정상 UTF-8 응답이 500 이 되므로 — `imask_backend/textsafe.py`). **이름·값은 원문 그대로**(바꾸지도 새로 짓지도 않음)라 `JSON.parse`·`json.loads` 하면 원래 키·값이 되살아나고, findings·include stages·summary 사이의 이름 대응도 그대로입니다. 상태 코드·헤더(201·`Cache-Control: no-store`)는 같고, escape 경로의 NaN·inf 는 정상 경로처럼 `null` 입니다. 서로게이트가 없으면 정상 경로 그대로라 응답은 바이트까지 같습니다.
- **`documents`**: 서류-분류 content 를 output 순서대로 훑어 `index`(0부터)를 매깁니다 — 병합 단계 `branch_key` 의 `"<순번>:<코드>"` 와 같은 번호라, 분류 코드를 못 읽은 content 도 순번은 차지합니다. `page_start`·`page_end` 는 `page_ranges` 의 최소 시작·최대 끝(없으면 `null`). `kind` 는 추출 결과가 붙으면 `extracted`, 없고 기타 안내가 붙었거나 코드가 `Other` 면 `other` 입니다.
- **짝짓기**: 추출·검증(`validation` = verdict)·기타 안내(`other_guide` = 본문 Markdown, 객체·목록이면 JSON 문자열 — 빈 문자열·빈 객체·빈 목록이면 `null`)는 서류 종류 없이 오므로 `additional_values.page_ranges` 로 잇습니다. `[a, b]`(정수, 1 ≤ a ≤ b ≤ 100000)만 남겨 정규화한 범위가 **정확히 같은**, 아직 그 값이 없는 서류 중 index 가 가장 작은 것에 붙입니다(추출 output 순서와 상관없음). **정규화한 범위가 빈 쪽이 있으면(서류든 항목이든) 짝짓지 않습니다** — 범위 없이 output 순서로 짝지어 추출 결과가 `Other` 서류에 붙는 일을 막습니다. 짝 없는 추출 결과(범위가 빈 것 포함)는 버리지 않고 서류(`type` null, index = 분류 content 수 + k, 범위가 없으면 `page_start`·`page_end` null)를 덧붙이고, 짝 없는 검증·기타 안내는 붙이지 않습니다.
- **`findings`**: 추출 결과가 붙은 서류마다 추출 키 순서대로, 빈 값은 건너뜁니다. `;` 로 여러 값이 와도 한 항목입니다. `category`·`label`·`subject`·`mapping_status` 는 [필드 대응표](docs/field-mapping.md)(`imask_backend/fields.py`, 표에 없는 키는 `unknown`)에서 옵니다. `field`·`id`(`"<document_index>:<field>"`)는 추출의 **원래 키** 그대로이고(다듬지 않음), 대응표·메타·항목별 위험등급도 원래 키로 찾습니다. 표에 없는 키의 `label` 도 원래 키(비었거나 공백만이면 `(이름 없는 항목)`)입니다. `page` 는 `additional_values[키].page`(1 이상 정수 — 관찰상 파일 전체 기준, `-1` 이면 `null`. 쪽 번호는 page·page_ranges 모두 **1~100000**(`MAX_PAGE`)만 인정하고 넘으면 버림 — 아주 큰 정수가 화면 JavaScript 에서 정밀도를 잃지 않게), `boxes` 는 단어별 사각형(`word_coordinates`)을 먼저, 없으면 값 영역(`coordinates`)을 0~1 비율로(`page` 가 없으면 `[]` — 점 4개·좌표가 -0.001~1.001 인 수가 아닌 사각형은 그것만 버림, 아주 큰 정수·inf·nan·문자열에도 예외 없음), `confidence` 는 `high`·`low`.
- **노출 상태·가림 미리보기**(`imask_backend/masking.py`)는 표시용 가공이고 판별이 아닙니다. `exposure` 는 값 속 가림 문자(`* ＊ ● ○ ■ □ ◆ ◇ ★ ☆`, 숫자 종류에서는 `X x ×` 도) 수로 `전체 노출`·`부분 마스킹`·`마스킹됨` 을 추정합니다. `masked` 는 `;` 조각마다 종류별 규칙(이름 `홍*동`, 주민등록번호 앞 7자리, 전화 앞 3·뒤 4자리, 카드 앞 4·뒤 4자리, 이메일 `@` 앞만, 주소 앞 2토큰, 그 밖은 토큰마다 첫 글자)을 쓰고, 길이는 원문과 같으며 글자는 원문 그대로이거나 `*` 입니다. 규칙 표는 [docs/field-mapping.md](docs/field-mapping.md#2-가림-규칙-화면-미리보기용--판별-아님)에 있습니다.
- **항목별 위험등급**은 서버가 판별하지 않습니다. `위험도_판정` 노드가 `[{branch_key, field, grade, reason}]` 목록을 낼 때만 옮기며, 찾는 곳은 ① `data` 가 배열이면 그것, 객체면 값 중 배열 ② `additional_values` 의 값 중 배열(예 `items`) ③ `data` Markdown 안의 **닫힌** ```` ```json ````(또는 언어 표시 없는) 코드 블록입니다. 블록 경계는 줄 단위로 읽습니다(여는 줄 = 앞 공백 0~3칸 + 백틱 3개 이상 + 정보 문자열, 닫는 줄 = 같은 개수 이상의 백틱만) — 다른 언어 블록은 닫는 줄까지 건너뛰므로 그 안의 ```` ```json ```` 줄이나 블록 밖 목록은 읽지 않고, 닫히지 않은 블록도 무시합니다. `branch_key`·`field` 는 비어 있는지(공백만 포함)만 보고 **다듬지 않고 정확히** 비교합니다(서류의 `"<index>:<type>"`·추출의 원래 키와 같을 때만 — 공백만 다른 키에 옮겨 가지 않음). `grade` 가 `상`·`중`·`하` 인 것만 `high`·`medium`·`low`(`risk_source` `"workflow"`)로 쓰고 그 밖(`검토 필요`·영어·짝 없는 키)은 무시합니다. 본문·citations 에서 추측하지 않습니다. **지금 워크플로우는 항목별 등급을 내지 않아 모든 항목이 `unrated` 입니다.**
- **`overall`**: `level` 은 `summary.risk_level`(`상`·`중`·`하`·`검토 필요` 밖이면 `null`), `text` 는 위험도_판정 본문 Markdown(인용 표시 `【†n】` 그대로), `next_stage`·`next_text` 는 `권장_조치`·`검토_안내` 단계와 그 본문입니다.
- 합성 6쪽 묶음 실측(2026-11-03): `documents` 6, `findings` 29(좌표 있는 항목 28), 기본 조회 응답 **21,008 bytes**, `?include=stages` 응답 **348,712 bytes**.

### 제한과 알아 둘 점

- **Vercel 함수의 요청·응답 본문은 4.5MB 까지**입니다. 그래서 파일은 서버를 거치지 않고 서명 업로드 URL 로 Storage 에 바로 올리고(원본 보기도 서명 다운로드 URL 로 Storage 에서 바로 받음), 기본 조회 응답에는 원본(`response`)과 단계별 결과(`stages`)를 넣지 않습니다. 합성 6쪽 묶음 실측은 기본 21,008 bytes, `?include=stages` 348,712 bytes 입니다. 쪽 수가 아주 많은 묶음은 `?include=stages` 응답이 서류-인식 결과(단어 좌표) 때문에 4.5MB 에 가까워질 수 있으니 진단용으로만 씁니다. 기본 응답은 탐지 항목 수(항목마다 단어 좌표)에 비례해 커집니다.
- **`maxDuration` 60초**(`vercel.json`). 한 요청 안에서 분석 완료를 기다리지 않습니다. 시작은 작업만 만들고, **상태는 조회(GET)가 올 때만 나아갑니다.** 아무도 조회하지 않으면 Upstage 작업이 끝나도 DB 는 `running` 으로 남고 Upstage 파일도 지워지지 않습니다. 백그라운드 작업·워커는 쓰지 않습니다.
- **실제 단계 이름이 Studio 노드 이름과 다릅니다**(`step_1_parse`, `Instruct - 위험도_판정` 등). 이름 문자열을 직접 비교하지 말고 `imask_backend.results.stage_key`·`stages_for` 를 씁니다.
- `vercel.json` 에서 `"framework": "nextjs"` 로 고정합니다. 루트 `requirements.txt` 에 FastAPI 가 있으면 Vercel 이 Python 프레임워크 프리셋을 잡아 `api/` 파일 함수 대신 앱 전체를 Python 으로 돌리기 때문입니다([공식 문서](https://vercel.com/docs/functions/runtimes/python/api-directory)). Python 함수 묶음에서는 `excludeFiles` 로 `node_modules`·`src`·`tests` 등을 뺍니다.
- 앞 단계가 Upstage 캐시를 쓰면 30초 안팎에 끝나지만, 처음 보는 파일은 1~3분 걸릴 수 있습니다.

---

## DB 변경 기록 (Supabase)

실제 API 단계에서 쓸 DB는 Supabase 프로젝트 `imask`(서울, `ap-northeast-2`)입니다. FastAPI 백엔드(`api/index.py`)가 서버 비밀 키로 이 DB와 `documents` 버킷을 읽고 씁니다([FastAPI 백엔드](#fastapi-백엔드-api) 참고). 화면은 [실제 분석 모드](#실제-분석-모드)에서만 백엔드를 부르고, 브라우저는 DB에 직접 접근하지 않습니다.

DB 구조를 바꿀 때는 **항상 `supabase/migrations/` 에 SQL 파일을 남기고 커밋합니다.** 파일 이름 앞의 번호(`YYYYMMDDHHMMSS`)가 DB에 기록된 번호와 같아야 Supabase CLI가 이미 적용된 파일로 알아봅니다.

| 파일 | 내용 |
|---|---|
| `20261102003443_init_analyses_documents.sql` | `analyses`(분석 건)·`documents`(문서) 테이블, `documents` 비공개 버킷(파일당 20MB, PDF·PNG·JPG) |
| `20261102024252_grant_service_role_tables.sql` | `service_role`(서버 비밀 키)에 두 테이블의 읽기·쓰기 권한(select·insert·update·delete)과 `public` 스키마 사용 권한을 명시. `imask` 에는 이미 같은 권한이 있어 적용해도 바뀐 것은 없음 |

- **이미 적용한 파일은 고치지 않습니다.** 바꿀 것이 있으면 새 파일을 추가합니다.
- **두 테이블 모두 RLS를 켜고 정책은 두지 않았습니다.** 브라우저는 DB에 직접 접근하지 않고, FastAPI가 비밀 키로만 읽고 씁니다. 파일은 FastAPI가 만든 서명된 업로드 주소(2시간 유효)로 브라우저가 버킷에 바로 올립니다. Vercel 함수가 받는 요청은 4.5MB까지라 파일을 서버로 보내지 않기 때문입니다.
- **새 테이블을 만드는 마이그레이션에는 `service_role` 용 GRANT를 직접 적습니다.** `service_role` 은 RLS를 건너뛰지만, 테이블 권한(GRANT)은 따로 있어야 합니다. 2026-11-02에 확인했을 때 `imask` 에는 예전 기본 권한이 남아 있어, 새 `public` 테이블에 API 역할 권한이 자동으로 붙습니다. 하지만 Supabase가 이 자동 권한을 없애는 중이라 새 환경에서는 붙지 않을 수 있습니다([공식 공지](https://supabase.com/changelog/45329-breaking-change-tables-not-exposed-to-data-and-graphql-api-automatically)). 적는 방법은 `20261102024252_grant_service_role_tables.sql` 을 따릅니다. 브라우저용 역할(`anon`·`authenticated`)은 DB에 직접 접근하지 않으므로, 지금 설계에서는 정책이나 권한을 더하지 않습니다.
- **`analyses.status` 값은 화면 코드의 상태 키(`src/display/rules.ts` 의 `ASTATUS`)와 같습니다**: `queued`·`running`·`done`·`partial`·`failed`. DB에는 이 키를 저장하고, 화면에는 키에 붙은 한국어 라벨(대기·분석 중·완료·일부 실패·실패)이 보입니다.
- `analyses.result` 에는 분석이 끝났을 때 백엔드가 `imask-upstage-v1` 형식 JSON 을 저장합니다: 요약(`summary`), 단계별로 푼 결과(`stages`), Upstage 원본 응답(`response`, 최상위 `model` 만 뺌). 자세한 모양은 [`analyses.result` 형식](#analysesresult-형식)에 있습니다. 탐지 항목·검토 기록 테이블은 화면에서 쓸 모양이 정해지면 새 마이그레이션으로 추가합니다.
- `analyses.agent_id`·`upstage_job_id` 와 `documents.upstage_file_id` 는 백엔드가 분석을 시작할 때 채웁니다. `documents.filename` 은 올린 원래 이름, `storage_path` 는 버킷 안 경로(`analyses/<분석 id>/<ASCII 로 바꾼 이름>`)입니다.

```bash
npx supabase login                                     # 처음 한 번. Supabase 계정 로그인(DB 비밀번호와 별개)
npx supabase link --project-ref wanmwoohjkdutzsrdwnf   # 처음 한 번. DB 비밀번호를 묻는다
npx supabase migration list                            # Local·Remote 양쪽에 같은 번호가 보이면 정상

# 구조를 바꿀 때
npx supabase migration new add_findings                # 빈 파일 supabase/migrations/<번호>_add_findings.sql 생성. SQL을 쓰고 검토한 뒤 db push
npx supabase db push                                   # 아직 적용 안 된 파일을 DB에 적용
```

- **Supabase 커넥터(MCP `apply_migration`)로 적용했다면 DB에 기록된 번호로 파일 이름을 만듭니다.** 커넥터로 적용하면 번호가 적용한 시각(UTC)으로 정해집니다. 그러니 적용한 뒤 `npx supabase migration list` 나 DB의 `supabase_migrations.schema_migrations` 에서 기록된 번호를 확인하고, 그 번호로 파일 이름을 만듭니다. CLI `db push` 로 적용할 때는 파일 이름의 번호가 그대로 기록됩니다.
- DB 비밀번호를 모르면 Supabase 대시보드의 Database > Settings 에서 재설정합니다([공식 안내](https://supabase.com/kb/troubleshooting/how-do-i-reset-my-supabase-database-password-oTs5sB)).
- 필요한 환경변수 이름은 `.env.example` 에 있습니다. Supabase 비밀 키(`SUPABASE_SECRET_KEY`)와 Upstage 키는 서버 전용이라 `NEXT_PUBLIC_` 을 붙이지 않습니다.
- `supabase/config.toml` 은 `supabase init` 이 만든 로컬 개발용 설정입니다. 이 파일을 커밋하거나 앱을 배포하는 것만으로는 원격 프로젝트 설정이 바뀌지 않습니다. 다만 `npx supabase config push` 는 이 파일의 설정을 연결된 원격 프로젝트에 올리므로, 따로 검토한 뒤에만 씁니다.

---

## 데모 서비스를 실제 API로 바꾸기

화면은 `src/services/react.tsx` 의 훅으로만 데이터를 다루고, 훅은 `AnalysisService` 인터페이스만 부릅니다. 데모 서비스(`src/services/demo/`)와 실제 분석 서비스(`src/services/api/`)가 같은 인터페이스를 구현하고, 어느 것을 쓸지는 한 곳에서 고릅니다.

### 1. 고르는 곳 — 주소 기준 `ServiceProvider`(`src/services/react.tsx`)

```ts
// src/services/mode.ts — /demo 아래는 언제나 데모, 그 밖은 빌드 모드
export function modeForPath(pathname: string | null | undefined, buildMode: ServiceMode): ServiceMode {
  return isDemoPath(pathname) ? 'demo' : buildMode;
}

// src/services/index.ts — 모드별 서비스 만들기
export function createServiceFor(mode: ServiceMode): AnalysisService {
  return mode === 'api' ? createApiService() : createDemoService();
}
```

- 빌드 모드 `SERVICE_MODE`(`src/services/mode.ts`)는 `NEXT_PUBLIC_IMASK_SERVICE` 가 정확히 `api` 일 때만 `'api'`, 그 밖(없음 포함)은 `'demo'` 입니다. `process.env.NEXT_PUBLIC_IMASK_SERVICE` 를 글자 그대로 참조해야 Next 가 빌드 때 값을 넣습니다(`process.env[name]` 처럼 쓰면 브라우저 코드에 값이 들어가지 않습니다). 이 환경변수는 `mode.ts` 와, pdf.js 묶음을 빼는 `src/components/detail/liveFile.ts` 의 빌드 분기에서만 읽습니다.
- `ServiceProvider` 가 `usePathname()` 으로 **화면의 모드**(`modeForPath(경로, SERVICE_MODE)`)와 **기준 경로**(`routeBaseFor(경로)` — `''` 또는 `'/demo'`, `src/lib/routes.ts`)를 한 번 계산해 내립니다. 화면은 `useServiceMode()`·`useRouteBase()` 로 받습니다. 모드·기준 경로는 서버에서도 주소로 정해지므로 첫 그림부터 맞습니다(하이드레이션 불일치 없음). `SERVICE_MODE` 는 `src/services` 밖에서 읽지 않고 `@/services` 로 다시 내보내지도 않습니다.
- 서비스는 **모드별 브라우저 싱글턴**(`createServiceCache()` — 데모 하나, 실제 분석 하나)입니다. 그 모드를 처음 쓸 때 만들고, 화면을 옮겨도 그대로 써서 상태가 이어집니다. 서버 렌더와 하이드레이션 첫 렌더에서는 서비스가 없고(`useService()` 가 `null`), 화면은 불러오는 중 화면을 보여 줍니다. `/` ↔ `/demo` 를 오가면 새 서비스 값이 올 때까지 불러오는 중이라 다른 서비스의 값(예: 헤더 '검토 필요' 숫자)이 남지 않습니다.
- 루트 라우트 페이지 3개(`src/app/analyses/new`·`[id]`·`[id]/report`)는 `ByServiceMode`(`src/components/layout/ByServiceMode.tsx` — `useServiceMode()` 로 둘 중 하나를 그림)에 데모 화면과 실제 분석 화면을 함께 넘깁니다. `/demo` 아래 페이지(`src/app/demo/`)는 실제 분석 화면을 거치지 않고 데모 화면을 바로 그립니다. 헤더 배지(`AppHeader`)도 `useServiceMode()` 로 정하고, 모드 전환 링크('데모 체험하기' · '실제 분석으로' — `modeSwitch.ts`)는 `useServiceMode()` 와 이 빌드의 모드 `useBuildMode()` 로 고릅니다(데모 빌드에는 없음). 실제 분석 화면은 `src/components/live/` 에 따로 있고, 목록(`/`·`/demo`)은 두 모드가 같은 화면을 씁니다.
- 화면 안 이동 주소는 `src/lib/routes.ts` 의 함수(`listHref`·`newAnalysisHref`·`detailHref`·`reportHref`, 기준 경로 붙이기 `withBase`)에 `useRouteBase()` 값을 넘겨 만듭니다. 기준이 `''` 이면 예전과 바이트 단위로 같은 주소입니다.
- 지킴 테스트(`src/lib/navigation-guard.test.ts`, `npm test`)가 소스를 읽어 `src/app`·`src/components`·`src/lib`·`src/dev` 의 `SERVICE_MODE` 사용, `mode.ts`·`liveFile.ts` 밖의 `NEXT_PUBLIC_IMASK_SERVICE` 사용, 화면 코드의 이동 주소 리터럴(`'/analyses…'`·`href="/"`·`push('/')` 등)을 파일:줄로 알려 줍니다.
- `createService()` 는 빌드 모드의 서비스를 만듭니다(테스트용 — 테스트 환경은 값이 없어 데모). 화면은 쓰지 않습니다.
- 실제 분석 화면은 데이터를 서비스로만 다루고, 예외로 오류 판별(`apiErrorCode`·`apiErrorAnalysisId`)만 `@/services` 에서 가져다 씁니다.

### 2. 인터페이스 계약 — `AnalysisService`

- **`subscribe` 를 뺀 모든 메서드는 `Promise` 를 돌려줍니다.** 각 메서드 주석에 예상 엔드포인트(`실제: GET /analyses` 등)를 적어 두었습니다. 지금 백엔드에 있는 경로는 [FastAPI 백엔드](#fastapi-백엔드-api)의 네 개뿐입니다.
- **조회 결과는 화면이 고치지 않는 값으로 다룹니다.** 데모 서비스는 깊은 복사본(`structuredClone`)을 돌려주고, 실제 분석 서비스는 요청마다 새로 만든 값을 돌려주므로 화면에서 고쳐도 서비스 상태가 바뀌지 않습니다. 바꾸려면 변경 메서드를 부릅니다.
- 위험등급과 판단 근거는 서비스가 준 값을 그대로 표시하고, 화면에서 계산하지 않습니다.

| 묶음 | 메서드 | 실제 분석 서비스 |
|---|---|---|
| 조회 | `list()`, `get(id)`(없으면 `null`), `pending(id)`(검토 완료 전에 남은 항목), `sampleFiles()` | `list` 는 이 탭에서 만든 분석을 조회(404 는 빼고 건너뜀), `get` 은 `GET /api/py/analyses/{id}`(404 → `null`), `pending` 은 늘 빈 값, `sampleFiles` 는 빈 목록 |
| 분석 | `requestAnalysis({ name, files, onProgress? })` → 분석 ID, `retry(id, docId?)` | `requestAnalysis` 는 파일 1개(`UploadFile.file`)로 만들기 → 서명 업로드 → 시작, 단계마다 `onProgress('create' \| 'upload' \| 'start')`. 시작이 5xx·네트워크·시간 초과면 분석 id 를 목록에 넣고 `ApiError.analysisId` 에 담아 거절. `retry` 는 `{ ok: false, message }`(지원하지 않음) |
| 탐지 항목 검토 | `setStatus`, `confirmMany`, `markFalsePositive`, `restore`, `reclassify`(바뀐 값이 없으면 `false`), `saveFindingMemo` | 거절(`실제 분석에서는 아직 지원하지 않는 기능입니다.`) |
| 검토사항·문서 간 연결 | `resolveItem`, `reopenItem`, `decideLink` | 거절 |
| 검토 메모·완료 | `saveMemo`, `completeReview`, `reopenReview` | 거절 |
| 내보내기 | `buildExport(id, format, brand?)` → `ExportFile`, `logExport(id, file, state)` | 거절 |
| 변경 알림 | `subscribe(listener)` → 구독 해제 함수 | 아래 3 참고 |

- 실제 분석을 위해 타입에 선택 필드를 더했습니다(데모 서비스·샘플은 넣지 않습니다):
  - `UploadFile.file`(브라우저 `File`), `RequestAnalysisInput.onProgress`(데모 화면은 넘기지 않습니다 — 데모 서비스는 입력을 `structuredClone` 하므로 함수를 넘기면 실패).
  - `Analysis.raw`(백엔드 원래 값) — 결과 JSON(`result`, 기본 조회에는 `stages` 가 없음)·올린 파일(`file`)·`detailReady`(공통 계약 결과라 상세 검토 화면으로 보일 수 있는지)·`overall`(묶음 위험도 판정과 다음 단계 Markdown)·오류·작업 번호·조회 상태·원래 시각.
  - `AnalysisDoc.source`(`DocSource` — 분류된 서류가 묶음 파일 안 어디에 있는지: 분류 순번·코드·파일 기준 쪽 범위·`extracted`/`other`·기타 서류 안내·검증 결과).
  - `Finding.boxes`(`FindingBox[]` — 위치 ID `a` 와 쪽 크기에 대한 0~1 비율 꼭짓점. 같은 ID 가 `anchors` 에 들어 있습니다), `Finding.live`(`FindingLive` — 계약 id·영문 키·원문 값·매핑 상태·신뢰도·위험등급 출처).
  - `Finding.rule` 은 `RuleId | ''`(`''` = 적용 규칙 없음 — 실제 분석). 규칙 이름은 `ruleName(rule)`(`src/display/rules.ts`, 없으면 `''`)로 읽습니다.
- 백엔드 오류는 `ApiError { status, code: 'unauthorized' | 'not_found' | 'conflict' | 'bad_request' | 'server' | 'network', message, analysisId }` 로 옵니다. `message` 는 백엔드의 한국어 `detail` 이거나 기본 문구이고, `analysisId` 는 시작 결과를 모를 때만 이미 만든 분석 id 입니다(화면은 `apiErrorAnalysisId()` 로 읽음).
- 서명 업로드 오류는 SDK 오류 문구(바깥 응답 그대로 — 서명 URL·토큰이 섞일 수 있음)를 기록하지 않습니다. 콘솔에는 고정 문구 + 오류 이름 + 숫자 HTTP 상태만 남깁니다(`describeUploadError`).
- `sampleFiles()` 는 새 분석 화면의 '데모용 샘플 문서로 체험하기'와 `/analyses/new?sample=1` 에 쓰는 데모 기능이지만, 인터페이스에 있으므로 실제 분석 서비스도 구현합니다(빈 목록).

### 3. 변경 알림 — `subscribe`

`subscribe(listener)` 는 유일하게 Promise가 아닌 메서드로, 구독 해제 함수를 돌려줍니다. 데이터 훅(`useAnalyses`·`useAnalysis`·`usePending`)과 헤더의 '검토 필요' 숫자는 **이 알림을 받으면 다시 불러옵니다.**

- 데모 서비스: 변경 메서드가 성공했을 때, 분석 진행(대기 → 분석 중 → 완료·실패)이 바뀌었을 때 `listener()`, 분석이 끝났을 때 `listener({ type: 'done', id, name, items, findings })`(`ServiceEvent` — 화면이 분석 완료 토스트를 띄웁니다).
- 실제 분석 서비스: `requestAnalysis` 가 성공했을 때만 `listener()`. 진행 확인은 알림 대신 상세 화면이 3초마다 `refresh()` 로 조회합니다. 분석 완료 이벤트는 보내지 않습니다(탐지 항목이 아직 없어 완료 토스트의 '탐지 0건'이 오해를 줍니다).

### 4. 데모 전용 조작 — `DemoControls`

`getDemoControls(service)`(`src/services/index.ts`)는 데모 서비스일 때만 `DemoControls` 를 주고, 그 밖에는 `null` 을 돌려줍니다. 화면에서는 `useDemoControls()` 로 받습니다(서비스가 주소 기준이라 실제 분석 모드 빌드에서도 `/demo` 아래에서는 데모 조작이 있습니다).

| 메서드 | 하는 일 |
|---|---|
| `reset()` | 샘플 분석 6건과 미리 해 둔 검토 동작으로 되돌린다 |
| `clearAll()` | 분석 이력을 모두 지운다(지금은 테스트에서만 부른다) |
| `prepare(state)` | `/dev/states` 의 상태를 만들고, 상세·보고서 상태면 열 분석 ID를 돌려준다 |

쓰는 곳과, 실제 분석 모드라 `null` 일 때:

| 쓰는 곳 | 실제 분석 서비스(`getDemoControls` 가 `null` — 실제 분석 모드 빌드의 `/demo` 밖)일 때 |
|---|---|
| 목록이 비었을 때의 '샘플 분석 건 둘러보기' 버튼(`src/components/list/ListScreen.tsx` → `reset()`) | 버튼이 나오지 않습니다. 목록 화면의 나머지는 그대로 동작합니다. |
| `/dev/**` — `/dev/states/[state]` 미리보기(`src/dev/PreparedState.tsx` → `prepare()`) | 상태를 만들지 않아 미리보기 화면이 그려지지 않습니다(위쪽 상태 이동 막대만 보임). |

화면 4개는 `DemoControls` 없이 `AnalysisService` 만으로 동작합니다.

**실제 분석 전용 통로 — `LiveExtras`.** 같은 방식으로 `getLiveExtras(service)`(`src/services/index.ts`)는 실제 분석 서비스일 때만 `LiveExtras` 를 주고, 데모 서비스(그 밖)면 `null` 입니다. 화면에서는 `useLiveExtras()`(`src/services/react.tsx`, 서비스가 아직 없으면 `null`)로 받습니다.

| 메서드 | 하는 일 |
|---|---|
| `loadFile(id)` → `{ bytes: ArrayBuffer, mime, filename }` | 부를 때마다 `GET /api/py/analyses/{id}/file` 로 **새 서명 주소**(10분 유효)를 받고 그 주소에서 원본 파일을 받습니다(캐시는 화면이 합니다). 주소는 `https:`(또는 로컬 가짜 백엔드용 `http://localhost`·`127.0.0.1`)만 받고, 받기 요청에는 사용자 지정 헤더를 붙이지 않습니다(`credentials: 'omit'`·`cache: 'no-store'`). 시간 제한 60초(본문까지), 2xx 아님·빈 본문·20MB 초과는 오류입니다. 없음 404 는 **안전한 백엔드 문구만** 그대로 보이고 주소·서명·키·긴 토큰 모양이 섞이면 고정 안내 문구로 바꾸며, 그 밖 오류(5xx·네트워크·시간 초과·받기 실패 등)는 늘 고정 한국어 문구의 `ApiError` 이고, **서명 주소·토큰은 오류 문구·콘솔 어디에도 남기지 않습니다**(`src/services/api/file-download.ts`). |
| `loadStages(id)` → `unknown[] \| null` | `GET /api/py/analyses/{id}?include=stages` 의 `result.stages`(배열이 아니면 `null`). 404·401 은 `null` 이 아니라 `ApiError` 로 거절합니다(화면이 문구를 보입니다). |

### 5. 분석 출력 형식이 확정되면

이 파일들을 바꿉니다. 타입은 ② 표시 규칙의 목록에서 뽑아 쓰므로, 바꾼 뒤 `npm run typecheck` 가 고칠 곳을 알려 줍니다.

- **`src/display/rules.ts`** — 위험등급(`RISK`), 분석·검토·탐지 상태(`ASTATUS`·`RSTATUS`·`FSTATUS`), 검토사항 종류(`RTYPE`), 연결 상태(`LSTATUS`), 규칙 ID 예시(`RULES`), 이력 구분(`HKIND`), 정보 종류(`CATS`), 정보 주체(`SUBJECTS`), 노출 상태(`EXPOSURES`), 오탐 사유(`FP_REASONS`), 내보내기 형식(`EXPORT_FORMATS`)의 키·라벨·아이콘·색 토큰.
- **`src/services/types.ts`** — 분석 건(`Analysis`), 문서(`AnalysisDoc`), 탐지 항목(`Finding`), 검토사항(`ReviewItem`), 문서 간 연결(`DocLink`), 이력(`HistoryEntry`), 업로드 파일(`UploadFile`), 내보내기 파일(`ExportFile`)의 모양.
- **`src/services/api/mapping.ts`** — 백엔드 응답(`AnalysisOut`)을 `Analysis` 로 바꾸는 순수 함수(`toAnalysis`). 상태·시각·분석 번호와 함께, 완료된 분석의 `result` 가 공통 계약(유효한 `documents` 1개 이상 + `findings` 배열)이면 `raw.detailReady = true` 로 표시하고 공통 계약 읽기(`src/services/api/contract.ts`)로 화면 도메인을 채웁니다. 그 밖(대기·분석 중·실패·옛 형식·서류 0개)은 전처럼 `docs` = 올린 파일 행, `findings` = `[]` 입니다. 결과 원래 값은 `Analysis.raw.result` 에 둡니다.
  - 서류: `documents[]` → `AnalysisDoc`(`index` 순, id `doc-<index>`, 제목 = 분류 코드의 한국어 이름 `docTypeName` — 같은 이름은 두 번째부터 ` 2`·` 3`, `pageCount`·`source`).
  - 탐지 항목: `findings[]` → `Finding`. 화면 번호는 `D<서류 목록 순번>-<그 서류 안 순번 두 자리>`(예 `D1-01`)로 새로 만들고 계약 id(`<document_index>:<field>`)는 `live.id` 에 둡니다. 서류 목록 순번은 정렬·중복 제거한 서류 목록(화면의 서류 순서)의 위치(1부터)라 계약 `index` 에 빈 번호가 있어도 `D1`·`D2`·`D3` 으로 이어집니다(계약 `index` 는 `source.index`·서류 id `doc-<index>` 에 남습니다). 짝이 되는 서류가 없는 항목은 버립니다. 정보 종류·주체·노출이 목록 밖이면 `기타 개인정보`·`기타`·`전체 노출`. 항목 위험등급은 `risk_source` 가 `workflow` 일 때만 받은 값이고 그 밖은 미평가(고정 판단 근거 문구). 쪽은 파일 기준 → 서류 안 쪽으로 바꾸고, 쪽을 모르거나 범위 밖이면 1쪽·위치 없음(`anchors: []` — '위치 확인 필요', 원문 값이 근거 문구). 상자는 꼭짓점 2개 이상·모든 좌표가 유한한 수인 것만 `boxes` 로 옮깁니다(위치 ID `<항목 번호>#<순번>`, 값은 자르지 않음).
  - 분석 건: 위험등급 = `overall.level`(없으면 `summary.risk_level`), `riskReasons` = `overall.text`, `recs` = `overall.next_text`(권장 조치든 검토 안내든 — 단계 이름은 `raw.overall.nextStage`)를 Markdown 줄 목록으로 바꿉니다(`markdownLines` — 제목·빈 줄을 빼고 목록 기호·인용 표시 `【…】`·굵게 `**` 를 지움).
  - 계약 모양 고정 자료는 `src/services/api/fixtures/done-result.json`(합성 묶음 `testdocs/iMASK_smoke_bundle.pdf` 6쪽 = 서류 6개, `stages` 없음)입니다. 테스트와 가짜 백엔드가 같은 파일을 씁니다.

---

## 디자인 규칙

- **색·크기는 `src/styles/tokens.css` 의 토큰(CSS 변수)으로만 씁니다.** 색·크기·간격·둥글기·그림자·글자 크기·줄 간격·자간·z-index·시간·곡선 모두 해당합니다. `npm run check:tokens` 가 검사합니다.
  - CSS Modules·`globals.css`: 16진수·`rgb()`·`hsl()` 같은 색 리터럴 금지. 길이는 `0`, `1px`, `2px`, `%`, `fr`, `vh`/`vw`, `var()` 만. `.2s` 같은 시간 리터럴 금지, 곡선은 `var(--ease…)` 만. `@media` 조건과 `@keyframes`·`@property` 블록 안은 예외입니다.
  - TS/TSX: `src/config/app.ts` 밖에서 색 문자열 금지. 인라인 style은 계산한 값(위치, 개수, CSS 변수 지정)에만 씁니다.
  - 꼭 필요한 예외는 그 줄 끝에 `tokens-ok: <이유>` 주석을 답니다(CSS는 `/* … */`, TS는 `// …` 또는 `/* … */`).
- **브랜드명·강조색(`#00845C`)·담당자·업로드 제한·데모 지연 시간은 `src/config/app.ts`(`CONFIG`)에서만 바꿉니다.** 강조색은 `<html style="--accent: …">` 로 들어가고, 파생 색(진하게·옅게 등)은 `tokens.css` 가 `color-mix` 로 만듭니다. 강조색을 바꾸면 `tokens.css` 의 `--accent` 기본값과 파비콘 `src/app/icon.svg` 의 색도 함께 바꿉니다(둘 다 같은 값을 직접 적어 두었습니다).
- **화면은 샘플 데이터를 import하지 않습니다.** `src/samples/**` 는 `src/services/demo/**` 만 import할 수 있고, ESLint 규칙(`no-restricted-imports`, 동적 `import()`·`require()` 는 `no-restricted-syntax`)이 막습니다. 화면은 `src/services/react.tsx` 의 훅을 씁니다.
- **등급·상태 라벨과 정보 종류·주체 목록은 `src/display/rules.ts` 한 곳에만** 둡니다. 다른 파일에 같은 목록을 다시 적지 않습니다.
- **글꼴**: 한글은 Pretendard(npm `pretendard` 의 가변 woff2를 `next/font/local` 로), 고정폭은 IBM Plex Mono(`next/font/google`, 400·500·600). `src/app/fonts.ts` 에 있고, CSS에서는 `var(--sans)`·`var(--mono)` 를 씁니다.
- **움직임과 접근성**: 곡선은 `--ease` 하나입니다. `prefers-reduced-motion: reduce` 이면 `globals.css` 의 전역 규칙으로 모든 움직임이 즉시 끝납니다(JS 부드러운 스크롤도 즉시 이동). 포커스는 `:focus-visible` 강조색 윤곽선으로 보이고, 탭(화살표)·드롭다운(화살표·Home·End·Enter·Esc)·모달(포커스 가둠·Esc·닫으면 원래 자리로)은 키보드로 다룹니다. 상태 변화는 `aria-live` 알림 영역으로 읽어 줍니다.
- **휴대폰 누름 영역은 44px 이상**(`--touch-min`)입니다. 디자인상 더 작은 조작(아이콘 버튼, 작은 버튼, 탭, 필터 칩, 스위치, 띠 버튼)은 보이는 크기를 그대로 두고 투명 `::after` 로 누르는 영역만 넓힙니다. 이웃과 간격이 좁은 곳은 넓힌 영역이 겹치지 않게 나눕니다 — 필터 칩·스위치는 감싼 요소가 `--filter-chip-hit-top/bottom`·`--switch-hit-top/bottom` 으로 넓힐 양을 정하고, 줄이 바뀌는 버튼 줄(상세 항목 행동·필터 칩)은 휴대폰에서만 줄 간격을 8px(= 44 − 36)로 둡니다.
- 컴포넌트 파일은 `Button.tsx` + `Button.module.css` 처럼 짝을 맞춥니다.
- **화면 안 이동 주소는 `src/lib/routes.ts` 함수 + `useRouteBase()` 로만 만듭니다**(`/demo` 아래에서 `/demo` 밖으로 새지 않게). 화면의 모드 판단은 `useServiceMode()` 로 합니다(`SERVICE_MODE` 를 직접 읽지 않음). `npm test` 의 지킴 테스트가 둘 다 검사합니다.

---

## /dev/states 사용법

디자인의 화면 상태를 하나씩 열어 보는 개발용 페이지입니다.

- `/dev/states` 에 상태 **23개**가 화면별(분석 목록 3, 새 분석 6, 상세 검토 11, 보고서 3)로 번호, 상태 ID, 여는 화면 경로(`/` · `/analyses/new` · `/analyses/[id]` · `/analyses/[id]/report`)와 함께 나옵니다. 상태 정의는 `src/dev/states.ts`, 상태별 화면 연결은 `src/dev/StatePreview.tsx` 입니다.
- 상태를 누르면 `/dev/states/<상태 ID>` 로 가서 **데모 서비스를 그 상태로 맞춘 뒤**(`DemoControls.prepare`) 해당 화면을 엽니다. 실제 화면 주소에는 개발용 파라미터를 넣지 않습니다(목록 상태의 필터도 URL과 잇지 않습니다).
- 위쪽 막대 `← 상태 목록 · n / 23 · 상태 이름 · 이전 · 다음` 으로 목록에 돌아가거나 이전·다음 상태로 옮겨 갑니다. 키보드로는 `[`(이전)·`]`(다음)을 누릅니다(입력칸에 글자를 쓰는 중에는 무시). 상태를 바꿀 때마다 데모 서비스를 그 상태로 다시 준비합니다.
- **휴대폰 전용 상태 2개는 목록에 없고 주소로만 엽니다**: `/dev/states/detail-docs`(문서 탭), `/dev/states/detail-results`(탐지 결과 탭). 막대에 번호 대신 '휴대폰 전용'이 나오며, 휴대폰 폭(768px 미만)으로 봅니다.
- 상태를 열 때마다 데모 데이터를 샘플로 되돌린 뒤 그 상태를 만듭니다. 같은 탭에서 실제 화면으로 넘어가면 그 데이터가 이어지므로, 처음 샘플로 돌아가려면 새로 고침합니다.
- 실제 분석 모드 빌드에서는 `/dev/**` 가 `/demo` 밖이라 실제 분석 서비스를 쓰고 `DemoControls` 가 없어 상태를 만들지 못합니다(데모 서비스 전용 — 데모는 `/demo` 에서 봅니다).

---

## 이번 단계에서 하지 않은 것

- **로그인, 실제 분석 결과의 검토.** 실제 분석 모드는 업로드·분석·진행 상태와, 끝난 결과를 상세 검토 화면으로 **읽기 전용** 보기까지입니다. 검토 동작·검토사항·문서 간 연결·검토 기록·보고서·내보내기는 데모 서비스에만 있습니다(업로드·분석 진행은 `CONFIG.sim` 의 지연 시간으로 흉내 냄). 담당자(`CONFIG.user`)는 로그인 전 단계의 데모 값입니다. 내보내기 파일은 브라우저 다운로드(Blob)로 저장합니다.
- **마스킹한 파일 만들기.** 데모의 원문은 프로토타입처럼 샘플 문서 화면(블록으로 그린 가상 문서)이고, 실제 분석 모드는 올린 PDF·이미지의 쪽을 그대로 그립니다. 마스킹 미리보기는 둘 다 화면에서만 가립니다(원본 파일은 바뀌지 않음).
- **규칙 ID(`PII-ID-001` 등)와 위험 판정은 디자인용 예시입니다.** 실제 기준처럼 늘리지 않습니다.
- **`next.config.ts` 의 `cacheComponents`·`partialPrefetching` 은 껐습니다.** 데이터를 모두 브라우저에서 가져오기 때문입니다(데모 서비스, 또는 실제 분석 모드에서 브라우저가 부르는 `/api/py`). 서버 컴포넌트에서 데이터를 가져오게 되면 다시 검토합니다.

---

## 알아 둘 점

- **CSS Module에서 전역 `@keyframes` 를 쓸 때는 이름을 변수로 넘깁니다.** Turbopack(Lightning CSS)의 CSS Modules는 `animation` 의 이름을 모듈마다 바꿔서 `globals.css` 의 `@keyframes dg-*` 와 연결을 끊습니다(움직임이 돌지 않음). 예:
  ```css
  --dg-anim: dg-in; /* globals.css 의 @keyframes — CSS 모듈이 이름을 바꾸지 않게 변수로 넘긴다 */
  animation: var(--dg-anim) var(--dur-enter) var(--ease) both;
  ```
- **브라우저 접두어 속성을 직접 쓰지 않습니다.** `backdrop-filter` 와 `-webkit-backdrop-filter` 를 함께 쓰면 Lightning CSS가 하나로 합쳐 `-webkit-` 쪽만 남기고, Chrome에서는 계산값이 `none` 이 되어 흐림이 사라집니다. 접두어 없는 속성 한 줄만 쓰면 처리기가 필요한 접두어를 붙입니다.
- 위 두 문제는 타입 검사·빌드로 잡히지 않습니다. 움직임·흐림을 고쳤다면 브라우저에서 `getComputedStyle` 값이나 스크린샷으로 확인합니다.
- **WSL에서 스크린샷·브라우저 확인은 Windows Chrome으로 합니다.** WSL 안의 `npx playwright` 는 Chromium 리비전이 맞지 않고 Linux 라이브러리(`libnss3` 등)가 없어 돌지 않았습니다. Windows의 `node.exe` 로 `playwright-core` 를 불러 Windows Chrome을 띄우면 WSL의 `localhost` 개발 서버에 그대로 접속됩니다. 휴대폰 폭(390px)은 Chrome `--headless --screenshot` 만으로는 최소 창 폭 때문에 틀리게 나오니 모바일 에뮬레이션(`isMobile`)을 씁니다. Playwright는 `package.json` 에 넣지 않았습니다.
- **`<main>` 은 AppShell이 그립니다.** 페이지·화면 컴포넌트의 최상위는 `<div>`(또는 `<section>`·`<article>`)로 하고 `<main>` 을 다시 쓰지 않습니다.
- **데이터 훅을 쓰는 화면은 클라이언트 컴포넌트(`'use client'`)입니다.** 서버 렌더 때는 서비스가 없어 불러오는 중 화면이 먼저 나옵니다.
- **Next 16에서 동적 라우트의 `params` 는 Promise입니다**(서버 컴포넌트는 `await params`, 클라이언트 컴포넌트는 `React.use(params)`).
- `next.config.ts` 의 그 밖의 설정: `agentRules: false` 는 `next dev` 가 AI 에이전트를 감지했을 때 저장소 루트에 `AGENTS.md` 를 만드는 것을 막고, `devIndicators: false` 는 개발 화면 왼쪽 아래 표시를 숨깁니다(컴파일·실행 오류 화면은 그대로 나옵니다).
