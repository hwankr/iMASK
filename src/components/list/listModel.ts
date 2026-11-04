/* ==========================================================================
   분석 목록 화면 모델 — 프로토타입 listVM · rowVM(Main.dc.html 1919–1991)의 계산 부분.
   - 데이터는 서비스(useAnalyses)가 준 분석 목록이다. 샘플 데이터를 직접 쓰지 않는다.
   - 라벨·색·아이콘은 ② 표시 규칙(src/display/rules.ts)에서 가져온다.
   - 필터 값은 URL 검색 파라미터(q · risk · status · review · sort)와 서로 바꿀 수 있다.
   ========================================================================== */

import { ASTATUS, RISK, RSTATUS, analysisRiskView, type AnalysisStatus, type ReviewStatus, type RiskLevel } from '@/display/rules';
import type { IconName } from '@/display/icon-names';
import { CONFIG } from '@/config/app';
import { fmtDT } from '@/lib/format';
import type { Analysis } from '@/services/types';

/* ---------- 필터 ---------- */

export type RiskFilter = 'all' | RiskLevel;
export type StatusFilter = 'all' | AnalysisStatus;
export type ReviewFilter = 'all' | ReviewStatus;
export type SortKey = 'recent' | 'risk';

/** 목록 검색·필터·정렬 (프로토타입 state 의 q · fRisk · fStatus · fReview · sort) */
export interface ListFilters {
  q: string;
  risk: RiskFilter;
  status: StatusFilter;
  review: ReviewFilter;
  sort: SortKey;
}

export const DEFAULT_FILTERS: Readonly<ListFilters> = { q: '', risk: 'all', status: 'all', review: 'all', sort: 'recent' };

/** 검색·필터 초기화(정렬은 그대로 — 프로토타입 resetFilters) */
export const CLEARED_FILTERS: Readonly<Omit<ListFilters, 'sort'>> = { q: '', risk: 'all', status: 'all', review: 'all' };

const SORT_KEYS: readonly SortKey[] = ['recent', 'risk'];

function own(table: object, key: string | null): boolean {
  return key != null && Object.prototype.hasOwnProperty.call(table, key);
}

/** 읽기 전용 검색 파라미터(URLSearchParams · Next ReadonlyURLSearchParams) */
export interface SearchParamsLike {
  get(name: string): string | null;
}

/** URL 검색 파라미터 → 필터. 모르는 값은 기본값('전체' · 최근 접수순). */
export function parseFilters(params: SearchParamsLike | null | undefined): ListFilters {
  const get = (k: string) => (params ? params.get(k) : null);
  const risk = get('risk');
  const status = get('status');
  const review = get('review');
  const sort = get('sort');
  return {
    q: get('q') ?? '',
    risk: risk !== null && own(RISK, risk) ? (risk as RiskLevel) : 'all',
    status: status !== null && own(ASTATUS, status) ? (status as AnalysisStatus) : 'all',
    review: review !== null && own(RSTATUS, review) ? (review as ReviewStatus) : 'all',
    sort: sort !== null && (SORT_KEYS as readonly string[]).includes(sort) ? (sort as SortKey) : 'recent',
  };
}

/** 필터 → URL 검색 문자열(물음표 없음). 기본값은 빼고, 순서는 q · risk · status · review · sort 로 고정. */
export function filtersToQuery(f: ListFilters): string {
  const p = new URLSearchParams();
  if (f.q) p.set('q', f.q);
  if (f.risk !== 'all') p.set('risk', f.risk);
  if (f.status !== 'all') p.set('status', f.status);
  if (f.review !== 'all') p.set('review', f.review);
  if (f.sort !== 'recent') p.set('sort', f.sort);
  return p.toString();
}

/** 검색어나 필터가 걸렸는지(정렬은 세지 않는다) */
export function isFiltered(f: ListFilters): boolean {
  return !!f.q.trim() || f.risk !== 'all' || f.status !== 'all' || f.review !== 'all';
}

/** 행 등장 움직임을 다시 돌리는 서명 — 필터·정렬이 바뀔 때만(검색어는 제외, 프로토타입 listSig) */
export function replaySignature(f: ListFilters): string {
  return [f.risk, f.status, f.review, f.sort].join('|');
}

/* ---------- 행 ---------- */

/** 표 · 휴대폰 카드 한 줄 (프로토타입 rowVM) */
export interface ListRow {
  id: string;
  name: string;
  /** '첫 파일명 외 n개' */
  files: string;
  docs: number;
  risk: string;
  status: string;
  review: string;
  /** 접수일시 'YYYY.MM.DD HH:mm' */
  date: string;
  /** 분석 상태 아래 작은 글자 */
  sub: string;
  failed: boolean;
  retrying: boolean;
}

export function toRow(a: Analysis): ListRow {
  const nDocs = a.docs.length;
  const nFail = a.docs.filter((d) => d.status === 'failed').length;
  const nDone = a.docs.filter((d) => d.status === 'done').length;
  let sub = '';
  if (a.retrying) sub = '다시 분석하는 중';
  else if (a.status === 'partial') sub = '문서 ' + nFail + '개 처리 실패';
  else if (a.status === 'running') sub = '문서 ' + nDone + '/' + nDocs + '개 완료';
  else if (a.status === 'queued' && a.demoQueued) sub = '데모 · 분석하지 않음';
  return {
    id: a.id,
    name: a.name,
    files: a.docs[0] ? a.docs[0].name + (nDocs > 1 ? ' 외 ' + (nDocs - 1) + '개' : '') : '-',
    docs: nDocs,
    risk: a.risk,
    status: a.status,
    review: a.review,
    date: fmtDT(a.submittedAt),
    sub,
    failed: a.status === 'failed',
    retrying: !!a.retrying,
  };
}

/* ---------- 걸러 내기 · 정렬 ---------- */

export function matchesFilters(a: Analysis, f: ListFilters): boolean {
  const q = f.q.trim().toLowerCase();
  return (
    (!q || a.name.toLowerCase().indexOf(q) >= 0 || a.docs.some((d) => d.name.toLowerCase().indexOf(q) >= 0)) &&
    (f.risk === 'all' || a.risk === f.risk) &&
    (f.status === 'all' || a.status === f.status) &&
    (f.review === 'all' || a.review === f.review)
  );
}

function byDate(x: Analysis, y: Analysis): number {
  return y.submittedAt > x.submittedAt ? 1 : y.submittedAt < x.submittedAt ? -1 : 0;
}

/** 위험도순 — 분석 건 위험도 순위(검토 필요 → 높음 → 보통 → 낮음 → 미평가), 같으면 최근 접수순 */
export function sortAnalyses(rows: readonly Analysis[], sort: SortKey): Analysis[] {
  return rows.slice().sort(sort === 'risk' ? (x, y) => analysisRiskView(y.risk).rank - analysisRiskView(x.risk).rank || byDate(x, y) : byDate);
}

/* ---------- 드롭다운 ---------- */

export type DropdownId = 'risk' | 'status' | 'review' | 'sort';

export interface DropdownOptionModel {
  value: string;
  label: string;
  icon: IconName;
  iconColor: string;
  tileColor: string;
  /** 건수(정렬에는 없음) */
  count?: number;
}

export interface DropdownModel {
  id: DropdownId;
  title: string;
  options: DropdownOptionModel[];
}

/**
 * 분석 상태 드롭다운의 타일 아이콘·색 — 프로토타입 listVM DDO.fStatus.
 * 라벨은 ② ASTATUS 에서 가져오고, 메뉴 타일 모양만 이 화면에 둔다(② 의 상태 아이콘과 다르다: 분석 중은 새로 고침 아이콘).
 */
const STATUS_TILE: Record<AnalysisStatus, { icon: IconName; fg: string; bg: string }> = {
  queued: { icon: 'dg-i-clock', fg: 'var(--status-queued-fg)', bg: 'var(--fill)' },
  running: { icon: 'dg-i-refresh', fg: 'var(--run)', bg: 'var(--run-bg)' },
  done: { icon: 'dg-i-check-circle', fg: 'var(--ink-2)', bg: 'var(--fill)' },
  partial: { icon: 'dg-i-alert', fg: 'var(--warn)', bg: 'var(--warn-bg)' },
  failed: { icon: 'dg-i-x-circle', fg: 'var(--err)', bg: 'var(--err-bg)' },
};

const ALL_OPTION = { value: 'all', label: '전체', icon: 'dg-i-layers', iconColor: 'var(--ink-2)', tileColor: 'var(--fill)' } as const;

/** 정렬 선택지(프로토타입 DDO.sort) */
export const SORT_OPTIONS: readonly DropdownOptionModel[] = [
  { value: 'recent', label: '최근 접수순', icon: 'dg-i-clock', iconColor: 'var(--ink-2)', tileColor: 'var(--fill)' },
  { value: 'risk', label: '위험도순', icon: RISK.high.glyph, iconColor: RISK.high.fg, tileColor: RISK.high.bg },
];

/** 드롭다운 4개 — 위험등급 · 분석 상태 · 검토 상태(건수는 전체 목록 기준) · 정렬 */
export function dropdownModels(all: readonly Analysis[]): DropdownModel[] {
  const count = (field: 'risk' | 'status' | 'review', v: string) => all.filter((a) => a[field] === v).length;
  return [
    {
      id: 'risk',
      title: '위험등급',
      options: [
        { ...ALL_OPTION, count: all.length },
        ...(Object.keys(RISK) as RiskLevel[]).map((k) => ({ value: k, label: RISK[k].label, icon: RISK[k].glyph, iconColor: RISK[k].fg, tileColor: RISK[k].bg, count: count('risk', k) })),
      ],
    },
    {
      id: 'status',
      title: '분석 상태',
      options: [
        { ...ALL_OPTION, count: all.length },
        ...(Object.keys(ASTATUS) as AnalysisStatus[]).map((k) => ({ value: k, label: ASTATUS[k].label, icon: STATUS_TILE[k].icon, iconColor: STATUS_TILE[k].fg, tileColor: STATUS_TILE[k].bg, count: count('status', k) })),
      ],
    },
    {
      id: 'review',
      title: '검토 상태',
      options: [
        { ...ALL_OPTION, count: all.length },
        ...(Object.keys(RSTATUS) as ReviewStatus[]).map((k) => ({ value: k, label: RSTATUS[k].label, icon: RSTATUS[k].icon, iconColor: RSTATUS[k].fg, tileColor: RSTATUS[k].bg, count: count('review', k) })),
      ],
    },
    { id: 'sort', title: '정렬', options: [...SORT_OPTIONS] },
  ];
}

/* ---------- 화면 모델 ---------- */

export type SummaryCardId = 'total' | 'high' | 'needed';

export interface SummaryCard {
  id: SummaryCardId;
  label: string;
  n: number;
  icon: IconName;
  /** 아이콘 색 · 숫자 색 */
  iconColor: string;
  color: string;
  on: boolean;
  hint: string;
  aria: string;
}

export interface ListModel {
  total: number;
  high: number;
  needed: number;
  hasData: boolean;
  empty: boolean;
  filtered: boolean;
  heroLead: string;
  heroStrong: string;
  heroTail: string;
  basis: string;
  resultText: string;
  resultSub: string;
  noResults: boolean;
  noResultsText: string;
  cards: SummaryCard[];
  rows: ListRow[];
}

export function listModel(all: readonly Analysis[], f: ListFilters, userName: string = CONFIG.user.name): ListModel {
  const total = all.length;
  const high = all.filter((a) => a.risk === 'high').length;
  const needed = all.filter((a) => a.review === 'needed').length;
  const filtered = isFiltered(f);
  const shown = sortAnalyses(all.filter((a) => matchesFilters(a, f)), f.sort);
  const fHigh = shown.filter((a) => a.risk === 'high').length;
  const fNeeded = shown.filter((a) => a.review === 'needed').length;
  const q = f.q.trim();
  const cards: SummaryCard[] = [
    {
      id: 'total',
      label: '전체 분석',
      n: total,
      icon: 'dg-i-layers',
      iconColor: 'var(--ink-2)',
      color: 'var(--ink)',
      on: !filtered,
      hint: filtered ? '누르면 검색 · 필터를 모두 해제합니다' : '모든 분석 건을 보고 있습니다',
      aria: '전체 분석 ' + total + '건' + (filtered ? ', 누르면 검색과 필터 해제' : ''),
    },
    {
      id: 'high',
      label: '고위험',
      n: high,
      icon: 'dg-i-alert',
      iconColor: 'var(--hi)',
      color: 'var(--hi)',
      on: f.risk === 'high',
      hint: f.risk === 'high' ? '필터 적용 중 · 다시 누르면 해제' : '위험등급이 ‘높음’인 분석 건',
      aria: '고위험 ' + high + '건, ' + (f.risk === 'high' ? '필터 해제' : '고위험만 보기'),
    },
    {
      id: 'needed',
      label: '검토 필요',
      n: needed,
      icon: 'dg-i-flag',
      iconColor: 'var(--ink)',
      color: 'var(--ink)',
      on: f.review === 'needed',
      hint: f.review === 'needed' ? '필터 적용 중 · 다시 누르면 해제' : '담당자 확인이 필요한 분석 건',
      aria: '검토 필요 ' + needed + '건, ' + (f.review === 'needed' ? '필터 해제' : '검토 필요만 보기'),
    },
  ];
  return {
    total,
    high,
    needed,
    hasData: total > 0,
    empty: total === 0,
    filtered,
    heroLead: userName + '님, ' + (needed ? '검토가 필요한 분석이 ' : '지금 검토가 필요한 분석은 없습니다.'),
    heroStrong: needed ? needed + '건' : '',
    heroTail: needed ? ' 있습니다.' : '',
    basis: filtered ? '검색 결과 기준' : '전체 기준',
    resultText: filtered ? shown.length + '건 표시 · 전체 ' + total + '건 중' : '전체 ' + total + '건',
    resultSub: '이 중 고위험 ' + fHigh + '건 · 검토 필요 ' + fNeeded + '건',
    noResults: shown.length === 0,
    noResultsText: q
      ? '‘' + q + '’에 맞는 분석명이나 파일명이 없습니다. 검색어를 바꾸거나 필터를 초기화해 보세요.'
      : '선택한 필터에 맞는 분석 건이 없습니다. 필터를 바꾸거나 초기화해 보세요.',
    cards,
    rows: shown.map(toRow),
  };
}
