# iMASK — 문서가드 웹

은행 여신 담당자가 대출 서류 묶음(PDF·이미지)에서 찾은 민감정보 탐지 결과(위험등급과 판단 근거)를 검토하고, 보고서로 내보내는 웹 서비스 **문서가드**의 **1단계 화면 껍데기**입니다.

- 지금은 브라우저 안의 **데모 서비스**가 샘플 데이터로 응답합니다. 샘플 속 이름·주민등록번호·전화번호·계좌번호·주소·금액은 모두 가상입니다. 화면의 '데모 데이터' 표시도 이 때문에 있습니다.
- 실제 분석은 나중에 **FastAPI 백엔드**가 **Upstage Studio 워크플로우**를 호출해서 합니다. 화면은 분석 상태·결과·검토 기록만 주고받습니다.
- Next.js 16(App Router), TypeScript strict, CSS Modules와 디자인 토큰(CSS 변수)으로 만들었습니다. Tailwind, CSS-in-JS, UI 라이브러리는 쓰지 않습니다.

## 화면

| 주소 | 화면 | 하는 일 |
|---|---|---|
| `/` | 분석 목록 | 요약 카드, 검색·필터·정렬(URL 검색 파라미터 `q`·`risk`·`status`·`review`·`sort` 와 이어짐), 분석 건 표, 비어 있을 때 안내 |
| `/analyses/new` | 새 분석 | 파일 선택 검사(PDF·PNG·JPG, 파일당 20MB, 최대 10개), 업로드 진행, 분석 요청 |
| `/analyses/[id]` | 상세 검토 | 문서 목록, 원문(샘플 문서 화면)과 하이라이트, 결과 패널(탐지 항목 · 검토 필요 · 문서 간 연결 탭, 필터 칩, '현재 문서만 보기'). 아래 검토 동작을 하고 검토를 완료합니다 |
| `/analyses/[id]/report` | 검토 결과 보고서 | 검토 결과 정리, 내보내기(CSV·JSON 파일을 브라우저 다운로드로 저장) |

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

목록의 검색·필터·정렬은 URL 검색 파라미터에 있고, 목록 화면이 마지막 값을 탭의 `sessionStorage`(`docguard:list-query`)에 기억합니다(`src/components/list/listReturn.ts`). 다른 화면에서 목록으로 갈 때는 프로토타입처럼 이 값을 이어 씁니다.

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
│  ├─ index.ts              createService() — 실제 API로 바꾸는 한 곳
│  └─ react.tsx             ServiceProvider와 훅(useService·useAnalyses·useAnalysis·usePending …)
├─ app/                     ⑤ 라우트 — layout.tsx·providers.tsx·fonts.ts·globals.css,
│                             page.tsx(/), analyses/(새 분석·상세·보고서), dev/(states·components)
├─ components/              ⑤ 화면 컴포넌트
│  ├─ ui/                   공통 컴포넌트(버튼·입력·드롭다운·탭·모달·토스트·상태 표기 …)
│  ├─ layout/               헤더, AppShell(<main>·토스트·알림 영역·아이콘 스프라이트), 데모 표시
│  ├─ list/                 분석 목록
│  ├─ upload/               새 분석
│  ├─ detail/               상세 검토
│  ├─ modals/               상세 검토의 검토 동작 모달
│  └─ report/               보고서와 내보내기
├─ styles/tokens.css        디자인 토큰(CSS 변수) — 색·크기 리터럴은 이 파일에만 있다
├─ lib/                     형식 도우미(format.ts), 브라우저 다운로드(download.ts), 공통 훅(hooks/)
└─ dev/                     /dev/states 상태 정의(states.ts)와 미리보기
scripts/check-tokens.mjs    토큰 규칙 검사기(같은 폴더에 검사기·ESLint 경계 테스트)
```

---

## 데모 서비스를 실제 API로 바꾸기

화면은 `src/services/react.tsx` 의 훅으로만 데이터를 다루고, 훅은 `AnalysisService` 인터페이스만 부릅니다. 그래서 바꿀 곳은 한 곳입니다.

### 1. 교체 지점 — `src/services/index.ts` 의 `createService()`

```ts
/** 데이터 서비스를 만든다. 실제 API 단계에서는 여기서 API 클라이언트를 돌려준다. */
export function createService(): AnalysisService {
  return createDemoService(); // ← 여기서 API 클라이언트를 돌려준다
}
```

`src/services/analysis-service.ts` 의 `AnalysisService` 를 구현한 API 클라이언트를 만들어 여기서 돌려주면 됩니다. `react.tsx` 가 브라우저에서 처음 한 번 `createService()` 를 불러 앱 전체가 같은 서비스를 씁니다. 서버 렌더와 하이드레이션 첫 렌더에서는 서비스가 없고(`useService()` 가 `null`), 화면은 불러오는 중 화면을 보여 줍니다.

### 2. 인터페이스 계약 — `AnalysisService`

- **`subscribe` 를 뺀 모든 메서드는 `Promise` 를 돌려줍니다.** 각 메서드 주석에 예상 엔드포인트(`실제: GET /analyses` 등)를 적어 두었습니다. 백엔드와 확정하기 전의 예시입니다.
- **조회 결과는 화면이 고치지 않는 값으로 다룹니다.** 데모 서비스는 깊은 복사본(`structuredClone`)을 돌려주므로 화면에서 고쳐도 서비스 상태가 바뀌지 않습니다. 바꾸려면 변경 메서드를 부릅니다.
- 위험등급과 판단 근거는 서비스가 준 값을 그대로 표시하고, 화면에서 계산하지 않습니다.

| 묶음 | 메서드 |
|---|---|
| 조회 | `list()`, `get(id)`(없으면 `null`), `pending(id)`(검토 완료 전에 남은 항목), `sampleFiles()` |
| 분석 | `requestAnalysis({ name, files })` → 분석 ID, `retry(id, docId?)` |
| 탐지 항목 검토 | `setStatus`, `confirmMany`, `markFalsePositive`, `restore`, `reclassify`(바뀐 값이 없으면 `false`), `saveFindingMemo` |
| 검토사항·문서 간 연결 | `resolveItem`, `reopenItem`, `decideLink` |
| 검토 메모·완료 | `saveMemo`, `completeReview`, `reopenReview` |
| 내보내기 | `buildExport(id, format, brand?)` → `ExportFile`, `logExport(id, file, state)` |
| 변경 알림 | `subscribe(listener)` → 구독 해제 함수 |

`sampleFiles()` 는 새 분석 화면의 '데모용 샘플 문서로 체험하기'와 `/analyses/new?sample=1` 에 쓰는 데모 기능이지만, 인터페이스에 있으므로 API 클라이언트도 구현해야 합니다.

### 3. 변경 알림 — `subscribe`

`subscribe(listener)` 는 유일하게 Promise가 아닌 메서드로, 구독 해제 함수를 돌려줍니다. 데이터 훅(`useAnalyses`·`useAnalysis`·`usePending`)과 헤더의 '검토 필요' 숫자는 **이 알림을 받아야 다시 불러옵니다.** 실제 API에서는 폴링이나 SSE로 구현하고, 다음 때에 알립니다.

- 변경 메서드(확인·오탐·검토 완료 등)가 성공했을 때 `listener()`. 데모 서비스도 변경할 때마다 알립니다.
- 분석 진행(대기 → 분석 중 → 완료·실패)이 바뀌었을 때 `listener()`.
- 분석이 끝났을 때 `listener({ type: 'done', id, name, items, findings })`(`ServiceEvent`). 화면이 분석 완료 토스트를 띄웁니다.

### 4. 데모 전용 조작 — `DemoControls`

`getDemoControls(service)`(`src/services/index.ts`)는 데모 서비스일 때만 `DemoControls` 를 주고, 그 밖에는 `null` 을 돌려줍니다. 화면에서는 `useDemoControls()` 로 받습니다.

| 메서드 | 하는 일 |
|---|---|
| `reset()` | 샘플 분석 6건과 미리 해 둔 검토 동작으로 되돌린다 |
| `clearAll()` | 분석 이력을 모두 지운다(지금은 테스트에서만 부른다) |
| `prepare(state)` | `/dev/states` 의 상태를 만들고, 상세·보고서 상태면 열 분석 ID를 돌려준다 |

쓰는 곳과, API 클라이언트로 바꿔 `null` 이 되었을 때:

| 쓰는 곳 | 실제 API(`getDemoControls` 가 `null`)일 때 |
|---|---|
| 목록이 비었을 때의 '샘플 분석 건 둘러보기' 버튼(`src/components/list/ListScreen.tsx` → `reset()`) | 버튼이 나오지 않습니다. 목록 화면의 나머지는 그대로 동작합니다. |
| `/dev/**` — `/dev/states/[state]` 미리보기(`src/dev/PreparedState.tsx` → `prepare()`) | 상태를 만들지 않아 미리보기 화면이 그려지지 않습니다(위쪽 상태 이동 막대만 보임). |

화면 4개는 `DemoControls` 없이 `AnalysisService` 만으로 동작합니다.

### 5. 분석 출력 형식이 확정되면

이 두 파일만 바꿉니다. 타입은 ② 표시 규칙의 목록에서 뽑아 쓰므로, 바꾼 뒤 `npm run typecheck` 가 고칠 곳을 알려 줍니다.

- **`src/display/rules.ts`** — 위험등급(`RISK`), 분석·검토·탐지 상태(`ASTATUS`·`RSTATUS`·`FSTATUS`), 검토사항 종류(`RTYPE`), 연결 상태(`LSTATUS`), 규칙 ID 예시(`RULES`), 이력 구분(`HKIND`), 정보 종류(`CATS`), 정보 주체(`SUBJECTS`), 노출 상태(`EXPOSURES`), 오탐 사유(`FP_REASONS`), 내보내기 형식(`EXPORT_FORMATS`)의 키·라벨·아이콘·색 토큰.
- **`src/services/types.ts`** — 분석 건(`Analysis`), 문서(`AnalysisDoc`), 탐지 항목(`Finding`), 검토사항(`ReviewItem`), 문서 간 연결(`DocLink`), 이력(`HistoryEntry`), 업로드 파일(`UploadFile`), 내보내기 파일(`ExportFile`)의 모양.

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

---

## /dev/states 사용법

디자인의 화면 상태를 하나씩 열어 보는 개발용 페이지입니다.

- `/dev/states` 에 상태 **23개**가 화면별(분석 목록 3, 새 분석 6, 상세 검토 11, 보고서 3)로 번호, 상태 ID, 여는 화면 경로(`/` · `/analyses/new` · `/analyses/[id]` · `/analyses/[id]/report`)와 함께 나옵니다. 상태 정의는 `src/dev/states.ts`, 상태별 화면 연결은 `src/dev/StatePreview.tsx` 입니다.
- 상태를 누르면 `/dev/states/<상태 ID>` 로 가서 **데모 서비스를 그 상태로 맞춘 뒤**(`DemoControls.prepare`) 해당 화면을 엽니다. 실제 화면 주소에는 개발용 파라미터를 넣지 않습니다(목록 상태의 필터도 URL과 잇지 않습니다).
- 위쪽 막대 `← 상태 목록 · n / 23 · 상태 이름 · 이전 · 다음` 으로 목록에 돌아가거나 이전·다음 상태로 옮겨 갑니다. 키보드로는 `[`(이전)·`]`(다음)을 누릅니다(입력칸에 글자를 쓰는 중에는 무시). 상태를 바꿀 때마다 데모 서비스를 그 상태로 다시 준비합니다.
- **휴대폰 전용 상태 2개는 목록에 없고 주소로만 엽니다**: `/dev/states/detail-docs`(문서 탭), `/dev/states/detail-results`(탐지 결과 탭). 막대에 번호 대신 '휴대폰 전용'이 나오며, 휴대폰 폭(768px 미만)으로 봅니다.
- 상태를 열 때마다 데모 데이터를 샘플로 되돌린 뒤 그 상태를 만듭니다. 같은 탭에서 실제 화면으로 넘어가면 그 데이터가 이어지므로, 처음 샘플로 돌아가려면 새로 고침합니다.
- 실제 API로 바꾸면 `DemoControls` 가 없어 상태를 만들지 못합니다(데모 서비스 전용).

---

## 이번 단계에서 하지 않은 것

- **실제 업로드·분석·저장·로그인·백엔드 연결.** 필요한 곳은 데모 서비스가 가짜로 응답하고, 업로드·분석 진행은 `CONFIG.sim` 의 지연 시간으로 흉내 냅니다. 담당자(`CONFIG.user`)는 로그인 전 단계의 데모 값입니다. 내보내기 파일만 브라우저 다운로드(Blob)로 저장합니다.
- **실제 PDF 뷰어.** 원문은 프로토타입처럼 샘플 문서 화면(블록으로 그린 가상 문서)입니다.
- **규칙 ID(`PII-ID-001` 등)와 위험 판정은 디자인용 예시입니다.** 실제 기준처럼 늘리지 않습니다.
- **`next.config.ts` 의 `cacheComponents`·`partialPrefetching` 은 껐습니다.** 데이터가 모두 브라우저의 데모 서비스라 이득이 없기 때문입니다. 실제 API 단계에서 서버에서 데이터를 가져오게 되면 다시 검토합니다.

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
