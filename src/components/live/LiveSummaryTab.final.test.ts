/* 실제 분석 '분석 요약' 탭 — 최종 흐름 워크플로우의 위험도 판정 칸 · 결과 요약의 묶음 검증 · 문서 간 연결 줄.
   순수 함수(decisionView · finalFlowRows)와 마크업(renderToStaticMarkup). 판정 키가 없는 옛 결과는 지금처럼(판정 본문).
   고정 자료 fixtures/final-flow-result.json(손으로 만든 모양 — 지어낸 값). */
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { toAnalysis } from '@/services/api/mapping';
import { analysisOut, contractResult, finalFlowResult, itemsResult } from '@/services/api/testing';
import type { Analysis, RawDecision, RawDecisionV2 } from '@/services/types';
import { LiveSummaryTab } from './LiveSummaryTab';
import { decisionView, finalFlowRows } from './liveModel';

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

describe('decisionView — 위험도 판정 칸', () => {
  const v2 = (patch: Partial<RawDecisionV2>): RawDecisionV2 => ({
    shape: 'v2',
    riskLevel: '상',
    documentTypes: [],
    highRiskItems: [],
    mediumRiskItems: [],
    lowRiskItems: [],
    reviewReasons: [],
    recommendedAction: null,
    reason: null,
    ...patch,
  });

  it('판정 키가 없으면 null', () => {
    expect(decisionView(null)).toBeNull();
    expect(decisionView(undefined)).toBeNull();
  });

  it('옛 모양 — 판단 근거는 따로, 줄은 정보 종류 · 검토 사유(목록은 ", "), 위험도 · 서류 종류 줄은 없다', () => {
    const d: RawDecision = {
      riskLevel: '상',
      documentTypes: ['loan_application', 'debit_card_application', 'unknown_code'],
      sensitiveCategories: ['고유식별정보', '계좌번호'],
      reviewReasons: ['사유 하나', '사유 둘'],
      reason: '근거 글',
    };
    expect(decisionView(d)).toEqual({
      reason: '근거 글',
      rows: [
        { key: 'sensitive_categories', label: '정보 종류', value: '고유식별정보, 계좌번호' },
        { key: 'review_reasons', label: '검토 사유', value: '사유 하나, 사유 둘' },
      ],
      groups: [],
    });
  });

  it('보일 값이 하나도 없으면 null(판정 본문을 보인다), 값이 없는 줄은 만들지 않는다', () => {
    expect(decisionView({ riskLevel: '상', documentTypes: ['loan_application'], sensitiveCategories: [], reviewReasons: null, reason: null })).toBeNull();
    expect(decisionView(v2({ highRiskItems: null, mediumRiskItems: [], lowRiskItems: null, reviewReasons: null }))).toBeNull();
    expect(decisionView(v2({ reason: '근거 글' }))).toEqual({ reason: '근거 글', rows: [], groups: [] });
  });

  it('설정 60 — 토큰을 등급 · 서류별로 모으고(처음 나온 순서), 코드는 이름으로 · 밑줄은 띄어쓰기로, 항목이 없는 등급은 뺀다', () => {
    const view = decisionView(
      v2({
        highRiskItems: ['체크카드_가입신청서.결제계좌', 'IRP_신규신청서.회사부담금_상품명', '체크카드_가입신청서.카드_수령지'],
        mediumRiskItems: [],
        lowRiskItems: ['IRP_신규신청서.작성일'],
      }),
    );
    expect(view?.groups).toEqual([
      {
        level: 'high',
        docs: [
          { name: '체크카드 가입신청서', items: ['결제계좌', '카드 수령지'] },
          { name: 'IRP 신규신청서', items: ['회사부담금 상품명'] },
        ],
      },
      { level: 'low', docs: [{ name: 'IRP 신규신청서', items: ['작성일'] }] },
    ]);
  });

  it('토큰을 가를 수 없으면 서류 이름 없이, 모르는 서식 코드는 밑줄만 띄어쓰기, 칸의 점은 그대로', () => {
    const view = decisionView(v2({ highRiskItems: ['서식없는_칸', '서식.', '.칸', '모르는_서식.칸.이름'] }));
    expect(view?.groups[0].docs).toEqual([
      { name: '', items: ['서식없는 칸', '서식.', '.칸'] },
      { name: '모르는 서식', items: ['칸.이름'] },
    ]);
  });

  it('이름이 같아지는 서류 코드는 한 서류로 모은다', () => {
    const view = decisionView(v2({ highRiskItems: ['체크카드_가입신청서.가', 'debit_card_application.나'] }));
    expect(view?.groups[0].docs).toEqual([{ name: '체크카드 가입신청서', items: ['가', '나'] }]);
  });
});

describe('finalFlowRows — 묶음 검증 · 문서 간 연결 줄(값이 있을 때만)', () => {
  const links = (c: number, k: number) => [...Array(c).fill({ status: 'confirmed' }), ...Array(k).fill({ status: 'check' })];

  it('판정 라벨 + 실패 규칙 수', () => {
    expect(finalFlowRows({ verdict: 'green', failed: 0 }, [])).toEqual([{ key: 'bundle', label: '묶음 검증', value: '통과' }]);
    expect(finalFlowRows({ verdict: 'yellow', failed: 0 }, [])[0].value).toBe('주의');
    expect(finalFlowRows({ verdict: 'red', failed: 2 }, [])[0].value).toBe('실패 2건');
    expect(finalFlowRows({ verdict: '', failed: 1 }, [])[0].value).toBe('실패 1건'); // 판정 라벨을 모르면 '실패 n건'
    expect(finalFlowRows({ verdict: 'yellow', failed: 1 }, [])[0].value).toBe('주의 1건');
    expect(finalFlowRows({ verdict: '', failed: 0 }, [])).toEqual([]);
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
  it('최종 흐름 — 위험도 판정 칸은 판단 근거 + 값이 있는 줄(머리 등급은 그대로), 결과 요약에 묶음 검증 · 문서 간 연결 줄(기타 서류 다음), 위험도 줄은 없다', () => {
    const r = finalFlowResult();
    const a = done(r);
    const m = html(a);
    const d = r.decision as Obj;
    const rows = rowsOf(m).map(([k, l, v]) => [k, l, unescape(v)]);
    expect(rows.slice(0, 2)).toEqual([
      ['sensitive_categories', '정보 종류', (d.sensitive_categories as string[]).join(', ')],
      ['review_reasons', '검토 사유', (d.review_reasons as string[]).join(', ')],
    ]);
    expect(unescape(m)).toContain(`>${d.reason as string}</p>`);
    expect(rows.slice(2).map(([k]) => k)).toEqual(['docs', 'extracted', 'final', 'other', 'bundle', 'links', 'took', 'job']);
    expect(rows.find(([k]) => k === 'bundle')?.[2]).toBe('실패 1건');
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
    expect(rowsOf(m).map(([k]) => k)).toEqual(['docs', 'extracted', 'final', 'other', 'took', 'job']);
  });

  it('옛 결과(done-result · items-result)는 판정 본문 · 줄 6개(위험도 줄 없음)', () => {
    for (const r of [contractResult(), itemsResult()]) {
      const m = html(done(r));
      expect(rowsOf(m).map(([k]) => k)).toEqual(['docs', 'extracted', 'final', 'other', 'took', 'job']);
      expect(m).not.toContain('data-group=');
    }
  });

  it('설정 60 — 등급별 항목은 접은 칸, 가장 높은 등급만 펼쳐 두고 안에 서류 이름 · 칸 이름', () => {
    const r = finalFlowResult();
    r.decision = {
      risk_level: '중',
      document_types: ['체크카드_가입신청서'],
      high_risk_items: [],
      medium_risk_items: ['체크카드_가입신청서.성명_한글', '체크카드_가입신청서.자택주소'],
      low_risk_items: ['체크카드_가입신청서.작성일'],
      review_reasons: [],
      recommended_action: '조치',
      reason: '근거 글',
    };
    const m = html(done(r));
    const groups = [...m.matchAll(/<details[^>]*data-group="(\w+)"[^>]*>/g)].map((x) => [x[1], / open=""/.test(x[0])]);
    expect(groups).toEqual([
      ['medium', true],
      ['low', false],
    ]);
    // 개수는 보이지 않는다(항목 종류를 세어 표의 행을 따로 세는 탐지 항목 탭의 수와 달라 보인다) — 이름은 낭독기용
    expect(m).not.toContain('개 항목');
    expect(m).toContain('aria-label="중 등급 항목"');
    expect(m).toContain('aria-label="하 등급 항목"');
    expect(m).toContain('체크카드 가입신청서</p>');
    expect(m).toContain('성명 한글</li>');
    expect(m).not.toContain('체크카드_가입신청서');
  });

  it('권장 조치 · 검토 안내 — 제목 · 굵게 표시는 보이지 않고, 글과 줄바꿈 · 마스킹 값의 별표는 남는다', () => {
    const r = finalFlowResult();
    const next = '## 조치 권고\n- **고유식별정보** | **위임장** | **접근 제한** | 김** 값이 있습니다.【†1】';
    (r.overall as Obj).next_text = next;
    const m = html(done(r));
    expect(m).toContain('조치 권고\n- 고유식별정보 | 위임장 | 접근 제한 | 김** 값이 있습니다.</p>');
    expect(m).not.toContain('## 조치 권고');
    expect(m).not.toContain('**고유식별정보');
  });

  it('결과 요약의 마지막 단계 — 코드의 밑줄 대신 띄어쓰기', () => {
    const value = (stage: unknown) => {
      const r = finalFlowResult();
      (r.summary as Obj).final_stage = stage;
      return rowsOf(html(done(r))).find(([k]) => k === 'final')?.[2];
    };
    expect(value('권장_조치')).toBe('권장 조치');
    expect(value('검토_안내')).toBe('검토 안내');
    expect(value(null)).toBe('없음');
  });
});
