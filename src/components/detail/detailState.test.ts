import { describe, expect, it } from 'vitest';
import { byRisk } from '@/display/rules';
import { createService, getDemoControls } from '@/services';
import type { Analysis } from '@/services/types';
import {
  autoFocus,
  createDetailState,
  detailReducer,
  focusAnchors,
  maskPicked,
  normalizeZoom,
  planGoPending,
  planOpenLink,
  planPickDoc,
  planPickFinding,
  planPickItem,
  planPickItemEvidence,
  planPickLinkDoc,
  resolveLeftOpen,
  SCROLL_TOP,
  toggledMaskPick,
  withMaskPick,
  type DetailUiState,
} from './detailState';

/** 서비스가 주는 분석 건(샘플을 직접 가져오지 않는다) */
async function analysis(id: string): Promise<Analysis> {
  const a = await createService().get(id);
  if (!a) throw new Error('분석 건 없음: ' + id);
  return a;
}

describe('처음 상태 — 원본 openDetail · detailState', () => {
  it('실제 화면 이동이면 미확인 항목 중 위험이 가장 높은 것이 상일 때 그 항목을 고르고 그 위치로 스크롤한다', async () => {
    const a = await analysis('A1');
    const expected = a.findings.filter((f) => f.status === 'open').sort(byRisk)[0];
    expect(expected.risk).toBe('high');
    const { state, plan } = createDetailState(a);
    expect(state.focus).toEqual({ kind: 'finding', id: expected.id });
    expect(state.docId).toBe(expected.docId);
    expect(state.page).toBe(expected.page);
    expect(state.tab).toBe('findings');
    expect(state.mTab).toBe('doc');
    expect(plan.viewer).toBe(expected.anchors[0]);
    expect(plan.card).toBe(expected.id);
  });

  it('고를 항목이 없으면 첫 문서 1쪽, 맨 위로', async () => {
    const a = await analysis('A3');
    const { state, plan } = createDetailState(a);
    expect(state.focus).toBeNull();
    expect(state.docId).toBe(a.docs[0].id);
    expect(state.page).toBe(1);
    expect(plan.viewer).toBe(SCROLL_TOP);
    expect(plan.card).toBeUndefined();
  });

  it('미확인 상 등급이 없으면 고르지 않는다(A5 — 모두 확인함)', async () => {
    const a = await analysis('A5');
    expect(autoFocus(a)).toBeNull();
  });

  it('initial 이 있으면 저절로 고르지 않고 initial.focus 의 문서·쪽을 연다(원본 initScenario)', async () => {
    const a = await analysis('A1');
    expect(createDetailState(a, { mTab: 'docs' }).state.focus).toBeNull();
    const review = createDetailState(a, { tab: 'review', focus: { kind: 'item', id: 'R-01', idx: 0 } });
    expect(review.state).toMatchObject({ tab: 'review', docId: 'd3', page: 2 });
    expect(review.plan.viewer).toBe('d3p2-blur');
    expect(review.plan.card).toBe('R-01');
    const links = createDetailState(a, { tab: 'links', focus: { kind: 'link', id: 'L-01', idx: 1 } });
    expect(links.state).toMatchObject({ tab: 'links', docId: 'd2', page: 1 });
    expect(focusAnchors(a, links.state.focus)).toEqual(['d2p1-appno', 'd2p1-name', 'd2p1-total']);
    /* 위치 없는 항목은 원문 스크롤 대상이 없다(맨 위로 가지 않음) */
    const noLoc = createDetailState(a, { focus: { kind: 'finding', id: 'F-23' } });
    expect(noLoc.state).toMatchObject({ docId: 'd3', page: 2 });
    expect(noLoc.plan.viewer).toBeUndefined();
  });

  it('initial.docId 는 그 문서 1쪽(원본 focusDoc), 모달 자리도 그대로 받는다', async () => {
    const a = await analysis('A4');
    const { state } = createDetailState(a, { docId: 't2', tab: 'review' });
    expect(state).toMatchObject({ docId: 't2', page: 1, tab: 'review', focus: null });
    const withModal = createDetailState(a, { modal: { type: 'complete', note: '', error: '' } });
    expect(withModal.state.modal).toEqual({ type: 'complete', note: '', error: '' });
  });
});

describe('리듀서', () => {
  it('apply 는 patch 를 붙이고 pulse 면 선택 신호 번호를 올린다', async () => {
    const a = await analysis('A1');
    const s0 = createDetailState(a, {}).state;
    const s1 = detailReducer(s0, { type: 'apply', patch: { tab: 'review' } });
    expect(s1.tab).toBe('review');
    expect(s1.pulse).toBe(0);
    const s2 = detailReducer(s1, { type: 'apply', patch: {}, pulse: true });
    expect(s2.pulse).toBe(1);
  });

  it('모달 자리 — 열기 · 입력값 바꾸기(종류는 그대로) · 닫기', async () => {
    const a = await analysis('A1');
    const s0 = createDetailState(a, {}).state;
    const s1 = detailReducer(s0, { type: 'openModal', modal: { type: 'memo', note: '', error: '' } });
    const s2 = detailReducer(s1, { type: 'patchModal', patch: { note: '메모' } });
    expect(s2.modal).toEqual({ type: 'memo', note: '메모', error: '' });
    expect(detailReducer(s2, { type: 'closeModal' }).modal).toBeNull();
    expect(detailReducer(s0, { type: 'patchModal', patch: { note: 'x' } })).toBe(s0);
  });
});

describe('선택 · 이동 계획 — 원본 상세 동작', () => {
  const base = async (patch: Partial<DetailUiState> = {}) => {
    const a = await analysis('A1');
    return { a, s: { ...createDetailState(a, {}).state, ...patch } };
  };

  it('pickDoc — 그 문서 1쪽, 맨 위로, 휴대폰이면 원문 탭', () => {
    expect(planPickDoc('d2', false)).toEqual({ patch: { docId: 'd2', page: 1 }, viewer: SCROLL_TOP });
    expect(planPickDoc('d2', true).patch.mTab).toBe('doc');
  });

  it('하이라이트에서 고르면(fromDoc) 탐지 항목 탭 · 필터에 걸리면 전체 · 그 행으로 스크롤 · 원문 위치로', async () => {
    const { a, s } = await base({ tab: 'links', fFilter: 'high' });
    const f = a.findings.find((x) => x.id === 'F-03');
    expect(f?.risk).toBe('medium');
    const plan = planPickFinding(s, a, 'F-03', { fromDoc: true }, false);
    expect(plan?.patch).toMatchObject({ tab: 'findings', fFilter: 'all', focus: { kind: 'finding', id: 'F-03' }, docId: 'd1', page: 1 });
    expect(plan?.card).toBe('F-03');
    expect(plan?.viewer).toBe('d1p1-phone');
    expect(plan?.pulse).toBe(true);
    /* 휴대폰: 탐지 결과 탭으로, 원문은 스크롤하지 않음 */
    const mobile = planPickFinding(s, a, 'F-03', { fromDoc: true }, true);
    expect(mobile?.patch.mTab).toBe('results');
    expect(mobile?.viewer).toBeUndefined();
    /* 보이는 필터면 그대로 */
    expect(planPickFinding({ ...s, fFilter: 'medium' }, a, 'F-03', { fromDoc: true }, false)?.patch.fFilter).toBeUndefined();
  });

  it('행 머리를 다시 누르면 접는다 · 원문 확인은 휴대폰이면 원문 탭', async () => {
    const { a, s } = await base({ focus: { kind: 'finding', id: 'F-03' } });
    expect(planPickFinding(s, a, 'F-03', { toggle: true }, false)?.patch).toEqual({ focus: null });
    expect(planPickFinding(s, a, 'F-03', { reveal: true }, true)?.patch.mTab).toBe('doc');
    expect(planPickFinding(s, a, 'F-03', { reveal: true }, false)?.patch.mTab).toBeUndefined();
    expect(planPickFinding(s, a, 'F-404', {}, false)).toBeNull();
  });

  it('위치 없는 항목은 맨 위로 · 검토사항 근거가 그 항목을 가리키면 그 항목을 고른다', async () => {
    const { a, s } = await base();
    expect(planPickFinding(s, a, 'F-23', {}, false)?.viewer).toBe(SCROLL_TOP);
    const ev = planPickItemEvidence(a, 'R-05', 0, false, true);
    expect(ev?.patch).toMatchObject({ focus: { kind: 'finding', id: 'F-23' }, docId: 'd3', page: 2, mTab: 'doc' });
    expect(ev?.viewer).toBe(SCROLL_TOP);
  });

  it('pickItem — 검토 필요 탭, 그 행으로, 첫 근거 위치(근거가 없으면 맨 위)', async () => {
    const { a } = await base();
    const r1 = planPickItem(a, 'R-03', true);
    expect(r1?.patch).toMatchObject({ tab: 'review', focus: { kind: 'item', id: 'R-03', idx: 0 }, docId: 'd1', page: 1 });
    expect(r1?.patch.mTab).toBeUndefined();
    expect(r1?.card).toBe('R-03');
    expect(r1?.viewer).toBe('d1p1-phone');
    const r4 = planPickItem(a, 'R-04', false);
    expect(r4?.patch).toMatchObject({ tab: 'review', focus: { kind: 'item', id: 'R-04', idx: null }, docId: 'd3', page: 1 });
    expect(r4?.viewer).toBe(SCROLL_TOP);
  });

  it('pickLinkDoc · openLink — 연결 문서의 근거 위치, openLink 는 연결 탭과 첫 문서', async () => {
    const { a } = await base();
    const d = planPickLinkDoc(a, 'L-02', 1, false, true);
    expect(d?.patch).toMatchObject({ focus: { kind: 'link', id: 'L-02', idx: 1 }, docId: 'd3', page: 1, mTab: 'doc' });
    expect(d?.viewer).toBe('d3p1-holder');
    const o = planOpenLink(a, 'L-02', true);
    expect(o?.patch).toMatchObject({ tab: 'links', focus: { kind: 'link', id: 'L-02', idx: 0 }, docId: 'd1' });
    expect(o?.patch.mTab).toBeUndefined();
    expect(o?.card).toBe('L-02');
  });

  it('goPending — 미해결 검토사항이 먼저, 모달을 닫는다', async () => {
    const svc = createService();
    const a = (await svc.get('A1')) as Analysis;
    const s = { ...createDetailState(a, {}).state, modal: { type: 'complete', note: '', error: '' } as const };
    const plan = planGoPending(s, a, await svc.pending('A1'), false);
    expect(plan.patch.modal).toBeNull();
    expect(plan.patch.tab).toBe('review');
    expect(plan.card).toBe((await svc.pending('A1')).openI[0].id);
  });

  it('확대 배율은 0.1 단위 · 0.4~2 배', () => {
    expect(normalizeZoom(0.94)).toBe(0.9);
    expect(normalizeZoom(0.31)).toBe(0.4);
    expect(normalizeZoom(2.07)).toBe(2);
    expect(normalizeZoom(1.25)).toBe(1.3);
  });

  it('왼쪽 목록 — 기본은 데스크톱만 펼침, 누르면 그 값', async () => {
    const { s } = await base();
    expect(resolveLeftOpen(s, true)).toBe(true);
    expect(resolveLeftOpen(s, false)).toBe(false);
    expect(resolveLeftOpen({ ...s, leftOpen: true }, false)).toBe(true);
  });

  it('데모 대기 건(detail-queued)은 문서만 있고 고를 것이 없다', async () => {
    const svc = createService();
    const { analysisId } = await getDemoControls(svc)!.prepare('detail-queued');
    const a = (await svc.get(analysisId!)) as Analysis;
    const { state, plan } = createDetailState(a);
    expect(state.focus).toBeNull();
    expect(state.docId).toBe(a.docs[0].id);
    expect(plan.viewer).toBe(SCROLL_TOP);
  });
});

describe('마스킹 미리보기 — 항목별 가림', () => {
  const open = { id: 'F-01', status: 'open' };
  const fp = { id: 'F-10', status: 'false_positive' };

  it('처음에는 고른 값이 없고, 오탐이 아닌 항목만 가린다', async () => {
    const a = await analysis('A1');
    expect(createDetailState(a).state.maskPick).toEqual({});
    expect(maskPicked({}, open)).toBe(true);
    expect(maskPicked({}, fp)).toBe(false);
  });

  it('고른 값이 기본값보다 먼저 — 오탐도 가릴 수 있고, 오탐이 아닌 항목도 보이게 할 수 있다', () => {
    expect(maskPicked({ 'F-01': false }, open)).toBe(false);
    expect(maskPicked({ 'F-10': true }, fp)).toBe(true);
    // 다른 항목의 값은 상관없다 · 객체 기본 속성 이름도 고른 값으로 보지 않는다
    expect(maskPicked({ 'F-02': false }, open)).toBe(true);
    expect(maskPicked({}, { id: 'constructor', status: 'open' })).toBe(true);
  });

  it('하나 뒤집기 — 지금 값의 반대를 남기고, 원래 값은 바꾸지 않는다', () => {
    const before = {};
    const once = toggledMaskPick(before, open);
    expect(once).toEqual({ 'F-01': false });
    expect(before).toEqual({});
    expect(toggledMaskPick(once, open)).toEqual({ 'F-01': true });
    expect(toggledMaskPick({}, fp)).toEqual({ 'F-10': true });
  });

  it('한꺼번에 — 준 ID 만 그 값으로, 나머지 고른 값은 그대로', () => {
    const pick = { 'F-01': false, 'F-03': true };
    expect(withMaskPick(pick, ['F-01', 'F-02'], true)).toEqual({ 'F-01': true, 'F-02': true, 'F-03': true });
    expect(withMaskPick(pick, ['F-03'], false)).toEqual({ 'F-01': false, 'F-03': false });
    expect(withMaskPick(pick, [], false)).toEqual(pick);
    expect(pick).toEqual({ 'F-01': false, 'F-03': true });
  });

  it('리듀서 apply 로 고른 값을 바꾼다(다른 화면 상태는 그대로)', async () => {
    const a = await analysis('A1');
    const s = createDetailState(a).state;
    const next = detailReducer(s, { type: 'apply', patch: { maskPick: toggledMaskPick(s.maskPick, open) } });
    expect(next.maskPick).toEqual({ 'F-01': false });
    expect({ ...next, maskPick: {} }).toEqual(s);
  });
});
