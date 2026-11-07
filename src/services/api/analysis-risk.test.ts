/* 분석 위험도 '검토 필요'(review) — 실제 분석의 분석 단위 위험도(overall.level · 목록 risk_level 이 '검토 필요')를 '미평가'가 아니라
   '검토 필요' 로 보인다: 매핑 · 상세 머리 · 분석 요약 · 목록(표 · 카드 · 정렬 · 필터 · 요약 카드) · 보고서 머리 · 내보내기 JSON · 검토 완료 모달.
   탐지 항목 위험도 · 항목 필터 · 분포 막대 · RISK 표 · 데모는 그대로.
   고정 자료 fixtures/final-flow-result.json(손으로 만든 모양) · final-flow-{C,D,E}.json(백엔드 출력) — 지어낸 값. 원문 값은 출력에 옮기지 않는다. */
import { createElement, type ReactElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { CONFIG } from '@/config/app';
import { ANALYSIS_RISK, FSTATUS, RISK, RISK_LEVELS, analysisRiskView, riskView } from '@/display/rules';
import { DetailHeader } from '@/components/detail/DetailHeader';
import { READ_ONLY_ACTIONS } from '@/components/detail/detailActions';
import { detailFacts, headerModel, resultsModel } from '@/components/detail/detailModel';
import { createDetailState } from '@/components/detail/detailState';
import { LiveSummaryTab } from '@/components/live/LiveSummaryTab';
import { AnalysisCardList } from '@/components/list/AnalysisCardList';
import { AnalysisTable } from '@/components/list/AnalysisTable';
import { DEFAULT_FILTERS, dropdownModels, listModel, matchesFilters, parseFilters, sortAnalyses, type ListFilters } from '@/components/list/listModel';
import { completeModel } from '@/components/modals/reviewModalModel';
import { reportView } from '@/components/report/reportModel';
import { ReportHead } from '@/components/report/ReportHead';
import { createService } from '@/services';
import { buildExportFile } from '@/services/export-file';
import { ServiceProvider, type ServiceProviderProps } from '@/services/react';
import { reportSafeAnalysis } from '@/services/report-safe';
import type { Analysis } from '@/services/types';
import { readAnalysisList, riskFromLevel, toAnalysis } from './mapping';
import { analysisOut, contractResult, finalFlowResult, finalFlowRun, itemsResult, listItemOut } from './testing';

type Obj = Record<string, unknown>;

const review = (): Obj => ({ status: 'needed', memo: '', memo_at: null, reviewer: '', reviewed_at: null, completion_note: '', findings: {}, items: {}, history: [], version: 0 });
const done = (result: Obj): Analysis => toAnalysis(analysisOut({ status: 'done', result, upstage_job_id: 'job_test', upstage_status: 'completed', review: review() }));
/** 위험도 판정 값만 바꾼 결과(overall.level · summary.risk_level · decision.risk_level 이 있으면 함께) */
const withLevel = (result: Obj, level: string | null): Obj => {
  const r = structuredClone(result);
  for (const k of ['overall', 'summary', 'decision'] as const) {
    const o = r[k] as Obj | undefined;
    if (o && typeof o === 'object') o[k === 'overall' ? 'level' : 'risk_level'] = level;
  }
  return r;
};
const inProvider = (el: ReactElement) =>
  renderToStaticMarkup(createElement(ServiceProvider as (p: Omit<ServiceProviderProps, 'children'>) => ReturnType<typeof ServiceProvider>, { service: createService() }, el));
/** 배지(data-risk) — [키, 라벨] 차례로 */
const badges = (html: string): [string, string][] => {
  const out: [string, string][] = [];
  const re = /data-risk="([^"]+)"[^>]*>(?:<svg[\s\S]*?<\/svg>)?([^<]*)</g;
  for (let m = re.exec(html); m; m = re.exec(html)) out.push([m[1], m[2]]);
  return out;
};
const F = (patch: Partial<ListFilters> = {}): ListFilters => ({ ...DEFAULT_FILTERS, ...patch });

describe('② 표시 규칙 — 분석 위험도 표(ANALYSIS_RISK)', () => {
  it("RISK · RISK_LEVELS 는 그대로 넷(탐지 항목 · 필터 · 분포) — review 는 분석 위험도 표에만", () => {
    expect(Object.keys(RISK)).toEqual(['high', 'medium', 'low', 'unrated']);
    expect(RISK_LEVELS).toEqual(['high', 'medium', 'low', 'unrated']);
    expect(Object.keys(ANALYSIS_RISK)).toEqual(['review', 'high', 'medium', 'low', 'unrated']);
    expect(riskView('review')).toBe(RISK.unrated);
  });

  it("review — '검토 필요', 주의(warn) 토큰, 순위는 높음보다 앞", () => {
    const v = analysisRiskView('review');
    expect(v).toEqual({ key: 'review', label: '검토 필요', rank: RISK.high.rank + 1, fg: 'var(--warn)', bg: 'var(--warn-bg)', glyph: 'dg-i-alert' });
  });

  it('그 밖 — riskView 와 같은 표기, 모르는 값 · 빈 값은 미평가', () => {
    for (const k of RISK_LEVELS) expect(analysisRiskView(k)).toBe(RISK[k]);
    for (const v of [null, undefined, '', 'bogus', 'toString', '__proto__', '검토 필요', 'REVIEW']) expect(analysisRiskView(v)).toBe(RISK.unrated);
  });
});

describe('매핑 — 상세 · 목록의 분석 위험도', () => {
  it("상세: overall.level '검토 필요' → review, 상 · 중 · 하 · 그 밖은 지금과 같다", () => {
    expect(done(finalFlowResult()).risk).toBe('review');
    expect(done(finalFlowRun('C')).risk).toBe('review');
    expect(done(finalFlowRun('D')).risk).toBe('review');
    expect(done(finalFlowRun('E')).risk).toBe('high');
    expect(done(itemsResult()).risk).toBe('high');
    expect(done(withLevel(finalFlowResult(), '중')).risk).toBe('medium');
    expect(done(withLevel(finalFlowResult(), '하')).risk).toBe('low');
    expect(done(withLevel(finalFlowResult(), '모르는 값')).risk).toBe('unrated');
    expect(done(withLevel(finalFlowResult(), null)).risk).toBe('unrated');
  });

  it("옛 결과: overall 이 없으면 summary.risk_level — '검토 필요' 도 같은 규칙", () => {
    const r = contractResult();
    delete r.overall;
    (r.summary as Obj).risk_level = '검토 필요';
    expect(done(r).risk).toBe('review');
    (r.summary as Obj).risk_level = '';
    expect(done(r).risk).toBe('unrated');
  });

  it("목록: risk_level '검토 필요' → review, 그 밖 그대로", () => {
    const list = readAnalysisList({
      analyses: [
        listItemOut({ id: 'a1', risk_level: '검토 필요' }),
        listItemOut({ id: 'a2', risk_level: ' 검토 필요 ' }),
        listItemOut({ id: 'a3', risk_level: '상' }),
        listItemOut({ id: 'a4', risk_level: null }),
        { ...listItemOut({ id: 'a5' }), risk_level: ['검토 필요'] },
      ],
    });
    expect(list?.map((a) => a.risk)).toEqual(['review', 'review', 'high', 'unrated', 'unrated']);
  });

  it('탐지 항목 위험도는 분석 위험도와 무관하다(review 가 항목에 오지 않음)', () => {
    for (const result of [finalFlowResult(), finalFlowRun('C'), finalFlowRun('D'), finalFlowRun('E'), itemsResult()]) {
      const a = done(result);
      const asHigh = done(withLevel(result, '상'));
      expect(a.findings.map((f) => f.risk)).toEqual(asHigh.findings.map((f) => f.risk));
      expect(a.findings.every((f) => Object.prototype.hasOwnProperty.call(RISK, f.risk))).toBe(true);
    }
    expect(done(finalFlowResult()).findings.map((f) => f.risk).every((r) => r === 'unrated')).toBe(true);
  });
});

describe('상세 — 머리 배지 · 분석 요약 · 항목 필터', () => {
  const a = done(finalFlowResult());
  const s = createDetailState(a).state;
  const x = detailFacts(a, s);

  it("머리: 위험등급 배지가 '검토 필요'(데스크톱 · 휴대폰)", () => {
    const m = headerModel(a, x);
    expect(m.risk).toBe('review');
    for (const mobile of [false, true]) {
      const html = inProvider(createElement(DetailHeader, { model: m, analysisId: a.id, mobile, actions: READ_ONLY_ACTIONS }));
      expect(badges(html)).toEqual([['review', '검토 필요']]);
      expect(html).not.toContain(RISK.unrated.label);
    }
  });

  /** '위험도 판정' 머리 — [배지들, 글 조각들] */
  const judgeHead = (x: Analysis) => {
    const html = renderToStaticMarkup(createElement(LiveSummaryTab, { analysis: x, stages: { status: 'idle' }, onLoadStages: () => {} }));
    const head = /<h3 id="live-judge-title"[^>]*>([\s\S]*?)<\/h3>/.exec(html)?.[1] ?? '';
    return { html, badges: badges(head), parts: head.replace(/<[^>]+>/g, '|').split('|').filter(Boolean) };
  };

  it("분석 요약: '위험도 판정' 머리는 배지 '검토 필요' 한 번(같은 등급 글은 숨김)", () => {
    const h = judgeHead(a);
    expect(h.badges).toEqual([['review', '검토 필요']]);
    expect(h.parts).toEqual(['위험도 판정', '검토 필요']);
    expect(h.html).not.toContain(RISK.unrated.label);
  });

  it("분석 요약: 배지가 같은 등급을 보이면 등급 글은 숨기고, 배지로 알 수 없는 글만 보인다('미평가 · 판정 없음', 모르는 값)", () => {
    expect(judgeHead(done(itemsResult())).parts).toEqual(['위험도 판정', RISK.high.label]);
    expect(judgeHead(done(withLevel(finalFlowResult(), '중'))).parts).toEqual(['위험도 판정', RISK.medium.label]);
    const none = judgeHead(done(withLevel(finalFlowResult(), null)));
    expect(none.badges).toEqual([['unrated', RISK.unrated.label]]);
    expect(none.parts).toEqual(['위험도 판정', RISK.unrated.label, '판정 없음']);
    expect(judgeHead(done(withLevel(finalFlowResult(), '모르는 값'))).parts).toEqual(['위험도 판정', RISK.unrated.label, '모르는 값']);
  });

  it('탐지 항목 필터 칩 · 항목 배지는 그대로(위험등급 넷)', () => {
    const rs = resultsModel(a, s, x);
    expect(rs.chips.map((c) => c.value)).toEqual(['all', 'open', 'high', 'medium', 'low']);
    expect(rs.chips.slice(1).map((c) => c.label)).toEqual([FSTATUS.open.label, RISK.high.label, RISK.medium.label, RISK.low.label]);
    expect(a.findings.every((f) => riskView(f.risk) === RISK.unrated)).toBe(true);
  });

  it("검토 완료 모달의 위험등급 글도 '검토 필요'", () => {
    const openF = a.findings.filter((f) => f.status === 'open');
    const openI = a.items.filter((i) => !i.resolved);
    expect(completeModel(a, { openF, openI, openL: [], any: true }).riskLabel).toBe('검토 필요');
    const old = done(itemsResult());
    expect(completeModel(old, { openF: [], openI: [], openL: [], any: false }).riskLabel).toBe(RISK.high.label);
  });
});

describe('목록 — 표 · 카드 · 정렬 · 필터 · 요약 카드', () => {
  const at = (id: string, risk: Analysis['risk'], submittedAt: string): Analysis => ({ ...done(itemsResult()), id, name: id, risk, submittedAt });
  const all: Analysis[] = [
    at('low', 'low', '2026-11-05 09:00'),
    at('review-old', 'review', '2026-11-01 09:00'),
    at('high', 'high', '2026-11-04 09:00'),
    at('unrated', 'unrated', '2026-11-05 10:00'),
    at('review-new', 'review', '2026-11-03 09:00'),
    at('medium', 'medium', '2026-11-02 09:00'),
  ];

  it('위험도순: 검토 필요(최근 먼저) → 높음 → 보통 → 낮음 → 미평가 · 최근 접수순은 그대로', () => {
    expect(sortAnalyses(all, 'risk').map((a) => a.id)).toEqual(['review-new', 'review-old', 'high', 'medium', 'low', 'unrated']);
    expect(sortAnalyses(all, 'recent').map((a) => a.id)).toEqual(['unrated', 'low', 'high', 'review-new', 'medium', 'review-old']);
    expect(listModel(all, F({ sort: 'risk' })).rows.map((r) => [r.id, r.risk])[0]).toEqual(['review-new', 'review']);
  });

  it("표 · 카드: 위험등급 배지 '검토 필요', 위험 타일 색은 주의 토큰", () => {
    const model = listModel(all, F({ sort: 'risk' }));
    const noop = () => {};
    const table = inProvider(createElement(AnalysisTable, { model, replay: false, onOpen: noop, onShowError: noop, onRetry: noop, onDelete: noop, onReset: noop }));
    const cards = inProvider(createElement(AnalysisCardList, { model, replay: false, onShowError: noop, onReset: noop }));
    const want: [string, string][] = [
      ['review', '검토 필요'],
      ['review', '검토 필요'],
      ['high', RISK.high.label],
      ['medium', RISK.medium.label],
      ['low', RISK.low.label],
      ['unrated', RISK.unrated.label],
    ];
    for (const html of [table, cards]) {
      expect(badges(html)).toEqual(want);
      expect(html).toContain('--tile-bg:var(--warn-bg);--tile-fg:var(--warn)');
    }
  });

  it("필터 · 요약 카드의 뜻은 그대로 — 선택지 넷, 검토 필요는 '고위험' · '미평가' 어디에도 세지 않는다", () => {
    const [risk] = dropdownModels(all);
    expect(risk.options.map((o) => [o.value, o.label, o.count])).toEqual([
      ['all', '전체', 6],
      ['high', RISK.high.label, 1],
      ['medium', RISK.medium.label, 1],
      ['low', RISK.low.label, 1],
      ['unrated', RISK.unrated.label, 1],
    ]);
    const m = listModel(all, F());
    expect(m.high).toBe(1);
    expect(m.cards.find((c) => c.id === 'high')?.n).toBe(1);
    expect(m.resultSub.startsWith('이 중 고위험 1건')).toBe(true);
    expect(all.filter((a) => matchesFilters(a, F({ risk: 'unrated' }))).map((a) => a.id)).toEqual(['unrated']);
    expect(all.filter((a) => matchesFilters(a, F({ risk: 'high' }))).map((a) => a.id)).toEqual(['high']);
    expect(parseFilters(new URLSearchParams('risk=review')).risk).toBe('all');
  });
});

describe('보고서 · 내보내기', () => {
  const a = done(finalFlowResult());
  const safe = reportSafeAnalysis(a);

  it("보고서 머리: 최종 위험등급 '검토 필요'(분포 막대 · 요약 카드는 탐지 항목 등급 그대로)", () => {
    const v = reportView(safe);
    expect(v.risk).toBe('review');
    const html = renderToStaticMarkup(createElement(ReportHead, { v, generatedAt: '2026.11.05 09:00' }));
    expect(badges(html)).toEqual([['review', '검토 필요']]);
    expect(html).toMatch(/최종 위험등급<\/dt><dd[^>]*><span[^>]*data-risk="review"/);
    expect(v.dist.map((d) => d.key)).toEqual(['unrated']);
    expect(v.dist.every((d) => Object.prototype.hasOwnProperty.call(RISK, d.key))).toBe(true);
    expect(reportView(reportSafeAnalysis(done(withLevel(finalFlowResult(), '상')))).dist).toEqual(v.dist);
  });

  it("JSON: 분석.위험등급 '검토 필요', 탐지 항목 위험등급 · CSV 는 그대로", () => {
    const opts = { brand: CONFIG.brandName, generatedAt: '2026-11-05 09:00', live: true };
    const json = JSON.parse(buildExportFile(safe, 'json', opts).text) as { 분석: Obj; 탐지항목: Obj[] };
    expect(json.분석.위험등급).toBe('검토 필요');
    expect(json.탐지항목.map((r) => r.위험등급)).toEqual(a.findings.map(() => RISK.unrated.label));
    const asHigh = reportSafeAnalysis(done(withLevel(finalFlowResult(), '상')));
    expect(buildExportFile(safe, 'csv', opts).text).toBe(buildExportFile(asHigh, 'csv', opts).text);
    expect((JSON.parse(buildExportFile(asHigh, 'json', opts).text) as { 분석: Obj }).분석.위험등급).toBe(RISK.high.label);
  });
});

describe('데모 — 그대로', () => {
  it('데모 분석 위험도는 위험 등급 넷 안 · 표기도 같다', async () => {
    const list = await createService().list();
    expect(list.map((a) => a.risk)).not.toContain('review');
    for (const a of list) expect(analysisRiskView(a.risk)).toBe(riskView(a.risk));
  });

  it('riskFromLevel 은 데모가 쓰지 않는 실제 분석 매핑 — 데모 값 키와 겹치지 않음', () => {
    expect(riskFromLevel('high')).toBe('unrated');
  });
});
