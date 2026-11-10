/* 실제 분석 상세 — 문서 간 연결 탭(최종 흐름 워크플로우 서류 대조 — 읽기 전용). 고정 자료(fixtures/final-flow-result.json, 손으로 만든 모양)
   + 검토 기록 → toAnalysis → 화면 모델 · 카드 마크업. 탭 3/4개 조건 · 탭 라벨 · 개수(데모와 같은 규칙) · 판단 버튼 · 설명 줄 숨김 ·
   검토사항 '연결 보기' → 연결 탭 · 근거 위치 강조 · 서류 종류 이름 · 기타 서류 대체 안내. 데모는 그대로. 원문 값은 테스트 출력에 옮기지 않는다. */
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { LSTATUS } from '@/display/rules';
import { createService } from '@/services';
import { toAnalysis } from '@/services/api/mapping';
import { analysisOut, contractResult, finalFlowResult, itemsResult } from '@/services/api/testing';
import type { Analysis } from '@/services/types';
import { READ_ONLY_ACTIONS } from './detailActions';
import { detailFacts, resultsModel, viewerModel, type ViewerMetrics } from './detailModel';
import { DETAIL_TABS, LIVE_DETAIL_TABS, LIVE_LINK_TABS, SCROLL_TOP, createDetailState, planOpenLink, planPickItem, planPickLinkDoc, type DetailPlan, type DetailUiState } from './detailState';
import { LinkCards } from './LinkCards';
import { ReviewItems } from './ReviewItems';

const M: ViewerMetrics = { width: 760 + 48 + 6, padX: 24, paperW: 760 };

function review(items: Record<string, unknown> = {}, patch: Record<string, unknown> = {}) {
  return { status: 'needed', memo: '', memo_at: null, reviewer: '', reviewed_at: null, completion_note: '', findings: {}, items, history: [], version: 0, ...patch };
}

function liveAnalysis(result: Record<string, unknown> = finalFlowResult(), rv: unknown = review()): Analysis {
  return toAnalysis(analysisOut({ status: 'done', result, upstage_job_id: 'job_test', upstage_status: 'completed', review: structuredClone(rv) }));
}

const stateOf = (a: Analysis, patch: Partial<DetailUiState> = {}): DetailUiState => ({ ...createDetailState(a).state, ...patch });
const applyPlan = (a: Analysis, plan: DetailPlan | null, base: Partial<DetailUiState> = {}): DetailUiState => {
  if (!plan) throw new Error('계획 없음');
  return { ...stateOf(a, base), ...plan.patch };
};
const results = (a: Analysis, s: DetailUiState = stateOf(a)) => resultsModel(a, s, detailFacts(a, s));
const viewer = (a: Analysis, s: DetailUiState) => viewerModel(a, s, detailFacts(a, s), M);
const anchorsOf = (a: Analysis, fid: string) => a.findings.find((f) => f.id === fid)?.anchors ?? [];

const INTRO = '문서 사이에서 같은 사람이나 같은 신청 건을 가리키는 정보를 찾았습니다.';

describe('실제 분석 — 탭 3/4개', () => {
  it('연결이 1개 이상이면 탐지 항목 · 검토 필요 · 문서 간 연결 · 분석 요약 — 라벨 · 개수(연결 수 — 데모 규칙) · 경고 색', () => {
    const a = liveAnalysis();
    expect(results(a).tabs.map((t) => [t.value, t.label, t.count, t.tone])).toEqual([
      ['findings', '탐지 항목', 7, 'default'],
      ['review', '검토사항', 8, 'warn'],
      ['links', '문서 간 연결', 3, 'default'],
      ['summary', '분석 요약', undefined, 'default'],
    ]);
    expect(results(a).tabs.map((t) => t.value)).toEqual([...LIVE_LINK_TABS]);
  });

  it('연결이 0개면(옛 결과 · links 빈 배열 · 모두 버림) 지금처럼 탭 셋', () => {
    const empty = finalFlowResult();
    empty.links = [];
    const broken = finalFlowResult();
    broken.links = (broken.links as Record<string, unknown>[]).map((l) => ({ ...l, status: 'linked' }));
    for (const a of [liveAnalysis(contractResult()), liveAnalysis(itemsResult()), liveAnalysis(empty), liveAnalysis(broken)]) {
      expect(a.links).toEqual([]);
      expect(results(a).tabs.map((t) => t.value)).toEqual([...LIVE_DETAIL_TABS]);
    }
  });

  it('데모는 그대로 — 탐지 항목 · 검토 필요 · 문서 간 연결', async () => {
    const a = await createService().get('A1');
    if (!a) throw new Error('A1 없음');
    expect(results(a).tabs.map((t) => t.value)).toEqual([...DETAIL_TABS]);
    expect(results(a).linksIntro).toBe(true);
  });
});

describe('실제 분석 — 연결 카드(읽기 전용)', () => {
  const a = liveAnalysis();

  it('상태 · 제목 · 서류(이름 · 형식 · 서류 안 쪽 · fields) · 근거 · 부족한 근거 · 확인할 내용, 판단 버튼 · 판단 결과 없음', () => {
    const rs = results(a, stateOf(a, { tab: 'links' }));
    expect(rs.linksIntro).toBe(false);
    expect(rs.links.map((l) => [l.id, l.status.label, l.canDecide, l.decided, l.decisionText])).toEqual([
      ['L-01', LSTATUS.check.label, false, false, ''],
      ['L-02', LSTATUS.confirmed.label, false, false, ''],
      ['L-03', LSTATUS.check.label, false, false, ''],
    ]);
    expect(rs.links.map((l) => l.docs.map((d) => [d.title, d.ext, d.page]))).toEqual([
      [['자동이체 신청서', 'PDF', 1], ['FATCA/CRS 본인확인서', 'PDF', 1]],
      [['자동이체 신청서', 'PDF', 1], ['소득 증빙', 'PDF', 2]],
      [['자동이체 신청서', 'PDF', 1], ['위임장', 'PDF', 1]],
    ]);
    expect(rs.links[1].docs[1].aria).toBe('소득 증빙 2쪽 근거 보기');
    expect(rs.links.map((l) => [l.title, l.basis, l.missing, l.check])).toEqual(a.links.map((l) => [l.title, l.basis, l.missing, l.check]));
  });

  it('같은 연결이라도 데모(raw 없음)면 확인 필요 연결에 판단 버튼 — 버튼을 가르는 것은 실제 분석 여부', () => {
    const demoLike: Analysis = { ...a, raw: undefined };
    expect(results(demoLike).links.map((l) => l.canDecide)).toEqual([true, false, true]);
    expect(results(demoLike).linksIntro).toBe(true);
  });

  it('카드 마크업 — 설명 줄 · 판단 버튼 없음, 근거 보기는 서류마다', () => {
    const rs = results(a, stateOf(a, { tab: 'links' }));
    const html = renderToStaticMarkup(createElement(LinkCards, { links: rs.links, locked: rs.locked, intro: rs.linksIntro, onPickDoc: () => {}, actions: READ_ONLY_ACTIONS }));
    expect(html).not.toContain(INTRO);
    expect(html).not.toContain('같은 사람·같은 건 맞음');
    expect(html).not.toContain('연결 아님');
    expect(html.split('근거 보기</button>').length - 1).toBe(6);
    expect(html).toContain('부족한 근거');
    // 연결 근거 칸은 근거가 있는 연결(L-02)만 — 빈 '연결 근거' 이름표를 그리지 않는다
    expect(html.split('연결 근거</span>').length - 1).toBe(1);
    // 데모 모양(intro 기본값)은 설명 줄이 있다
    const demoHtml = renderToStaticMarkup(createElement(LinkCards, { links: rs.links, locked: false, onPickDoc: () => {}, actions: READ_ONLY_ACTIONS }));
    expect(demoHtml).toContain(INTRO);
  });
});

describe('실제 분석 — 연결 카드 글의 원문 값(V-T4-1 M3)', () => {
  it('응답의 다섯 글 자리(title · fields · basis · missing · check)에 원문 값이 와도 카드에는 masked 만, 원문 보기 값 · 위치는 그대로', () => {
    const r = finalFlowResult();
    const fs = r.findings as { value: string; masked: string }[];
    const raws = [...new Set(fs.filter((f) => f.value && f.value !== f.masked && Array.from(f.value).length >= 2).map((f) => f.value))];
    expect(raws.length).toBeGreaterThanOrEqual(4);
    const links = r.links as { title: string; basis: string[]; missing: string; check: string; docs: { fields: string }[] }[];
    links.forEach((l, i) => {
      l.title = '제목 ' + raws[i % raws.length];
      l.basis = [raws[(i + 1) % raws.length]];
      l.missing = raws[(i + 2) % raws.length];
      l.check = '확인 ' + raws[(i + 3) % raws.length];
      l.docs.forEach((d, k) => (d.fields = '값 ' + raws[(i + k) % raws.length]));
    });
    const a = liveAnalysis(r);
    const rs = results(a, stateOf(a, { tab: 'links' }));
    const html = renderToStaticMarkup(createElement(LinkCards, { links: rs.links, locked: rs.locked, intro: rs.linksIntro, onPickDoc: () => {}, actions: READ_ONLY_ACTIONS }));
    expect(raws.filter((v) => html.includes(v)).length).toBe(0);
    expect(rs.links.length).toBe(3);
    // 탐지 항목(원문 보기 · 근거 문구에 쓰는 값)과 연결 위치는 그대로
    expect(a.findings.filter((f) => raws.includes(f.live?.value ?? '')).length).toBe(fs.filter((f) => raws.includes(f.value)).length);
    expect(a.links.map((l) => l.docs.map((d) => d.anchors))).toEqual(liveAnalysis().links.map((l) => l.docs.map((d) => d.anchors)));
  });
});

describe('실제 분석 — 검토사항 연결 보기 → 연결 탭', () => {
  const a = liveAnalysis();

  it('mismatch · weaklink 행에 연결 번호(연결 보기 버튼), 그 밖은 없음', () => {
    const rs = results(a, stateOf(a, { tab: 'review' }));
    expect(rs.items.map((i) => [i.id, i.type, i.linkId])).toEqual([
      ['R-01', '필수 항목 없음', null],
      ['R-02', '위치 확인 필요', null],
      ['R-03', '인식 확인 필요', null],
      ['R-04', '값 불일치', 'L-01'],
      ['R-05', '위치 확인 필요', null],
      ['R-06', '인식 확인 필요', null],
      ['R-07', '연결 근거 부족', 'L-03'],
      ['R-08', '기타 서류', null],
    ]);
    const html = renderToStaticMarkup(
      createElement(ReviewItems, { keep: rs.keep, nOpen: rs.nOpen, nDone: rs.nDone, items: rs.items, locked: rs.itemsLocked, emptyText: rs.itemsEmptyText, onEvidence: () => {}, onOpenLink: () => {}, actions: READ_ONLY_ACTIONS }),
    );
    expect(html.split('연결 보기').length - 1).toBe(2);
  });

  it("'연결 보기'(planOpenLink) — 연결 탭 · 그 카드 · 첫 서류 근거 위치(기준 서류 성명 상자)로, 원문 이름표 'L-01 · 연결 근거'", () => {
    const item = a.items.find((i) => i.id === 'R-04')!;
    const plan = planOpenLink(a, item.linkId!, false);
    expect(plan?.card).toBe('L-01');
    expect(plan?.patch).toMatchObject({ tab: 'links', focus: { kind: 'link', id: 'L-01', idx: 0 }, docId: 'doc-0', page: 1 });
    const d101 = anchorsOf(a, 'D1-01');
    expect(d101.length).toBe(1);
    expect(plan?.viewer).toBe(d101[0]);
    const s = applyPlan(a, plan);
    const v = viewer(a, s);
    expect(v.tag.text).toBe('L-01 · 연결 근거');
    expect(v.live?.boxes.filter((b) => b.on).map((b) => [b.anchor, b.tag])).toEqual([[d101[0], true]]);
    expect(results(a, s).links.map((l) => [l.id, l.sel, l.docs.map((d) => d.on)])).toEqual([
      ['L-01', true, [true, false]],
      ['L-02', false, [false, false]],
      ['L-03', false, [false, false]],
    ]);
  });

  it('근거 보기(planPickLinkDoc) — 다른 서류 · 서류 안 2쪽의 상자, 위치 없는 서류는 그 서류 첫 쪽 맨 위', () => {
    const p2 = planPickLinkDoc(a, 'L-02', 1, false, true);
    expect(p2?.patch).toMatchObject({ focus: { kind: 'link', id: 'L-02', idx: 1 }, docId: 'doc-2', page: 2, mTab: 'doc' });
    const d301 = anchorsOf(a, 'D3-01');
    expect(p2?.viewer).toBe(d301[0]);
    const v2 = viewer(a, applyPlan(a, p2));
    expect(v2.live?.filePage).toBe(4);
    expect(v2.live?.boxes.filter((b) => b.on).map((b) => b.anchor)).toEqual(d301);
    const p3 = planPickLinkDoc(a, 'L-03', 1, false, false);
    expect(p3?.patch).toMatchObject({ docId: 'doc-3', page: 1 });
    expect(p3?.viewer).toBe(SCROLL_TOP);
    expect(viewer(a, applyPlan(a, p3)).live?.boxes.some((b) => b.on)).toBe(false);
  });

  it('weaklink 검토사항 고르기(planPickItem)는 그 서류 첫 쪽(근거 = 첫 쪽 열기)', () => {
    const s = applyPlan(a, planPickItem(a, 'R-07', false));
    expect([s.tab, s.docId, s.page]).toEqual(['review', 'doc-3', 1]);
  });
});

describe('서류 종류 이름 · 기타 서류 대체 안내', () => {
  it('새 분류 코드는 한국어 이름', () => {
    expect(liveAnalysis().docs.map((d) => d.title)).toEqual(['자동이체 신청서', 'FATCA/CRS 본인확인서', '소득 증빙', '위임장', '기타']);
  });

  it('기타 서류 안내가 비면 서류 수를 말하지 않는 짧은 문구', () => {
    const r = finalFlowResult();
    (r.documents as { other_guide: unknown }[])[4].other_guide = null;
    const a = liveAnalysis(r);
    const n = viewer(a, stateOf(a, { docId: 'doc-4', page: 1, focus: null })).notices.find((x) => x.title === '기타 서류 안내');
    expect(n?.text).toBe('워크플로우가 기타 서류로 분류했습니다.');
  });
});
