/* ==========================================================================
   ② 표시 규칙 — 서비스 값을 화면 표기(라벨·아이콘·색)로 바꾼다.
   분석 출력 형식이 확정되면 이 파일과 services/types.ts만 바꾼다.

   - 원본: Main.dc.html 780–853줄. 키·라벨·아이콘·순서를 그대로 옮겼다.
   - 색은 모두 tokens.css 의 var(--토큰)이다(리터럴 없음). 색은 항상 글자·아이콘과 함께 쓴다.
   - 규칙 ID(PII-ID-001 등)와 위험 판정은 디자인용 예시다. 실제 기준처럼 늘리지 않는다.
   - 등급 라벨·정보 종류·정보 주체·노출 상태·오탐 사유·이력 구분 목록은 이 파일에만 둔다.
   ========================================================================== */

import type { IconName } from './icon-names';

/* ---------- 위험 등급 ---------- */

export interface RiskView {
  readonly key: string;
  readonly label: string;
  /** 정렬 순위 — 클수록 위험 */
  readonly rank: number;
  /** 글자색 */
  readonly fg: string;
  /** 알약·칸 바탕 */
  readonly bg: string;
  /** 테두리 */
  readonly line: string;
  /** 원문 밑줄·막대 */
  readonly solid: string;
  /** 원문 이름표 바탕 */
  readonly tag: string;
  /** 원문 하이라이트 바탕 */
  readonly soft: string;
  /** 선택한 하이라이트 바탕 */
  readonly focus: string;
  /** 선택 신호 퍼짐 */
  readonly halo: string;
  /** 위험 막대 아이콘 */
  readonly glyph: IconName;
}

export const RISK = {
  high: { key: 'high', label: '높음', rank: 3, fg: 'var(--hi)', bg: 'var(--hi-bg)', line: 'var(--hi-line)', solid: 'var(--hi-solid)', tag: 'var(--hi-tag)', soft: 'var(--hi-soft)', focus: 'var(--hi-focus)', halo: 'var(--hi-halo)', glyph: 'dg-r3' },
  medium: { key: 'medium', label: '보통', rank: 2, fg: 'var(--md)', bg: 'var(--md-bg)', line: 'var(--md-line)', solid: 'var(--md-solid)', tag: 'var(--md-tag)', soft: 'var(--md-soft)', focus: 'var(--md-focus)', halo: 'var(--md-halo)', glyph: 'dg-r2' },
  low: { key: 'low', label: '낮음', rank: 1, fg: 'var(--lo)', bg: 'var(--lo-bg)', line: 'var(--lo-line)', solid: 'var(--lo-solid)', tag: 'var(--lo-tag)', soft: 'var(--lo-soft)', focus: 'var(--lo-focus)', halo: 'var(--lo-halo)', glyph: 'dg-r1' },
  unrated: { key: 'unrated', label: '미평가', rank: 0, fg: 'var(--na)', bg: 'var(--na-bg)', line: 'var(--na-line)', solid: 'var(--na-solid)', tag: 'var(--na-tag)', soft: 'var(--na-soft)', focus: 'var(--na-focus)', halo: 'var(--na-halo)', glyph: 'dg-r0' },
} as const satisfies Record<string, RiskView>;

export type RiskLevel = keyof typeof RISK;
/** 위험 등급 키 — 높은 순서 */
export const RISK_LEVELS = Object.keys(RISK) as RiskLevel[];

/* ---------- 분석 상태(분석 건·문서) ---------- */

export interface AnalysisStatusView {
  readonly label: string;
  readonly fg: string;
  readonly icon: IconName;
  /** 아이콘을 돌리는지(분석 중) */
  readonly spin: boolean;
  /** 목록 점 색 */
  readonly dot: string;
}

export const ASTATUS = {
  queued: { label: '대기', fg: 'var(--status-queued-fg)', icon: 'dg-i-clock', spin: false, dot: 'var(--status-queued-dot)' },
  running: { label: '분석 중', fg: 'var(--status-running-fg)', icon: 'dg-i-clock', spin: true, dot: 'var(--status-running-dot)' },
  done: { label: '완료', fg: 'var(--status-done-fg)', icon: 'dg-i-check-circle', spin: false, dot: 'var(--status-done-dot)' },
  partial: { label: '일부 실패', fg: 'var(--status-partial-fg)', icon: 'dg-i-alert', spin: false, dot: 'var(--status-partial-dot)' },
  failed: { label: '실패', fg: 'var(--status-failed-fg)', icon: 'dg-i-x-circle', spin: false, dot: 'var(--status-failed-dot)' },
} as const satisfies Record<string, AnalysisStatusView>;

export type AnalysisStatus = keyof typeof ASTATUS;

/* ---------- 검토 상태(분석 건) ---------- */

export interface ReviewStatusView {
  readonly label: string;
  readonly fg: string;
  readonly bg: string;
  readonly line: string;
  readonly icon: IconName;
}

export const RSTATUS = {
  none: { label: '미검토', fg: 'var(--ink-2)', bg: 'var(--fill)', line: 'transparent', icon: 'dg-i-circle-dashed' },
  needed: { label: '검토 필요', fg: 'var(--on-solid)', bg: 'var(--ink)', line: 'transparent', icon: 'dg-i-flag' },
  done: { label: '검토 완료', fg: 'var(--accent-ink)', bg: 'var(--accent-soft-2)', line: 'transparent', icon: 'dg-i-check-badge' },
} as const satisfies Record<string, ReviewStatusView>;

export type ReviewStatus = keyof typeof RSTATUS;

/* ---------- 탐지 항목 확인 상태 ---------- */

export interface FindingStatusView {
  readonly label: string;
  readonly fg: string;
  readonly icon: IconName;
}

export const FSTATUS = {
  open: { label: '미확인', fg: 'var(--ink-3)', icon: 'dg-i-circle' },
  confirmed: { label: '확인함', fg: 'var(--accent-ink)', icon: 'dg-i-check' },
  false_positive: { label: '오탐', fg: 'var(--ink-3)', icon: 'dg-i-ban' },
  reclassified: { label: '분류 수정', fg: 'var(--lo)', icon: 'dg-i-pencil' },
} as const satisfies Record<string, FindingStatusView>;

export type FindingStatus = keyof typeof FSTATUS;

/* ---------- 검토사항 유형 ---------- */

export interface ReviewItemTypeView {
  readonly label: string;
  readonly icon: IconName;
}

export const RTYPE = {
  unreadable: { label: '판독 불가', icon: 'dg-i-eye-off' },
  cutoff: { label: '페이지 잘림', icon: 'dg-i-scissors' },
  mismatch: { label: '값 불일치', icon: 'dg-i-neq' },
  weaklink: { label: '연결 근거 부족', icon: 'dg-i-link-off' },
  nolocation: { label: '위치 확인 필요', icon: 'dg-i-pin-q' },
  failed: { label: '분석 실패', icon: 'dg-i-x-circle' },
} as const satisfies Record<string, ReviewItemTypeView>;

export type ReviewItemType = keyof typeof RTYPE;

/* ---------- 문서 간 연결 상태 ---------- */

export interface LinkStatusView {
  readonly label: string;
  readonly fg: string;
  readonly bg: string;
  readonly icon: IconName;
}

export const LSTATUS = {
  confirmed: { label: '연결 근거 확인됨', fg: 'var(--ink)', bg: 'var(--fill)', icon: 'dg-i-link' },
  check: { label: '연결 확인 필요', fg: 'var(--warn)', bg: 'var(--warn-bg)', icon: 'dg-i-help' },
  linked: { label: '담당자 확인 · 연결 맞음', fg: 'var(--accent-ink)', bg: 'var(--accent-soft-2)', icon: 'dg-i-link' },
  unlinked: { label: '담당자 확인 · 연결 아님', fg: 'var(--ink-2)', bg: 'var(--fill)', icon: 'dg-i-link-off' },
} as const satisfies Record<string, LinkStatusView>;

export type LinkStatus = keyof typeof LSTATUS;

/* ---------- 적용 규칙 예시(디자인용) ---------- */

export const RULES = {
  'PII-ID-001': '주민등록번호 전체 노출', 'PII-ID-002': '주민등록번호 일부 가림',
  'PII-NM-001': '성명', 'PII-NM-002': '일부 가린 성명', 'PII-NM-003': '거래 상대방 성명',
  'PII-CT-001': '휴대전화번호', 'PII-CT-002': '이메일 주소', 'PII-CT-003': '일부 가린 연락처',
  'PII-AD-001': '상세 주소', 'PII-BD-001': '생년월일',
  'FIN-AC-001': '본인 계좌번호 전체 노출', 'FIN-AC-002': '계좌번호 형식 숫자열', 'FIN-AC-003': '제3자 계좌번호 전체 노출', 'FIN-AC-004': '가린 계좌번호',
  'FIN-IN-001': '연간 소득 금액', 'FIN-IN-002': '세액 정보', 'FIN-IN-003': '식별정보와 함께 적힌 소득',
  'FIN-TX-002': '고액 이체 내역', 'FIN-TX-004': '정기 급여 입금',
} as const;

export type RuleId = keyof typeof RULES;

/* ---------- 검토 이력 구분 ---------- */

export const HKIND = {
  ai: '최초 AI 결과',
  request: '분석 요청',
  retry: '다시 분석',
  confirm: '탐지 확인',
  unconfirm: '확인 취소',
  fp: '오탐 표시',
  restore: '오탐 취소',
  reclass: '분류 수정',
  fmemo: '항목 메모',
  memo: '검토 메모',
  resolve: '검토사항 해결',
  reopenItem: '검토사항 다시 열기',
  link: '연결 판단',
  complete: '검토 완료',
  reopen: '검토 다시 열기',
  export: '결과 내보내기',
} as const;

export type HistoryKind = keyof typeof HKIND;

/* ---------- 정보 종류 · 정보 주체 · 노출 상태 · 오탐 사유 ---------- */

export const CATS = ['이름', '연락처·이메일', '주소', '생년월일', '고유식별정보', '계좌번호', '소득·거래정보', '기타 개인정보'] as const;
export type InfoCategory = (typeof CATS)[number];

export const SUBJECTS = ['신청인', '보증인', '기타 · 거래 상대방', '기타 · 은행 직원', '기타'] as const;
export type InfoSubject = (typeof SUBJECTS)[number];

export const EXPOSURES = ['전체 노출', '부분 마스킹', '마스킹됨'] as const;
export type Exposure = (typeof EXPOSURES)[number];

export const FP_REASONS = ['개인정보가 아닌 번호·문구', '다른 정보 종류를 잘못 인식', '이미 가려진 값', '기타'] as const;
export type FpReason = (typeof FP_REASONS)[number];

/* ---------- 내보내기 형식 ---------- */

export const EXPORT_FORMATS = [
  { key: 'csv', label: 'CSV · 탐지 항목 목록', desc: '엑셀 등에서 열 수 있는 표입니다. 탐지 항목, 판단 근거, 확인 상태를 담습니다.' },
  { key: 'json', label: 'JSON · 보고서 전체', desc: '분석 정보, 탐지 항목, 검토사항, 문서 간 연결, 검토 이력을 모두 담습니다.' },
] as const;

export type ExportFormat = (typeof EXPORT_FORMATS)[number]['key'];

/* ---------- 도우미 ---------- */

function hasKey<T extends object>(table: T, key: string | null | undefined): key is Extract<keyof T, string> {
  return key != null && Object.prototype.hasOwnProperty.call(table, key);
}

/** 위험 등급 표기. 모르는 값은 '미평가'. (원본 riskV) */
export function riskView(level: string | null | undefined): RiskView {
  return hasKey(RISK, level) ? RISK[level] : RISK.unrated;
}

/** 분석 상태 표기. 모르는 값은 '대기'. still = 아이콘이 멈춰 있는지. (원본 stV) */
export function analysisStatusView(status: string | null | undefined): AnalysisStatusView & { readonly still: boolean } {
  const s: AnalysisStatusView = hasKey(ASTATUS, status) ? ASTATUS[status] : ASTATUS.queued;
  return { ...s, still: !s.spin };
}

/** 검토 상태 표기. 모르는 값은 '미검토'. (원본 rvV) */
export function reviewStatusView(status: string | null | undefined): ReviewStatusView {
  return hasKey(RSTATUS, status) ? RSTATUS[status] : RSTATUS.none;
}

/** 위험 높은 순 정렬 비교 함수. (원본 byRisk) */
export function byRisk(x: { readonly risk: string }, y: { readonly risk: string }): number {
  return riskView(y.risk).rank - riskView(x.risk).rank;
}
