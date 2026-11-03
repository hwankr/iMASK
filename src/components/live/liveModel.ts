/* ==========================================================================
   실제 분석 화면 모델 — 순수 함수만(React·서비스 없음). 테스트 대상.
   - 파일 검사(개수 1 · PDF·PNG·JPEG · 20MB 이하), 분석명, 진행 단계, 폴링 여부, 경과·걸린 시간 문구
   - 결과 요약 줄(result.summary), 단계별 결과 목록(result.stages), 서류 종류·위험도·단계 라벨
   결과 모양은 T2 '결과 저장 형식'(imask-upstage-v1)의 summary·stages 다. 모양이 달라도 예외 없이 빈 값으로.
   ========================================================================== */

import { CONFIG } from '@/config/app';
import { DOC_TYPE_NAMES, docTypeName, type AnalysisStatus } from '@/display/rules';
import { fmtSize, pad2 } from '@/lib/format';
import type { RequestStep } from '@/services/analysis-service';

/* ---------- 파일 검사 ---------- */

/** 실제 분석은 묶음 PDF(또는 이미지) 하나를 받는다 */
export const LIVE_MAX_FILES = 1;
export const LIVE_MAX_FILE_MB: number = CONFIG.upload.maxFileMB;
export const LIVE_MAX_FILE_BYTES = LIVE_MAX_FILE_MB * 1024 * 1024;
/** 분석명 최대 글자 수(백엔드와 같다) */
export const LIVE_NAME_MAX = 60;

/** 확장자 → 브라우저가 붙일 수 있는 형식 값 */
const TYPES_BY_EXT: Record<string, readonly string[]> = {
  pdf: ['application/pdf', 'application/x-pdf'],
  png: ['image/png', 'image/x-png'],
  jpg: ['image/jpeg', 'image/pjpeg'],
  jpeg: ['image/jpeg', 'image/pjpeg'],
};

/** <input accept> — 확장자와 형식 둘 다 */
export const LIVE_ACCEPT = '.pdf,.png,.jpg,.jpeg,application/pdf,image/png,image/jpeg';

export const MSG_PICK_FILE = '분석할 파일을 골라 주세요.';
export const MSG_ONE_FILE_ONLY = '실제 분석에는 파일 1개만 올릴 수 있습니다.';
export const MSG_BAD_TYPE = 'PDF·PNG·JPEG 파일만 올릴 수 있습니다.';
export const MSG_TYPE_MISMATCH = '파일 형식과 확장자가 맞지 않습니다.';
export const MSG_EMPTY_FILE = '빈 파일은 올릴 수 없습니다.';
export const MSG_TOO_LARGE = `파일은 ${LIVE_MAX_FILE_MB}MB 이하여야 합니다.`;

/** 브라우저 File 에서 쓰는 값 */
export interface PickedLiveFile {
  name: string;
  size: number;
  /** 브라우저가 붙인 형식(비어 있을 수 있다) */
  type: string;
}

export type FileCheck = { ok: true } | { ok: false; error: string };

/** 파일 이름의 확장자(소문자, 점 없이). 없으면 '' */
export function fileExt(name: string): string {
  const m = /\.([a-z0-9]+)$/i.exec(name);
  return m ? m[1].toLowerCase() : '';
}

/** 고른 파일 검사 — 개수 · 확장자 · 형식 · 크기 */
export function checkLiveFiles(files: readonly PickedLiveFile[]): FileCheck {
  if (files.length === 0) return { ok: false, error: MSG_PICK_FILE };
  if (files.length > LIVE_MAX_FILES) return { ok: false, error: MSG_ONE_FILE_ONLY };
  const f = files[0];
  const types = TYPES_BY_EXT[fileExt(f.name)];
  if (!types) return { ok: false, error: MSG_BAD_TYPE };
  if (f.type && !types.includes(f.type.toLowerCase())) return { ok: false, error: MSG_TYPE_MISMATCH };
  if (!(f.size > 0)) return { ok: false, error: MSG_EMPTY_FILE };
  if (f.size > LIVE_MAX_FILE_BYTES) return { ok: false, error: MSG_TOO_LARGE };
  return { ok: true };
}

/** 고른 파일 한 줄 — '묶음.pdf · 315KB' */
export function fileLine(f: Pick<PickedLiveFile, 'name' | 'size'>): string {
  return `${f.name} · ${fmtSize(f.size)}`;
}

/** 보낼 분석명 — 앞뒤 공백을 떼고, 비면 파일 이름(60자까지) */
export function analysisNameFor(name: string, fileName: string): string {
  const n = name.trim();
  return (n || fileName.trim()).slice(0, LIVE_NAME_MAX);
}

/* ---------- 요청 진행 단계 ---------- */

export const STEP_ORDER: readonly RequestStep[] = ['create', 'upload', 'start'];

export const STEP_LABEL: Record<RequestStep, string> = {
  create: '분석 건 만드는 중',
  upload: '파일 올리는 중',
  start: '분석 시작 중',
};

export type StepState = 'done' | 'current' | 'todo';

/** 진행 단계 목록 — 지금 단계 앞은 끝남, 지금 단계는 진행 중 */
export function progressSteps(current: RequestStep | null): { step: RequestStep; label: string; state: StepState }[] {
  const at = current ? STEP_ORDER.indexOf(current) : -1;
  return STEP_ORDER.map((step, i) => ({ step, label: STEP_LABEL[step], state: i < at ? 'done' : i === at ? 'current' : 'todo' }));
}

/* ---------- 폴링 · 시간 ---------- */

/** 상태 확인 간격(밀리초) */
export const POLL_MS = 3000;

/** 상태를 계속 확인할지 — 대기·분석 중일 때만 */
export function isPolling(status: AnalysisStatus | string | null | undefined): boolean {
  return status === 'queued' || status === 'running';
}

/** ISO 8601 → 밀리초(소수 초 3자리까지). 못 읽으면 NaN */
export function isoMs(value: string | null | undefined): number {
  if (!value) return NaN;
  return Date.parse(value.trim().replace(' ', 'T').replace(/(\.\d{3})\d+/, '$1'));
}

/** 경과 시간 'm:ss'(분:초). 시작 시각을 모르면 '' */
export function elapsedText(fromIso: string | null | undefined, nowMs: number): string {
  const from = isoMs(fromIso);
  if (Number.isNaN(from)) return '';
  const sec = Math.max(0, Math.floor((nowMs - from) / 1000));
  return `${Math.floor(sec / 60)}:${pad2(sec % 60)}`;
}

/** 걸린 시간 '34초' · '1분 5초'. 모르면 '' */
export function durationText(fromIso: string | null | undefined, toIso: string | null | undefined): string {
  const from = isoMs(fromIso);
  const to = isoMs(toIso);
  if (Number.isNaN(from) || Number.isNaN(to) || to < from) return '';
  const sec = Math.round((to - from) / 1000);
  if (sec < 60) return `${sec}초`;
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return s ? `${m}분 ${s}초` : `${m}분`;
}

/* ---------- 라벨 ---------- */

/** 서류 종류 코드 → 한국어 이름 — 표시 규칙(rules.ts)에 있다(서비스 매핑과 함께 쓴다). 여기서는 다시 내보내기만 한다 */
export { DOC_TYPE_NAMES, docTypeName };

/** 위험도 판정 문구 — 상·중·하·검토 필요, 없으면 '판정 없음' */
export function riskText(level: unknown): string {
  const s = typeof level === 'string' ? level.trim() : '';
  return s || '판정 없음';
}

/** 다음 단계 제목 — 권장_조치 → '권장 조치', 검토_안내 → '검토 안내', 그 밖 → '다음 단계' */
export function nextStageTitle(stage: unknown): string {
  const s = typeof stage === 'string' ? stage.trim() : '';
  if (s === '권장_조치') return '권장 조치';
  if (s === '검토_안내') return '검토 안내';
  return '다음 단계';
}

/** Upstage 상태 문구 */
export function upstageStatusText(status: string): string {
  if (status === 'queued') return '대기(queued)';
  if (status === 'in_progress') return '진행 중(in_progress)';
  if (status === 'completed') return '완료(completed)';
  return status || '아직 확인 전';
}

/** 단계 상태 문구 */
export function stageStatusText(status: unknown): string {
  if (status === 'completed') return '완료';
  if (status === 'failed') return '실패';
  if (status === 'in_progress') return '진행 중';
  if (status === 'incomplete') return '미완료';
  return typeof status === 'string' ? status : '';
}

/** 상태가 바뀌었을 때 화면 낭독기에 알릴 문구(바뀌지 않았거나 처음이면 '') */
export function statusAnnouncement(prev: AnalysisStatus | null, next: AnalysisStatus): string {
  if (prev === null || prev === next) return '';
  if (next === 'running') return '분석을 시작했습니다.';
  if (next === 'done') return '분석이 끝났습니다. 결과를 확인하세요.';
  if (next === 'failed' || next === 'partial') return '분석에 실패했습니다.';
  return '';
}

/* ---------- 결과(imask-upstage-v1) ---------- */

const isObj = (v: unknown): v is Record<string, unknown> => !!v && typeof v === 'object' && !Array.isArray(v);
const num = (v: unknown): number | null => (typeof v === 'number' && Number.isFinite(v) ? v : null);
const text = (v: unknown): string => (typeof v === 'string' ? v : '');

/** result.summary(T1 summarize 결과) */
export interface LiveSummary {
  documentCount: number | null;
  documentTypes: string[];
  extractedCount: number | null;
  riskLevel: string;
  finalStage: string;
  otherCount: number | null;
}

export function readSummary(result: unknown): LiveSummary | null {
  if (!isObj(result) || !isObj(result.summary)) return null;
  const s = result.summary;
  return {
    documentCount: num(s.document_count),
    documentTypes: Array.isArray(s.document_types) ? s.document_types.filter((t): t is string => typeof t === 'string') : [],
    extractedCount: num(s.extracted_document_count),
    riskLevel: text(s.risk_level).trim(),
    finalStage: text(s.final_stage),
    otherCount: num(s.other_document_count),
  };
}

export interface SummaryRow {
  key: string;
  label: string;
  value: string;
}

const countText = (n: number | null): string => (n === null ? '읽지 못함' : `${n}개`);

/** 요약 줄 — 서류(수·종류), 추출한 서류, 위험도, 마지막 단계, 기타 서류, 걸린 시간, Upstage 작업 번호 */
export function summaryRows(
  result: unknown,
  info: { createdAt: string; updatedAt: string; jobId: string },
): SummaryRow[] {
  const s = readSummary(result);
  const types = s ? s.documentTypes.map(docTypeName) : [];
  const docs = s ? countText(s.documentCount) + (types.length ? ' — ' + types.join(' · ') : '') : '읽지 못함';
  return [
    { key: 'docs', label: '분류한 서류', value: docs },
    { key: 'extracted', label: '정보를 추출한 서류', value: s ? countText(s.extractedCount) : '읽지 못함' },
    { key: 'risk', label: '위험도', value: riskText(s?.riskLevel) },
    { key: 'final', label: '마지막 단계', value: s?.finalStage || '없음' },
    { key: 'other', label: '기타 서류', value: s ? (s.otherCount === null ? '없음' : `${s.otherCount}개`) : '읽지 못함' },
    { key: 'took', label: '걸린 시간', value: durationText(info.createdAt, info.updatedAt) || '-' },
    { key: 'job', label: 'Upstage 작업 번호', value: info.jobId || '-' },
  ];
}

/** 단계 하나(result.stages[] — T1 parse_stages 결과) */
export interface StageRow {
  /** output 순서(0부터) — 목록 key */
  index: number;
  /** 단계 이름(key, 없으면 name) */
  label: string;
  /** 같은 이름이 여러 개일 때 '(2/5)', 하나면 '' */
  counter: string;
  /** 상태 문구 */
  status: string;
  /** 실패한 단계 */
  failed: boolean;
  data: unknown;
  additionalValues: unknown;
  /** content[] 가 둘 이상일 때만(하나면 data·additional_values 와 같다) */
  contents: unknown[] | null;
}

/** 단계 이름 — key, 없으면 name, 그것도 없으면 '이름 없는 단계' */
export function stageLabel(stage: unknown): string {
  if (!isObj(stage)) return '이름 없는 단계';
  return text(stage.key).trim() || text(stage.name).trim() || '이름 없는 단계';
}

/** result.stages → 단계 목록(output 순서 그대로) */
export function stageRows(result: unknown): StageRow[] {
  if (!isObj(result) || !Array.isArray(result.stages)) return [];
  const stages = result.stages;
  const labels = stages.map(stageLabel);
  const totals = new Map<string, number>();
  for (const l of labels) totals.set(l, (totals.get(l) ?? 0) + 1);
  const seen = new Map<string, number>();
  return stages.map((stage, index) => {
    const label = labels[index];
    const nth = (seen.get(label) ?? 0) + 1;
    seen.set(label, nth);
    const total = totals.get(label) ?? 1;
    const s = isObj(stage) ? stage : {};
    const contents = Array.isArray(s.contents) && s.contents.length > 1 ? s.contents : null;
    return {
      index,
      label,
      counter: total > 1 ? `(${nth}/${total})` : '',
      status: stageStatusText(s.status),
      failed: s.status === 'failed',
      data: s.data ?? null,
      additionalValues: s.additional_values ?? null,
      contents,
    };
  });
}
