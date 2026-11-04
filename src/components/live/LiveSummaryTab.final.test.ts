/* 실제 분석 '분석 요약' 탭 — 최종 흐름 워크플로우의 위험도 판정 키 표 · 결과 요약의 묶음 검증 · 문서 간 연결 줄.
   순수 함수(decisionRows · finalFlowRows)와 마크업(renderToStaticMarkup). 판정 키가 없는 옛 결과는 지금처럼(판정 본문 · 줄 그대로).
   고정 자료 fixtures/final-flow-result.json(손으로 만든 모양 — 지어낸 값). */
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { toAnalysis } from '@/services/api/mapping';
import { analysisOut, contractResult, finalFlowResult, itemsResult } from '@/services/api/testing';
import type { Analysis, RawDecision } from '@/services/types';
import { LiveSummaryTab } from './LiveSummaryTab';
import { decisionRows, finalFlowRows } from './liveModel';

type Obj = Record<string, unknown>;

const NEW_REVIEW = { status: 'needed', memo: '', memo_at: null, reviewer: '', reviewed_at: null, completion_note: '', findings: {}, items: {}, history: [], version: 0 };
const done = (result: Obj): Analysis =>
  toAnalysis(analysisOut({ status: 'done', result, upstage_job_id: 'job_test', upstage_status: 'completed', review: structuredClone(NEW_REVIEW) }));
const html = (a: Analysis) => renderToStaticMarkup(createElement(LiveSummaryTab, { analysis: a, stages: { status: 'idle' }, onLoadStages: () => {} }));

/** dl 줄 [data-row, dt, dd] 차례로 */
function rowsOf(markup: string): [string, string, string][] {
  const out: [string, string, string][] = [];
  const re = /<div class="[^"]*" data-row="([^"]+)"><dt class="[^"]*">([^<]*)<\/dt><dd class="[^"]*">([^<]*)<\/dd><\/div>/g;
  for (let m = re.exec(markup); m; m = re.exec(markup)) out.push([m[1], m[2], m[3]]);
  return out;
}
const unescape = (s: string) => s.replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"').replace(/&#x27;/g, "'");

describe('decisionRows — 위험도 판정 키 표', () => {
  it('판정 키가 없으면 null', () => {
    expect(decisionRows(null)).toBeNull();
    expect(decisionRows(undefined)).toBeNull();
  });

  it('5줄 — 위험도 · 서류 종류(이름) · 정보 종류 · 검토 사유 · 판단 근거, 목록은 ", "', () => {
    const d: RawDecision = {
      riskLevel: '상',
      documentTypes: ['loan_application', 'debit_card_application', 'unknown_code'],
      sensitiveCategories: ['고유식별정보', '계좌번호'],
      reviewReasons: ['사유 하나'],
      reason: '근거 글',
    };
    expect(decisionRows(d)).toEqual([
      { key: 'risk_level', label: '위험도', value: '상' },
      { key: 'document_types', label: '서류 종류', value: '대출신청서, 체크카드 가입신청서, unknown_code' },
      { key: 'sensitive_categories', label: '정보 종류', value: '고유식별정보, 계좌번호' },
      { key: 'review_reasons', label: '검토 사유', value: '사유 하나' },
      { key: 'reason', label: '판단 근거', value: '근거 글' },
    ]);
  });

  it("못 읽은 값(null) · 빈 목록은 '-'", () => {
    const empty: RawDecision = { riskLevel: null, documentTypes: null, sensitiveCategories: [], reviewReasons: [], reason: null };
    expect(decisionRows(empty)?.map((r) => r.value)).toEqual(['-', '-', '-', '-', '-']);
  });
});

describe('finalFlowRows — 묶음 검증 · 문서 간 연결 줄(값이 있을 때만)', () => {
  const links = (c: number, k: number) => [...Array(c).fill({ status: 'confirmed' }), ...Array(k).fill({ status: 'check' })];

  it('판정 라벨 + 실패 규칙 수', () => {
    expect(finalFlowRows({ verdict: 'green', failed: 0 }, [])).toEqual([{ key: 'bundle', label: '묶음 검증', value: '통과' }]);
    expect(finalFlowRows({ verdict: 'yellow', failed: 0 }, [])[0].value).toBe('주의');
    expect(finalFlowRows({ verdict: 'red', failed: 2 }, [])[0].value).toBe('실패 · 실패 2');
    expect(finalFlowRows({ verdict: '', failed: 1 }, [])[0].value).toBe('실패 1');
  });

  it('연결 수 · 확인 필요 수', () => {
    expect(finalFlowRows(null, links(1, 2))).toEqual([{ key: 'links', label: '문서 간 연결', value: '연결 1 · 확인 필요 2' }]);
    expect(finalFlowRows(null, links(2, 0))[0].value).toBe('연결 2 · 확인 필요 0');
  });

  it('값이 없으면 줄을 만들지 않는다', () => {
    expect(finalFlowRows(null, [])).toEqual([]);
    expect(finalFlowRows(undefined, [])).toEqual([]);
    expect(finalFlowRows({ verdict: '', failed: 0 }, [])).toEqual([]);
  });
});

describe('LiveSummaryTab 마크업', () => {
  it('최종 흐름 — 위험도 판정 칸은 키 5개 표(머리 등급은 그대로), 결과 요약에 묶음 검증 · 문서 간 연결 줄(기타 서류 다음)', () => {
    const r = finalFlowResult();
    const a = done(r);
    const m = html(a);
    const d = r.decision as Obj;
    const rows = rowsOf(m).map(([k, l, v]) => [k, l, unescape(v)]);
    expect(rows.slice(0, 5)).toEqual([
      ['risk_level', '위험도', '검토 필요'],
      ['document_types', '서류 종류', '자동이체 신청서, FATCA/CRS 본인확인서, 소득 증빙, 위임장, 기타'],
      ['sensitive_categories', '정보 종류', (d.sensitive_categories as string[]).join(', ')],
      ['review_reasons', '검토 사유', (d.review_reasons as string[]).join(', ')],
      ['reason', '판단 근거', d.reason],
    ]);
    expect(rows.slice(5).map(([k]) => k)).toEqual(['docs', 'extracted', 'risk', 'final', 'other', 'bundle', 'links', 'took', 'job']);
    expect(rows.find(([k]) => k === 'bundle')?.[2]).toBe('실패 · 실패 1');
    expect(rows.find(([k]) => k === 'links')?.[2]).toBe('연결 1 · 확인 필요 2');
    // 판정 본문(overall.text)은 표가 대신한다 · 머리는 배지 '검토 필요'(같은 등급 글은 숨김)
    expect(m).not.toContain('판단됩니다');
    expect(m).toContain('검토 필요</span>');
  });

  it('판정 키가 객체가 아니면 지금처럼 판정 본문, 묶음 검증 · 연결이 없으면 줄도 없다', () => {
    const r = finalFlowResult();
    r.decision = null;
    r.bundle_check = 'red';
    r.links = [];
    const m = html(done(r));
    expect(m).toContain('판단됩니다');
    expect(rowsOf(m).map(([k]) => k)).toEqual(['docs', 'extracted', 'risk', 'final', 'other', 'took', 'job']);
  });

  it('옛 결과(done-result · items-result)는 그대로 — 판정 본문 · 줄 7개', () => {
    for (const r of [contractResult(), itemsResult()]) {
      const m = html(done(r));
      expect(rowsOf(m).map(([k]) => k)).toEqual(['docs', 'extracted', 'risk', 'final', 'other', 'took', 'job']);
      expect(m).not.toContain('data-row="risk_level"');
    }
  });
});
