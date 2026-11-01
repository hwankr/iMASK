/* ==========================================================================
   상세 검토 화면 상태 — 하나의 리듀서로 모은 화면 상태와, 선택·이동 계획(순수 함수).
   원본: Main.dc.html detailState(1471–1484) · openDetail(1663–1674) · 상세 동작(1730–1808)의
   pickDoc · setPage · setZoom · pickFinding · pickItemEvidence · pickItem · pickLinkDoc · openLink · goPending.

   - 화면 상태(DetailUiState)는 데이터가 아니다. 탐지 항목·검토사항·연결은 서비스가 준 값을 그대로 보고,
     여기에는 '무엇을 골랐는지 · 어느 탭 · 어느 쪽 · 얼마나 확대했는지' 같은 화면 조건만 둔다.
   - 선택(focus)은 대상의 종류와 ID(+ 근거 순번)만 가진다. 원문 위치(anchors)는 그때그때 데이터에서 찾는다
     (focusAnchors). 그래서 /dev/states 가 `initial` 로 선택을 그대로 넘길 수 있다.
   - plan* 함수는 프로토타입 동작을 그대로 옮긴 순수 함수다. 상태에 붙일 값(patch)과
     스크롤 요청(viewer: 원문 위치 · card: 결과 패널 행)을 돌려주고, 훅(useDetailUi)이 적용한다.
   - T7 은 같은 리듀서의 `apply` · 모달 자리(openModal · patchModal · closeModal)를 쓴다.
   ========================================================================== */

import { byRisk, type Exposure, type FpReason, type InfoCategory, type InfoSubject, type RiskLevel } from '@/display/rules';
import { clamp } from '@/lib/format';
import type { Pending } from '@/services/analysis-service';
import type { Analysis, LinkDecision } from '@/services/types';

/* ---------- 화면 조건 ---------- */

/** 결과 패널 탭 — 탐지 항목 · 검토 필요 · 문서 간 연결 */
export type DetailTab = 'findings' | 'review' | 'links';
export const DETAIL_TABS: readonly DetailTab[] = ['findings', 'review', 'links'];

/** 탐지 항목 필터 칩 — 전체 · 미확인 · 위험등급별 */
export type FindingFilter = 'all' | 'open' | Exclude<RiskLevel, 'unrated'>;

/** 휴대폰 화면 전환 탭 — 원문 · 탐지 결과 · 문서 */
export type MobileTab = 'doc' | 'results' | 'docs';
export const MOBILE_TABS: readonly MobileTab[] = ['doc', 'results', 'docs'];

/**
 * 고른 대상(원본 state.focus).
 * - finding: 탐지 항목
 * - item: 검토사항 — idx 는 근거(evidence) 순번. null 이면 근거 없이 고른 것(원문 위치 없음)
 * - link: 문서 간 연결 — idx 는 연결에 묶인 문서 순번
 */
export type DetailFocus =
  | { kind: 'finding'; id: string }
  | { kind: 'item'; id: string; idx: number | null }
  | { kind: 'link'; id: string; idx: number };

/**
 * 모달 자리(원본 state.modal) — T7 이 모달을 그린다. 모양은 프로토타입 openModal 인자 그대로.
 * note · error 는 입력 중인 글과 검사 오류 문구다.
 */
export type DetailModal =
  | { type: 'fp'; fid: string; reason: FpReason; note: string; error: string }
  | { type: 'restore'; fid: string; note: string; error: string }
  | { type: 'edit'; fid: string; cat: InfoCategory; subject: InfoSubject; exposure: Exposure; note: string; error: string }
  | { type: 'fmemo'; fid: string; note: string; error: string }
  | { type: 'resolve'; rid: string; note: string; error: string }
  | { type: 'link'; lid: string; decision: LinkDecision; note: string; error: string }
  | { type: 'memo'; note: string; error: string }
  | { type: 'complete'; note: string; error: string }
  | { type: 'reopen'; note: string; error: string };

export type DetailModalType = DetailModal['type'];

/** 열린 모달의 입력값 바꾸기 — 종류(type)별로 그 모달에 있는 값만(예: fp 의 reason, edit 의 cat) */
type PatchOf<M> = M extends { type: string } ? Partial<Omit<M, 'type'>> : never;
export type DetailModalPatch = PatchOf<DetailModal>;

/** 상세 화면 상태 — 원본 baseState · detailState 의 상세 화면 부분 */
export interface DetailUiState {
  /** 결과 패널 탭 */
  tab: DetailTab;
  /** 탐지 항목 필터 칩 */
  fFilter: FindingFilter;
  /** '현재 문서만 보기' */
  onlyDoc: boolean;
  /** 고른 대상(없으면 null) — 탐지 항목 행은 이 값으로 펼쳐진다 */
  focus: DetailFocus | null;
  /** 원문 뷰어의 문서(없으면 첫 문서) */
  docId: string | null;
  /** 원문 뷰어의 쪽(1부터) */
  page: number;
  /** 확대 배율(0.4~2) — null 이면 화면 맞춤 */
  zoom: number | null;
  /** 마스킹 미리보기(화면에서만 가림) */
  mask: boolean;
  /** 휴대폰 화면 전환 탭 */
  mTab: MobileTab;
  /** 왼쪽 문서 목록 펼침 — null 이면 기본(데스크톱 펼침 · 태블릿 접힘) */
  leftOpen: boolean | null;
  /** 모달 자리(T7) */
  modal: DetailModal | null;
  /** 선택 신호 번호 — 고를 때마다 1씩 늘고, 원문 테두리 신호(dg-ring-a/b)를 다시 재생한다 */
  pulse: number;
}

/** 원문 맨 위로 스크롤(원본 '__top') */
export const SCROLL_TOP = '__top';

/** 원문 뷰어 스크롤 대상 — 원문 위치 ID(앵커) 또는 맨 위 */
export type ViewerScrollTarget = string;

/** 선택·이동 계획 — 상태에 붙일 값과 스크롤 요청 */
export interface DetailPlan {
  patch: Partial<DetailUiState>;
  /** true 면 선택 신호를 다시 재생한다(원본 forcePulse) */
  pulse?: boolean;
  /** 원문 뷰어를 이 위치(또는 맨 위)로 스크롤 */
  viewer?: ViewerScrollTarget;
  /** 결과 패널에서 이 행(data-card)이 보이게 스크롤 */
  card?: string;
}

/* ---------- 리듀서 ---------- */

export type DetailAction =
  /** 계획(patch)을 적용한다. pulse 면 선택 신호 번호를 올린다. */
  | { type: 'apply'; patch: Partial<DetailUiState>; pulse?: boolean }
  /** 모달을 연다(T7). 열린 모달이 있으면 바꾼다. */
  | { type: 'openModal'; modal: DetailModal }
  /** 열린 모달의 입력값을 바꾼다(T7). 종류는 바꾸지 않는다. */
  | { type: 'patchModal'; patch: DetailModalPatch }
  /** 모달을 닫는다(T7). */
  | { type: 'closeModal' };

export function detailReducer(state: DetailUiState, action: DetailAction): DetailUiState {
  switch (action.type) {
    case 'apply':
      return { ...state, ...action.patch, pulse: action.pulse ? state.pulse + 1 : (action.patch.pulse ?? state.pulse) };
    case 'openModal':
      return { ...state, modal: action.modal };
    case 'patchModal':
      return state.modal ? { ...state, modal: { ...state.modal, ...action.patch, type: state.modal.type } as DetailModal } : state;
    case 'closeModal':
      return state.modal ? { ...state, modal: null } : state;
    default:
      return state;
  }
}

/* ---------- 데이터에서 찾기 ---------- */

/** 고른 대상의 원문 위치 목록(원본 focus.anchors) */
export function focusAnchors(a: Analysis, focus: DetailFocus | null): string[] {
  if (!focus) return [];
  if (focus.kind === 'finding') return a.findings.find((f) => f.id === focus.id)?.anchors.slice() ?? [];
  if (focus.kind === 'item') {
    if (focus.idx == null) return [];
    return a.items.find((i) => i.id === focus.id)?.evidence[focus.idx]?.anchors.slice() ?? [];
  }
  return a.links.find((l) => l.id === focus.id)?.docs[focus.idx]?.anchors.slice() ?? [];
}

/** 고른 대상이 있는 문서·쪽(원본 detailState 의 docId · page) */
export function focusLocation(a: Analysis, focus: DetailFocus): { docId: string; page: number } | null {
  if (focus.kind === 'finding') {
    const f = a.findings.find((x) => x.id === focus.id);
    return f ? { docId: f.docId, page: f.page } : null;
  }
  if (focus.kind === 'item') {
    const it = a.items.find((x) => x.id === focus.id);
    if (!it) return null;
    const ev = focus.idx == null ? undefined : it.evidence[focus.idx];
    return ev ? { docId: ev.docId, page: ev.page } : { docId: it.docId, page: it.page };
  }
  const ld = a.links.find((x) => x.id === focus.id)?.docs[focus.idx];
  return ld ? { docId: ld.docId, page: ld.page } : null;
}

/** 선택 신호를 다시 재생할 서명(원본 selKey) */
export function focusKey(focus: DetailFocus | null): string {
  if (!focus) return '';
  return focus.kind + ':' + focus.id + ':' + (focus.kind === 'finding' || focus.idx == null ? '' : focus.idx);
}

/** 필터 칩에 이 탐지 항목이 보이는지(원본 pickFinding 의 ok · detailVM 의 필터) */
export function passesFilter(filter: FindingFilter, f: { status: string; risk: string }): boolean {
  return filter === 'all' || (filter === 'open' ? f.status === 'open' : f.risk === filter);
}

/* ---------- 처음 상태 ---------- */

/** 기본값(원본 baseState · detailState) */
export function baseDetailState(a: Analysis | null): DetailUiState {
  return {
    tab: 'findings',
    fFilter: 'all',
    onlyDoc: false,
    focus: null,
    docId: a && a.docs[0] ? a.docs[0].id : null,
    page: 1,
    zoom: null,
    mask: false,
    mTab: 'doc',
    leftOpen: null,
    modal: null,
    pulse: 0,
  };
}

/** 처음 열 때 고를 탐지 항목 — 미확인 항목 중 위험이 가장 높은 것이 '높음'이면 그 항목(원본 openDetail) */
export function autoFocus(a: Analysis): DetailFocus | null {
  if (!a.findings.length) return null;
  const first = a.findings.filter((f) => f.status === 'open').sort(byRisk)[0];
  return first && first.risk === 'high' ? { kind: 'finding', id: first.id } : null;
}

/**
 * 상세 화면 처음 상태와 첫 스크롤 요청.
 * - initial 이 없으면(실제 화면 이동) 원본 openDetail 처럼 고위험 미확인 항목을 저절로 고르고,
 *   고른 위치(없으면 맨 위)로 스크롤한다.
 * - initial 이 있으면(/dev/states) 원본 initScenario 처럼 저절로 고르지 않고 initial.focus 만 쓴다.
 *   focus 가 있으면 그 문서·쪽을 열고, initial.docId 가 있으면 그 문서의 initial.page(기본 1)를 연다(원본 focusDoc).
 */
export function createDetailState(a: Analysis, initial?: Partial<DetailUiState>): { state: DetailUiState; plan: DetailPlan } {
  const st = baseDetailState(a);
  const focus = initial ? (initial.focus ?? null) : autoFocus(a);
  if (focus) {
    st.focus = focus;
    const loc = focusLocation(a, focus);
    if (loc) {
      st.docId = loc.docId;
      st.page = loc.page;
    }
  }
  if (initial) {
    const { focus: _f, docId, page, ...rest } = initial;
    void _f;
    Object.assign(st, rest);
    if (docId !== undefined) {
      st.docId = docId;
      st.page = page ?? 1;
    } else if (page !== undefined) {
      st.page = page;
    }
  }
  const first = focusAnchors(a, st.focus)[0];
  const plan: DetailPlan = { patch: {}, card: st.focus ? st.focus.id : undefined };
  if (first) plan.viewer = first;
  else if (!initial) plan.viewer = SCROLL_TOP;
  return { state: st, plan };
}

/* ---------- 선택 · 이동 계획(원본 상세 동작) ---------- */

/** 문서를 고른다 — 그 문서 1쪽, 휴대폰이면 원문 탭(원본 pickDoc) */
export function planPickDoc(docId: string, mobile: boolean): DetailPlan {
  const patch: Partial<DetailUiState> = { docId, page: 1 };
  if (mobile) patch.mTab = 'doc';
  return { patch, viewer: SCROLL_TOP };
}

/** 쪽을 옮긴다(원본 setPage) */
export function planSetPage(page: number): DetailPlan {
  return { patch: { page }, viewer: SCROLL_TOP };
}

/** 확대 배율 — 0.1 단위로 반올림, 0.4~2 배(원본 setZoom) */
export function normalizeZoom(z: number): number {
  return clamp(Math.round(z * 10) / 10, 0.4, 2);
}

export interface PickFindingOptions {
  /** 행을 다시 누르면 접는다(행 머리 누름) */
  toggle?: boolean;
  /** 원문 하이라이트에서 골랐다 — 결과 패널 탐지 항목 탭으로, 필터에 걸리면 '전체', 그 행으로 스크롤, 휴대폰이면 탐지 결과 탭 */
  fromDoc?: boolean;
  /** '원문 확인' — 휴대폰이면 원문 탭으로 */
  reveal?: boolean;
  /** 이 탭으로 바꾼다 */
  tab?: DetailTab;
}

/** 탐지 항목을 고른다(원본 pickFinding) */
export function planPickFinding(state: DetailUiState, a: Analysis, fid: string, opt: PickFindingOptions, mobile: boolean): DetailPlan | null {
  const f = a.findings.find((x) => x.id === fid);
  if (!f) return null;
  const isOpen = !!state.focus && state.focus.kind === 'finding' && state.focus.id === fid;
  if (opt.toggle && isOpen) return { patch: { focus: null }, pulse: true };
  const patch: Partial<DetailUiState> = { focus: { kind: 'finding', id: fid }, docId: f.docId, page: f.page };
  const plan: DetailPlan = { patch, pulse: true };
  if (opt.fromDoc) {
    patch.tab = 'findings';
    if (!passesFilter(state.fFilter, f)) patch.fFilter = 'all';
    plan.card = fid;
    if (mobile) patch.mTab = 'results';
  }
  if (opt.reveal && mobile) patch.mTab = 'doc';
  if (opt.tab) patch.tab = opt.tab;
  if (!opt.fromDoc || !mobile) plan.viewer = f.anchors[0] || SCROLL_TOP;
  return plan;
}

/** 검토사항의 근거 위치로 간다(원본 pickItemEvidence) — 위치 없는 탐지 항목을 가리키면 그 항목을 고른다 */
export function planPickItemEvidence(a: Analysis, rid: string, idx: number, noReveal: boolean, mobile: boolean): DetailPlan | null {
  const it = a.items.find((x) => x.id === rid);
  if (!it) return null;
  const ev = it.evidence[idx];
  let patch: Partial<DetailUiState>;
  if (ev && ev.findingId) {
    patch = { focus: { kind: 'finding', id: ev.findingId }, docId: ev.docId, page: ev.page };
  } else {
    patch = { focus: { kind: 'item', id: rid, idx: ev ? idx : null }, docId: ev ? ev.docId : it.docId, page: ev ? ev.page : it.page };
  }
  if (mobile && !noReveal) patch.mTab = 'doc';
  return { patch, pulse: true, viewer: (ev && ev.anchors[0]) || SCROLL_TOP };
}

/** 검토사항을 고른다 — 검토 필요 탭, 그 행으로 스크롤, 첫 근거 위치로(원본 pickItem) */
export function planPickItem(a: Analysis, rid: string, mobile: boolean): DetailPlan | null {
  const it = a.items.find((x) => x.id === rid);
  if (!it) return null;
  if (it.evidence.length) {
    const ev = planPickItemEvidence(a, rid, 0, true, mobile);
    if (!ev) return null;
    return { ...ev, patch: { tab: 'review', ...ev.patch }, card: rid };
  }
  return { patch: { tab: 'review', focus: { kind: 'item', id: rid, idx: null }, docId: it.docId, page: it.page }, pulse: true, viewer: SCROLL_TOP, card: rid };
}

/** 연결에 묶인 문서의 근거 위치로 간다(원본 pickLinkDoc) */
export function planPickLinkDoc(a: Analysis, lid: string, idx: number, noReveal: boolean, mobile: boolean): DetailPlan | null {
  const l = a.links.find((x) => x.id === lid);
  const ld = l?.docs[idx];
  if (!l || !ld) return null;
  const patch: Partial<DetailUiState> = { focus: { kind: 'link', id: lid, idx }, docId: ld.docId, page: ld.page };
  if (mobile && !noReveal) patch.mTab = 'doc';
  return { patch, pulse: true, viewer: ld.anchors[0] || SCROLL_TOP };
}

/** 연결을 연다 — 문서 간 연결 탭, 그 카드로 스크롤, 첫 문서 근거로(원본 openLink) */
export function planOpenLink(a: Analysis, lid: string, mobile: boolean): DetailPlan | null {
  const pick = planPickLinkDoc(a, lid, 0, true, mobile);
  if (!pick) return { patch: { tab: 'links' }, card: lid };
  return { ...pick, patch: { tab: 'links', ...pick.patch }, card: lid };
}

/**
 * 남은 항목으로 간다 — 모달을 닫고 미해결 검토사항 → 미확인 탐지 항목(위험 높은 것) → 확인 필요 연결 순서(원본 goPending).
 * pending 은 서비스 조회 결과(service.pending)다.
 */
export function planGoPending(state: DetailUiState, a: Analysis, p: Pending, mobile: boolean): DetailPlan {
  const close: Partial<DetailUiState> = { modal: null };
  if (p.openI.length) {
    const pick = planPickItem(a, p.openI[0].id, mobile);
    return pick ? { ...pick, patch: { ...close, ...pick.patch } } : { patch: close };
  }
  if (p.openF.length) {
    const f = p.openF.slice().sort(byRisk)[0];
    const next: DetailUiState = { ...state, fFilter: 'open', tab: 'findings' };
    const pick = planPickFinding(next, a, f.id, { tab: 'findings' }, mobile);
    const base: Partial<DetailUiState> = { ...close, fFilter: 'open', tab: 'findings' };
    return pick ? { ...pick, patch: { ...base, ...pick.patch }, card: f.id } : { patch: base, card: f.id };
  }
  if (p.openL.length) {
    const pick = planOpenLink(a, p.openL[0].id, mobile);
    return pick ? { ...pick, patch: { ...close, ...pick.patch } } : { patch: close };
  }
  return { patch: close };
}

/* ---------- 레이아웃 ---------- */

/** 왼쪽 문서 목록이 펼쳐져 있는지 — null 이면 데스크톱(≥1200)만 펼침(원본 renderVals leftOpen) */
export function resolveLeftOpen(state: DetailUiState, desktop: boolean): boolean {
  return state.leftOpen == null ? desktop : state.leftOpen;
}
