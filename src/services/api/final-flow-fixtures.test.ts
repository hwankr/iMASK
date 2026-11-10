/* 백엔드가 만든 최종 흐름 결과(fixtures/final-flow-{C,D,E}.json — tests/test_final_flow_fixture_sync.py 가 백엔드 출력과 바이트까지
   같은지 지킨다) → toAnalysis → 상세(탭 · 연결 카드 · 검토사항 '연결 보기') · 분석 요약(판정 칸 · 묶음 검증 · 연결 줄) · 보고서 · 내보내기.
   C 불일치(mismatch · linked) · D 빈 신청인(weaklink · missing) · E 팀원 서식(linked 2 · other).
   원문 값(masked 와 다른 value)은 테스트 출력에 옮기지 않는다(있음/없음 · 개수만). */
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { CONFIG } from '@/config/app';
import { LSTATUS } from '@/display/rules';
import { READ_ONLY_ACTIONS } from '@/components/detail/detailActions';
import { detailFacts, resultsModel } from '@/components/detail/detailModel';
import { createDetailState, planOpenLink, type DetailUiState } from '@/components/detail/detailState';
import { LinkCards } from '@/components/detail/LinkCards';
import { decisionView, finalFlowRows } from '@/components/live/liveModel';
import { reportView, type ReportView } from '@/components/report/reportModel';
import { ReportHead } from '@/components/report/ReportHead';
import { ReportHistory } from '@/components/report/ReportHistory';
import { ReportMemo, ReportReasons, ReportRecs, ReportRemaining } from '@/components/report/ReportLists';
import { ReportSummary } from '@/components/report/ReportSummary';
import { ReportDocTable, ReportFindings } from '@/components/report/ReportTables';
import { buildExportFile } from '@/services/export-file';
import { reportSafeAnalysis } from '@/services/report-safe';
import type { Analysis } from '@/services/types';
import { toAnalysis } from './mapping';
import { analysisOut, finalFlowRun } from './testing';

type Obj = Record<string, unknown>;
type Run = 'C' | 'D' | 'E';

const review = (): Obj => ({ status: 'needed', memo: '', memo_at: null, reviewer: '', reviewed_at: null, completion_note: '', findings: {}, items: {}, history: [], version: 0 });
const live = (key: Run): Analysis =>
  toAnalysis(analysisOut({ status: 'done', result: finalFlowRun(key), upstage_job_id: 'job_test', upstage_status: 'completed', review: review() }));
const stateOf = (a: Analysis, patch: Partial<DetailUiState> = {}): DetailUiState => ({ ...createDetailState(a).state, ...patch });
const results = (a: Analysis, s: DetailUiState = stateOf(a)) => resultsModel(a, s, detailFacts(a, s));

/** 원문 값 — 탐지 항목 value 중 masked 와 다르고 2글자 이상인 것 */
const rawValues = (a: Analysis) =>
  [...new Set(a.findings.map((f) => f.live?.value ?? '').filter((v, i) => v && Array.from(v).length >= 2 && v !== a.findings[i].masked))];
const hits = (raws: string[], text: string) => raws.filter((x) => text.includes(x)).length;

const SECTIONS = [ReportSummary, ReportReasons, ReportDocTable, ReportFindings, ReportRemaining, ReportRecs, ReportMemo, ReportHistory];
const renderReport = (v: ReportView) =>
  [renderToStaticMarkup(createElement(ReportHead, { v, generatedAt: '2026.11.04 09:00' })), ...SECTIONS.map((C) => renderToStaticMarkup(createElement(C, { v })))].join('\n');
const file = (a: Analysis, format: 'csv' | 'json') =>
  buildExportFile(reportSafeAnalysis(a), format, { brand: CONFIG.brandName, generatedAt: '2026-11-04 15:07', live: true });

/** 고정 응답마다 기대 모양(tests/test_final_flow_fixture_sync.py SHAPES 와 같은 값) */
const WANT: Record<Run, { links: [string, 'confirmed' | 'check', string][]; items: [string, string, string | undefined][]; bundle: string; linkRow: string; risk: string }> = {
  C: {
    links: [
      ['L-01', 'check', 'link:0:1'],
      ['L-02', 'confirmed', 'link:0:2'],
    ],
    items: [
      ['R-01', 'lowconf', undefined],
      ['R-02', 'mismatch', 'L-01'],
      ['R-03', 'lowconf', undefined],
    ],
    bundle: '주의',
    linkRow: '연결 1 · 확인 필요 1',
    risk: '검토 필요',
  },
  D: {
    links: [['L-01', 'check', 'link:0:1']],
    items: [
      ['R-01', 'missing', undefined],
      ['R-02', 'lowconf', undefined],
      ['R-03', 'weaklink', 'L-01'],
    ],
    bundle: '실패 1건',
    linkRow: '연결 0 · 확인 필요 1',
    risk: '검토 필요',
  },
  E: {
    links: [
      ['L-01', 'confirmed', 'link:0:1'],
      ['L-02', 'confirmed', 'link:0:2'],
    ],
    items: [
      ['R-01', 'lowconf', undefined],
      ['R-02', 'other', undefined],
    ],
    bundle: '주의',
    linkRow: '연결 2 · 확인 필요 0',
    risk: '상',
  },
};

describe.each(['C', 'D', 'E'] as const)('백엔드가 만든 최종 흐름 결과 %s', (key) => {
  const a = live(key);
  const want = WANT[key];
  const result = finalFlowRun(key);

  it('연결 수 · 상태 · 계약 id, 검토사항 종류 · linkId(같은 결과의 연결 번호)', () => {
    expect(a.links.map((l) => [l.id, l.status, l.live?.id])).toEqual(want.links);
    expect(a.items.map((i) => [i.id, i.type, i.linkId])).toEqual(want.items);
    expect((result.links as Obj[]).length).toBe(want.links.length);
    expect((result.items as Obj[]).length).toBe(want.items.length);
    // 연결 서류마다 백엔드 finding_ids 가 있으면 그 탐지 항목 위치(anchors)가 있고, 없으면 위치도 없다
    const raw = result.links as { docs: { finding_ids: string[] }[] }[];
    expect(a.links.map((l) => l.docs.map((d) => d.anchors.length > 0))).toEqual(raw.map((l) => l.docs.map((d) => d.finding_ids.length > 0)));
  });

  it('탭 넷(연결이 있음) — 탐지 항목 · 검토 필요 · 문서 간 연결 · 분석 요약, 개수는 데모와 같은 규칙', () => {
    expect(results(a).tabs.map((t) => [t.value, t.count])).toEqual([
      ['findings', a.findings.length],
      ['review', a.items.length],
      ['links', a.links.length],
      ['summary', undefined],
    ]);
  });

  it('연결 카드 — 판단 버튼 없음, 서류마다 근거 보기, 상태 라벨', () => {
    const rs = results(a, stateOf(a, { tab: 'links' }));
    expect(rs.links.map((l) => [l.id, l.status.label, l.canDecide])).toEqual(want.links.map(([id, s]) => [id, LSTATUS[s].label, false]));
    const html = renderToStaticMarkup(createElement(LinkCards, { links: rs.links, locked: rs.locked, intro: rs.linksIntro, onPickDoc: () => {}, actions: READ_ONLY_ACTIONS }));
    expect(html).not.toContain('같은 사람·같은 건 맞음');
    expect(html).not.toContain('연결 아님');
    expect(html.split('근거 보기</button>').length - 1).toBe(a.links.reduce((n, l) => n + l.docs.length, 0));
  });

  it("검토사항 '연결 보기' → 문서 간 연결 탭의 그 연결", () => {
    for (const item of a.items.filter((i) => i.linkId)) {
      const plan = planOpenLink(a, item.linkId ?? '', false);
      expect(plan?.patch.tab).toBe('links');
      expect(plan?.card).toBe(item.linkId);
    }
  });

  it('분석 요약 — 판단 근거 · 값이 있는 줄(응답 값 그대로) · 묶음 검증 줄 · 문서 간 연결 줄', () => {
    const d = result.decision as Obj;
    const list = (key: string, label: string) => {
      const values = d[key] as string[];
      return values.length ? [{ key, label, value: values.join(', ') }] : [];
    };
    expect(a.raw?.decision?.riskLevel).toBe(want.risk);
    expect(decisionView(a.raw?.decision)).toEqual({
      reason: d.reason,
      rows: [...list('sensitive_categories', '정보 종류'), ...list('review_reasons', '검토 사유')],
      groups: [],
    });
    expect(finalFlowRows(a.raw?.bundleCheck, a.links)).toEqual([
      { key: 'bundle', label: '묶음 검증', value: want.bundle },
      { key: 'links', label: '문서 간 연결', value: want.linkRow },
    ]);
  });

  it('보고서 — 문서 간 연결 카드 · 남은 검토사항, 원문 값 없음(연결 · 검토사항 · 보고서 마크업)', () => {
    const raws = rawValues(a);
    expect(raws.length).toBeGreaterThan(0);
    const v = reportView(reportSafeAnalysis(a));
    const card = v.cards.find((c) => c.key === 'links');
    expect(card).toMatchObject({ num: a.links.length });
    expect(v.remaining.map((r) => r.id)).toEqual(a.items.map((i) => i.id));
    const linkText = a.links.map((l) => [l.title, ...l.docs.map((d) => d.fields), ...l.basis, l.missing, l.check].join('\n')).join('\n');
    const itemText = a.items.map((i) => [i.title, i.desc, i.next, ...i.evidence.map((e) => e.label)].join('\n')).join('\n');
    expect(hits(raws, linkText)).toBe(0);
    expect(hits(raws, itemText)).toBe(0);
    expect(hits(raws, renderReport(v))).toBe(0);
  });

  it('내보내기 — JSON 문서간연결 · 검토사항(개수), CSV · JSON 어디에도 원문 값 없음', () => {
    const raws = rawValues(a);
    const obj = JSON.parse(file(a, 'json').text);
    expect(obj.문서간연결.map((r: Obj) => [r.ID, r.판단])).toEqual(want.links.map(([id, s]) => [id, LSTATUS[s].label]));
    expect(obj.검토사항.map((r: Obj) => r.ID)).toEqual(want.items.map(([id]) => id));
    for (const format of ['csv', 'json'] as const) expect(hits(raws, file(a, format).text), format).toBe(0);
  });
});
