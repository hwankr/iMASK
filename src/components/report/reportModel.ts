/* ==========================================================================
   보고서 화면 모델 — 프로토타입 reportVM(Main.dc.html 2329–2376) 을 순수 함수로 옮겼다.
   - 위험등급·근거·라벨은 서비스 값과 ② 표시 규칙 그대로다(화면에서 다시 판정하지 않는다).
   - 민감한 값은 마스킹된 표시값(masked)만 쓴다. 원문 위치 조각(Highlight.x)은 보고서에 넣지 않는다.
   - 휴대폰 배치(요약 카드 구분선 등)는 CSS 가 맡는다. 여기에는 폭과 상관없는 값만 둔다.
   ========================================================================== */

import {
  CATS,
  FSTATUS,
  HKIND,
  RISK,
  RTYPE,
  analysisStatusView,
  riskView,
  type FindingStatusView,
  type HistoryKind,
  type InfoCategory,
  type RiskLevel,
  type RiskView,
} from '@/display/rules';
import { fmtDT } from '@/lib/format';
import type { Analysis } from '@/services/types';

/* ---------- 이력 구분별 색(원본 reportVM 의 KDOT · KFG) ----------
   ② 의 HKIND 키로 묶어 두어 ② 에 구분이 늘면 컴파일 오류가 난다. 색은 모두 토큰이다.
   원본 값: #A3ABB8 = --na-solid · #F08C1A = --warn-solid · #141B2D = --ink · #3D7BEF = --lo-solid */
const HISTORY_DOT: Record<HistoryKind, string> = {
  ai: 'var(--na-solid)',
  request: 'var(--na-solid)',
  retry: 'var(--warn-solid)',
  confirm: 'var(--accent)',
  unconfirm: 'var(--na-solid)',
  fp: 'var(--ink)',
  restore: 'var(--na-solid)',
  reclass: 'var(--lo-solid)',
  fmemo: 'var(--na-solid)',
  memo: 'var(--na-solid)',
  resolve: 'var(--accent)',
  reopenItem: 'var(--warn-solid)',
  link: 'var(--ink)',
  complete: 'var(--accent)',
  reopen: 'var(--warn-solid)',
  export: 'var(--na-solid)',
};

const HISTORY_FG: Record<HistoryKind, string> = {
  ai: 'var(--ink)',
  request: 'var(--ink-2)',
  retry: 'var(--warn)',
  confirm: 'var(--accent-ink)',
  unconfirm: 'var(--ink-2)',
  fp: 'var(--ink)',
  restore: 'var(--ink-2)',
  reclass: 'var(--lo)',
  fmemo: 'var(--ink-2)',
  memo: 'var(--ink-2)',
  resolve: 'var(--accent-ink)',
  reopenItem: 'var(--warn)',
  link: 'var(--ink)',
  complete: 'var(--accent-ink)',
  reopen: 'var(--warn)',
  export: 'var(--ink-2)',
};

/** 분포·요약에 세는 위험등급(높은 순) — 라벨·색은 ② RISK 에서 가져온다 */
const COUNTED_LEVELS = ['high', 'medium', 'low'] as const satisfies readonly RiskLevel[];

function hasOwn<T extends object>(table: T, key: string): key is Extract<keyof T, string> {
  return Object.prototype.hasOwnProperty.call(table, key);
}

/* ---------- 모양 ---------- */

/** 결과 요약 카드 한 장 */
export interface KpiCard {
  key: 'findings' | 'reviewed' | 'remaining' | 'links';
  label: string;
  num: number;
  /** 숫자 뒤 단위('건' 또는 빈 글자) */
  unit: string;
  /** 단위 뒤 흐린 글자('/ 12' 등, 없으면 빈 글자) */
  after: string;
  sub: string;
  /** 숫자를 주의 색으로(남은 검토사항이 있을 때) */
  warn: boolean;
}

/** 위험등급별 탐지 분포 막대 한 조각 */
export interface DistSegment {
  key: 'high' | 'medium' | 'low';
  label: string;
  n: number;
  /** 막대·범례 색(② RISK[key].solid) */
  color: string;
  /** 차례(등장 지연 = 0.12초 × index) */
  index: number;
}

/** 03 대상 문서 표 한 줄 */
export interface DocRow {
  id: string;
  title: string;
  file: string;
  /** '형식 · N페이지' 또는 '형식 · 페이지 확인 불가' */
  meta: string;
  statusLabel: string;
  statusFg: string;
  /** 분석이 끝난 문서만 숫자, 아니면 '-' */
  nFind: number | '-';
  nHigh: number | '-';
  /** 높음이 있으면 높음 색 */
  highOn: boolean;
  /** '확인 수/탐지 수' 또는 '-' */
  reviewed: string;
  /** 남은 검토사항 수 */
  open: number;
}

/** 04 정보 종류별 표 한 줄 */
export interface CatRow {
  cat: InfoCategory;
  n: number;
  high: number;
  medium: number;
  low: number;
  reviewed: number;
  fp: number;
}

/** 04 전체 탐지 항목(펼치기) 한 줄 — 표시값은 마스킹된 값 */
export interface FindingLine {
  id: string;
  cat: InfoCategory;
  masked: string;
  subject: string;
  /** '문서 제목 N쪽' */
  where: string;
  risk: RiskView;
  status: FindingStatusView;
  /** 오탐이면 표시값을 흐리게·취소선 */
  falsePositive: boolean;
}

/** 05 남아 있는 검토사항 한 줄 */
export interface RemainingLine {
  id: string;
  type: string;
  title: string;
  where: string;
  next: string;
}

/** 08 최초 AI 결과와 담당자 수정 한 줄 */
export interface ChangeLine {
  id: string;
  item: string;
  ai: string;
  now: string;
  reason: string;
  at: string;
}

/** 08 검토 기록 한 줄 */
export interface HistoryLine {
  id: string;
  at: string;
  actor: string;
  kind: string;
  kindFg: string;
  dot: string;
  target: string;
  change: string;
  reason: string;
}

export interface ReportView {
  code: string;
  name: string;
  /** 서비스 값 그대로 — 표기는 공통 상태 표기 컴포넌트가 ② 규칙으로 */
  risk: string;
  status: string;
  review: string;
  /** '검토자 · 완료 시각' 또는 '검토 진행 중 (완료 전)' */
  completedText: string;
  notDone: boolean;
  cards: KpiCard[];
  dist: DistSegment[];
  distAria: string;
  nFind: number;
  reasons: string[];
  noReasonsText: string;
  limits: string;
  docs: DocRow[];
  cats: CatRow[];
  findings: FindingLine[];
  remaining: RemainingLine[];
  recs: string[];
  /** 메모 글자(없으면 안내 문구) */
  memo: string;
  hasMemo: boolean;
  completionNote: string;
  changes: ChangeLine[];
  history: HistoryLine[];
}

/** 분석 건 → 보고서 화면 값 (원본 reportVM) */
export function reportView(a: Analysis): ReportView {
  const f = a.findings;
  const docs = a.docs;
  const by = (fn: (x: (typeof f)[number]) => boolean) => f.filter(fn).length;
  const c = {
    total: f.length,
    high: by((x) => x.risk === 'high'),
    medium: by((x) => x.risk === 'medium'),
    low: by((x) => x.risk === 'low'),
    reviewed: by((x) => x.status !== 'open'),
    fp: by((x) => x.status === 'false_positive'),
    recl: by((x) => x.status === 'reclassified'),
  };
  const openI = a.items.filter((i) => !i.resolved);
  const linksCheck = a.links.filter((l) => l.status === 'check' && !l.decision).length;
  const docT = (id: string) => {
    const d = docs.find((x) => x.id === id);
    return d ? d.title || d.name : '';
  };

  const cats: CatRow[] = CATS.map((cat) => {
    const l = f.filter((x) => x.cat === cat);
    return {
      cat,
      n: l.length,
      high: l.filter((x) => x.risk === 'high').length,
      medium: l.filter((x) => x.risk === 'medium').length,
      low: l.filter((x) => x.risk === 'low').length,
      reviewed: l.filter((x) => x.status !== 'open').length,
      fp: l.filter((x) => x.status === 'false_positive').length,
    };
  }).filter((r) => r.n > 0);

  const changes: ChangeLine[] = f
    .filter((x) => x.status === 'false_positive' || x.status === 'reclassified')
    .map((x) => {
      const h = a.history
        .slice()
        .reverse()
        .find((e) => (e.kind === 'fp' || e.kind === 'reclass') && String(e.target).indexOf(x.id) === 0);
      const fp = x.status === 'false_positive';
      return {
        id: x.id,
        item: x.label,
        ai: x.ai.cat + ' · ' + x.ai.subject + ' · ' + x.ai.exposure,
        now: fp ? FSTATUS.false_positive.label + ' (' + (x.fpType || '사유 기록') + ')' : x.cat + ' · ' + x.subject + ' · ' + x.exposure,
        reason: fp ? x.fpNote || '-' : x.reclassNote || '-',
        at: h ? fmtDT(h.at) : '-',
      };
    });

  const dist: DistSegment[] = COUNTED_LEVELS.map((key) => ({ key, label: RISK[key].label, n: c[key], color: RISK[key].solid }))
    .filter((d) => d.n > 0)
    .map((d, index) => ({ ...d, index }));

  const cards: KpiCard[] = [
    {
      key: 'findings',
      label: '탐지 항목',
      num: c.total,
      unit: '건',
      after: '',
      /* '높음 3 · 보통 11 · 낮음 9' — 등급 라벨은 ② RISK */
      sub: COUNTED_LEVELS.map((k) => RISK[k].label + ' ' + c[k]).join(' · '),
      warn: false,
    },
    {
      key: 'reviewed',
      label: '담당자 확인',
      num: c.reviewed,
      unit: '',
      after: '/ ' + c.total,
      /* '오탐 1 · 분류 수정 1' — 확인 상태 라벨은 ② FSTATUS */
      sub: FSTATUS.false_positive.label + ' ' + c.fp + ' · ' + FSTATUS.reclassified.label + ' ' + c.recl,
      warn: false,
    },
    {
      key: 'remaining',
      label: '남은 검토사항',
      num: openI.length,
      unit: '건',
      after: '',
      sub: '전체 ' + a.items.length + '건 중 해결 ' + (a.items.length - openI.length) + '건',
      warn: openI.length > 0,
    },
    {
      key: 'links',
      label: '문서 간 연결',
      num: a.links.length,
      unit: '건',
      after: '',
      sub: a.links.length ? (linksCheck ? '확인 필요 ' + linksCheck + '건' : '모두 확인 · 판단 완료') : '찾은 연결 없음',
      warn: false,
    },
  ];

  return {
    code: a.code,
    name: a.name,
    risk: a.risk,
    status: a.status,
    review: a.review,
    completedText: a.review === 'done' ? a.reviewer + ' · ' + fmtDT(a.reviewedAt) : '검토 진행 중 (완료 전)',
    notDone: a.review !== 'done',
    cards,
    dist,
    distAria: '위험등급별 탐지 분포: ' + (dist.length ? dist.map((d) => d.label + ' ' + d.n + '건').join(', ') : '탐지 없음'),
    nFind: c.total,
    reasons: a.riskReasons.slice(),
    noReasonsText: a.status === 'failed' ? '분석에 실패해 위험 사유를 판단하지 못했습니다.' : '분석이 끝나면 위험 사유가 표시됩니다.',
    limits: a.limits || '',
    docs: docs.map((d) => {
      const fl = f.filter((x) => x.docId === d.id);
      const oi = a.items.filter((i) => i.docId === d.id && !i.resolved).length;
      const nh = fl.filter((x) => x.risk === 'high').length;
      const pc = d.pageCount || (d.pages ? d.pages.length : 0);
      const ok = d.status === 'done';
      const st = analysisStatusView(d.status);
      return {
        id: d.id,
        title: d.title || d.name,
        file: d.name,
        meta: d.ext + ' · ' + (pc ? pc + '페이지' : '페이지 확인 불가'),
        statusLabel: st.label,
        statusFg: st.fg,
        nFind: ok ? fl.length : '-',
        nHigh: ok ? nh : '-',
        highOn: nh > 0,
        reviewed: ok ? fl.filter((x) => x.status !== 'open').length + '/' + fl.length : '-',
        open: oi,
      };
    }),
    cats,
    findings: f
      .slice()
      .sort((x, y) => (x.id < y.id ? -1 : 1))
      .map((x) => ({
        id: x.id,
        cat: x.cat,
        masked: x.masked,
        subject: x.subject,
        where: docT(x.docId) + ' ' + x.page + '쪽',
        risk: riskView(x.risk),
        status: FSTATUS[x.status],
        falsePositive: x.status === 'false_positive',
      })),
    remaining: openI.map((i) => ({ id: i.id, type: RTYPE[i.type].label, title: i.title, where: docT(i.docId) + ' ' + i.page + '쪽', next: i.next })),
    recs: a.recs.slice(),
    memo: a.memo || '작성한 검토 메모가 없습니다.',
    hasMemo: !!a.memo,
    completionNote: a.completionNote || '',
    changes,
    history: a.history.map((h) => {
      const known = hasOwn(HKIND, h.kind);
      return {
        id: h.id,
        at: fmtDT(h.at),
        actor: h.actor,
        kind: known ? HKIND[h.kind] : String(h.kind),
        kindFg: known ? HISTORY_FG[h.kind] : 'var(--ink)',
        dot: known ? HISTORY_DOT[h.kind] : 'var(--na-solid)',
        target: h.target,
        change: h.change,
        reason: h.reason || '-',
      };
    }),
  };
}
