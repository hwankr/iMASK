/* ==========================================================================
   AnalysisOut(T2 계약) → Analysis(화면 도메인 타입) — 순수 함수
   - 분석 번호 code = 'DG-YYYYMMDD-XXXX'(만든 날짜는 서울 시각, XXXX = id 앞 4자 대문자).
   - 시각은 'YYYY-MM-DD HH:mm'(Asia/Seoul — src/lib/format.ts 의 형식과 같다). 한국은 서머타임이 없어
     UTC+9 로 고정 계산한다(브라우저 시간대와 무관하게 같은 값).
   - 위험도는 result.overall.level(공통 계약), 없으면 result.summary.risk_level:
     상 → high · 중 → medium · 하 → low · 그 밖(검토 필요·없음) → unrated.
   - 완료 + 공통 계약 결과(result.documents 에 유효한 서류 1개 이상 + result.findings 배열)면 detailReady:
     docs = 분류된 서류, findings = 계약 탐지 항목(contract.ts), riskReasons·recs = overall 의 Markdown 줄.
     그 밖(대기·분석 중·실패·옛 형식·서류 0개)은 전과 같이 docs = 올린 파일 행, findings = [].
   - 검토 기록(out.review — 검토할 수 있는 분석이면 객체, 아니면 null)은 detailReady 일 때만 읽는다:
     검토 상태 = review.status 가 'done' 이면 done, 그 밖 needed. 검토 메모 · 메모 시각 · 검토자 · 검토 완료 시각 · 완료 메모 ·
     이력(kind 가 HKIND 키인 줄만, 시각은 서울)을 분석에, 항목별 값(review.findings)을 탐지 항목에 덧씌운다(contract.ts).
     detailReady 인데 review 가 객체가 아니면(검토 기록을 읽지 못함) 검토 상태 'none' · 빈 값이고 raw.reviewable false.
     그 밖(대기·분석 중·실패·옛 형식)은 review 가 있어도 'none' · 빈 이력.
   - 검토사항은 detailReady 일 때만 서버가 계산한 result.items 를 옮긴다(contract.ts toLiveItems — 없거나 배열이 아니면 [] =
     옛 결과). reviewable 이면 해결 기록(review.items)을 덧씌운다(overlayItemReviews). 그 밖은 빈 목록.
   - 문서 간 연결은 detailReady 일 때만 서버가 계산한 result.links 를 옮긴다(contract.ts toLiveLinks — 읽기 전용, 없으면 []).
     검토사항의 link_id 는 그 연결의 화면 번호(linkId)가 된다. 위험도 판정 키(result.decision) · 묶음 검증(result.bundle_check)은
     raw.decision · raw.bundleCheck 에 두고(상세 판정 표 — 원래 글, 최종 규칙만), 판정 키가 있으면 주요 위험 사유 = 판단 근거 + 검토 사유 줄
     (contract.ts riskReasonLines — 자르지 않은 응답 값에서 원문 값을 가린 뒤 최종 규칙을 적용한 글). 원문 값 바꾸기(raw-mask.ts)는
     분석 하나를 읽을 때 한 번 만들어 연결 글과 주요 위험 사유에 같이 쓴다.
   - 백엔드가 준 원래 값은 raw 에 둔다(결과 JSON · 올린 파일 · detailReady · reviewable · overall · 오류 · 작업 번호 · 조회 상태 ·
     원래 시각 — 만든 · 바뀐 · 시작한 시각).
   - 목록(GET /analyses)은 상세 매핑과 따로 읽는다(readAnalysisList · toListAnalysis — 가벼운 항목):
     docs = 올린 파일 행(toDoc 과 같은 모양, 문서 id 가 없어 분석 안에서 겹치지 않는 'f1'·'f2'… 를 만든다),
     위험등급 = risk_level(상·중·하 → high·medium·low, 그 밖 · null → unrated), 검토 상태 = review(done · needed, 그 밖 none),
     탐지 항목 · 검토사항 · 연결 · 이력 = 빈 값, raw 는 result null · detailReady false · reviewable false.
     응답이 객체가 아니거나 analyses 가 배열이 아니면 null(목록 불러오기 실패). 객체가 아니거나 id 가 빈 항목만 뺀다. 순서는 서버 순서.
   ========================================================================== */

import { ASTATUS, HKIND, type AnalysisStatus, type HistoryKind, type ReviewStatus, type RiskLevel } from '@/display/rules';
import { pad2 } from '@/lib/format';
import { rawValueMasker } from '../raw-mask';
import type { Analysis, AnalysisDoc, DocStatus, HistoryEntry, RawAnalysisInfo } from '../types';
import type { AnalysisOut, DocumentOut } from './client';
import {
  isDetailReady,
  markdownLines,
  overlayFindingReviews,
  overlayItemReviews,
  readBundleCheck,
  readDecision,
  readDocSources,
  readFile,
  readOverall,
  riskReasonLines,
  toLiveDocs,
  toLiveFindings,
  toLiveItems,
  toLiveLinks,
} from './contract';

/** 서울 시각 = UTC + 9시간 */
const SEOUL_OFFSET_MS = 9 * 60 * 60 * 1000;

const str = (v: unknown): string => (typeof v === 'string' ? v : '');
const isObj = (v: unknown): v is Record<string, unknown> => !!v && typeof v === 'object' && !Array.isArray(v);

/**
 * ISO 8601 → 밀리초. 소수 초는 3자리까지만 읽는다(Postgres 는 6자리를 준다). 읽지 못하면 NaN.
 * 예: '2026-11-02T14:20:31.123456+00:00'
 */
export function parseIsoMs(value: unknown): number {
  const s = str(value).trim();
  if (!s) return NaN;
  const normalized = s.replace(' ', 'T').replace(/(\.\d{3})\d+/, '$1');
  return Date.parse(normalized);
}

/** 밀리초 → 서울 시각의 [년, 월, 일, 시, 분] */
function seoulParts(ms: number): [number, number, number, number, number] {
  const d = new Date(ms + SEOUL_OFFSET_MS);
  return [d.getUTCFullYear(), d.getUTCMonth() + 1, d.getUTCDate(), d.getUTCHours(), d.getUTCMinutes()];
}

/** ISO 8601 → 'YYYY-MM-DD HH:mm'(서울 시각). 읽지 못하면 '' */
export function seoulDateTime(value: unknown): string {
  const ms = parseIsoMs(value);
  if (Number.isNaN(ms)) return '';
  const [y, mo, d, h, mi] = seoulParts(ms);
  return `${y}-${pad2(mo)}-${pad2(d)} ${pad2(h)}:${pad2(mi)}`;
}

/** 지금 시각(서울) 'YYYY-MM-DD HH:mm' — 실제 분석 보고서 · 내보내기 파일의 생성 시각(seoulDateTime 과 같은 기준) */
export function seoulNow(date: Date = new Date()): string {
  return seoulDateTime(date.toISOString());
}

/** 분석 번호 'DG-YYYYMMDD-XXXX' — 만든 날짜(서울) + id 앞 4자 대문자. 날짜를 모르면 'DG-XXXX' */
export function analysisCode(id: unknown, createdAt: unknown): string {
  const head = str(id).replace(/[^0-9a-zA-Z]/g, '').slice(0, 4).toUpperCase();
  const ms = parseIsoMs(createdAt);
  if (Number.isNaN(ms)) return `DG-${head}`;
  const [y, mo, d] = seoulParts(ms);
  return `DG-${y}${pad2(mo)}${pad2(d)}-${head}`;
}

/** 상태 값 → 화면 상태. 모르는 값은 queued */
export function toStatus(value: unknown): AnalysisStatus {
  const s = str(value);
  return Object.prototype.hasOwnProperty.call(ASTATUS, s) ? (s as AnalysisStatus) : 'queued';
}

/** 위험도 판정 값(상·중·하·검토 필요) → 화면 위험등급 */
export function riskFromLevel(level: unknown): RiskLevel {
  const s = str(level).trim();
  if (s === '상') return 'high';
  if (s === '중') return 'medium';
  if (s === '하') return 'low';
  return 'unrated';
}

/** result.summary.risk_level(없으면 null) */
export function summaryRiskLevel(result: unknown): string | null {
  if (!result || typeof result !== 'object') return null;
  const summary = (result as { summary?: unknown }).summary;
  if (!summary || typeof summary !== 'object') return null;
  const level = (summary as { risk_level?: unknown }).risk_level;
  return typeof level === 'string' && level.trim() ? level.trim() : null;
}

const EXT_BY_MIME: Record<string, string> = {
  'application/pdf': 'PDF',
  'image/png': 'PNG',
  'image/jpeg': 'JPG',
};

/** 형식 표기 — MIME 형식이 우선, 모르면 파일 확장자(jpeg → JPG), 그것도 없으면 '' */
export function extLabel(mimeType: unknown, filename: unknown): string {
  const byMime = EXT_BY_MIME[str(mimeType).toLowerCase()];
  if (byMime) return byMime;
  const m = /\.([a-z0-9]+)$/i.exec(str(filename));
  if (!m) return '';
  const ext = m[1].toUpperCase();
  return ext === 'JPEG' ? 'JPG' : ext;
}

/** 분석 상태 → 문서 상태('일부 실패'는 문서에서는 실패) */
function docStatus(status: AnalysisStatus): DocStatus {
  return status === 'partial' ? 'failed' : status;
}

/** documents 행 → 문서 */
export function toDoc(doc: DocumentOut, status: AnalysisStatus, error: string): AnalysisDoc {
  const filename = str(doc?.filename);
  const size = typeof doc?.size_bytes === 'number' && Number.isFinite(doc.size_bytes) ? doc.size_bytes : 0;
  const s = docStatus(status);
  return {
    id: str(doc?.id),
    title: filename,
    name: filename,
    ext: extLabel(doc?.mime_type, filename),
    size,
    status: s,
    error: s === 'failed' ? error : '',
    pages: null,
  };
}

/* ---------- 검토 기록 ---------- */

/** 분석 건에 덧씌우는 검토 기록 */
export interface ReviewInfo {
  review: ReviewStatus;
  memo: string;
  memoAt: string;
  reviewer: string;
  reviewedAt: string;
  completionNote: string;
  history: HistoryEntry[];
}

/** 검토 기록이 없을 때(검토할 수 없는 분석 · 기록을 읽지 못함) */
const NO_REVIEW: ReviewInfo = { review: 'none', memo: '', memoAt: '', reviewer: '', reviewedAt: '', completionNote: '', history: [] };

/**
 * 이력 줄들 — kind 가 HKIND 키(자기 속성)인 객체만 받은 순서대로. 시각은 서울(못 읽으면 ''), 글이 아니면 '',
 * id 가 빈 값 · 글이 아니면 'H<받은 배열 안 순번(1부터)>'. 배열이 아니면 [].
 */
export function readHistory(value: unknown): HistoryEntry[] {
  if (!Array.isArray(value)) return [];
  const out: HistoryEntry[] = [];
  value.forEach((row: unknown, i) => {
    if (!isObj(row) || typeof row.kind !== 'string' || !Object.prototype.hasOwnProperty.call(HKIND, row.kind)) return;
    out.push({
      id: str(row.id) || 'H' + (i + 1),
      at: seoulDateTime(row.at),
      actor: str(row.actor),
      kind: row.kind as HistoryKind,
      target: str(row.target),
      change: str(row.change),
      reason: str(row.reason),
    });
  });
  return out;
}

/** review 블록(객체) → 분석 건의 검토 기록. 객체가 아니면 null */
export function readReviewInfo(review: unknown): ReviewInfo | null {
  if (!isObj(review)) return null;
  return {
    review: review.status === 'done' ? 'done' : 'needed',
    memo: str(review.memo),
    memoAt: seoulDateTime(review.memo_at),
    reviewer: str(review.reviewer),
    reviewedAt: seoulDateTime(review.reviewed_at),
    completionNote: str(review.completion_note),
    history: readHistory(review.history),
  };
}

/** AnalysisOut → Analysis */
export function toAnalysis(out: AnalysisOut): Analysis {
  const status = toStatus(out.status);
  const error = str(out.error);
  const result = out.result !== undefined && out.result !== null && typeof out.result === 'object' ? out.result : null;
  const terminal = status === 'done' || status === 'failed' || status === 'partial';
  const analyzedAt = terminal ? seoulDateTime(out.updated_at) : '';
  const documents = Array.isArray(out.documents) ? out.documents : [];
  const file = readFile(documents);
  const overall = readOverall(result);
  const sources = result ? readDocSources((result as { documents?: unknown }).documents) : [];
  const detailReady = isDetailReady(status, result, sources);
  // 검토 기록은 상세 검토 화면 대상(detailReady)일 때만 — 그 밖은 review 가 와도 보지 않는다
  const reviewBlock: unknown = detailReady ? out.review : null;
  const info = readReviewInfo(reviewBlock);
  const reviewable = info !== null;
  const shown = info ?? NO_REVIEW;
  const findings = detailReady ? toLiveFindings((result as { findings?: unknown }).findings, sources, analyzedAt) : [];
  // 원문 값 바꾸기 — 이 분석의 탐지 항목으로 한 번(연결 글 · 주요 위험 사유)
  const mask = rawValueMasker(findings);
  // 문서 간 연결 — 서버가 계산한 result.links(없으면 옛 결과 = 0개, 읽기 전용)
  const links = detailReady ? toLiveLinks((result as { links?: unknown }).links, sources, findings, mask) : [];
  // 검토사항 — 서버가 계산한 result.items(없으면 옛 결과 = 0개). 위치는 덧씌우기 전 탐지 항목으로 찾는다(위치 · 번호는 덧씌우기와 무관)
  const items = detailReady ? toLiveItems((result as { items?: unknown }).items, sources, findings, links) : [];
  const decision = readDecision(result);
  const raw: RawAnalysisInfo = {
    result,
    file,
    detailReady,
    reviewable,
    overall,
    decision,
    bundleCheck: readBundleCheck(result),
    error,
    jobId: str(out.upstage_job_id),
    upstageStatus: str(out.upstage_status),
    pollError: str(out.poll_error),
    createdAt: str(out.created_at),
    updatedAt: str(out.updated_at),
    startedAt: str(out.started_at),
  };
  return {
    id: str(out.id),
    code: analysisCode(out.id, out.created_at),
    name: str(out.name),
    submittedAt: seoulDateTime(out.created_at),
    analyzedAt,
    status,
    risk: riskFromLevel(overall && overall.level.trim() ? overall.level : summaryRiskLevel(result)),
    review: shown.review,
    docs: detailReady ? toLiveDocs(sources, file, extLabel(file?.mime, file?.name)) : documents.map((d) => toDoc(d, status, error)),
    findings: reviewable ? overlayFindingReviews(findings, (reviewBlock as { findings?: unknown }).findings, seoulDateTime) : findings,
    items: reviewable ? overlayItemReviews(items, (reviewBlock as { items?: unknown }).items, seoulDateTime) : items,
    links,
    history: shown.history,
    memo: shown.memo,
    memoAt: shown.memoAt,
    riskReasons: riskReasonLines(readDecision(result, mask), overall),
    recs: markdownLines(overall?.nextText),
    limits: '',
    reviewer: shown.reviewer,
    reviewedAt: shown.reviewedAt,
    completionNote: shown.completionNote,
    demoQueued: false,
    retrying: false,
    raw,
  };
}

/* ---------- 목록(GET /analyses) ---------- */

/** 목록 항목의 검토 상태 — done · needed 만, 그 밖(none · 모르는 값 · 빠짐)은 none */
function listReview(value: unknown): ReviewStatus {
  return value === 'done' || value === 'needed' ? value : 'none';
}

/** 목록 항목 하나 → Analysis(가벼운 값). 객체가 아니거나 id 가 비면 null(그 항목만 뺀다) */
export function toListAnalysis(item: unknown): Analysis | null {
  if (!isObj(item)) return null;
  const id = str(item.id);
  if (!id) return null;
  const status = toStatus(item.status);
  const error = str(item.error);
  const terminal = status === 'done' || status === 'failed' || status === 'partial';
  const documents = Array.isArray(item.documents) ? item.documents.filter(isObj) : [];
  const raw: RawAnalysisInfo = {
    result: null,
    file: readFile(documents),
    detailReady: false,
    reviewable: false,
    overall: null,
    decision: null,
    bundleCheck: null,
    error,
    jobId: '',
    upstageStatus: '',
    pollError: '',
    createdAt: str(item.created_at),
    updatedAt: str(item.updated_at),
    startedAt: str(item.started_at),
  };
  return {
    id,
    code: analysisCode(id, item.created_at),
    name: str(item.name),
    submittedAt: seoulDateTime(item.created_at),
    analyzedAt: terminal ? seoulDateTime(item.updated_at) : '',
    status,
    risk: riskFromLevel(item.risk_level),
    review: listReview(item.review),
    // 목록 항목의 파일 행에는 id 가 없다 — 분석 안에서 겹치지 않는 id
    docs: documents.map((d, i) => ({ ...toDoc(d as unknown as DocumentOut, status, error), id: 'f' + (i + 1) })),
    findings: [],
    items: [],
    links: [],
    history: [],
    memo: '',
    memoAt: '',
    riskReasons: [],
    recs: [],
    limits: '',
    reviewer: '',
    reviewedAt: '',
    completionNote: '',
    demoQueued: false,
    retrying: false,
    raw,
  };
}

/** GET /analyses 응답 → 목록(서버 순서). 응답이 객체가 아니거나 analyses 가 배열이 아니면 null */
export function readAnalysisList(body: unknown): Analysis[] | null {
  if (!isObj(body) || !Array.isArray(body.analyses)) return null;
  const out: Analysis[] = [];
  for (const item of body.analyses) {
    const a = toListAnalysis(item);
    if (a) out.push(a);
  }
  return out;
}
