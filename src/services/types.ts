/* ==========================================================================
   도메인 타입 — 프로토타입(Main.dc.html 854–1392줄) 객체 모양 그대로.
   분석 출력 형식이 확정되면 이 파일과 display/rules.ts만 바꾼다.
   - 라벨·목록에서 뽑는 타입(등급·상태·정보 종류 등)은 ② 표시 규칙에서 가져온다.
   - 날짜·시각은 'YYYY-MM-DD HH:mm' 문자열이다(빈 문자열 = 아직 없음).
   ========================================================================== */

import type {
  AnalysisStatus,
  Exposure,
  ExportFormat,
  FindingStatus,
  FpReason,
  HistoryKind,
  InfoCategory,
  InfoSubject,
  LinkStatus,
  ReviewItemType,
  ReviewStatus,
  RiskLevel,
  RuleId,
} from '@/display/rules';

/* ---------- 원문 위치와 글자 조각 ---------- */

/** 원문 위치 조각 — 원본 H(a, x, m). 탐지 항목의 anchors 가 a 를 가리킨다. */
export interface Highlight {
  /** 위치 ID(앵커) */
  a: string;
  /** 원문 그대로의 값 */
  x: string;
  /** 마스킹 미리보기 값(없으면 빈 문자열) */
  m: string;
}

/** 글자 조각 — 일반 글자 또는 원문 위치 조각 */
export type Segment = string | Highlight;

/** 블록 안의 값 — 일반 글자 하나 또는 조각 목록 */
export type TextValue = string | Segment[];

/** 표 칸 정렬 — l 왼쪽 / r 오른쪽 / c 가운데 */
export type CellAlign = 'l' | 'r' | 'c';

/* ---------- 샘플 문서 페이지 블록 12종 ---------- */

/** 문서 머리 막대(기관명 · 용도) */
export interface BarBlock {
  t: 'bar';
  left: string;
  right: string;
}

/** 문서 제목(+부제) */
export interface TitleBlock {
  t: 'title';
  text: string;
  sub?: string;
}

/** 구역 제목 */
export interface SectionBlock {
  t: 'sec';
  text: string;
}

/** 항목표 한 칸 — [이름, 값, 차지하는 열 수(기본 1)] */
export type KvItem = [label: string, value: TextValue, span?: number];

/** 항목표(이름-값 격자) */
export interface KvBlock {
  t: 'kv';
  /** 열 수(기본 2). 3이면 이름 칸이 좁다. */
  cols?: 2 | 3;
  items: KvItem[];
}

/** 표 */
export interface TableBlock {
  t: 'table';
  head: string[];
  /** 열별 정렬(기본 왼쪽) */
  align?: CellAlign[];
  /** 행 × 칸. 빈 칸은 '' */
  rows: TextValue[][];
}

/** 문단 */
export interface ParagraphBlock {
  t: 'p';
  text: TextValue;
  /** 작은 글자(안내문) */
  small?: boolean;
}

/** 동의 체크 목록 */
export interface ChecksBlock {
  t: 'checks';
  items: { on: boolean; text: string }[];
}

/** 서명란 한 줄 — [역할, 이름, 서명 표시('(서명)'·'(인)')] */
export type SignItem = [role: string, name: TextValue, mark?: string];

/** 서명란 */
export interface SignBlock {
  t: 'sign';
  date: string;
  items: SignItem[];
}

/** 접수 도장 — 줄마다 글자 또는 조각 목록 */
export interface StampBlock {
  t: 'stamp';
  lines: TextValue[];
}

/** 판독 불가 영역(흐린 글자) */
export interface BlurBlock {
  t: 'blur';
  /** 위치 ID(검토사항 근거가 가리킴) */
  a: string;
  label: string;
  lines: string[];
}

/** 스캔 범위를 벗어나 잘린 영역 */
export interface CutBlock {
  t: 'cut';
  /** 위치 ID(검토사항 근거가 가리킴) */
  a: string;
  label: string;
  /** 잘린 아래로 흐리게 보이는 서식 */
  ghost: string;
}

/** 바닥글(왼쪽 글자 · 오른쪽 쪽 번호) */
export interface FootBlock {
  t: 'foot';
  left: TextValue;
  right?: string;
}

export type PageBlock =
  | BarBlock
  | TitleBlock
  | SectionBlock
  | KvBlock
  | TableBlock
  | ParagraphBlock
  | ChecksBlock
  | SignBlock
  | StampBlock
  | BlurBlock
  | CutBlock
  | FootBlock;

export type PageBlockType = PageBlock['t'];

/** 한 쪽 = 블록 목록 */
export type DocPage = PageBlock[];

/* ---------- 문서 ---------- */

/** 문서 처리 상태 — 분석 상태 중 '일부 실패'를 뺀 것 */
export type DocStatus = Exclude<AnalysisStatus, 'partial'>;

/** 분석 건에 묶인 문서 하나 — 원본 loanDocs() 등의 항목 */
export interface AnalysisDoc {
  id: string;
  /** 화면 제목(문서 종류) */
  title: string;
  /** 파일 이름 */
  name: string;
  /** 형식 표기(대문자) — 'PDF' · 'JPG' · 'PNG' */
  ext: string;
  /** 바이트 */
  size: number;
  status: DocStatus;
  /** 실패 이유(없으면 빈 문자열) */
  error: string;
  /** 쪽별 블록. 분석 전·실패 문서는 null */
  pages: DocPage[] | null;
  /** 쪽 수를 따로 아는 경우(pages 가 없을 때 등) */
  pageCount?: number | null;
  /** 스캔 이미지(종이색·필터가 다름) */
  scan?: boolean;
  /** 실제 분석에서만 — 분류된 서류가 올린 묶음 파일 안 어디에 있는지. 데모 문서는 넣지 않는다. */
  source?: DocSource;
}

/** 실제 분석의 '분류된 서류' 위치 — 계약 result.documents[] 한 행 */
export interface DocSource {
  /** 분류 순번(0부터) */
  index: number;
  /** 분류 코드(loan_application · Other 등) */
  type: string;
  /** 파일 전체 기준 첫 쪽(1부터) */
  pageStart: number;
  /** 파일 전체 기준 끝 쪽(1부터, 포함) */
  pageEnd: number;
  /** extracted = 정보를 추출한 서류 / other = 기타 서류 */
  kind: 'extracted' | 'other';
  /** 기타 서류 안내 Markdown(없으면 빈 문자열) */
  otherGuide: string;
  /** 필수항목 검증 결과(예 'green', 없으면 빈 문자열) */
  validation: string;
}

/* ---------- 탐지 항목 ---------- */

/** 탐지 항목의 최초 AI 분류 — 분류 수정 후에도 남는다 */
export interface FindingAi {
  cat: InfoCategory;
  subject: InfoSubject;
  exposure: Exposure;
}

/** 탐지 항목 — 원본 F() */
export interface Finding {
  id: string;
  /** 정보 종류 */
  cat: InfoCategory;
  /** 세부 항목 이름 */
  label: string;
  /** 마스킹된 표시값 */
  masked: string;
  /** 정보 주체 */
  subject: InfoSubject;
  /** 노출 상태 */
  exposure: Exposure;
  risk: RiskLevel;
  /** 판단 근거 */
  reason: string;
  /** 적용 규칙(디자인용 예시). '' = 적용 규칙 없음(실제 분석) */
  rule: RuleId | '';
  docId: string;
  /** 1부터 */
  page: number;
  /** 원문 위치 ID 목록. 비어 있으면 '위치 확인 필요' */
  anchors: string[];
  /** 위치가 없을 때 찾을 근거 문구 */
  evidence: string;
  status: FindingStatus;
  /** 항목 메모 */
  memo: string;
  /** 오탐 사유(오탐이 아니면 빈 문자열) */
  fpType: FpReason | '';
  fpNote: string;
  /** 분류 수정 사유 */
  reclassNote: string;
  updatedAt: string;
  /** 최초 AI 결과 */
  ai: FindingAi;
  /** 실제 분석에서만 — 원문 위치 상자(쪽 크기에 대한 비율). anchors 의 위치 ID 와 짝. 데모는 넣지 않는다. */
  boxes?: FindingBox[];
  /** 실제 분석에서만 — 계약이 준 원래 값. 데모는 넣지 않는다. */
  live?: FindingLive;
}

/** 원문 위치 상자 하나(실제 분석) */
export interface FindingBox {
  /** 위치 ID — 이 항목의 anchors 에 같은 값이 들어 있다 */
  a: string;
  /** 쪽 크기에 대한 0~1 비율 꼭짓점(2개 이상). 범위 밖 값도 그대로 둔다(화면 변환이 자른다) */
  points: { x: number; y: number }[];
}

/** 계약 매핑 상태 — ok 대응됨 / needs_review 대응 확인 필요 / unknown 대응표에 없음 */
export type FindingMappingStatus = 'ok' | 'needs_review' | 'unknown';

/** 실제 분석 탐지 항목의 원래 값(계약 findings[] 한 행에서) */
export interface FindingLive {
  /** 계약 id '<document_index>:<field>' */
  id: string;
  /** 워크플로우 영문 키(applicant_name 등) */
  field: string;
  /** 원문 값 */
  value: string;
  mappingStatus: FindingMappingStatus;
  /** 추출 신뢰도(모르면 null) */
  confidence: 'high' | 'low' | null;
  /** 항목 위험등급을 워크플로우가 판정했으면 'workflow', 아니면 null(미평가) */
  riskSource: 'workflow' | null;
}

/* ---------- 검토사항 ---------- */

/** 검토사항 근거 — 원문 위치로 가는 바로가기 */
export interface EvidenceRef {
  label: string;
  docId: string;
  page: number;
  anchors: string[];
  /** 위치가 없는 탐지 항목을 함께 고를 때 */
  findingId?: string;
}

/** 검토사항 — 원본 I() */
export interface ReviewItem {
  id: string;
  type: ReviewItemType;
  title: string;
  /** 설명 */
  desc: string;
  /** 다음에 할 일 */
  next: string;
  docId: string;
  page: number;
  evidence: EvidenceRef[];
  resolved: boolean;
  /** 처리 내용 */
  note: string;
  resolvedAt: string;
  resolvedBy: string;
  /** 연결 판단으로 함께 해결되는 문서 간 연결 ID */
  linkId?: string;
  /** 관련 탐지 항목 ID(위치 확인 필요) */
  findingId?: string;
  /** 다시 분석할 수 있는 실패 문서 ID */
  retryDoc?: string;
}

/* ---------- 문서 간 연결 ---------- */

/** 담당자의 연결 판단 */
export type LinkDecision = Extract<LinkStatus, 'linked' | 'unlinked'>;

/** 연결에 묶인 문서 한쪽 */
export interface LinkDocRef {
  docId: string;
  page: number;
  /** 연결 근거가 된 값 요약 */
  fields: string;
  anchors: string[];
}

/** 문서 간 연결 — 원본 Lk() */
export interface DocLink {
  id: string;
  /** 분석 결과 상태 — 판단 후 표시는 decision 으로 바뀐다 */
  status: Extract<LinkStatus, 'confirmed' | 'check'>;
  title: string;
  docs: LinkDocRef[];
  /** 연결 근거 */
  basis: string[];
  /** 부족한 근거(없으면 빈 문자열) */
  missing: string;
  /** 확인할 점 */
  check: string;
  decision: LinkDecision | null;
  decisionNote: string;
  decidedAt: string;
  decidedBy: string;
}

/* ---------- 검토 이력 ---------- */

/** 이력 한 줄 — 원본 log() */
export interface HistoryEntry {
  id: string;
  at: string;
  /** 처리자(담당자 이름 또는 '시스템') */
  actor: string;
  kind: HistoryKind;
  /** 대상 */
  target: string;
  /** 바뀐 내용 */
  change: string;
  /** 사유(없으면 빈 문자열) */
  reason: string;
}

/* ---------- 분석 건 ---------- */

/** 분석 건 — 원본 mkA() */
export interface Analysis {
  id: string;
  /** 분석 ID 표기 — 'DG-20261030-0007' */
  code: string;
  name: string;
  submittedAt: string;
  analyzedAt: string;
  status: AnalysisStatus;
  risk: RiskLevel;
  review: ReviewStatus;
  docs: AnalysisDoc[];
  findings: Finding[];
  items: ReviewItem[];
  links: DocLink[];
  history: HistoryEntry[];
  /** 검토 메모 */
  memo: string;
  memoAt: string;
  /** 주요 위험 사유 */
  riskReasons: string[];
  /** 권장 조치 */
  recs: string[];
  /** 분석 한계(없으면 빈 문자열) */
  limits: string;
  reviewer: string;
  reviewedAt: string;
  completionNote: string;
  /** 직접 올린 파일 — 데모에서는 분석이 시작되지 않고 대기에 머문다 */
  demoQueued: boolean;
  /** 다시 분석 중 */
  retrying: boolean;
  /** 실제 분석(API 서비스)에서만 채운다 — 백엔드가 준 원래 값. 데모 서비스는 넣지 않는다. */
  raw?: RawAnalysisInfo;
}

/** 실제 분석의 원래 값 — 빈 값은 '' / null */
export interface RawAnalysisInfo {
  /**
   * analyses.result(imask-upstage-v1 — format·job·summary, 공통 계약이면 documents·findings·overall).
   * 기본 조회에는 stages 가 없다(단계별 JSON 은 LiveExtras.loadStages). 아직 없으면 null
   */
  result: unknown | null;
  /** 올린 파일(documents 첫 행). 없으면 null */
  file: RawFileInfo | null;
  /** result 가 공통 계약(서류 1개 이상 + findings 배열)을 담은 완료 분석이라 상세 검토 화면으로 보일 수 있는지 */
  detailReady: boolean;
  /**
   * 검토 동작을 저장할 수 있는지 — detailReady 이고 백엔드가 검토 기록(review 객체)을 줬다.
   * detailReady 인데 false 면 검토 기록을 읽지 못한 것(상세 화면은 검토 버튼만 막는다).
   */
  reviewable: boolean;
  /** 계약 overall(묶음 전체 위험도 판정 · 다음 단계 안내). 없으면 null, 빠진 값은 '' */
  overall: RawOverall | null;
  /** 실패 이유(백엔드 문구 그대로) */
  error: string;
  /** Upstage 작업 번호(job_…) */
  jobId: string;
  /** 이번 조회에서 본 Upstage 상태(queued·in_progress 등) */
  upstageStatus: string;
  /** 이번 조회에서 Upstage 확인이 실패했을 때의 짧은 문구(분석은 계속된다) */
  pollError: string;
  /** 만든 시각(ISO 8601 원문) — 경과·걸린 시간을 초 단위로 셀 때 */
  createdAt: string;
  /** 마지막으로 바뀐 시각(ISO 8601 원문) */
  updatedAt: string;
}

/** 실제 분석에 올린 파일 */
export interface RawFileInfo {
  id: string;
  /** 파일 이름 */
  name: string;
  /** MIME 형식 */
  mime: string;
  /** 바이트 */
  size: number;
}

/** 계약 overall — 빈 값은 '' */
export interface RawOverall {
  /** 위험도 판정 원문(상·중·하·검토 필요) */
  level: string;
  /** 위험도 판정 Markdown */
  text: string;
  /** 다음 단계 이름(권장_조치 · 검토_안내) */
  nextStage: string;
  /** 다음 단계 Markdown */
  nextText: string;
}

/* ---------- 업로드 파일 ---------- */

/** user = 직접 고른 파일 / sample = 샘플 문서 */
export type UploadFileKind = 'user' | 'sample';
export type UploadFileState = 'uploading' | 'ready' | 'failed';

/** 새 분석에 올린 파일 — 원본 userFile() · sampleFiles() */
export interface UploadFile {
  id: string;
  name: string;
  /** 형식 표기(대문자, jpeg → 'JPG') */
  ext: string;
  size: number;
  kind: UploadFileKind;
  state: UploadFileState;
  /** 업로드 실패 이유 */
  error: string;
  /** 실제 업로드에 쓸 브라우저 파일(실제 분석 서비스만 쓴다 — 데모는 이름·크기만 쓴다) */
  file?: File;
}

/* ---------- 내보내기 파일 ---------- */

/** 내보내기 결과 — 원본 buildExport() 반환값(마스킹된 표시값만 담는다) */
export interface ExportFile {
  format: ExportFormat;
  /** 파일 이름 — '<브랜드>_<분석 ID>_검토결과…' */
  name: string;
  mime: string;
  /** 파일 내용 */
  text: string;
  /** UTF-8 바이트 */
  size: number;
  /** 미리보기(앞부분 몇 줄) */
  preview: string;
}
