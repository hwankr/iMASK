/* 실제 분석 보고서 · 내보내기 — 문서 간 연결(최종 흐름 워크플로우 서류 대조)이 있는 결과(fixtures/final-flow-result.json, 손으로 만든 모양)
   + 검토 기록 → toAnalysis → 안전한 사본 → reportView · 마크업 · buildExportFile. 연결이 있을 때만 '문서 간 연결' 카드 · JSON 문서간연결,
   주요 위험 사유 = 판단 근거 + 검토 사유, 연결 글의 원문 값 바꾸기. 연결이 없는 옛 결과(done-result · items-result)는 그대로.
   원문 값은 테스트 출력에 옮기지 않는다(있음/없음 · 개수만). */
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { CONFIG } from '@/config/app';
import { LSTATUS } from '@/display/rules';
import { toAnalysis } from '@/services/api/mapping';
import { analysisOut, contractResult, finalFlowResult, itemsResult } from '@/services/api/testing';
import { buildExportFile } from '@/services/export-file';
import { reportSafeAnalysis } from '@/services/report-safe';
import type { Analysis } from '@/services/types';
import { reportView, type ReportView } from './reportModel';
import { ReportHead } from './ReportHead';
import { ReportHistory } from './ReportHistory';
import { ReportMemo, ReportReasons, ReportRecs, ReportRemaining } from './ReportLists';
import { ReportSummary } from './ReportSummary';
import { ReportDocTable, ReportFindings } from './ReportTables';

type Obj = Record<string, unknown>;

function review(items: Obj = {}): Obj {
  return { status: 'needed', memo: '', memo_at: null, reviewer: '', reviewed_at: null, completion_note: '', findings: {}, items, history: [], version: 1 };
}
const live = (result: Obj, items: Obj = {}): Analysis =>
  toAnalysis(analysisOut({ status: 'done', result, upstage_job_id: 'job_test', upstage_status: 'completed', review: review(items) }));

const SECTIONS = [ReportSummary, ReportReasons, ReportDocTable, ReportFindings, ReportRemaining, ReportRecs, ReportMemo, ReportHistory];
function renderReport(v: ReportView): string {
  return [
    renderToStaticMarkup(createElement(ReportHead, { v, generatedAt: '2026.11.04 09:00' })),
    ...SECTIONS.map((C) => renderToStaticMarkup(createElement(C, { v }))),
  ].join('\n');
}
const rawValues = (a: Analysis) =>
  a.findings.map((f) => f.live?.value ?? '').filter((v, i) => v && Array.from(v).length >= 2 && v !== a.findings[i].masked);
const file = (a: Analysis, format: 'csv' | 'json') => buildExportFile(reportSafeAnalysis(a), format, { brand: CONFIG.brandName, generatedAt: '2026-11-04 15:07', live: true });

const DEMO_KEYS = ['보고서', '분석', '대상문서', '주요위험사유', '탐지항목', '검토사항', '문서간연결', '권장조치', '검토메모', '검토이력'];
const LIVE_KEYS = DEMO_KEYS.filter((k) => k !== '문서간연결');

/** 원문 값을 연결 글(제목 · 서류 fields · 근거 · 부족한 근거 · 확인할 내용)에 심은 분석 */
function planted(): { a: Analysis; raws: string[] } {
  const raws = rawValues(live(finalFlowResult()));
  const r = finalFlowResult();
  const links = r.links as Obj[];
  links[0].title = '제목 ' + raws[0] + ' 끝';
  (links[0].docs as Obj[])[1].fields = '성명 ' + raws[1];
  links[1].basis = ['근거 ' + raws[2]];
  links[2].missing = raws[3] + ' 없음';
  links[2].check = '확인 ' + raws[0];
  return { a: live(r), raws };
}

describe('보고서 — 연결이 있는 실제 분석', () => {
  const a = live(finalFlowResult(), { 'mismatch:0:1': { resolved: true, note: '같은 고객 확인', resolved_at: '2026-11-04T01:00:00Z', resolved_by: '이지은' } });
  const v = reportView(reportSafeAnalysis(a));
  const html = renderReport(v);

  it("카드 4장(데모와 같다) — '문서 간 연결' 수 · 확인 필요 수, 4장 배치(3장용 클래스 없음)", () => {
    expect(v.cards.map((c) => [c.key, c.label])).toEqual([
      ['findings', '탐지 항목'],
      ['reviewed', '담당자 확인'],
      ['remaining', '남은 검토사항'],
      ['links', '문서 간 연결'],
    ]);
    expect(v.cards[3]).toEqual({ key: 'links', label: '문서 간 연결', num: 3, unit: '건', after: '', sub: '확인 필요 2건', warn: false });
    expect(v.cards[2]).toMatchObject({ num: 7, sub: '전체 8건 중 해결 1건' });
    const summary = renderToStaticMarkup(createElement(ReportSummary, { v }));
    expect(summary).not.toMatch(/cardsThree/);
    expect(summary).toContain('문서 간 연결');
    expect(v.liveJsonDesc).toBe(false);
  });

  it('주요 위험 사유 = 판단 근거 + 검토 사유 줄', () => {
    const d = finalFlowResult().decision as Obj;
    expect(v.reasons).toEqual([d.reason, ...(d.review_reasons as string[])]);
  });

  it("판정 키는 있는데 사유를 못 읽으면 주요 위험 사유는 비고 '-'(overall 본문으로 돌아가지 않는다)", () => {
    const r = finalFlowResult();
    r.decision = { risk_level: '검토 필요', document_types: null, sensitive_categories: null, review_reasons: [], reason: null };
    const empty = reportView(reportSafeAnalysis(live(r)));
    expect(empty.reasons).toEqual([]);
    expect(empty.noReasonsText).toBe('-');
    const reasons = renderToStaticMarkup(createElement(ReportReasons, { v: empty }));
    expect(reasons).toContain('-');
    expect(reasons).not.toContain('판단됩니다');
  });

  it('원문 값 없음 — 보고서 마크업 어디에도', () => {
    const raws = rawValues(a);
    expect(raws.length).toBeGreaterThan(0);
    expect(raws.filter((x) => html.includes(x)).length).toBe(0);
  });
});

describe('안전한 사본 — 연결 글', () => {
  it('제목 · 서류 fields · 근거 · 부족한 근거 · 확인할 내용의 원문 값은 masked 로, 위치 · 번호 · 계약 id 는 그대로, 원래 객체는 그대로', () => {
    const { a, raws } = planted();
    const before = structuredClone(a.links);
    const safe = reportSafeAnalysis(a);
    const masked = (raw: string) => a.findings.find((f) => f.live?.value === raw)?.masked ?? '';
    expect(safe.links[0].title).toBe('제목 ' + masked(raws[0]) + ' 끝');
    expect(safe.links[0].docs[1].fields).toBe('성명 ' + masked(raws[1]));
    expect(safe.links[1].basis).toEqual(['근거 ' + masked(raws[2])]);
    expect(safe.links[2].missing).toBe(masked(raws[3]) + ' 없음');
    expect(safe.links[2].check).toBe('확인 ' + masked(raws[0]));
    expect(safe.links.map((l) => [l.id, l.live?.id, l.status, l.docs.map((d) => [d.docId, d.page, d.anchors])])).toEqual(
      a.links.map((l) => [l.id, l.live?.id, l.status, l.docs.map((d) => [d.docId, d.page, d.anchors])]),
    );
    expect(a.links).toEqual(before);
    expect(safe.links).not.toBe(a.links);
  });

  it('판정 키의 판단 근거 · 검토 사유 · 정보 종류도 바꾼다(서류 종류 코드 · 위험도는 그대로)', () => {
    const raws = rawValues(live(finalFlowResult()));
    const r = finalFlowResult();
    r.decision = { risk_level: '상', document_types: ['income_proof'], sensitive_categories: ['이름 ' + raws[0]], review_reasons: [raws[1]], reason: '근거 ' + raws[2] };
    const a = live(r);
    const safe = reportSafeAnalysis(a);
    const masked = (raw: string) => a.findings.find((f) => f.live?.value === raw)?.masked ?? '';
    expect(safe.raw?.decision).toEqual({
      riskLevel: '상',
      documentTypes: ['income_proof'],
      sensitiveCategories: ['이름 ' + masked(raws[0])],
      reviewReasons: [masked(raws[1])],
      reason: '근거 ' + masked(raws[2]),
    });
    expect(safe.riskReasons).toEqual(['근거 ' + masked(raws[2]), masked(raws[1])]);
  });
});

describe('내보내기 — 연결이 있는 실제 분석', () => {
  const a = live(finalFlowResult());

  it('JSON 최상위 키 = 데모와 같은 10개(문서간연결은 검토사항 뒤 · 권장조치 앞)', () => {
    const obj = JSON.parse(file(a, 'json').text);
    expect(Object.keys(obj)).toEqual(DEMO_KEYS);
    expect(obj.보고서.데모데이터).toBe(false);
  });

  it('문서간연결 모양 — 데모와 같은 키(ID · 내용 · 판단 · 근거), 판단 = 결과 상태 라벨', () => {
    const obj = JSON.parse(file(a, 'json').text);
    expect(obj.문서간연결.every((r: Obj) => Object.keys(r).join(',') === 'ID,내용,판단,근거')).toBe(true);
    expect(obj.문서간연결.map((r: Obj) => [r.ID, r.판단])).toEqual([
      ['L-01', LSTATUS.check.label],
      ['L-02', LSTATUS.confirmed.label],
      ['L-03', LSTATUS.check.label],
    ]);
    expect(obj.문서간연결.map((r: Obj) => [r.내용, r.근거])).toEqual(a.links.map((l) => [l.title, l.basis]));
    const d = finalFlowResult().decision as Obj;
    expect(obj.주요위험사유).toEqual([d.reason, ...(d.review_reasons as string[])]);
  });

  it('원문 값 없음 — 연결 글에 심어도 CSV · JSON 어디에도 없다', () => {
    const plain = file(a, 'json').text;
    expect(rawValues(a).filter((x) => plain.includes(x)).length).toBe(0);
    const { a: p, raws } = planted();
    for (const format of ['csv', 'json'] as const) {
      const t = file(p, format).text;
      expect(raws.slice(0, 4).filter((x) => t.includes(x)).length, format).toBe(0);
    }
  });
});

describe('연결이 없는 실제 분석은 그대로', () => {
  it('옛 결과(done-result · items-result) · 연결 0개 — 카드 3장 · JSON 9개 키(문서간연결 없음) · JSON 설명은 실제 분석 문구', () => {
    const empty = finalFlowResult();
    empty.links = [];
    for (const r of [contractResult(), itemsResult(), empty]) {
      const a = live(r);
      const v = reportView(reportSafeAnalysis(a));
      expect(v.cards.map((c) => c.key)).toEqual(['findings', 'reviewed', 'remaining']);
      expect(v.liveJsonDesc).toBe(true);
      const obj = JSON.parse(file(a, 'json').text);
      expect(Object.keys(obj)).toEqual(LIVE_KEYS);
    }
  });
});
