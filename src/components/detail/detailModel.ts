/* ==========================================================================
   상세 검토 화면 모델(순수 함수) — 원본 Main.dc.html 화면 모델
   bannerVM(2036) · docVM(2045) · findingVM(2059) · itemVM(2094) · linkVM(2114) · placeholderVM(2131) · detailVM(2139–2328),
   collectAnchors(1459).
   - 문구는 프로토타입 그대로. 라벨·아이콘·위험 색은 ② 표시 규칙에서만 가져온다.
   - 위험등급·판단 근거는 서비스 값을 그대로 쓰고 여기서 계산하지 않는다(건수 세기·정렬만 한다).
   - 화면 색은 되도록 상태 표시(flag)로 넘기고 CSS 모듈이 토큰으로 칠한다. 원문 하이라이트처럼
     항목마다 색이 바뀌는 곳만 ② 의 CSS 변수 값(var(--hi-soft) 등)을 넘긴다.
   - 행동(누름)은 담지 않는다. 화면 조각이 useDetailUi(선택·이동)와 DetailActions(T7 검토 동작)를 부른다.
   - 실제 분석(Analysis.raw 가 있음 — API 서비스만 채운다, DetailFacts.live)도 데모처럼 검토 동작을 쓴다. 다른 점:
     결과 탭은 탐지 항목 · 검토 필요 · (문서 간 연결 — 1개 이상일 때만, 판단 버튼 · 설명 줄 없는 읽기 전용) · 분석 요약,
     원문은 블록 대신 원본 파일 쪽(live — 파일 기준 쪽 ·
     위치 상자)을 그린다. 검토사항(서버가 계산한 result.items)의 근거는 위치 상자 id 를 가리키므로 데모와 같은 규칙으로
     그 상자를 검토사항 색으로 강조하고 이름표를 단다 — 지금 쪽에 근거 상자가 없으면 원문 보기 안 item 안내(제목 'R-0n · 종류',
     글 = 할 일). 검토사항이 없을 때 빈 화면은 제목만(데모의 설명 줄은 실제 분석이 만들지 않는 종류를 말해서 뺀다).
     검토 완료 띠의 '보고서 보기'는 데모와 같다(실제 분석 보고서 — 보고서 화면이 reportGate 로 가른다).
     검토 기록을 불러오지 못한 실제 분석(raw.reviewable false)은 readOnly — 검토 동작 버튼(해결 · 다시 열기 포함)만 막는다
     (검토 완료 버튼 title 만 '검토 기록을 불러오지 못했습니다'). 데모 분석에는 raw 가 없어 값이 전과 같다.
   ========================================================================== */

import {
  analysisStatusView,
  byRisk,
  findingNotes,
  FSTATUS,
  LSTATUS,
  riskView,
  RTYPE,
  ruleName,
  type AnalysisStatusView,
  type FindingStatusView,
  type LinkStatusView,
  type RiskView,
} from '@/display/rules';
import type { IconName } from '@/display/icon-names';
import { clamp, fmtDT, fmtSize } from '@/lib/format';
import type { Analysis, AnalysisDoc, DocLink, Finding, PageBlock, ReviewItem, Segment, TextValue } from '@/services/types';
import { DETAIL_TABS, LIVE_DETAIL_TABS, LIVE_LINK_TABS, focusAnchors, focusKey, passesFilter, type DetailFocus, type DetailTab, type DetailUiState, type FindingFilter, type MobileTab } from './detailState';
import { FILE_FAILED, filePageOf, guideText, liveDocMeta, pageMissingText } from './liveViewerModel';

/** 검토 기록을 불러오지 못한 실제 분석 — 막힌 '검토 완료' 버튼의 title */
export const REVIEW_UNAVAILABLE_TITLE = '검토 기록을 불러오지 못했습니다';

/* ---------- 원문 위치 모으기 ---------- */

/** 블록 목록 안 원문 위치 ID 를 나오는 순서대로 모은다(원본 collectAnchors) */
export function collectAnchors(blocks: readonly PageBlock[] | null | undefined): string[] {
  const out: string[] = [];
  const walk = (v: TextValue | Segment | null | undefined): void => {
    if (!v) return;
    if (Array.isArray(v)) {
      v.forEach(walk);
      return;
    }
    if (typeof v === 'object' && v.a && typeof v.x === 'string') out.push(v.a);
  };
  (blocks || []).forEach((b) => {
    if (b.t === 'blur' || b.t === 'cut') {
      out.push(b.a);
      return;
    }
    if (b.t === 'kv') b.items.forEach((it) => walk(it[1]));
    if (b.t === 'sign') b.items.forEach((it) => walk(it[1]));
    if (b.t === 'table') b.rows.forEach((r) => r.forEach(walk));
    if (b.t === 'p') walk(b.text);
    if (b.t === 'stamp') b.lines.forEach(walk);
    if (b.t === 'foot') walk(b.left);
  });
  return out;
}

/* ---------- 공통 사실 ---------- */

/** 문서의 쪽 수(원본 d.pageCount || pages.length) */
export function docPageCount(d: AnalysisDoc | null | undefined): number {
  if (!d) return 0;
  return d.pageCount || (d.pages ? d.pages.length : 0);
}

/** 문서 화면 이름(원본 d.title || d.name) */
export function docName(d: AnalysisDoc | null | undefined): string {
  return d ? d.title || d.name : '';
}

/** 화면 전체가 같이 쓰는 값(원본 detailVM 머리 부분) */
export interface DetailFacts {
  /** 지금 원문 뷰어의 문서 */
  doc: AnalysisDoc | null;
  /** 결과가 있다(분석이 끝났거나 · 일부 실패 · 다시 분석 중) */
  hasResults: boolean;
  /** 결과를 기다린다(대기 · 분석 중이고 결과 없음) */
  waiting: boolean;
  /** 검토 완료 — 검토 동작을 막는다 */
  locked: boolean;
  /** 대기 · 분석 중 */
  notReady: boolean;
  /** 확인한(미확인이 아닌) 탐지 항목 수 */
  reviewed: number;
  /** 오탐 수 */
  fpN: number;
  /** 미해결 검토사항 수 */
  openItems: number;
  /** 전체 쪽 수 */
  pageTotal: number;
  nFailDocs: number;
  nDoneDocs: number;
  /** 실제 분석(Analysis.raw 가 있음) — 결과 탭 · 검토 완료 띠가 데모와 다르다 */
  live: boolean;
  /** 실제 분석인데 검토 기록을 불러오지 못함 — 검토 동작 버튼을 막는다 */
  readOnly: boolean;
}

export function detailFacts(a: Analysis, s: Pick<DetailUiState, 'docId'>): DetailFacts {
  const docs = a.docs;
  const hasResults = !!a.analyzedAt && (a.status === 'done' || a.status === 'partial' || !!a.retrying);
  return {
    doc: docs.find((d) => d.id === s.docId) || docs[0] || null,
    hasResults,
    waiting: !hasResults && (a.status === 'queued' || a.status === 'running'),
    locked: a.review === 'done',
    notReady: a.status === 'queued' || a.status === 'running',
    reviewed: a.findings.filter((f) => f.status !== 'open').length,
    fpN: a.findings.filter((f) => f.status === 'false_positive').length,
    openItems: a.items.filter((i) => !i.resolved).length,
    pageTotal: docs.reduce((n, d) => n + docPageCount(d), 0),
    nFailDocs: docs.filter((d) => d.status === 'failed').length,
    nDoneDocs: docs.filter((d) => d.status === 'done').length,
    live: !!a.raw,
    readOnly: !!a.raw && !a.raw.reviewable,
  };
}

/* ---------- 머리글 ---------- */

export interface HeaderModel {
  name: string;
  code: string;
  date: string;
  docCount: number;
  /** '5페이지' · '페이지 수 확인 전' */
  pageTotalText: string;
  risk: string;
  status: string;
  review: string;
  /** 탐지 확인 진행 막대 */
  hasProgress: boolean;
  progress: { reviewed: number; total: number; fp: number; open: number; pct: number };
  /** '검토 완료' 버튼(완료 전) · '검토 다시 열기' 버튼(완료 후) */
  showComplete: boolean;
  showReopen: boolean;
  noComplete: boolean;
  completeTitle: string;
  /** '결과 보고서' 를 열 수 없음(결과를 기다리는 중) */
  noReport: boolean;
  reportTitle: string;
  /** 실제 분석인데 검토 기록을 불러오지 못함 — 검토 완료를 막는다 */
  readOnly: boolean;
}

export function headerModel(a: Analysis, x: DetailFacts): HeaderModel {
  const total = a.findings.length;
  return {
    name: a.name,
    code: a.code,
    date: fmtDT(a.submittedAt),
    docCount: a.docs.length,
    pageTotalText: x.pageTotal ? x.pageTotal + '페이지' : '페이지 수 확인 전',
    risk: a.risk,
    status: a.status,
    review: a.review,
    hasProgress: x.hasResults && total > 0,
    progress: { reviewed: x.reviewed, total, fp: x.fpN, open: x.openItems, pct: total ? Math.round((x.reviewed / total) * 1000) / 10 : 0 },
    showComplete: !x.locked,
    showReopen: x.locked,
    noComplete: (x.notReady && !a.retrying) || x.readOnly,
    completeTitle: x.readOnly ? REVIEW_UNAVAILABLE_TITLE : x.notReady ? '분석이 끝난 뒤 검토를 완료할 수 있습니다' : '검토를 마치고 결과를 기록합니다',
    noReport: x.waiting,
    reportTitle: x.waiting ? '분석이 끝나면 보고서를 볼 수 있습니다' : '검토 결과 보고서를 엽니다',
    readOnly: x.readOnly,
  };
}

/* ---------- 상태 띠 ---------- */

/** 띠 안 행동 — 화면이 누름을 붙인다 */
export type BannerActionKey = 'trySample' | 'showFailedDoc' | 'retryFailed' | 'openReport';

export interface BannerModel {
  variant: 'running' | 'info' | 'partial' | 'done';
  icon?: IconName;
  title: string;
  text: string;
  actions: { key: BannerActionKey; label: string; disabled: boolean }[];
}

/** 화면 위 띠(원본 bannerVM) — 보이지 않으면 null */
export function bannerModel(a: Analysis, x: DetailFacts): BannerModel | null {
  if (a.retrying) return { variant: 'running', title: '실패한 문서를 다시 분석하고 있습니다.', text: '기존 결과와 위험등급은 그대로 유지합니다.', actions: [] };
  if (a.status === 'running')
    return {
      variant: 'running',
      title: '분석 중입니다 · 문서 ' + a.docs.length + '개 중 ' + x.nDoneDocs + '개 완료',
      text: '정확한 진행률은 알 수 없어 표시하지 않습니다. 이 화면을 떠나도 분석은 계속됩니다.',
      actions: [],
    };
  if (a.status === 'queued')
    return {
      variant: 'info',
      icon: 'dg-i-clock',
      title: '분석 대기 중입니다.',
      text: a.demoQueued
        ? '데모 환경에서는 직접 올린 파일을 분석하지 않아 이 상태로 남습니다. 실제 서비스에서는 접수 순서대로 분석이 시작됩니다.'
        : '접수 순서에 따라 곧 분석이 시작됩니다.',
      actions: a.demoQueued ? [{ key: 'trySample', label: '샘플 문서로 체험하기', disabled: false }] : [],
    };
  if (a.status === 'partial')
    return {
      variant: 'partial',
      icon: 'dg-i-alert',
      title: '문서 ' + a.docs.length + '개 중 ' + x.nFailDocs + '개를 분석하지 못했습니다.',
      text: '결과는 분석된 문서 기준이며, 이미 발견한 고위험 정보는 실패한 문서와 관계없이 그대로 표시합니다.',
      actions: [
        { key: 'showFailedDoc', label: '실패 문서 보기', disabled: false },
        { key: 'retryFailed', label: '실패 문서 다시 분석', disabled: !!a.retrying },
      ],
    };
  if (a.review === 'done')
    return {
      variant: 'done',
      icon: 'dg-i-check-badge',
      title: '검토 완료 · ' + a.reviewer + ' · ' + fmtDT(a.reviewedAt),
      text: '위험등급과 최초 탐지 결과는 검토 완료 후에도 그대로 유지됩니다.',
      actions: [{ key: 'openReport', label: '보고서 보기', disabled: false }],
    };
  return null;
}

/* ---------- 문서 목록 ---------- */

export interface DocModel {
  id: string;
  /** 1부터 */
  idx: number;
  title: string;
  file: string;
  ext: string;
  /** '2페이지 · 1.2MB' */
  meta: string;
  status: AnalysisStatusView & { readonly still: boolean };
  /** 탐지 건수 표시(결과가 있고 문서가 완료) */
  hasCount: boolean;
  nFind: number;
  hasHigh: boolean;
  nHigh: number;
  cur: boolean;
  /** 접힌 레일 버튼 이름 */
  railLabel: string;
}

/** 문서 목록 한 줄(원본 docVM) */
export function docModels(a: Analysis, x: DetailFacts): DocModel[] {
  return a.docs.map((d, i) => {
    const st = analysisStatusView(d.status);
    const nFind = a.findings.filter((f) => f.docId === d.id).length;
    const nHigh = a.findings.filter((f) => f.docId === d.id && f.risk === 'high').length;
    const pc = docPageCount(d);
    const done = x.hasResults && d.status === 'done';
    return {
      id: d.id,
      idx: i + 1,
      title: docName(d),
      file: d.name,
      ext: d.ext,
      // 실제 분석 서류는 묶음 파일 안 쪽 범위(파일 크기는 서류마다 보이지 않는다)
      meta: d.source ? liveDocMeta(d.source) : (pc ? pc + '페이지 · ' : '') + fmtSize(d.size),
      status: st,
      hasCount: done,
      nFind,
      hasHigh: done && nHigh > 0,
      nHigh,
      cur: !!x.doc && d.id === x.doc.id,
      railLabel: i + 1 + '번 문서 ' + docName(d) + ', ' + st.label,
    };
  });
}

/* ---------- 원문 뷰어 ---------- */

/** 고른 위치의 색(원본 fColor · fSoft · fTagBg · fHalo) — ② 위험 색 또는 토큰 이름 */
export interface FocusTone {
  /** 테두리(링) */
  line: string;
  /** 고른 위치 바탕 */
  bg: string;
  /** 이름표 바탕 */
  tag: string;
  /** 퍼지는 신호 */
  halo: string;
}

/** 고른 대상이 없거나 연결일 때 — 강조색 */
const ACCENT_TONE: FocusTone = { line: 'var(--accent)', bg: 'var(--accent-soft-2)', tag: 'var(--accent-ink)', halo: 'var(--accent-halo)' };
/** 검토사항(주황) */
const ITEM_TONE: FocusTone = { line: 'var(--warn-solid)', bg: 'var(--warn-focus)', tag: 'var(--warn)', halo: 'var(--warn-halo)' };

/** 하이라이트 한 조각의 색 — CSS 변수로 넘긴다 */
export interface HighlightVars {
  /** 평소 바탕 · 밑줄(② RISK soft · solid) */
  soft: string;
  solid: string;
  /** 고른 때 바탕 · 테두리 · 퍼짐 */
  onBg: string;
  pc: string;
  ph: string;
}

export type SegmentModel =
  | { kind: 'plain'; text: string }
  /** 탐지 위치 — 누르면 그 탐지 항목을 고른다(진짜 버튼) */
  | { kind: 'hl'; anchor: string; findingId: string; text: string; shown: string; aria: string; on: boolean; fp: boolean; tag: boolean; vars: HighlightVars }
  /** 탐지 항목이 아닌 고른 위치(검토사항 근거 · 연결 근거) — 표시만 */
  | { kind: 'mark'; anchor: string; text: string; tag: boolean; vars: HighlightVars };

export type BlockModel =
  | { t: 'bar'; left: string; right: string }
  | { t: 'title'; text: string; sub: string }
  | { t: 'sec'; text: string }
  | { t: 'kv'; cols: 2 | 3; items: { k: string; segs: SegmentModel[]; span: number }[] }
  | { t: 'table'; head: { text: string; align: CellAlignName }[]; rows: { segs: SegmentModel[]; align: CellAlignName }[][] }
  | { t: 'p'; small: boolean; segs: SegmentModel[] }
  | { t: 'checks'; items: { on: boolean; text: string }[] }
  | { t: 'sign'; date: string; items: { k: string; segs: SegmentModel[]; suffix: string }[] }
  | { t: 'stamp'; lines: SegmentModel[][] }
  | { t: 'blur'; anchor: string; label: string; lines: string[]; on: boolean; tag: boolean; vars: HighlightVars }
  | { t: 'cut'; anchor: string; label: string; ghost: string; on: boolean; tag: boolean; vars: HighlightVars }
  | { t: 'foot'; segs: SegmentModel[]; right: string };

export type CellAlignName = 'left' | 'right' | 'center';

export interface NoticeModel {
  tone: 'warn' | 'accent' | 'run';
  icon: IconName;
  title: string;
  text: string;
  /** 여러 줄 글(줄바꿈을 지킨다 — 기타 서류 안내) */
  pre?: boolean;
}

export type PlaceholderActionKey = 'trySample' | 'retryDoc' | 'retryFile';

/** 미리보기 대신 보이는 화면(원본 placeholderVM) */
export interface PlaceholderModel {
  tone: 'neutral' | 'err' | 'run';
  spin: boolean;
  icon: IconName;
  title: string;
  text: string;
  skeleton: boolean;
  action: { key: PlaceholderActionKey; label: string; icon: IconName; disabled: boolean } | null;
  note: string;
}

export function placeholderModel(a: Analysis, doc: AnalysisDoc | null, hasPage: boolean): PlaceholderModel | null {
  if (hasPage || !doc) return null;
  const base: PlaceholderModel = { tone: 'neutral', spin: false, icon: 'dg-i-file', title: '', text: '', skeleton: false, action: null, note: '' };
  if (a.demoQueued)
    return {
      ...base,
      title: '미리보기를 표시할 수 없습니다',
      text: '데모 환경에서는 직접 올린 파일을 열거나 분석하지 않습니다. 준비된 샘플 문서로 전체 과정을 체험해 보세요.',
      action: { key: 'trySample', label: '샘플 문서로 체험하기', icon: 'dg-i-play', disabled: false },
    };
  if (doc.status === 'failed')
    return {
      ...base,
      tone: 'err',
      icon: 'dg-i-x-circle',
      title: '이 문서는 분석하지 못했습니다',
      text: doc.error || '파일을 처리하지 못했습니다.',
      action: { key: 'retryDoc', label: a.retrying ? '다시 분석하는 중…' : '이 문서 다시 분석', icon: 'dg-i-refresh', disabled: !!a.retrying },
      note: '다시 스캔한 파일은 새 분석으로 올려 주세요.',
    };
  if (doc.status === 'running')
    return {
      ...base,
      tone: 'run',
      spin: true,
      title: '원문 미리보기를 준비하고 있습니다',
      text: '이 문서를 분석하고 있습니다. 분석이 끝나면 원문과 탐지 위치를 함께 표시합니다.',
      skeleton: true,
    };
  return { ...base, icon: 'dg-i-clock', title: '분석 대기 중인 문서입니다', text: '앞 문서의 분석이 끝나면 이어서 분석합니다.', skeleton: true };
}

/**
 * 실제 분석 원문 자리 — 원본 파일 상태(받는 중 · 실패 · 준비됨)와 지금 서류의 파일 기준 쪽으로 정한다.
 * 받는 중 · 실패면 그 화면, 준비됐지만 그 쪽이 파일에 없으면 안내, 그 밖(그릴 수 있음)은 null.
 */
export function liveFilePlaceholder(
  file: { status: 'loading' } | { status: 'error'; message: string } | { status: 'ready'; pageCount: number },
  filePage: number,
): PlaceholderModel | null {
  if (file.status !== 'ready') return filePlaceholder(file);
  if (filePage >= 1 && filePage <= file.pageCount) return null;
  return {
    tone: 'err',
    spin: false,
    icon: 'dg-i-x-circle',
    title: '원문을 표시하지 못했습니다',
    text: pageMissingText(filePage, file.pageCount),
    skeleton: false,
    action: null,
    note: '탐지 항목 · 분석 요약은 결과 패널에서 그대로 볼 수 있습니다.',
  };
}

/** 실제 분석 원본 파일을 받는 중 · 실패했을 때 원문 자리 화면 */
export function filePlaceholder(file: { status: 'loading' } | { status: 'error'; message: string }): PlaceholderModel {
  if (file.status === 'loading')
    return {
      tone: 'run',
      spin: true,
      icon: 'dg-i-file',
      title: '원본 파일을 받고 있습니다',
      text: '올린 파일을 받아 이 서류의 쪽을 그립니다. 그동안 결과 패널은 그대로 쓸 수 있습니다.',
      skeleton: true,
      action: null,
      note: '',
    };
  return {
    tone: 'err',
    spin: false,
    icon: 'dg-i-x-circle',
    title: '원문을 표시하지 못했습니다',
    text: file.message || FILE_FAILED,
    skeleton: false,
    action: { key: 'retryFile', label: '다시 시도', icon: 'dg-i-refresh', disabled: false },
    note: '탐지 항목 · 분석 요약은 결과 패널에서 그대로 볼 수 있습니다.',
  };
}

/** 원문 뷰어 크기 — 실행 중에 잰 값 */
export interface ViewerMetrics {
  /** 뷰어 스크롤 영역 폭(px) */
  width: number;
  /** 뷰어 좌우 안쪽 여백(px) */
  padX: number;
  /** 종이 폭(px) — --paper-w */
  paperW: number;
}

/** 화면 맞춤 배율(원본 fitZ: (뷰어 폭 - 여백×2 - 6) ÷ 종이 폭, 0.35~1.5) */
export function fitZoom(m: ViewerMetrics): number {
  if (!m.paperW) return 1;
  return clamp((m.width - m.padX * 2 - 6) / m.paperW, 0.35, 1.5);
}

/** 도구 줄이 줄어드는 뷰어 폭(원본 vCompact: 700px 미만) */
export const VIEWER_COMPACT_MAX = 700;

export interface ViewerModel {
  doc: AnalysisDoc | null;
  docName: string;
  page: number;
  pageCount: number;
  /** '1 / 2' · '- / -' */
  pageLabel: string;
  hasPage: boolean;
  /** 탐지 위치를 표시한다(결과가 있고 문서 완료) */
  showFind: boolean;
  noPrev: boolean;
  noNext: boolean;
  /** 실제 배율(맞춤이면 계산값) */
  zoom: number;
  zoomLabel: string;
  noOut: boolean;
  noIn: boolean;
  isFit: boolean;
  noPage: boolean;
  /** 마스킹 미리보기 켬(스위치 상태) */
  mask: boolean;
  noMask: boolean;
  notices: NoticeModel[];
  pageAria: string;
  scan: boolean;
  blocks: BlockModel[];
  /** 고른 위치 이름표(한 쪽에 하나 — 처음 나오는 위치) */
  tag: { text: string; bg: string };
  placeholder: PlaceholderModel | null;
  /** 쪽이 바뀌었는지 알아보는 서명(dg-page-a/b) */
  pageKey: string;
  /** 선택 신호 서명(dg-ring-a/b) */
  ringKey: string;
  /** 실제 분석 서류 — 원본 파일 쪽과 위치 상자(데모 문서는 null) */
  live: LiveViewerModel | null;
}

/** 실제 분석 원문 쪽 */
export interface LiveViewerModel {
  /** 파일 기준 쪽(1부터) = source.pageStart + (뷰어 쪽 − 1) */
  filePage: number;
  /** 기타 서류 */
  other: boolean;
  /** 지금 쪽에 있는 이 서류의 위치 상자(탐지 항목 순서 · 항목 안 상자 순서) */
  boxes: LiveBoxModel[];
}

/** 위치 상자 하나 — 누르면 그 탐지 항목을 고른다(진짜 버튼) */
export interface LiveBoxModel {
  /** 위치 ID(data-anchor) */
  anchor: string;
  findingId: string;
  /** 쪽 크기에 대한 0~1 비율 꼭짓점 — 화면이 px 사각형으로 바꾼다(src/lib/pageBox.ts) */
  points: { x: number; y: number }[];
  aria: string;
  /** 고른 항목의 상자 */
  on: boolean;
  /** 고른 위치 이름표를 이 상자 위에 */
  tag: boolean;
  /** 마스킹 미리보기 — 검은 상자로 가린다 */
  masked: boolean;
  vars: HighlightVars;
}

const align = (x: string | undefined): CellAlignName => (x === 'r' ? 'right' : x === 'c' ? 'center' : 'left');

/** 원문 뷰어(원본 detailVM 의 '원문 뷰어' 부분) */
export function viewerModel(a: Analysis, s: DetailUiState, x: DetailFacts, metrics: ViewerMetrics): ViewerModel {
  const doc = x.doc;
  const fAll = a.findings;
  const focus = s.focus;
  const pages = doc ? doc.pages : null;
  const pc = docPageCount(doc);
  const page = clamp(s.page || 1, 1, Math.max(1, pc));
  const source = doc ? doc.source : undefined;
  // 실제 분석 서류는 블록 대신 원본 파일 쪽을 그린다 — 완료된 서류면 쪽이 있다
  const hasPage = source ? !!doc && doc.status === 'done' && pc > 0 : !!(doc && pages && pages[page - 1]) && !a.demoQueued;
  const showFind = x.hasResults && !!doc && doc.status === 'done';
  const z = Math.round((s.zoom == null ? fitZoom(metrics) : s.zoom) * 100) / 100;

  const anchorF: Record<string, Finding> = {};
  if (showFind) fAll.forEach((f) => f.anchors.forEach((an) => (anchorF[an] = f)));
  const fset = new Set(focusAnchors(a, focus));
  const pageBlocks = hasPage && pages ? pages[page - 1] : [];
  // 지금 쪽에 있는 이 서류의 위치 상자(실제 분석) — 위치 없는 항목(boxes [])은 빠진다
  const liveBoxSrc =
    source && hasPage && showFind && doc
      ? fAll.filter((f) => f.docId === doc.id && f.page === page).flatMap((f) => (f.boxes ?? []).map((b) => ({ f, b })))
      : [];
  const first = (source ? liveBoxSrc.map((x) => x.b.a) : collectAnchors(pageBlocks)).find((an) => fset.has(an)) || null;

  let tone: FocusTone = ACCENT_TONE;
  let tagText = '';
  if (focus && focus.kind === 'finding') {
    const ff = fAll.find((f) => f.id === focus.id);
    if (ff) {
      const R = riskView(ff.risk);
      tone = { line: R.solid, bg: R.focus, tag: R.tag, halo: R.halo };
      tagText = ff.id + ' · ' + ff.cat + ' · ' + R.label;
    }
  } else if (focus && focus.kind === 'item') {
    const it = a.items.find((i) => i.id === focus.id);
    tone = ITEM_TONE;
    tagText = it ? it.id + ' · ' + RTYPE[it.type].label : '검토 필요';
  } else if (focus && focus.kind === 'link') {
    tagText = focus.id + ' · 연결 근거';
  }

  const mask = s.mask && showFind;
  const markVars: HighlightVars = { soft: tone.bg, solid: tone.line, onBg: tone.bg, pc: tone.line, ph: tone.halo };
  const selfFocus = !!focus && focus.kind === 'finding';

  const segs = (val: TextValue | null | undefined): SegmentModel[] => {
    const arr: Segment[] = val == null ? [] : Array.isArray(val) ? val : [val];
    return arr.map((p): SegmentModel => {
      if (typeof p === 'string' || typeof p === 'number') return { kind: 'plain', text: String(p) };
      const f = anchorF[p.a];
      const on = fset.has(p.a);
      const tag = on && p.a === first;
      if (f) {
        const R = riskView(f.risk);
        const fp = f.status === 'false_positive';
        return {
          kind: 'hl',
          anchor: p.a,
          findingId: f.id,
          text: p.x,
          shown: mask && !fp && p.m ? p.m : p.x,
          aria: f.id + ' ' + f.cat + ' ' + R.label + ' — 탐지 항목 보기',
          on,
          fp,
          tag,
          vars: {
            soft: R.soft,
            solid: R.solid,
            onBg: selfFocus ? R.focus : tone.bg,
            pc: selfFocus ? R.solid : tone.line,
            ph: selfFocus ? R.halo : tone.halo,
          },
        };
      }
      if (on) return { kind: 'mark', anchor: p.a, text: mask && p.m ? p.m : p.x, tag, vars: markVars };
      return { kind: 'plain', text: mask && p.m ? p.m : p.x };
    });
  };

  const blockOf = (b: PageBlock): BlockModel => {
    switch (b.t) {
      case 'bar':
        return { t: 'bar', left: b.left, right: b.right };
      case 'title':
        return { t: 'title', text: b.text, sub: b.sub || '' };
      case 'sec':
        return { t: 'sec', text: b.text };
      case 'kv':
        return { t: 'kv', cols: b.cols === 3 ? 3 : 2, items: b.items.map((it) => ({ k: it[0], segs: segs(it[1]), span: it[2] || 1 })) };
      case 'table':
        return {
          t: 'table',
          head: b.head.map((h, i) => ({ text: h, align: align(b.align && b.align[i]) })),
          rows: b.rows.map((r) => r.map((c, i) => ({ segs: segs(c), align: align(b.align && b.align[i]) }))),
        };
      case 'p':
        return { t: 'p', small: !!b.small, segs: segs(b.text) };
      case 'checks':
        return { t: 'checks', items: b.items.map((c) => ({ on: !!c.on, text: c.text })) };
      case 'sign':
        return { t: 'sign', date: b.date, items: b.items.map((it) => ({ k: it[0], segs: segs(it[1]), suffix: it[2] || '' })) };
      case 'stamp':
        return { t: 'stamp', lines: b.lines.map((l) => segs(l)) };
      case 'blur': {
        const on = fset.has(b.a);
        return { t: 'blur', anchor: b.a, label: b.label, lines: b.lines, on, tag: on && b.a === first, vars: markVars };
      }
      case 'cut': {
        const on = fset.has(b.a);
        return { t: 'cut', anchor: b.a, label: b.label, ghost: b.ghost, on, tag: on && b.a === first, vars: markVars };
      }
      case 'foot':
        return { t: 'foot', segs: segs(b.left), right: b.right || '' };
    }
  };

  const notices: NoticeModel[] = [];
  if (focus && focus.kind === 'finding') {
    const ff = fAll.find((f) => f.id === focus.id);
    if (ff && !ff.anchors.length && doc && ff.docId === doc.id)
      notices.push({
        tone: 'warn',
        icon: 'dg-i-pin-q',
        title: '위치 확인 필요 · ' + ff.id + ' ' + ff.cat,
        text: '원문 좌표가 없어 강조할 수 없습니다. ' + ff.page + '쪽에서 근거 문구 “' + ff.evidence + '”를 직접 찾아 확인해 주세요.',
      });
  }
  if (focus && focus.kind === 'item' && !first && doc) {
    const it = a.items.find((i) => i.id === focus.id);
    if (it && it.docId === doc.id && hasPage) notices.push({ tone: 'warn', icon: RTYPE[it.type].icon, title: it.id + ' · ' + RTYPE[it.type].label, text: it.next });
  }
  if (source && source.kind === 'other' && hasPage)
    notices.push({
      tone: 'run',
      icon: 'dg-i-info',
      title: '기타 서류 안내',
      text: guideText(source.otherGuide) || '워크플로우가 기타 서류로 분류했습니다.',
      pre: true,
    });
  if (mask && hasPage)
    notices.push({
      tone: 'accent',
      icon: 'dg-i-eye-off',
      title: '마스킹 미리보기',
      text: '화면에서만 가려 보는 미리보기입니다. 원본 파일은 바뀌지 않으며, 마스킹한 파일을 만드는 기능과는 다릅니다.',
    });
  if (hasPage && !showFind)
    notices.push({ tone: 'run', icon: 'dg-i-info', title: '탐지 위치 표시 전', text: '분석이 끝나면 이 문서에서 찾은 정보의 위치를 강조해 표시합니다.' });

  return {
    doc,
    docName: doc ? docName(doc) : '-',
    page,
    pageCount: pc,
    pageLabel: pc ? page + ' / ' + pc : '- / -',
    hasPage,
    showFind,
    noPrev: !hasPage || page <= 1,
    noNext: !hasPage || page >= pc,
    zoom: z,
    zoomLabel: Math.round(z * 100) + '%',
    noOut: !hasPage || z <= 0.41,
    noIn: !hasPage || z >= 1.99,
    isFit: s.zoom == null,
    noPage: !hasPage,
    mask: s.mask,
    noMask: !hasPage || !showFind,
    notices,
    pageAria: doc ? docName(doc) + ' ' + page + '쪽' : '',
    scan: !!(doc && doc.scan),
    blocks: pageBlocks.map(blockOf),
    tag: { text: tagText, bg: tone.tag },
    placeholder: placeholderModel(a, doc, hasPage),
    pageKey: (doc ? doc.id : '') + ':' + page,
    ringKey: focusKey(focus) + '#' + s.pulse,
    live:
      source && hasPage
        ? {
            filePage: filePageOf(source, page),
            other: source.kind === 'other',
            boxes: liveBoxSrc.map(({ f, b }): LiveBoxModel => {
              const R = riskView(f.risk);
              const on = fset.has(b.a);
              const fp = f.status === 'false_positive';
              return {
                anchor: b.a,
                findingId: f.id,
                points: b.points.map((pt) => ({ x: pt.x, y: pt.y })),
                aria: f.id + ' ' + f.cat + ' ' + R.label + ' — 탐지 항목 보기',
                on,
                tag: on && b.a === first,
                masked: mask && !fp,
                vars: {
                  soft: R.soft,
                  solid: R.solid,
                  onBg: selfFocus ? R.focus : tone.bg,
                  pc: selfFocus ? R.solid : tone.line,
                  ph: selfFocus ? R.halo : tone.halo,
                },
              };
            }),
          }
        : null,
  };
}

/* ---------- 결과 패널 ---------- */

export interface FindingModel {
  id: string;
  cat: string;
  label: string;
  masked: string;
  subject: string;
  exposure: string;
  /** '개인 여신거래 신청서 · 1쪽' */
  where: string;
  risk: RiskView;
  status: FindingStatusView;
  statusKey: Finding['status'];
  open: boolean;
  fp: boolean;
  noLoc: boolean;
  aria: string;
  reason: string;
  rule: string;
  ruleName: string;
  /** 적용 규칙이 있다(실제 분석은 없음 — 줄을 뺀다) */
  hasRule: boolean;
  /** 실제 분석 항목 안내(분류 확인 필요 · 인식 신뢰도 낮음) */
  notes: string[];
  locText: string;
  hasEvidence: boolean;
  evidence: string;
  /** 분류가 바뀌었거나 오탐 — 최초 AI 결과를 보인다 */
  changed: boolean;
  aiText: string;
  noteLabel: string;
  note: string;
  memo: string;
  memoLabel: string;
  canConfirm: boolean;
  canUnconfirm: boolean;
  canFp: boolean;
  canRestore: boolean;
}

/** 탐지 항목 행(원본 findingVM) */
export function findingModel(a: Analysis, f: Finding, focus: DetailFocus | null): FindingModel {
  const R = riskView(f.risk);
  const st = Object.prototype.hasOwnProperty.call(FSTATUS, f.status) ? FSTATUS[f.status] : FSTATUS.open;
  const d = a.docs.find((x) => x.id === f.docId);
  const dName = docName(d);
  const fp = f.status === 'false_positive';
  const changed = fp || f.cat !== f.ai.cat || f.subject !== f.ai.subject || f.exposure !== f.ai.exposure;
  const aiText = f.ai.cat + ' · ' + f.ai.subject + ' · ' + f.ai.exposure;
  let noteLabel = '';
  let note = '';
  if (fp) {
    noteLabel = '오탐 사유';
    note = (f.fpType ? f.fpType + ' — ' : '') + (f.fpNote || '');
  } else if (f.status === 'reclassified') {
    noteLabel = '수정 사유';
    note = f.reclassNote || '';
  }
  return {
    id: f.id,
    cat: f.cat,
    label: f.label,
    masked: f.masked,
    subject: f.subject,
    exposure: f.exposure,
    where: dName + ' · ' + f.page + '쪽',
    risk: R,
    status: st,
    statusKey: f.status,
    open: !!focus && focus.kind === 'finding' && focus.id === f.id,
    fp,
    noLoc: f.anchors.length === 0,
    aria: f.id + ' ' + f.cat + ' ' + f.label + ', 위험등급 ' + R.label + ', ' + st.label,
    reason: f.reason,
    rule: f.rule,
    ruleName: ruleName(f.rule),
    hasRule: !!f.rule,
    notes: findingNotes(f.live),
    locText: f.anchors.length ? dName + ' ' + f.page + '쪽 · 원문 위치 확인됨' : dName + ' ' + f.page + '쪽 · 좌표 없음 (위치 확인 필요)',
    hasEvidence: !!f.evidence,
    evidence: f.evidence || '',
    changed,
    aiText: fp ? aiText + ' (오탐 표시 전)' : aiText,
    noteLabel,
    note,
    memo: f.memo || '',
    memoLabel: f.memo ? '메모 수정' : '메모',
    canConfirm: f.status === 'open',
    canUnconfirm: f.status === 'confirmed',
    canFp: !fp,
    canRestore: fp,
  };
}

export interface ItemModel {
  id: string;
  type: string;
  icon: IconName;
  title: string;
  desc: string;
  next: string;
  where: string;
  resolved: boolean;
  sel: boolean;
  resolvedText: string;
  evidence: { label: string }[];
  linkId: string | null;
  canRetry: boolean;
  retryDoc: string | null;
  retrying: boolean;
  retryLabel: string;
  canResolve: boolean;
  canReopen: boolean;
}

/** 검토사항 행(원본 itemVM) */
export function itemModel(a: Analysis, it: ReviewItem, focus: DetailFocus | null): ItemModel {
  const T = RTYPE[it.type];
  const d = a.docs.find((x) => x.id === it.docId);
  const failedDoc = it.retryDoc ? a.docs.find((x) => x.id === it.retryDoc) : null;
  return {
    id: it.id,
    type: T.label,
    icon: T.icon,
    title: it.title,
    desc: it.desc,
    next: it.next,
    where: d ? docName(d) + ' · ' + it.page + '쪽' : '',
    resolved: !!it.resolved,
    sel: !!focus && focus.kind === 'item' && focus.id === it.id,
    resolvedText: it.resolved ? '해결 · ' + it.resolvedBy + ' · ' + fmtDT(it.resolvedAt) + ' — ' + it.note : '',
    evidence: it.evidence.map((ev) => ({ label: ev.label })),
    linkId: it.linkId || null,
    canRetry: !!(failedDoc && failedDoc.status !== 'done' && !it.resolved),
    retryDoc: it.retryDoc || null,
    retrying: !!a.retrying,
    retryLabel: a.retrying ? '다시 분석하는 중…' : '다시 분석',
    canResolve: !it.resolved,
    canReopen: !!it.resolved,
  };
}

export interface LinkDocModel {
  title: string;
  ext: string;
  page: number;
  fields: string;
  on: boolean;
  aria: string;
}

export interface LinkModel {
  id: string;
  title: string;
  status: LinkStatusView;
  sel: boolean;
  docs: LinkDocModel[];
  basis: string[];
  missing: string;
  check: string;
  decided: boolean;
  decisionText: string;
  canDecide: boolean;
}

/** 문서 간 연결 카드(원본 linkVM) — 실제 분석(raw 있음)의 연결은 읽기 전용이라 판단 버튼이 없다 */
export function linkModel(a: Analysis, l: DocLink, focus: DetailFocus | null): LinkModel {
  const sel = !!focus && focus.kind === 'link' && focus.id === l.id;
  return {
    id: l.id,
    title: l.title,
    status: LSTATUS[l.decision || l.status],
    sel,
    docs: l.docs.map((ld, i) => {
      const d = a.docs.find((x) => x.id === ld.docId);
      const nm = docName(d);
      return { title: nm, ext: d ? d.ext : '', page: ld.page, fields: ld.fields, on: sel && focus.kind === 'link' && focus.idx === i, aria: nm + ' ' + ld.page + '쪽 근거 보기' };
    }),
    basis: l.basis,
    missing: l.missing || '',
    check: l.check,
    decided: !!l.decision,
    decisionText: l.decision
      ? l.decidedBy + ' · ' + fmtDT(l.decidedAt) + ' · ' + (l.decision === 'linked' ? '같은 사람 · 같은 건으로 판단' : '연결 아님으로 판단') + ' — ' + l.decisionNote
      : '',
    canDecide: !a.raw && l.status === 'check' && !l.decision,
  };
}

export interface WaitingDocModel {
  title: string;
  status: AnalysisStatusView & { readonly still: boolean };
}

/** 결과 대신 보이는 대기 안내(원본 rs.w) */
export interface WaitingModel {
  queued: boolean;
  title: string;
  sub: string;
  text: string;
  docs: WaitingDocModel[];
  hint: string;
  demo: boolean;
}

export function waitingModel(a: Analysis, x: DetailFacts): WaitingModel | null {
  if (!x.waiting) return null;
  const queued = a.status === 'queued';
  return {
    queued,
    title: queued ? '분석 대기' : '분석 중',
    sub: queued ? '접수 ' + fmtDT(a.submittedAt) : '문서 ' + a.docs.length + '개 중 ' + x.nDoneDocs + '개 완료',
    text: queued
      ? a.demoQueued
        ? '데모 환경에서는 직접 올린 파일을 분석하지 않습니다. 실제 서비스에서는 접수 순서에 따라 분석이 시작되고, 끝나면 위험등급과 탐지 항목이 이곳에 표시됩니다.'
        : '곧 분석이 시작됩니다.'
      : '문서별로 개인정보와 금융 중요정보를 찾고 있습니다. 모든 문서의 분석이 끝나면 위험등급, 탐지 항목, 검토할 문제를 이곳에 표시합니다.',
    docs: a.docs.map((d) => ({ title: docName(d), status: analysisStatusView(d.status) })),
    hint: '정확한 진행률을 알 수 없어 백분율은 표시하지 않습니다. 위험등급은 분석이 끝난 뒤 정해지며, 그 전까지는 ‘미평가’입니다.',
    demo: !!a.demoQueued,
  };
}

export interface ResultTabModel {
  value: DetailTab;
  label: string;
  /** 건수(분석 요약 탭은 없음) */
  count?: number;
  tone: 'default' | 'warn';
}

export interface ResultsModel {
  /** 결과 탭이 있다(결과가 있음) */
  hasTabs: boolean;
  locked: boolean;
  tab: DetailTab;
  tabs: ResultTabModel[];
  /* 탐지 항목 */
  chips: { value: FindingFilter; label: string; count: number }[];
  findings: FindingModel[];
  shownText: string;
  /* 검토 필요 */
  keep: string | null;
  nOpen: number;
  nDone: number;
  items: ItemModel[];
  /** 해결 · 다시 열기 버튼을 막는다(검토 완료 · 검토 기록을 불러오지 못함) */
  itemsLocked: boolean;
  /** 검토사항이 없을 때 제목 아래 설명 줄(실제 분석은 '' — 제목만) */
  itemsEmptyText: string;
  /* 문서 간 연결 */
  links: LinkModel[];
  /** 연결 카드 위 설명 줄을 보이는지(데모만 — 실제 분석의 서류 대조는 이름 같은 값으로도 연결하므로 그 설명이 맞지 않는다) */
  linksIntro: boolean;
  /* 기다림 */
  waiting: WaitingModel | null;
  /* 검토 메모 */
  memo: string;
  memoPreview: string;
  memoBtn: string;
  /** 실제 분석인데 검토 기록을 불러오지 못함 — 검토 동작 · 메모 버튼을 막는다 */
  readOnly: boolean;
}

/** 검토사항이 없을 때 설명 줄(데모만 — 원본 문구) */
export const ITEMS_EMPTY_TEXT = '판독 실패, 잘린 페이지, 값 불일치, 연결 근거 부족 같은 문제가 발견되면 이곳에 표시됩니다.';

/** 결과 패널(원본 detailVM 의 '탐지 결과 패널' 부분) */
export function resultsModel(a: Analysis, s: DetailUiState, x: DetailFacts): ResultsModel {
  const fAll = a.findings;
  const docs = a.docs;
  const doc = x.doc;
  const focus = s.focus;
  const docIdx: Record<string, number> = {};
  docs.forEach((d, i) => (docIdx[d.id] = i));
  const cnt = (fn: (f: Finding) => boolean) => fAll.filter(fn).length;

  const items = fAll
    .filter((f) => passesFilter(s.fFilter, f) && (!s.onlyDoc || !doc || f.docId === doc.id))
    .slice()
    .sort((p, q) => byRisk(p, q) || (docIdx[p.docId] ?? 0) - (docIdx[q.docId] ?? 0) || p.page - q.page || (p.id < q.id ? -1 : 1));

  const hi = fAll.filter((f) => f.risk === 'high' && f.status !== 'false_positive').length;
  const issues = a.items.some((i) => !i.resolved && (i.type === 'unreadable' || i.type === 'cutoff' || i.type === 'failed'));

  const tabLabel: Record<DetailTab, string> = { findings: '탐지 항목', review: '검토 필요', links: '문서 간 연결', summary: '분석 요약' };
  const tabCount: Record<DetailTab, number | undefined> = { findings: fAll.length, review: x.openItems, links: a.links.length, summary: undefined };
  // 실제 분석은 '분석 요약'(위험도 판정 · 다음 단계 · 결과 요약 · 단계별 JSON)을 두고, 문서 간 연결은 1개 이상일 때만 그 탭(읽기 전용)
  const tabList = x.live ? (a.links.length ? LIVE_LINK_TABS : LIVE_DETAIL_TABS) : DETAIL_TABS;

  return {
    hasTabs: x.hasResults,
    locked: x.locked,
    tab: s.tab,
    tabs: tabList.map((t) => ({ value: t, label: tabLabel[t], count: tabCount[t], tone: t === 'review' ? 'warn' : 'default' })),
    chips: [
      { value: 'all', label: '전체', count: fAll.length },
      // 상태 · 위험등급 라벨은 ② 표시 규칙에서 — 키와 순서는 원본 그대로
      { value: 'open', label: FSTATUS.open.label, count: cnt((f) => f.status === 'open') },
      { value: 'high', label: riskView('high').label, count: cnt((f) => f.risk === 'high') },
      { value: 'medium', label: riskView('medium').label, count: cnt((f) => f.risk === 'medium') },
      { value: 'low', label: riskView('low').label, count: cnt((f) => f.risk === 'low') },
    ],
    findings: items.map((f) => findingModel(a, f, focus)),
    shownText: items.length + '건 표시 · 확인 ' + x.reviewed + '/' + fAll.length,
    keep: hi > 0 && issues ? '이미 발견한 고위험 정보 ' + hi + '건은 아래 판독 실패 · 누락과 관계없이 그대로 표시하고 유지합니다. 아직 읽지 못한 부분에 추가 정보가 있을 수 있습니다.' : null,
    nOpen: x.openItems,
    nDone: a.items.length - x.openItems,
    items: a.items
      .slice()
      .sort((p, q) => (p.resolved ? 1 : 0) - (q.resolved ? 1 : 0))
      .map((it) => itemModel(a, it, focus)),
    itemsLocked: x.locked || x.readOnly,
    itemsEmptyText: x.live ? '' : ITEMS_EMPTY_TEXT,
    links: a.links.map((l) => linkModel(a, l, focus)),
    linksIntro: !x.live,
    waiting: waitingModel(a, x),
    memo: a.memo,
    memoPreview: a.memo ? a.memo.replace(/\n/g, ' ') : '아직 작성한 메모가 없습니다.',
    memoBtn: a.memo ? '수정' : '작성',
    readOnly: x.readOnly,
  };
}

/* ---------- 휴대폰 탭 · 전체 실패 ---------- */

export function mobileTabs(a: Analysis, x: DetailFacts): { value: MobileTab; label: string }[] {
  return [
    { value: 'doc', label: '원문' },
    { value: 'results', label: x.hasResults ? '탐지 결과 ' + a.findings.length : '분석 결과' },
    { value: 'docs', label: '문서 ' + a.docs.length },
  ];
}

/** 전체 실패 화면(원본 dt.fail · failedBody) */
export interface FailModel {
  retrying: boolean;
  title: string;
  text: string;
  retryLabel: string;
  files: { name: string; meta: string; error: string }[];
}

/** 결과 대신 전체 실패 화면을 보이는지 — 실패, 또는 실패 문서를 모두 다시 분석하는 중(원본 failedBody) */
export function failModel(a: Analysis, x: DetailFacts): FailModel | null {
  const allRetrying = !!a.retrying && a.status === 'running' && x.nFailDocs === 0 && a.docs.every((d) => d.status === 'running');
  if (a.status !== 'failed' && !allRetrying) return null;
  return {
    retrying: !!a.retrying,
    title: allRetrying ? '같은 파일로 다시 분석하고 있습니다' : '분석에 실패했습니다',
    text: allRetrying
      ? '결과가 나오면 이 화면에 표시합니다.'
      : '문서 ' + a.docs.length + '개를 모두 분석하지 못했습니다. 개인정보 포함 여부를 확인할 수 없어 위험등급은 ‘미평가’입니다.',
    retryLabel: a.retrying ? '다시 분석하는 중…' : '다시 시도',
    files: a.docs.map((d) => ({ name: d.name, meta: d.ext + ' · ' + fmtSize(d.size), error: d.status === 'running' ? '다시 분석하는 중입니다…' : d.error || '-' })),
  };
}

/** 휴대폰 탭을 보이는지(원본 showMTabs: 휴대폰이고 전체 실패가 아님) */
export function showMobileTabs(a: Analysis): boolean {
  return a.status !== 'failed';
}
