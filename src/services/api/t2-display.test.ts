/* web-polish T2 — 표시 말 · 목록 서류 수 · 연결 이름표 · 보고서 다음 단계 제목 · 옛 이름 이력 · 개발용 경로.
   실제 분석은 백엔드가 설정 60 고정 응답으로 만든 결과(fixtures/v2-cases.json — 가상 값)로 만든다. 값은 테스트 출력에 옮기지 않는다. */
import { afterEach, describe, expect, it, vi } from 'vitest';
import { detailFacts, linkModel, resultsModel } from '@/components/detail/detailModel';
import { createDetailState } from '@/components/detail/detailState';
import { listModel, parseFilters, toRow, DEFAULT_FILTERS } from '@/components/list/listModel';
import { finalFlowRows } from '@/components/live/liveModel';
import { reportView } from '@/components/report/reportModel';
import { devPagesEnabled } from '@/dev/devPages';
import { ANALYSIS_RISK, RISK, RSTATUS, linkMissingLabel } from '@/display/rules';
import { createService } from '@/services';
import { reportSafeAnalysis } from '@/services/report-safe';
import type { Analysis } from '@/services/types';
import { analysisCode, documentCount, readAnalysisList, readHistory, toAnalysis } from './mapping';
import { analysisOut, listItemOut, v2Case, type V2Case } from './testing';

type Obj = Record<string, unknown>;
const review = (): Obj => ({ status: 'needed', memo: '', memo_at: null, reviewer: '', reviewed_at: null, completion_note: '', findings: {}, items: {}, history: [], version: 0 });
const live = (key: V2Case): Analysis => toAnalysis(analysisOut({ status: 'done', result: v2Case(key), upstage_job_id: 'job_test', upstage_status: 'completed', review: review() }));

describe('표시 말 — 등급 상·중·하 · 검토 상태 검토 대기 · 위험도 판정 검토 필요', () => {
  it('② 라벨', () => {
    expect([RISK.high.label, RISK.medium.label, RISK.low.label, RISK.unrated.label]).toEqual(['상', '중', '하', '미평가']);
    expect([RSTATUS.none.label, RSTATUS.needed.label, RSTATUS.done.label]).toEqual(['미검토', '검토 대기', '검토 완료']);
    expect(ANALYSIS_RISK.review.label).toBe('검토 필요'); // 위험등급 뜻은 그대로
  });

  it('분석 번호 머리글자 IM-', () => {
    expect(analysisCode('ab12cd34-0000', '2026-11-02T15:30:00Z')).toBe('IM-20261103-AB12');
  });

  it('목록 요약 카드 · 머리말 · 결과 부가 문구 — 설명 줄(hint) 없음', () => {
    const all = readAnalysisList({
      analyses: [
        listItemOut({ id: 'a1', status: 'done', risk_level: '상', review: 'needed', document_count: 2 }),
        listItemOut({ id: 'a2', status: 'done', risk_level: '검토 필요', review: 'done', document_count: 1 }),
      ],
    });
    if (!all) throw new Error('list');
    const m = listModel(all, DEFAULT_FILTERS);
    expect(m.cards.map((c) => c.label)).toEqual(['전체 분석', '상 등급', '검토 대기']);
    expect(m.cards.every((c) => !('hint' in c))).toBe(true);
    expect(m.cards[1].aria).toBe('상 등급 1건, 상 등급만 보기');
    expect(m.cards[2].aria).toBe('검토 대기 1건, 검토 대기만 보기');
    expect(m.heroLead + m.heroStrong + m.heroTail).toBe('검토를 기다리는 분석이 1건 있습니다.');
    expect(m.basis).toBe('');
    const f = listModel(all, { ...DEFAULT_FILTERS, risk: 'high' });
    expect([f.basis, f.resultSub]).toEqual(['검색 결과 기준', '이 중 상 등급 1건 · 검토 대기 1건']);
    expect(f.cards[1].aria).toBe('상 등급 1건, 필터 해제');
    const none = listModel(all.map((a) => ({ ...a, review: 'done' as const })), DEFAULT_FILTERS);
    expect(none.heroLead + none.heroStrong + none.heroTail).toBe('검토를 기다리는 분석이 없습니다.');
  });
});

describe('목록 문서 수 — document_count', () => {
  it.each([
    [4, 4],
    [0, 0],
    [null, null],
    [undefined, null],
    [true, null],
    [-1, null],
    [1.5, null],
    ['3', null],
    [Number.MAX_SAFE_INTEGER + 1, null],
  ])('document_count %s → %s', (value, want) => {
    const list = readAnalysisList({ analyses: [{ ...listItemOut({ id: 'x', status: 'done' }), document_count: value }] });
    expect(list?.[0].raw?.documentCount).toBe(want);
    expect(documentCount(value)).toBe(want);
    // 실제 분석 행의 문서 수는 분류한 서류 수(모르면 null — 화면은 '-'), 올린 파일 수가 아니다
    expect(list && toRow(list[0]).docs).toBe(want);
  });

  it('데모 행은 올린 문서 수 그대로', async () => {
    const svc = createService();
    const a = await svc.get('A1');
    if (!a) throw new Error('A1');
    expect(toRow(a).docs).toBe(a.docs.length);
  });

  it('상세 결과의 summary.document_count 도 같은 규칙', () => {
    expect(live('A').raw?.documentCount).toBe(4);
  });
});

describe('문서 간 연결 — missing 줄 이름표', () => {
  it('unmatched → 다른 값, insufficient · 데모 → 부족한 근거', () => {
    const u = live('U');
    const states = u.links.map((l) => l.live?.state);
    expect(states).toEqual(['unmatched', 'unmatched']);
    expect(u.links.map((l) => linkMissingLabel(l))).toEqual(['다른 값', '다른 값']);
    expect(u.links.map((l) => linkModel(u, l, null).missingLabel)).toEqual(['다른 값', '다른 값']);
    const a = live('A');
    const weak = a.links.find((l) => l.live?.state === 'insufficient');
    expect(weak && linkModel(a, weak, null).missingLabel).toBe('부족한 근거');
    expect(linkMissingLabel({})).toBe('부족한 근거');
    expect(linkMissingLabel({ live: { state: '모르는 값' } })).toBe('부족한 근거');
  });

  it('모르는 state 는 live.state 로 옮기지 않는다(연결은 남는다)', () => {
    const result = v2Case('U');
    const links = result.links as Obj[];
    links[0].state = 'mystery';
    const a = toAnalysis(analysisOut({ status: 'done', result, review: review() }));
    expect(a.links).toHaveLength(2);
    expect(a.links[0].live).toEqual({ id: links[0].id });
    expect(a.links[1].live?.state).toBe('unmatched');
  });
});

describe('보고서 다음 단계 제목 · 묶음 검증 줄 · 결과 탭', () => {
  it('실제 분석은 nextStageTitle(검토_안내 → 검토 안내, 권장_조치 → 권장 조치), 데모는 권장 조치', async () => {
    expect(reportView(reportSafeAnalysis(live('U'))).recsTitle).toBe('검토 안내');
    expect(reportView(reportSafeAnalysis(live('A'))).recsTitle).toBe('권장 조치');
    const a = await createService().get('A1');
    if (!a) throw new Error('A1');
    expect(reportView(a).recsTitle).toBe('권장 조치');
  });

  it('묶음 검증 — 판정 라벨 + 건수 하나', () => {
    expect(finalFlowRows({ verdict: 'red', failed: 3 }, [])[0].value).toBe('실패 3건');
    expect(finalFlowRows({ verdict: 'green', failed: 0 }, [])[0].value).toBe('통과');
    expect(finalFlowRows({ verdict: 'green', failed: 1 }, [])[0].value).toBe('실패 1건');
  });

  it("결과 탭 '검토사항'", () => {
    const a = live('U');
    const s = createDetailState(a).state;
    expect(resultsModel(a, s, detailFacts(a, s)).tabs.find((t) => t.value === 'review')?.label).toBe('검토사항');
  });
});

describe('이력 — 저장된 옛 글은 그대로 읽는다', () => {
  it('옛 이름 iMASK_DG-… 내보내기 줄 · 옛 검토 상태 글', () => {
    const rows = [
      { id: 'H1', at: '2026-11-04T02:00:00+00:00', actor: '이지은', kind: 'export', target: 'iMASK_DG-20261102-AB12_검토결과.json', change: 'JSON · 22KB · 저장 완료', reason: '민감한 값 마스킹' },
      { id: 'H2', at: '2026-11-04T02:10:00+00:00', actor: '이지은', kind: 'reopen', target: '분석 건', change: '검토 완료 → 검토 필요', reason: '' },
    ];
    const h = readHistory(rows);
    expect(h.map((x) => [x.target, x.change])).toEqual([
      ['iMASK_DG-20261102-AB12_검토결과.json', 'JSON · 22KB · 저장 완료'],
      ['분석 건', '검토 완료 → 검토 필요'],
    ]);
  });
});

describe('개발용 경로 — next dev 이거나 IMASK_DEV_PAGES=1 빌드만', () => {
  afterEach(() => vi.unstubAllEnvs());
  it.each([
    ['development', '', true],
    ['test', '', true],
    ['production', '', false],
    ['production', '0', false],
    ['production', '1', true],
  ])('NODE_ENV=%s IMASK_DEV_PAGES=%s → %s', (nodeEnv, flag, want) => {
    vi.stubEnv('NODE_ENV', nodeEnv);
    vi.stubEnv('IMASK_DEV_PAGES', flag);
    expect(devPagesEnabled()).toBe(want);
  });
});

describe("목록 주소의 risk=review — 데모는 받지 않는다(T2-fix1)", () => {
  it('데모 목록: 6건 모두 · 전체 · 걸렀다는 표시 없음(모르는 값 risk=zzz 와 같은 길)', async () => {
    const all = await createService().list();
    expect(all).toHaveLength(6);
    const f = parseFilters(new URLSearchParams('risk=review'));
    expect(f).toEqual(parseFilters(new URLSearchParams('risk=zzz')));
    expect(f).toEqual(DEFAULT_FILTERS);
    const m = listModel(all, f);
    expect([m.rows.length, m.filtered, m.basis, m.resultText]).toEqual([6, false, '', '전체 6건']);
    expect(m.cards[0].on).toBe(true);
  });

  it('실제 분석 목록: 위험등급 검토 필요만 · 걸렀다는 표시', () => {
    const all = readAnalysisList({
      analyses: [
        listItemOut({ id: 'r1', status: 'done', risk_level: '검토 필요', review: 'needed', document_count: 1 }),
        listItemOut({ id: 'h1', status: 'done', risk_level: '상', review: 'needed', document_count: 1 }),
      ],
    });
    if (!all) throw new Error('list');
    const f = parseFilters(new URLSearchParams('risk=review'), { live: true });
    const m = listModel(all, f);
    expect([f.risk, m.rows.map((r) => r.id), m.filtered, m.basis]).toEqual(['review', ['r1'], true, '검색 결과 기준']);
  });
});
