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
   - 검토사항·연결·이력은 아직 없다(빈 목록). 검토 상태는 늘 'none'.
   - 백엔드가 준 원래 값은 raw 에 둔다(결과 JSON · 올린 파일 · detailReady · overall · 오류 · 작업 번호 · 조회 상태 · 원래 시각).
   ========================================================================== */

import { ASTATUS, type AnalysisStatus, type RiskLevel } from '@/display/rules';
import { pad2 } from '@/lib/format';
import type { Analysis, AnalysisDoc, DocStatus, RawAnalysisInfo } from '../types';
import type { AnalysisOut, DocumentOut } from './client';
import { isDetailReady, markdownLines, readDocSources, readFile, readOverall, toLiveDocs, toLiveFindings } from './contract';

/** 서울 시각 = UTC + 9시간 */
const SEOUL_OFFSET_MS = 9 * 60 * 60 * 1000;

const str = (v: unknown): string => (typeof v === 'string' ? v : '');

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
  const raw: RawAnalysisInfo = {
    result,
    file,
    detailReady,
    overall,
    error,
    jobId: str(out.upstage_job_id),
    upstageStatus: str(out.upstage_status),
    pollError: str(out.poll_error),
    createdAt: str(out.created_at),
    updatedAt: str(out.updated_at),
  };
  return {
    id: str(out.id),
    code: analysisCode(out.id, out.created_at),
    name: str(out.name),
    submittedAt: seoulDateTime(out.created_at),
    analyzedAt,
    status,
    risk: riskFromLevel(overall && overall.level.trim() ? overall.level : summaryRiskLevel(result)),
    review: 'none',
    docs: detailReady ? toLiveDocs(sources, file, extLabel(file?.mime, file?.name)) : documents.map((d) => toDoc(d, status, error)),
    findings: detailReady ? toLiveFindings((result as { findings?: unknown }).findings, sources, analyzedAt) : [],
    items: [],
    links: [],
    history: [],
    memo: '',
    memoAt: '',
    riskReasons: markdownLines(overall?.text),
    recs: markdownLines(overall?.nextText),
    limits: '',
    reviewer: '',
    reviewedAt: '',
    completionNote: '',
    demoQueued: false,
    retrying: false,
    raw,
  };
}
