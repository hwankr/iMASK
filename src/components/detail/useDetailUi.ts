'use client';

/* ==========================================================================
   상세 화면 상태 훅 — 리듀서(detailState.ts) + 스크롤 요청 + 원문 뷰어 크기 재기.
   원본: Main.dc.html 뷰어 스크롤·크기(1606–1653: motion · attachViewer · flushScroll)와 상세 동작(1730–1808).

   - 상태는 useReducer 하나(DetailUiState). 화면 조각은 이 훅이 돌려주는 처리기만 부른다.
   - 스크롤 요청(원문 위치 · 결과 행)은 원본처럼 '대기 중인 대상'으로 들고 있다가, 그리고 난 뒤
     해당 영역이 화면에 있으면 처리한다(휴대폰에서 다른 탭에 있으면 그 탭이 열릴 때 처리).
   - 부드러운 스크롤은 동작 줄이기면 즉시(scrollBehavior → 'auto').
   - 원문 뷰어 폭은 ResizeObserver 로 재고, 종이 폭은 실행 중에 --paper-w 토큰에서 읽는다(화면 맞춤 배율).
   - 실제 분석 원문은 원본 파일을 받은 뒤에야 쪽 크기 · 위치 상자가 생긴다 — 쪽이 준비되면 recenter() 로
     고른 항목의 첫 위치로 다시 스크롤한다(데모는 부르지 않는다).
   ========================================================================== */

import { useCallback, useEffect, useLayoutEffect, useReducer, useRef, useState, type Dispatch } from 'react';
import { scrollBehavior, useIsMobile, useMediaQuery } from '@/lib/hooks';
import type { Pending } from '@/services/analysis-service';
import { useService } from '@/services/react';
import type { Analysis } from '@/services/types';
import type { ViewerMetrics } from './detailModel';
import {
  createDetailState,
  detailReducer,
  normalizeZoom,
  planGoPending,
  planOpenLink,
  planPickDoc,
  planPickFinding,
  planPickItem,
  planPickItemEvidence,
  planPickLinkDoc,
  planSetPage,
  resolveLeftOpen,
  SCROLL_TOP,
  type DetailAction,
  type DetailModal,
  type DetailModalPatch,
  type DetailPlan,
  type DetailTab,
  type DetailUiState,
  type FindingFilter,
  type MobileTab,
  type PickFindingOptions,
} from './detailState';

/** 데스크톱 폭(≥ 1200px) — tokens.css 중단점과 같다 */
export const DESKTOP_QUERY = '(min-width: 1200px)';

/** 원본 flushScroll — 두 프레임 뒤(새 쪽이 그려진 뒤)에 잰다 */
function afterPaint(fn: () => void) {
  requestAnimationFrame(() => requestAnimationFrame(fn));
}

/** 속성 선택자용 값 — 위치 ID 는 영문·숫자·하이픈이지만 안전하게 감싼다 */
function attrSel(name: string, value: string): string {
  const v = typeof CSS !== 'undefined' && CSS.escape ? CSS.escape(value) : value.replace(/["\\]/g, '\\$&');
  return `[${name}="${v}"]`;
}

/** 실행 중에 토큰 값(px)을 읽는다 */
function readPx(el: Element, prop: string): number {
  const v = parseFloat(getComputedStyle(el).getPropertyValue(prop));
  return Number.isFinite(v) ? v : 0;
}

function measure(el: HTMLElement): ViewerMetrics {
  return {
    width: Math.round(el.clientWidth || 0),
    padX: readPx(el, 'padding-left'),
    paperW: readPx(document.documentElement, '--paper-w'),
  };
}

export interface DetailUi {
  state: DetailUiState;
  /** T7: 리듀서에 직접 보낼 때(apply · openModal · patchModal · closeModal) */
  dispatch: Dispatch<DetailAction>;
  /** 계획(상태 + 스크롤 요청)을 적용한다 */
  run: (plan: DetailPlan | null) => void;
  /* 레이아웃 */
  mobile: boolean;
  desktop: boolean;
  leftOpen: boolean;
  /** 뷰어 크기(재기 전에는 null) */
  metrics: ViewerMetrics | null;
  /** 원문 뷰어 스크롤 영역 ref */
  viewerRef: (el: HTMLElement | null) => void;
  /** 결과 패널 스크롤 영역 ref */
  resultsRef: (el: HTMLElement | null) => void;
  /* 탭 · 필터 */
  setTab: (tab: DetailTab) => void;
  setFilter: (filter: FindingFilter) => void;
  setOnlyDoc: (on: boolean) => void;
  /** '필터 해제' — 전체 · 현재 문서만 끔 */
  clearFilter: () => void;
  setMobileTab: (tab: MobileTab) => void;
  toggleLeft: () => void;
  /* 원문 뷰어 */
  pickDoc: (docId: string) => void;
  setPage: (page: number) => void;
  setZoom: (zoom: number) => void;
  fit: () => void;
  toggleMask: () => void;
  /* 선택 동기화 */
  pickFinding: (fid: string, opt?: PickFindingOptions) => void;
  pickItemEvidence: (rid: string, idx: number) => void;
  pickItem: (rid: string) => void;
  pickLinkDoc: (lid: string, idx: number) => void;
  openLink: (lid: string) => void;
  /** 남은 항목으로 가기(검토 완료 모달에서 — T7) */
  goPending: () => void;
  /**
   * 실제 분석 원문 쪽이 준비됐을 때(파일 · 쪽 크기를 늦게 앎) — 고른 탐지 항목이 지금 문서 · 쪽에 있으면
   * 그 첫 위치로 다시 스크롤한다. 없으면 아무것도 하지 않는다.
   */
  recenter: () => void;
  /* 모달 자리(T7) */
  openModal: (modal: DetailModal) => void;
  patchModal: (patch: DetailModalPatch) => void;
  closeModal: () => void;
}

/**
 * 상세 화면 상태. `analysis` 는 처음 렌더 때 받은 값으로 처음 상태를 만들고(원본 openDetail),
 * 그 뒤에는 최신 값으로 선택·이동을 계산한다.
 */
export function useDetailUi(analysis: Analysis, initial?: Partial<DetailUiState>): DetailUi {
  const service = useService();
  const mobile = useIsMobile();
  const desktop = useMediaQuery(DESKTOP_QUERY);

  const [init] = useState(() => createDetailState(analysis, initial));
  const [state, dispatch] = useReducer(detailReducer, init.state);
  const [metrics, setMetrics] = useState<ViewerMetrics | null>(null);

  /** 대기 중인 스크롤 대상(원본 scrollTarget · cardTarget) */
  const pending = useRef<{ viewer: string | null; card: string | null }>({ viewer: init.plan.viewer ?? null, card: init.plan.card ?? null });
  const viewerEl = useRef<HTMLElement | null>(null);
  const resultsEl = useRef<HTMLElement | null>(null);
  const ro = useRef<ResizeObserver | null>(null);
  /** 비동기 응답(goPending)이 쓰는 최신 값 */
  const latest = useRef({ state, analysis, mobile });
  useLayoutEffect(() => {
    latest.current = { state, analysis, mobile };
  });

  const flush = useCallback(() => {
    const vt = pending.current.viewer;
    const vEl = viewerEl.current;
    if (vt && vEl && vEl.isConnected) {
      pending.current.viewer = null;
      afterPaint(() => {
        if (!vEl.isConnected) return;
        if (vt === SCROLL_TOP) {
          vEl.scrollTo({ top: 0, left: 0 });
          return;
        }
        const el = vEl.querySelector(attrSel('data-anchor', vt));
        if (!el) {
          vEl.scrollTo({ top: 0, left: 0 });
          return;
        }
        const r = el.getBoundingClientRect();
        const c = vEl.getBoundingClientRect();
        vEl.scrollBy({ top: r.top - c.top - (c.height / 2 - r.height / 2), left: r.left - c.left - (c.width / 2 - r.width / 2), behavior: scrollBehavior() });
      });
    }
    const ct = pending.current.card;
    const rEl = resultsEl.current;
    if (ct && rEl && rEl.isConnected) {
      pending.current.card = null;
      afterPaint(() => {
        if (!rEl.isConnected) return;
        const el = rEl.querySelector(attrSel('data-card', ct));
        if (!el) return;
        const r = el.getBoundingClientRect();
        const c = rEl.getBoundingClientRect();
        const stk = rEl.querySelector('[data-sticky]');
        const top = c.top + (stk ? stk.getBoundingClientRect().height : 0) + 4;
        let d = 0;
        if (r.top < top) d = r.top - top;
        else if (r.bottom > c.bottom - 8) d = Math.min(r.top - top, r.bottom - c.bottom + 8);
        if (Math.abs(d) > 1) rEl.scrollBy({ top: d, behavior: scrollBehavior() });
      });
    }
  }, []);

  /* 그린 뒤마다 대기 중인 스크롤을 처리한다(원본 componentDidUpdate → flushScroll) */
  useEffect(() => {
    flush();
  });

  const viewerRef = useCallback(
    (el: HTMLElement | null) => {
      if (el === viewerEl.current) return;
      if (ro.current) {
        ro.current.disconnect();
        ro.current = null;
      }
      viewerEl.current = el;
      if (!el) return;
      setMetrics(measure(el));
      if (typeof ResizeObserver !== 'undefined') {
        const obs = new ResizeObserver(() => {
          const next = measure(el);
          setMetrics((prev) => (prev && Math.abs(next.width - prev.width) <= 2 && next.padX === prev.padX && next.paperW === prev.paperW ? prev : next));
        });
        obs.observe(el);
        ro.current = obs;
      }
      flush();
    },
    [flush],
  );

  const resultsRef = useCallback(
    (el: HTMLElement | null) => {
      resultsEl.current = el;
      if (el) flush();
    },
    [flush],
  );

  useEffect(
    () => () => {
      if (ro.current) ro.current.disconnect();
      ro.current = null;
    },
    [],
  );

  const run = useCallback((plan: DetailPlan | null) => {
    if (!plan) return;
    if (plan.viewer !== undefined) pending.current.viewer = plan.viewer;
    if (plan.card !== undefined) pending.current.card = plan.card;
    dispatch({ type: 'apply', patch: plan.patch, pulse: plan.pulse });
  }, []);

  const apply = (patch: Partial<DetailUiState>) => dispatch({ type: 'apply', patch });
  const leftOpen = resolveLeftOpen(state, desktop);

  return {
    state,
    dispatch,
    run,
    mobile,
    desktop,
    leftOpen,
    metrics,
    viewerRef,
    resultsRef,
    setTab: (tab) => apply({ tab }),
    setFilter: (fFilter) => apply({ fFilter }),
    setOnlyDoc: (onlyDoc) => apply({ onlyDoc }),
    clearFilter: () => apply({ fFilter: 'all', onlyDoc: false }),
    setMobileTab: (mTab) => apply({ mTab }),
    toggleLeft: () => apply({ leftOpen: !leftOpen }),
    pickDoc: (docId) => run(planPickDoc(docId, mobile)),
    setPage: (page) => run(planSetPage(page)),
    setZoom: (zoom) => apply({ zoom: normalizeZoom(zoom) }),
    fit: () => apply({ zoom: null }),
    toggleMask: () => apply({ mask: !state.mask }),
    pickFinding: (fid, opt = {}) => run(planPickFinding(state, analysis, fid, opt, mobile)),
    pickItemEvidence: (rid, idx) => run(planPickItemEvidence(analysis, rid, idx, false, mobile)),
    pickItem: (rid) => run(planPickItem(analysis, rid, mobile)),
    pickLinkDoc: (lid, idx) => run(planPickLinkDoc(analysis, lid, idx, false, mobile)),
    openLink: (lid) => run(planOpenLink(analysis, lid, mobile)),
    goPending: () => {
      if (!service) return;
      void service.pending(analysis.id).then((p: Pending) => {
        const cur = latest.current;
        run(planGoPending(cur.state, cur.analysis, p, cur.mobile));
      });
    },
    recenter: () => {
      const focus = state.focus;
      if (!focus || focus.kind !== 'finding') return;
      const f = analysis.findings.find((x) => x.id === focus.id);
      const docId = state.docId ?? analysis.docs[0]?.id ?? null;
      if (!f || !f.anchors.length || f.docId !== docId || f.page !== state.page) return;
      pending.current.viewer = f.anchors[0];
      flush();
    },
    openModal: (modal) => dispatch({ type: 'openModal', modal }),
    patchModal: (patch) => dispatch({ type: 'patchModal', patch }),
    closeModal: () => dispatch({ type: 'closeModal' }),
  };
}
