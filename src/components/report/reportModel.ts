/* ==========================================================================
   보고서 화면 모델 — 프로토타입 reportVM(Main.dc.html 2329–2376) 을 순수 함수로 옮겼다.
   - 위험등급·근거·라벨은 서비스 값과 ② 표시 규칙 그대로다(화면에서 다시 판정하지 않는다).
   - 민감한 값은 마스킹된 표시값(masked)만 쓴다. 원문 위치 조각(Highlight.x)은 보고서에 넣지 않는다.
   - 휴대폰 배치(요약 카드 구분선 등)는 CSS 가 맡는다. 여기에는 폭과 상관없는 값만 둔다.
   - 실제 분석(Analysis.raw 가 있음 — 화면은 원문 값을 지운 안전한 사본을 넘긴다)도 데모와 같은 구역 01~08 · 대상 문서 표의
     '남은 검토사항' 열 · '남아 있는 검토사항' 구역(서버가 계산한 검토사항 중 미해결)을 쓴다. 다른 점(데모 값은 그대로):
     요약 카드 3장(탐지 항목 · 담당자 확인 · 남은 검토사항 — 문서 간 연결이 0개면 '문서 간 연결' 카드를 뺀다(옛 워크플로우),
     있으면(최종 흐름 워크플로우) 데모와 같은 4장, 미평가가 있으면 탐지 항목
     아랫줄에 ' · 미평가 n'), 위험등급별 탐지 분포 막대의 마지막 '미평가' 조각(1건 이상일 때 — 데모 막대는 높음 · 보통 · 낮음만),
     정보 종류별 표의 '미평가' 열(1건 이상일 때), 전체 탐지 항목은 서류 순번 → 서류 안 순번의 숫자 순
     (D2-01 이 D10-01 앞), 빈 위험 사유 · 권장 조치는 '-', 꼬리말 한 문장.
   - 수정 표의 수정 시각 = 이력 대상(target)이 항목 번호와 같거나 '번호 + 공백'으로 시작하는 마지막 오탐 · 분류 수정 줄
     (D1-10 이 'D1-100 …' 줄을 잡지 않게).
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
import { CONFIG } from '@/config/app';
import { fmtDT } from '@/lib/format';
import { isLiveAnalysis } from '@/services/report-safe';
import type { Analysis, Finding } from '@/services/types';

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

/** 실제 분석의 분포 막대 등급 — 높음 · 보통 · 낮음 뒤 마지막에 미평가(워크플로우가 등급을 주지 않은 항목) */
const LIVE_DIST_LEVELS = [...COUNTED_LEVELS, 'unrated'] as const satisfies readonly RiskLevel[];

/** 꼬리말 — 마스킹 안내(두 모드 공통 문장) */
export const FOOTER_MASKED = '민감한 값은 마스킹해 표시했습니다. 원문 값은 보고서와 내보내기 파일에 포함하지 않습니다.';

/** 실제 분석 화면 번호 'D<서류 순번>-<서류 안 순번>' */
const LIVE_NUMBER = /^D(\d+)-(\d+)$/;

/** 실제 분석 탐지 항목 순서 — 서류 순번 → 서류 안 순번(숫자). 번호 꼴이 아니면 뒤에 글자 순 */
function liveOrder(x: Finding, y: Finding): number {
  const a = LIVE_NUMBER.exec(x.id);
  const b = LIVE_NUMBER.exec(y.id);
  if (a && b) return Number(a[1]) - Number(b[1]) || Number(a[2]) - Number(b[2]);
  if (a) return -1;
  if (b) return 1;
  return x.id < y.id ? -1 : x.id > y.id ? 1 : 0;
}

/** 이력 대상이 그 탐지 항목 번호의 줄인지 — 번호와 같거나 '번호 + 공백'으로 시작 */
export function targetsFinding(target: unknown, id: string): boolean {
  const t = String(target);
  return t === id || t.startsWith(id + ' ');
}

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

/** 위험등급별 탐지 분포 막대 한 조각 — 0건 조각은 없다. 'unrated' 는 실제 분석에만(마지막 조각) */
export interface DistSegment {
  key: 'high' | 'medium' | 'low' | 'unrated';
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
  /** 미평가 수(실제 분석 표에서만 열로 보인다 — catUnratedCol) */
  unrated: number;
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

/** 구역 번호 — 데모 · 실제 분석 같다(01~08) */
export interface ReportSections {
  summary: number;
  reasons: number;
  docs: number;
  findings: number;
  remaining: number;
  recs: number;
  memo: number;
  history: number;
}

const SECTIONS: ReportSections = { summary: 1, reasons: 2, docs: 3, findings: 4, remaining: 5, recs: 6, memo: 7, history: 8 };

export interface ReportView {
  /** 실제 분석 보고서인지 */
  live: boolean;
  sections: ReportSections;
  /** 내보내기 모달의 JSON 설명을 실제 분석 문구(문서 간 연결 없음)로 — 실제 분석이고 연결이 0개일 때 */
  liveJsonDesc: boolean;
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
  /** 대상 문서 표에 '남은 검토사항' 열을 보이는지(데모 · 실제 분석 모두) */
  docOpenCol: boolean;
  cats: CatRow[];
  /** 정보 종류별 표에 '미평가' 열을 보이는지(실제 분석 · 미평가 1건 이상) */
  catUnratedCol: boolean;
  findings: FindingLine[];
  remaining: RemainingLine[];
  recs: string[];
  /** 권장 조치가 없을 때 */
  noRecsText: string;
  /** 꼬리말 문장들 */
  footer: string[];
  /** 메모 글자(없으면 안내 문구) */
  memo: string;
  hasMemo: boolean;
  completionNote: string;
  changes: ChangeLine[];
  history: HistoryLine[];
}

/** 분석 건 → 보고서 화면 값 (원본 reportVM) */
export function reportView(a: Analysis): ReportView {
  const live = isLiveAnalysis(a);
  const f = a.findings;
  const docs = a.docs;
  const by = (fn: (x: (typeof f)[number]) => boolean) => f.filter(fn).length;
  const c = {
    total: f.length,
    high: by((x) => x.risk === 'high'),
    medium: by((x) => x.risk === 'medium'),
    low: by((x) => x.risk === 'low'),
    unrated: by((x) => x.risk === 'unrated'),
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
      unrated: l.filter((x) => x.risk === 'unrated').length,
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
        .find((e) => (e.kind === 'fp' || e.kind === 'reclass') && targetsFinding(e.target, x.id));
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

  /* 데모는 높음 · 보통 · 낮음만, 실제 분석은 미평가도 마지막 조각으로(0건 조각은 빼고 index 는 남은 조각 차례) */
  const distLevels: readonly DistSegment['key'][] = live ? LIVE_DIST_LEVELS : COUNTED_LEVELS;
  const dist: DistSegment[] = distLevels
    .map((key) => ({ key, label: RISK[key].label, n: c[key], color: RISK[key].solid }))
    .filter((d) => d.n > 0)
    .map((d, index) => ({ ...d, index }));

  const cards: KpiCard[] = [
    {
      key: 'findings',
      label: '탐지 항목',
      num: c.total,
      unit: '건',
      after: '',
      /* '높음 3 · 보통 11 · 낮음 9' — 등급 라벨은 ② RISK. 실제 분석은 미평가가 있으면 ' · 미평가 n' 을 덧붙인다 */
      sub: COUNTED_LEVELS.map((k) => RISK[k].label + ' ' + c[k]).join(' · ') + (live && c.unrated > 0 ? ' · ' + RISK.unrated.label + ' ' + c.unrated : ''),
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
    live,
    sections: { ...SECTIONS },
    code: a.code,
    name: a.name,
    risk: a.risk,
    status: a.status,
    review: a.review,
    completedText: a.review === 'done' ? a.reviewer + ' · ' + fmtDT(a.reviewedAt) : '검토 진행 중 (완료 전)',
    notDone: a.review !== 'done',
    /* 실제 분석은 문서 간 연결(최종 흐름 워크플로우의 서류 대조)이 있을 때만 그 카드 — 없으면 세 장만 */
    cards: live && a.links.length === 0 ? cards.filter((k) => k.key !== 'links') : cards,
    liveJsonDesc: live && a.links.length === 0,
    dist,
    distAria: '위험등급별 탐지 분포: ' + (dist.length ? dist.map((d) => d.label + ' ' + d.n + '건').join(', ') : '탐지 없음'),
    nFind: c.total,
    reasons: a.riskReasons.slice(),
    noReasonsText: live ? '-' : a.status === 'failed' ? '분석에 실패해 위험 사유를 판단하지 못했습니다.' : '분석이 끝나면 위험 사유가 표시됩니다.',
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
    docOpenCol: true,
    cats,
    catUnratedCol: live && c.unrated > 0,
    findings: f
      .slice()
      .sort(live ? liveOrder : (x, y) => (x.id < y.id ? -1 : 1))
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
    noRecsText: live ? '-' : '분석이 끝나면 권장 조치가 표시됩니다.',
    footer: live
      ? [FOOTER_MASKED]
      : [
          '이 보고서는 ' + CONFIG.brandName + ' 데모 환경에서 만든 예시입니다. 위험 규칙 ID와 위험 기준은 데모용이며, 실측 정확도나 공식 인증 결과가 아닙니다.',
          FOOTER_MASKED,
        ],
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
