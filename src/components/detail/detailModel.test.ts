import { describe, expect, it } from 'vitest';
import { FSTATUS, RISK } from '@/display/rules';
import { createService, getDemoControls } from '@/services';
import type { Analysis } from '@/services/types';
import { analysisDoneText } from './AnalysisDoneToast';
import {
  bannerModel,
  collectAnchors,
  detailFacts,
  docModels,
  failModel,
  fitZoom,
  headerModel,
  mobileTabs,
  placeholderModel,
  resultsModel,
  viewerModel,
  waitingModel,
  type SegmentModel,
  type ViewerMetrics,
} from './detailModel';
import { createDetailState, type DetailUiState } from './detailState';

async function analysis(id: string): Promise<Analysis> {
  const a = await createService().get(id);
  if (!a) throw new Error('분석 건 없음: ' + id);
  return a;
}

const M: ViewerMetrics = { width: 760 + 48 + 6, padX: 24, paperW: 760 };

function stateOf(a: Analysis, patch: Partial<DetailUiState> = {}): DetailUiState {
  return { ...createDetailState(a, {}).state, ...patch };
}

/** 블록 모델에서 조각을 모두 꺼낸다 */
function allSegs(v: ReturnType<typeof viewerModel>): SegmentModel[] {
  const out: SegmentModel[] = [];
  v.blocks.forEach((b) => {
    if (b.t === 'kv') b.items.forEach((it) => out.push(...it.segs));
    if (b.t === 'table') b.rows.forEach((r) => r.forEach((c) => out.push(...c.segs)));
    if (b.t === 'p' || b.t === 'foot') out.push(...b.segs);
    if (b.t === 'sign') b.items.forEach((it) => out.push(...it.segs));
    if (b.t === 'stamp') b.lines.forEach((l) => out.push(...l));
  });
  return out;
}

describe('원문 위치 모으기 — 원본 collectAnchors', () => {
  it('블록 순서대로 위치 ID 를 모은다(판독 불가 · 잘림 포함)', async () => {
    const a = await analysis('A1');
    const d1 = a.docs.find((d) => d.id === 'd1')!;
    const p1 = collectAnchors(d1.pages![0]);
    expect(p1[0]).toBe('d1p1-appno');
    expect(p1).toContain('d1p1-rrn');
    expect(p1[p1.length - 1]).toBe('d1p1-formno');
    expect(collectAnchors(d1.pages![1])).toEqual(['d1p2-sign', 'd1p2-staff', 'd1p2-cut']);
  });
});

describe('원문 뷰어 모델', () => {
  it('고른 탐지 위치만 테두리 · 이름표는 처음 위치 하나 · 색은 ② 위험 색', async () => {
    const a = await analysis('A1');
    const s = stateOf(a, { focus: { kind: 'finding', id: 'F-03' }, docId: 'd1', page: 1 });
    const v = viewerModel(a, s, detailFacts(a, s), M);
    const hls = allSegs(v).filter((x): x is Extract<SegmentModel, { kind: 'hl' }> => x.kind === 'hl');
    const on = hls.filter((x) => x.on);
    expect(on.map((x) => x.anchor)).toEqual(['d1p1-phone']);
    expect(on[0].tag).toBe(true);
    expect(on[0].vars.pc).toBe(RISK.medium.solid);
    expect(v.tag).toEqual({ text: 'F-03 · 연락처·이메일 · 보통', bg: RISK.medium.tag });
    expect(hls.filter((x) => x.tag)).toHaveLength(1);
    expect(on[0].aria).toBe('F-03 연락처·이메일 보통 — 탐지 항목 보기');
  });

  it('오탐 항목은 fp, 마스킹 미리보기는 마스킹 값(오탐은 원래 값)', async () => {
    const a = await analysis('A1');
    const s = stateOf(a, { focus: null, docId: 'd1', page: 1, mask: true });
    const v = viewerModel(a, s, detailFacts(a, s), M);
    const hls = allSegs(v).filter((x): x is Extract<SegmentModel, { kind: 'hl' }> => x.kind === 'hl');
    const rrn = hls.find((x) => x.anchor === 'd1p1-rrn')!;
    expect(rrn.shown).toBe('920314-2******');
    const fp = hls.find((x) => x.findingId === 'F-10')!;
    expect(fp.fp).toBe(true);
    expect(fp.shown).toBe(fp.text);
    expect(v.notices.map((n) => n.title)).toContain('마스킹 미리보기');
    // 데모에는 원본 파일이 없다 — '가린 PDF 내려받기' 버튼 없음
    expect(v.notices.find((n) => n.title === '마스킹 미리보기')?.action).toBeUndefined();
    expect(v.noMask).toBe(false);
  });

  it('마스킹 미리보기 — 항목별 가림: 보이게 고른 항목은 원래 값, 오탐도 가리게 고르면 마스킹 값 · 누름 상태와 이름', async () => {
    const a = await analysis('A1');
    const s = stateOf(a, { focus: null, docId: 'd1', page: 1, mask: true, maskPick: { 'F-01': false, 'F-10': true } });
    const v = viewerModel(a, s, detailFacts(a, s), M);
    expect(v.maskPicking).toBe(true);
    const hls = allSegs(v).filter((x): x is Extract<SegmentModel, { kind: 'hl' }> => x.kind === 'hl');
    // 같은 위치를 기본 선택(고른 값 없음)으로 본 값 — 오탐이 아닌 F-01 은 마스킹 값, 오탐 F-10 은 원래 값
    const base = viewerModel(a, { ...s, maskPick: {} }, detailFacts(a, s), M);
    const baseHls = allSegs(base).filter((x): x is Extract<SegmentModel, { kind: 'hl' }> => x.kind === 'hl');
    const rrn = hls.find((x) => x.anchor === 'd1p1-rrn')!;
    const rrnMasked = baseHls.find((x) => x.anchor === 'd1p1-rrn')!.shown;
    expect(rrn).toMatchObject({ findingId: 'F-01', pressed: false, aria: 'F-01 고유식별정보 높음 — 가리기' });
    // 보이게 고름 — 원래 값 그대로(가림 글자 없음), 마스킹 값과 다르다
    expect(rrn.shown).toBe(rrn.text);
    expect(rrn.shown).not.toContain('*');
    expect(rrn.shown).not.toBe(rrnMasked);
    expect(rrnMasked).toContain('*');
    const fp = hls.find((x) => x.findingId === 'F-10')!;
    expect(fp).toMatchObject({ fp: true, pressed: true });
    // 오탐을 가리게 고름 — 원래 값이 아니라 마스킹 값(가림 글자)
    const fpBase = baseHls.find((x) => x.anchor === fp.anchor)!;
    expect(fpBase.shown).toBe(fp.text);
    expect(fp.shown).not.toBe(fp.text);
    expect(fp.shown).toContain('*');
    // 고르지 않은 항목은 기본값(가림)
    expect(hls.filter((x) => x.findingId !== 'F-01' && x.findingId !== 'F-10').every((x) => x.pressed === true)).toBe(true);
    // 미리보기를 끄면 고른 값과 관계없이 원래 값 · 누름 상태 없음 · 이름은 '탐지 항목 보기'
    const off = viewerModel(a, { ...s, mask: false }, detailFacts(a, s), M);
    expect(off.maskPicking).toBe(false);
    const offHls = allSegs(off).filter((x): x is Extract<SegmentModel, { kind: 'hl' }> => x.kind === 'hl');
    expect(offHls.every((x) => x.shown === x.text && !('pressed' in x))).toBe(true);
    expect(offHls.find((x) => x.anchor === 'd1p1-rrn')!.aria).toBe('F-01 고유식별정보 높음 — 탐지 항목 보기');
  });

  it('검토사항 근거는 표시(mark) — 판독 불가 블록 테두리 · 주황 이름표', async () => {
    const a = await analysis('A1');
    const s = stateOf(a, { focus: { kind: 'item', id: 'R-01', idx: 0 }, docId: 'd3', page: 2 });
    const v = viewerModel(a, s, detailFacts(a, s), M);
    const blur = v.blocks.find((b) => b.t === 'blur');
    expect(blur && blur.t === 'blur' && blur.on && blur.tag).toBe(true);
    expect(v.tag.text).toBe('R-01 · 판독 불가');
    expect(v.tag.bg).toBe('var(--warn)');
  });

  it('위치 없는 항목 — 강조 대신 공지(근거 문구 · 쪽)', async () => {
    const a = await analysis('A1');
    const s = stateOf(a, { focus: { kind: 'finding', id: 'F-23' }, docId: 'd3', page: 2 });
    const v = viewerModel(a, s, detailFacts(a, s), M);
    expect(v.notices[0].title).toBe('위치 확인 필요 · F-23 고유식별정보');
    expect(v.notices[0].text).toContain('2쪽에서 근거 문구 “본인확인 920314-2…”를 직접 찾아 확인해 주세요.');
    expect(allSegs(v).some((x) => x.kind !== 'plain' && 'on' in x && x.on)).toBe(false);
  });

  it('쪽 이동 · 확대 · 맞춤 값', async () => {
    const a = await analysis('A1');
    const s = stateOf(a, { focus: null, docId: 'd1', page: 2, zoom: 0.4 });
    const v = viewerModel(a, s, detailFacts(a, s), M);
    expect(v.pageLabel).toBe('2 / 2');
    expect(v).toMatchObject({ noPrev: false, noNext: true, zoomLabel: '40%', noOut: true, noIn: false, isFit: false });
    expect(fitZoom(M)).toBe(1);
    expect(fitZoom({ width: 400, padX: 12, paperW: 760 })).toBeCloseTo((400 - 24 - 6) / 760);
    expect(fitZoom({ width: 3000, padX: 24, paperW: 760 })).toBe(1.5);
    const fit = viewerModel(a, { ...s, zoom: null }, detailFacts(a, s), { width: 600, padX: 24, paperW: 760 });
    expect(fit.zoomLabel).toBe(Math.round(Math.round(((600 - 54) / 760) * 100)) + '%');
    expect(fit.isFit).toBe(true);
  });

  it('분석 중 문서는 미리보기 대신 화면 · 끝난 문서는 탐지 위치 표시 전 공지(A3)', async () => {
    const a = await analysis('A3');
    const running = stateOf(a, { docId: 'n2' });
    expect(viewerModel(a, running, detailFacts(a, running), M).placeholder?.title).toBe('원문 미리보기를 준비하고 있습니다');
    const queued = stateOf(a, { docId: 'n3' });
    expect(placeholderModel(a, a.docs[2], false)?.title).toBe('분석 대기 중인 문서입니다');
    expect(viewerModel(a, queued, detailFacts(a, queued), M).hasPage).toBe(false);
    const done = stateOf(a, { docId: 'n1' });
    const v = viewerModel(a, done, detailFacts(a, done), M);
    expect(v.hasPage).toBe(true);
    expect(v.showFind).toBe(false);
    expect(v.notices.map((n) => n.title)).toEqual(['탐지 위치 표시 전']);
    expect(allSegs(v).every((x) => x.kind === 'plain')).toBe(true);
  });

  it('실패 문서 — 다시 분석 행동 · 안내(A4 t2)', async () => {
    const a = await analysis('A4');
    const ph = placeholderModel(a, a.docs[1], false);
    expect(ph).toMatchObject({ tone: 'err', title: '이 문서는 분석하지 못했습니다', note: '다시 스캔한 파일은 새 분석으로 올려 주세요.' });
    expect(ph?.action).toMatchObject({ key: 'retryDoc', label: '이 문서 다시 분석', disabled: false });
  });
});

describe('머리글 · 띠 · 문서 목록 · 휴대폰 탭', () => {
  it('A1 — 진행, 문서 목록 건수 · 높음', async () => {
    const a = await analysis('A1');
    const s = stateOf(a);
    const x = detailFacts(a, s);
    const h = headerModel(a, x);
    expect(h).toMatchObject({ docCount: 3, pageTotalText: '5페이지', date: '2026.10.30 14:22', code: 'DG-20261030-0007', hasProgress: true, showComplete: true, noReport: false });
    expect(h.progress.total).toBe(23);
    expect(bannerModel(a, x)).toBeNull();
    const docs = docModels(a, x);
    expect(docs[0]).toMatchObject({ idx: 1, title: '개인 여신거래 신청서', ext: 'PDF', meta: '2페이지 · 1.2MB', hasCount: true });
    expect(docs[0].railLabel).toBe('1번 문서 개인 여신거래 신청서, 완료');
    expect(mobileTabs(a, x).map((t) => t.label)).toEqual(['원문', '탐지 결과 23', '문서 3']);
  });

  it('A3 분석 중 — 흐르는 막대 띠 · 보고서 막힘 · 기다림 안내', async () => {
    const a = await analysis('A3');
    const x = detailFacts(a, stateOf(a));
    expect(bannerModel(a, x)).toMatchObject({ variant: 'running', title: '분석 중입니다 · 문서 3개 중 1개 완료' });
    expect(headerModel(a, x)).toMatchObject({ noReport: true, noComplete: true, hasProgress: false, pageTotalText: '3페이지' });
    expect(waitingModel(a, x)).toMatchObject({ queued: false, title: '분석 중', sub: '문서 3개 중 1개 완료', demo: false });
    expect(mobileTabs(a, x)[1].label).toBe('분석 결과');
  });

  it('A4 일부 실패 · A5 검토 완료 · A6 전체 실패', async () => {
    const a4 = await analysis('A4');
    const b4 = bannerModel(a4, detailFacts(a4, stateOf(a4)));
    expect(b4?.title).toBe('문서 3개 중 1개를 분석하지 못했습니다.');
    expect(b4?.actions.map((x) => x.label)).toEqual(['실패 문서 보기', '실패 문서 다시 분석']);
    const a5 = await analysis('A5');
    const x5 = detailFacts(a5, stateOf(a5));
    expect(bannerModel(a5, x5)).toMatchObject({ variant: 'done', title: '검토 완료 · 이지은 · 2026.10.29 09:12' });
    expect(headerModel(a5, x5)).toMatchObject({ showComplete: false, showReopen: true });
    const a6 = await analysis('A6');
    const f6 = failModel(a6, detailFacts(a6, stateOf(a6)));
    expect(f6?.title).toBe('분석에 실패했습니다');
    expect(f6?.files).toHaveLength(1);
    expect(failModel(a5, x5)).toBeNull();
  });

  it('데모 대기 건 — 직접 올린 파일 안내 · 샘플로 체험하기', async () => {
    const svc = createService();
    const { analysisId } = await getDemoControls(svc)!.prepare('detail-queued');
    const a = (await svc.get(analysisId!)) as Analysis;
    const x = detailFacts(a, stateOf(a));
    const b = bannerModel(a, x);
    expect(b?.variant).toBe('info');
    expect(b?.actions[0]).toMatchObject({ key: 'trySample', label: '샘플 문서로 체험하기' });
    expect(waitingModel(a, x)?.demo).toBe(true);
    expect(placeholderModel(a, a.docs[0], false)?.action?.key).toBe('trySample');
  });
});

describe('결과 패널 모델', () => {
  it('탭 건수 · 필터 칩 · 위험 순 정렬 · 현재 문서만', async () => {
    const a = await analysis('A1');
    const s = stateOf(a, { focus: null });
    const x = detailFacts(a, s);
    const rs = resultsModel(a, s, x);
    expect(rs.tabs.map((t) => [t.label, t.count])).toEqual([
      ['탐지 항목', 23],
      ['검토 필요', 5],
      ['문서 간 연결', 3],
    ]);
    expect(rs.chips[0]).toEqual({ value: 'all', label: '전체', count: 23 });
    // 필터 칩: 키 · 순서는 원본 그대로, 상태 · 위험등급 라벨은 ② 표시 규칙에서 가져온다(문구는 그대로)
    expect(rs.chips.map((c) => c.value)).toEqual(['all', 'open', 'high', 'medium', 'low']);
    expect(rs.chips.slice(1).map((c) => c.label)).toEqual([FSTATUS.open.label, RISK.high.label, RISK.medium.label, RISK.low.label]);
    expect(rs.chips.map((c) => c.label)).toEqual(['전체', '미확인', '높음', '보통', '낮음']);
    expect(rs.chips.map((c) => c.count)).toEqual([23, 20, 3, 11, 9]);
    expect(rs.findings[0].risk.key).toBe('high');
    expect(rs.shownText).toMatch(/^23건 표시 · 확인 \d+\/23$/);
    const only = resultsModel(a, { ...s, onlyDoc: true, docId: 'd2' }, detailFacts(a, { docId: 'd2' }));
    expect(only.findings.every((f) => f.where.startsWith('근로소득 원천징수영수증'))).toBe(true);
    const high = resultsModel(a, { ...s, fFilter: 'high' }, x);
    expect(high.findings.every((f) => f.risk.key === 'high')).toBe(true);
  });

  it('펼친 행 — 오탐 사유 · 바뀐 분류 · 위치 확인 필요', async () => {
    const a = await analysis('A1');
    const s = stateOf(a, { focus: { kind: 'finding', id: 'F-10' } });
    const rs = resultsModel(a, s, detailFacts(a, s));
    const fp = rs.findings.find((f) => f.id === 'F-10')!;
    expect(fp).toMatchObject({ open: true, fp: true, noteLabel: '오탐 사유', canRestore: true, canFp: false, changed: true });
    expect(fp.aiText.endsWith('(오탐 표시 전)')).toBe(true);
    const re = rs.findings.find((f) => f.id === 'F-12')!;
    expect(re).toMatchObject({ noteLabel: '수정 사유', changed: true });
    const noLoc = rs.findings.find((f) => f.id === 'F-23')!;
    expect(noLoc.noLoc).toBe(true);
    expect(noLoc.locText).toBe('급여계좌 거래내역서 2쪽 · 좌표 없음 (위치 확인 필요)');
  });

  it('검토 필요 — 유지 안내(A4) · 미해결 먼저', async () => {
    const a = await analysis('A4');
    const s = stateOf(a, { tab: 'review' });
    const rs = resultsModel(a, s, detailFacts(a, s));
    expect(rs.keep).toMatch(/^이미 발견한 고위험 정보 \d+건은/);
    expect(rs.items[0]).toMatchObject({ id: 'S-01', canRetry: true, retryLabel: '다시 분석' });
    expect(rs.nOpen).toBe(2);
  });

  it('문서 간 연결 — 고른 문서 · 판단 버튼', async () => {
    const a = await analysis('A1');
    const s = stateOf(a, { tab: 'links', focus: { kind: 'link', id: 'L-02', idx: 1 } });
    const rs = resultsModel(a, s, detailFacts(a, s));
    const l2 = rs.links.find((l) => l.id === 'L-02')!;
    expect(l2.sel).toBe(true);
    expect(l2.docs.map((d) => d.on)).toEqual([false, true]);
    expect(l2.canDecide).toBe(true);
    expect(l2.docs[1].aria).toBe('급여계좌 거래내역서 1쪽 근거 보기');
    expect(rs.links.find((l) => l.id === 'L-01')!.canDecide).toBe(false);
  });
});

describe('분석 완료 알림 문구 — 원본 onServiceEvent', () => {
  it('이름 · 탐지 · 검토사항 건수', () => {
    expect(analysisDoneText({ type: 'done', id: 'A115', name: '샘플 대출상담 서류', findings: 23, items: 5 })).toBe('분석이 끝났습니다 · 샘플 대출상담 서류 — 탐지 23건, 검토사항 5건');
  });
});
