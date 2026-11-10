/* 실제 분석 상세 — 검토 필요 탭(서버가 계산한 검토사항). 고정 자료(fixtures/items-result.json) + 검토 기록 → toAnalysis → 화면 모델.
   탭 · 검토사항 행 · 근거 누르기(위치 상자 강조 · 이름표 · 탐지 항목 고르기 · item 안내) · 막힘 · 빈 화면 · 남은 항목 · 해결 모달.
   원문 값(근거 문구)은 테스트 출력에 옮기지 않는다. */
import { describe, expect, it, vi } from 'vitest';
import { RTYPE } from '@/display/rules';
import { completeModel, applyReviewModal, reviewModalModel } from '@/components/modals/reviewModalModel';
import type { AnalysisService, Pending } from '@/services/analysis-service';
import { createService } from '@/services';
import { toAnalysis } from '@/services/api/mapping';
import { analysisOut, contractResult, itemsResult } from '@/services/api/testing';
import type { Analysis } from '@/services/types';
import { ITEMS_EMPTY_TEXT, detailFacts, docName, resultsModel, viewerModel, type ViewerMetrics } from './detailModel';
import { SCROLL_TOP, createDetailState, planGoPending, planPickItem, planPickItemEvidence, type DetailPlan, type DetailUiState } from './detailState';

const M: ViewerMetrics = { width: 760 + 48 + 6, padX: 24, paperW: 760 };
const AT = '2026-11-04T01:02:00+00:00';

function review(items: Record<string, unknown> = {}, patch: Record<string, unknown> = {}) {
  return { status: 'needed', memo: '', memo_at: null, reviewer: '', reviewed_at: null, completion_note: '', findings: {}, items, history: [], version: 0, ...patch };
}

function liveAnalysis(opts: { items?: Record<string, unknown>; review?: unknown; edit?: (r: Record<string, unknown>) => void; result?: Record<string, unknown> } = {}): Analysis {
  const result = opts.result ?? itemsResult();
  opts.edit?.(result);
  const rv = opts.review !== undefined ? opts.review : review(opts.items);
  return toAnalysis(analysisOut({ status: 'done', result, upstage_job_id: 'job_test', upstage_status: 'completed', review: structuredClone(rv) }));
}

const stateOf = (a: Analysis, patch: Partial<DetailUiState> = {}): DetailUiState => ({ ...createDetailState(a).state, ...patch });
const applyPlan = (a: Analysis, plan: DetailPlan | null, base: Partial<DetailUiState> = {}): DetailUiState => {
  if (!plan) throw new Error('계획 없음');
  return { ...stateOf(a, base), ...plan.patch };
};
const viewer = (a: Analysis, s: DetailUiState) => viewerModel(a, s, detailFacts(a, s), M);
const results = (a: Analysis, s: DetailUiState = stateOf(a)) => resultsModel(a, s, detailFacts(a, s));
const docTitle = (a: Analysis, id: string) => docName(a.docs.find((d) => d.id === id));

describe('검토 필요 탭 — 실제 분석', () => {
  const a = liveAnalysis();

  it('탭 셋(탐지 항목 · 검토 필요 · 분석 요약) — 순서 · 라벨 · 개수(미해결 수) · 경고 색', () => {
    const rs = results(a);
    expect(rs.tabs.map((t) => [t.value, t.label, t.count, t.tone])).toEqual([
      ['findings', '탐지 항목', 19, 'default'],
      ['review', '검토사항', 8, 'warn'],
      ['summary', '분석 요약', undefined, 'default'],
    ]);
    const resolved = liveAnalysis({ items: { 'lowconf:0': { resolved: true }, 'other:5': { resolved: true } } });
    expect(results(resolved).tabs[1].count).toBe(6);
  });

  it('검토사항 행 — 종류 라벨 · 아이콘 · 제목 · 위치 글 · 할 일 · 근거 이름 · 버튼', () => {
    const rs = results(a);
    expect(rs.nOpen).toBe(8);
    expect(rs.nDone).toBe(0);
    expect(rs.keep).toBeNull();
    expect(rs.itemsLocked).toBe(false);
    expect(rs.items.map((i) => [i.id, i.type, i.icon])).toEqual([
      ['R-01', '인식 확인 필요', 'dg-i-eye-half'],
      ['R-02', '필수 항목 없음', 'dg-i-alert'],
      ['R-03', '위치 확인 필요', 'dg-i-pin-q'],
      ['R-04', '인식 확인 필요', 'dg-i-eye-half'],
      ['R-05', '인식 확인 필요', 'dg-i-eye-half'],
      ['R-06', '위치 확인 필요', 'dg-i-pin-q'],
      ['R-07', '인식 확인 필요', 'dg-i-eye-half'],
      ['R-08', '기타 서류', 'dg-i-file'],
    ]);
    const r1 = rs.items[0];
    expect(r1).toMatchObject({
      title: '인식 신뢰도가 낮은 항목 3건',
      desc: 'D1-06, D1-08, D1-09의 값이 틀렸을 수 있습니다.',
      next: '원본과 값을 비교해 확인해 주세요.',
      where: docTitle(a, 'doc-0') + ' · 1쪽',
      resolved: false,
      resolvedText: '',
      evidence: [{ label: '1쪽 값 보기' }],
      linkId: null,
      canRetry: false,
      retryDoc: null,
      canResolve: true,
      canReopen: false,
    });
    expect(rs.items[1]).toMatchObject({ title: '신청인 성명이 없습니다', where: docTitle(a, 'doc-1') + ' · 1쪽', evidence: [{ label: '1쪽 열기' }] });
    expect(rs.items[3].evidence).toEqual([]);
    expect(rs.items[7]).toMatchObject({ title: '기타 서류로 분류된 문서', where: docTitle(a, 'doc-5') + ' · 1쪽' });
  });

  it('해결한 항목 — 처리 글(처리자 · 서울 시각 · 처리 내용) · 다시 열기 버튼 · 미해결 뒤로', () => {
    const b = liveAnalysis({ items: { 'lowconf:0': { resolved: true, note: '원본 대조함', resolved_at: AT, resolved_by: '이지은' } } });
    const rs = results(b);
    expect(rs.nOpen).toBe(7);
    expect(rs.nDone).toBe(1);
    const last = rs.items[rs.items.length - 1];
    expect(last).toMatchObject({ id: 'R-01', resolved: true, canResolve: false, canReopen: true, resolvedText: '해결 · 이지은 · 2026.11.04 10:02 — 원본 대조함' });
    expect(rs.items.map((i) => i.id).slice(0, 2)).toEqual(['R-02', 'R-03']);
  });
});

describe('근거 누르기 · 검토사항 고르기 — 실제 분석 위치 상자 기준', () => {
  const a = liveAnalysis();

  it('lowconf 근거 → 그 서류 · 쪽, 근거 상자 셋을 검토사항 색으로 강조 · 첫 상자에 이름표 R-01 · 인식 확인 필요, item 안내 없음', () => {
    const plan = planPickItemEvidence(a, 'R-01', 0, false, false);
    expect(plan).toMatchObject({ patch: { focus: { kind: 'item', id: 'R-01', idx: 0 }, docId: 'doc-0', page: 1 }, pulse: true, viewer: 'D1-06#1' });
    const v = viewer(a, applyPlan(a, plan));
    const on = v.live?.boxes.filter((b) => b.on).map((b) => b.anchor);
    expect(on).toEqual(['D1-06#1', 'D1-08#1', 'D1-09#1']);
    expect(v.live?.boxes.filter((b) => b.tag).map((b) => b.anchor)).toEqual(['D1-06#1']);
    expect(v.tag).toEqual({ text: 'R-01 · ' + RTYPE.lowconf.label, bg: 'var(--warn)' });
    const box = v.live?.boxes.find((b) => b.anchor === 'D1-06#1');
    expect(box?.vars).toMatchObject({ onBg: 'var(--warn-focus)', pc: 'var(--warn-solid)', ph: 'var(--warn-halo)' });
    expect(v.notices.filter((n) => n.title.startsWith('R-'))).toEqual([]);
  });

  it('휴대폰이면 원문 탭으로(noReveal 이 아닐 때)', () => {
    expect(planPickItemEvidence(a, 'R-01', 0, false, true)?.patch.mTab).toBe('doc');
    expect(planPickItemEvidence(a, 'R-01', 0, true, true)?.patch.mTab).toBeUndefined();
  });

  it('nolocation 근거 → 그 탐지 항목(D3-02)을 고른다 — 위치 확인 필요 안내(탐지 항목)', () => {
    const plan = planPickItemEvidence(a, 'R-03', 0, false, false);
    expect(plan).toMatchObject({ patch: { focus: { kind: 'finding', id: 'D3-02' }, docId: 'doc-2', page: 1 }, viewer: SCROLL_TOP });
    const v = viewer(a, applyPlan(a, plan));
    const titles = v.notices.map((n) => n.title);
    expect(titles.some((t) => t.startsWith('위치 확인 필요 · D3-02'))).toBe(true);
    expect(v.live?.boxes.some((b) => b.on)).toBe(false);
    // R-06 도 같다(상자 0 인 항목)
    expect(planPickItemEvidence(a, 'R-06', 0, false, false)?.patch.focus).toEqual({ kind: 'finding', id: 'D5-03' });
  });

  it('missing 근거 → 그 서류 1쪽, 강조할 상자가 없어 item 안내(제목 R-02 · 필수 항목 없음, 글 = 할 일)', () => {
    const plan = planPickItemEvidence(a, 'R-02', 0, false, false);
    expect(plan).toMatchObject({ patch: { focus: { kind: 'item', id: 'R-02', idx: 0 }, docId: 'doc-1', page: 1 }, viewer: SCROLL_TOP });
    const v = viewer(a, applyPlan(a, plan));
    expect(v.notices.filter((n) => n.title.startsWith('R-'))).toEqual([{ tone: 'warn', icon: 'dg-i-alert', title: 'R-02 · 필수 항목 없음', text: '원본에서 직접 확인해 주세요.' }]);
    expect(v.live?.boxes.some((b) => b.on)).toBe(false);
    expect(v.tag.text).toBe('R-02 · 필수 항목 없음');
  });

  it('other 근거 → 기타 서류 1쪽, item 안내(R-08 · 기타 서류) + 기타 서류 안내', () => {
    const v = viewer(a, applyPlan(a, planPickItemEvidence(a, 'R-08', 0, false, false)));
    expect(v.live?.other).toBe(true);
    expect(v.notices.find((n) => n.title === 'R-08 · 기타 서류')).toEqual({ tone: 'warn', icon: 'dg-i-file', title: 'R-08 · 기타 서류', text: '원본에 개인정보가 있는지 직접 확인해 주세요.' });
    expect(v.notices.some((n) => n.title === '기타 서류 안내')).toBe(true);
  });

  it('근거가 없는 lowconf(R-04) — 고르면 검토 필요 탭 · 그 서류 1쪽 · item 안내', () => {
    const plan = planPickItem(a, 'R-04', false);
    expect(plan).toMatchObject({ patch: { tab: 'review', focus: { kind: 'item', id: 'R-04', idx: null }, docId: 'doc-2', page: 1 }, card: 'R-04', viewer: SCROLL_TOP });
    const v = viewer(a, applyPlan(a, plan));
    expect(v.notices.filter((n) => n.title.startsWith('R-')).map((n) => [n.title, n.text])).toEqual([['R-04 · 인식 확인 필요', '원본과 값을 비교해 확인해 주세요.']]);
  });

  it('검토사항 고르기 — 첫 근거로(R-05 → 상자 5개 강조, 그 카드로 스크롤)', () => {
    const plan = planPickItem(a, 'R-05', false);
    expect(plan).toMatchObject({ patch: { tab: 'review', focus: { kind: 'item', id: 'R-05', idx: 0 }, docId: 'doc-3' }, card: 'R-05', viewer: 'D4-03#1' });
    const v = viewer(a, applyPlan(a, plan));
    expect(v.live?.boxes.filter((b) => b.on)).toHaveLength(5);
    expect(results(a, applyPlan(a, plan)).items.find((i) => i.id === 'R-05')?.sel).toBe(true);
  });

  it('item 안내는 근거 상자가 그 쪽에 없을 때만 — 여러 쪽 서류의 다른 쪽에서는 안내', () => {
    const b = liveAnalysis({ edit: (r) => ((r.documents as Record<string, unknown>[])[0].page_end = 2) });
    const plan = planPickItemEvidence(b, 'R-01', 0, false, false);
    const onPage1 = viewer(b, applyPlan(b, plan));
    expect(onPage1.notices.some((n) => n.title.startsWith('R-01'))).toBe(false);
    const onPage2 = viewer(b, { ...applyPlan(b, plan), page: 2 });
    expect(onPage2.live?.filePage).toBe(2);
    expect(onPage2.notices.filter((n) => n.title.startsWith('R-01')).map((n) => n.text)).toEqual(['원본과 값을 비교해 확인해 주세요.']);
  });
});

describe('막힘 · 빈 화면', () => {
  it('검토 기록을 불러오지 못함(review null) — 검토사항은 보이고 해결 · 다시 열기가 막힌다', () => {
    const a = liveAnalysis({ review: null });
    const rs = results(a);
    expect(rs.readOnly).toBe(true);
    expect(rs.items).toHaveLength(8);
    expect(rs.itemsLocked).toBe(true);
  });

  it('검토 완료(잠김) — 해결 · 다시 열기가 막힌다', () => {
    const a = liveAnalysis({ review: review({ 'lowconf:0': { resolved: true } }, { status: 'done', reviewer: '이지은', reviewed_at: AT }) });
    const rs = results(a);
    expect(rs.locked).toBe(true);
    expect(rs.readOnly).toBe(false);
    expect(rs.itemsLocked).toBe(true);
  });

  it('검토사항 0개인 실제 분석 — 빈 화면은 제목만(설명 줄 없음)', () => {
    const a = liveAnalysis({ result: contractResult() });
    const rs = results(a);
    expect(rs.items).toEqual([]);
    expect(rs.itemsEmptyText).toBe('');
  });

  it('데모는 그대로 — 설명 줄 원문 · 막힘은 잠김과 같다', async () => {
    const svc = createService();
    for (const id of ['A1', 'A2', 'A3', 'A4', 'A5', 'A6']) {
      const d = await svc.get(id);
      if (!d) throw new Error(id);
      const rs = results(d);
      expect(rs.itemsEmptyText).toBe(ITEMS_EMPTY_TEXT);
      expect(rs.itemsLocked).toBe(rs.locked);
      expect(rs.tabs.map((t) => t.value)).toEqual(['findings', 'review', 'links']);
    }
    expect(ITEMS_EMPTY_TEXT).toBe('판독 실패, 잘린 페이지, 값 불일치, 연결 근거 부족 같은 문제가 발견되면 이곳에 표시됩니다.');
  });
});

describe('검토 완료 모달 · 남은 항목으로 가기 — 미해결 검토사항이 앞', () => {
  const pendingOf = (a: Analysis): Pending => {
    const openF = a.findings.filter((f) => f.status === 'open');
    const openI = a.items.filter((i) => !i.resolved);
    return { openF, openI, openL: [], any: openF.length + openI.length > 0 };
  };

  it('completeModel — 요약 줄(탐지 · 검토사항) · 바로가기 5개는 검토사항부터', () => {
    const a = liveAnalysis({ items: { 'lowconf:0': { resolved: true } } });
    const c = completeModel(a, pendingOf(a));
    expect(c.any).toBe(true);
    expect(c.lines).toEqual(['미확인 탐지 항목 19건 (위험등급 상 2건 포함)', '해결되지 않은 검토사항 7건']);
    expect(c.items).toHaveLength(5);
    expect(c.items[0]).toEqual({ id: 'R-02', label: '필수 항목 없음 · 신청인 성명이 없습니다', go: { kind: 'item', id: 'R-02' } });
    expect(c.items.every((i) => i.go.kind === 'item')).toBe(true);
  });

  it('탐지 항목을 모두 확인했어도 검토사항이 남으면 남은 항목 있음', () => {
    const findings = Object.fromEntries((itemsResult().findings as { id: string }[]).map((f) => [f.id, { status: 'confirmed' }]));
    const a = liveAnalysis({ review: { ...review(), findings } });
    const c = completeModel(a, pendingOf(a));
    expect(c.lines).toEqual(['해결되지 않은 검토사항 8건']);
    expect(c.any).toBe(true);
  });

  it('planGoPending — 모달을 닫고 첫 미해결 검토사항(R-01 → 해결하면 R-02)으로', () => {
    const a = liveAnalysis();
    const plan = planGoPending(stateOf(a), a, pendingOf(a), false);
    expect(plan).toMatchObject({ patch: { modal: null, tab: 'review', focus: { kind: 'item', id: 'R-01', idx: 0 }, docId: 'doc-0', page: 1 }, card: 'R-01', viewer: 'D1-06#1' });
    const b = liveAnalysis({ items: { 'lowconf:0': { resolved: true } } });
    expect(planGoPending(stateOf(b), b, pendingOf(b), false)).toMatchObject({ patch: { focus: { kind: 'item', id: 'R-02', idx: 0 }, docId: 'doc-1' }, card: 'R-02' });
  });
});

describe('해결 모달 — 실제 분석 검토사항', () => {
  const a = liveAnalysis();

  it('대상 카드 = 서버 글 제목 · 표시 번호 · 종류 · 서류 · 쪽', () => {
    const m = reviewModalModel(a, { type: 'resolve', rid: 'R-03', note: '', error: '' }, null);
    expect(m?.title).toBe('검토사항 해결로 표시');
    expect(m?.target).toEqual({ risk: null, title: '원문 위치가 없는 탐지 항목', id: 'R-03', value: null, meta: '위치 확인 필요 · ' + docTitle(a, 'doc-2') + ' 1쪽' });
    expect(reviewModalModel(a, { type: 'resolve', rid: 'R-99', note: '', error: '' }, null)).toBeNull();
  });

  it('저장 — 서비스 resolveItem(분석 id · 화면 번호 · 다듬은 처리 내용) + 토스트 문구', async () => {
    const resolveItem = vi.fn(async () => {});
    const svc = { resolveItem } as unknown as AnalysisService;
    const toast = await applyReviewModal(svc, a, { type: 'resolve', rid: 'R-03', note: '  원본에서 확인함 ', error: '' });
    expect(resolveItem).toHaveBeenCalledWith(a.id, 'R-03', '원본에서 확인함');
    expect(toast).toEqual({ text: '검토사항을 해결로 표시했습니다 · R-03' });
  });
});
