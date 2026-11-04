/* 실제 분석 보고서 — 화면 모델(reportView) · 구역 렌더(renderToStaticMarkup) · 데모 값 그대로(바꾸기 전 고정 자료와 비교) ·
   수정 표 시각 짝짓기. 실제 분석은 합성 고정 자료(fixtures/done-result.json) + 검토 기록 → toAnalysis → 안전한 사본 순서로 만든다.
   원문 값은 테스트 출력에 옮기지 않는다(있음/없음 · 개수만). */
import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { HKIND, RISK } from '@/display/rules';
import { createService, getDemoControls } from '@/services';
import { toAnalysis } from '@/services/api/mapping';
import { analysisOut, contractResult } from '@/services/api/testing';
import { reportSafeAnalysis } from '@/services/report-safe';
import type { Analysis } from '@/services/types';
import { FOOTER_MASKED, reportView, targetsFinding, type ReportView } from './reportModel';
import { ReportHead } from './ReportHead';
import { ReportHistory } from './ReportHistory';
import { ReportMemo, ReportReasons, ReportRecs, ReportRemaining } from './ReportLists';
import { ReportSummary } from './ReportSummary';
import { ReportDocTable, ReportFindings } from './ReportTables';

const NEW_REVIEW = { status: 'needed', memo: '', memo_at: null, reviewer: '', reviewed_at: null, completion_note: '', findings: {}, history: [], version: 1 };

function liveAnalysis(edit?: (r: Record<string, unknown>) => void, review: Record<string, unknown> = NEW_REVIEW): Analysis {
  const result = contractResult();
  edit?.(result);
  return toAnalysis(analysisOut({ status: 'done', result, upstage_job_id: 'job_test', upstage_status: 'completed', review: structuredClone(review) }));
}

const SECTIONS = [ReportSummary, ReportReasons, ReportDocTable, ReportFindings, ReportRemaining, ReportRecs, ReportMemo, ReportHistory];

/** 보고서 머리 + 구역 전부의 HTML(화면과 같은 순서) */
function renderReport(v: ReportView): string {
  return [
    renderToStaticMarkup(createElement(ReportHead, { v, generatedAt: '2026.11.04 09:00' })),
    ...SECTIONS.map((C) => renderToStaticMarkup(createElement(C, { v }))),
  ].join('\n');
}

const text = (html: string) => html.replace(/<!-- -->/g, '').replace(/<[^>]+>/g, '|');
const h2s = (html: string) => [...html.matchAll(/<h2 id="(rp-s\d)"[^>]*><span[^>]*>(\d\d)<\/span>([^<]*)<\/h2>/g)].map((m) => `${m[1]} ${m[2]} ${m[3]}`);
const heads = (html: string) => [...html.matchAll(/<th scope="col"[^>]*>(.*?)<\/th>/g)].map((m) => m[1]);

/** 원래 분석의 대상 원문 값 */
const rawValues = (a: Analysis) =>
  a.findings.map((f) => f.live?.value ?? '').filter((v, i) => v && Array.from(v).length >= 2 && v !== a.findings[i].masked);

describe('실제 분석 보고서 모델', () => {
  const a = liveAnalysis();
  const v = reportView(reportSafeAnalysis(a));

  it('카드 3장(탐지 항목 · 담당자 확인 · 남은 검토사항), 미평가가 있으면 탐지 항목 아랫줄에 · 미평가 n', () => {
    expect(v.live).toBe(true);
    expect(v.cards.map((c) => c.key)).toEqual(['findings', 'reviewed', 'remaining']);
    // 옛 결과(items 없음) — 남은 검토사항 0건
    expect(v.cards[2]).toMatchObject({ label: '남은 검토사항', num: 0, unit: '건', after: '', sub: '전체 0건 중 해결 0건', warn: false });
    const n = (k: string) => a.findings.filter((f) => f.risk === k).length;
    expect(n('unrated')).toBeGreaterThan(0);
    expect(v.cards[0].sub).toBe(`높음 ${n('high')} · 보통 ${n('medium')} · 낮음 ${n('low')} · ${RISK.unrated.label} ${n('unrated')}`);
    expect(v.cards[0].num).toBe(a.findings.length);
  });

  it('미평가가 0건이면 덧붙이지 않는다 · 정보 종류별 표의 미평가 열도 없다', () => {
    const rated = liveAnalysis((r) => {
      for (const f of r.findings as Record<string, unknown>[]) {
        f.risk_source = 'workflow';
        f.risk = 'low';
      }
    });
    const rv = reportView(reportSafeAnalysis(rated));
    expect(rv.cards[0].sub).toBe(`높음 0 · 보통 0 · 낮음 ${rated.findings.length}`);
    expect(rv.catUnratedCol).toBe(false);
    expect(heads(renderReport(rv))).not.toContain(RISK.unrated.label);
  });

  it('구역 번호 01~08(데모와 같음) · 대상 문서 표의 남은 검토사항 열 · 남은 0개면 데모 문구 · 정보 종류별 표의 미평가 열', () => {
    const html = renderReport(v);
    expect(h2s(html)).toEqual([
      'rp-s1 01 결과 요약',
      'rp-s2 02 주요 위험 사유',
      'rp-s3 03 대상 문서와 문서별 확인 결과',
      'rp-s4 04 탐지 항목 요약',
      'rp-s5 05 남아 있는 검토사항',
      'rp-s6 06 권장 조치',
      'rp-s7 07 검토자 메모',
      'rp-s8 08 수정 이력과 검토 기록',
    ]);
    expect(v.sections).toEqual({ summary: 1, reasons: 2, docs: 3, findings: 4, remaining: 5, recs: 6, memo: 7, history: 8 });
    expect(html).not.toContain('문서 간 연결');
    expect(v.docOpenCol).toBe(true);
    expect(v.remaining).toEqual([]);
    expect(text(html)).toContain('남아 있는 검토사항이 없습니다.');
    const h = heads(html);
    expect(h.slice(0, 7)).toEqual(['문서', '형식·페이지', '처리 상태', '탐지', '높음', '담당자 확인', '남은 검토사항']);
    expect(h.slice(7, 15)).toEqual(['정보 종류', '건수', '높음', '보통', '낮음', '미평가', '확인', '오탐']);
    expect(v.catUnratedCol).toBe(true);
    expect(v.cats.reduce((s, c) => s + c.unrated, 0)).toBe(a.findings.filter((f) => f.risk === 'unrated').length);
  });

  it('빈 위험 사유 · 권장 조치는 -, 꼬리말은 한 문장', () => {
    const empty = liveAnalysis((r) => {
      const overall = r.overall as Record<string, unknown>;
      overall.text = '';
      overall.next_text = '';
    });
    const ev = reportView(reportSafeAnalysis(empty));
    expect(ev.reasons).toEqual([]);
    expect(ev.recs).toEqual([]);
    expect(ev.noReasonsText).toBe('-');
    expect(ev.noRecsText).toBe('-');
    const html = renderReport(ev);
    expect(html).not.toContain('분석이 끝나면');
    expect(text(html)).toContain('|02|주요 위험 사유||-|');
    expect(text(html)).toContain('|06|권장 조치||-|');
    expect(ev.footer).toEqual([FOOTER_MASKED]);
    expect(ev.footer[0]).toBe('민감한 값은 마스킹해 표시했습니다. 원문 값은 보고서와 내보내기 파일에 포함하지 않습니다.');
  });

  it('전체 탐지 항목은 서류 순번 → 서류 안 순번의 숫자 순(D2 가 D10 앞, D1-02 가 D1-10 앞)', () => {
    // 서류 11개(D1~D11)로 늘리고 계약 순서를 섞는다
    const many = liveAnalysis((r) => {
      const docs = r.documents as Record<string, unknown>[];
      const base = docs[0];
      const out: Record<string, unknown>[] = [];
      for (let i = 0; i < 11; i++) out.push({ ...base, index: i, page_start: 1, page_end: 1 });
      r.documents = out;
      const f0 = (r.findings as Record<string, unknown>[])[0];
      const fs: Record<string, unknown>[] = [];
      for (let d = 10; d >= 0; d--) for (let k = 0; k < (d === 0 ? 11 : 1); k++) fs.push({ ...f0, id: `${d}:f${k}`, document_index: d, field: `f${k}` });
      r.findings = fs;
    });
    const mv = reportView(reportSafeAnalysis(many));
    const ids = mv.findings.map((f) => f.id);
    expect(ids.slice(0, 12)).toEqual(['D1-01', 'D1-02', 'D1-03', 'D1-04', 'D1-05', 'D1-06', 'D1-07', 'D1-08', 'D1-09', 'D1-10', 'D1-11', 'D2-01']);
    expect(ids.indexOf('D2-01')).toBeLessThan(ids.indexOf('D10-01'));
    expect(ids.slice(-2)).toEqual(['D10-01', 'D11-01']);
    // 서비스(계약) 순서는 섞여 있었다(D11 이 먼저)
    expect(many.findings[0].id).toBe('D11-01');
  });

  it('렌더한 HTML 에 원문 값이 없다(접힌 전체 탐지 항목 · 속성 포함) — 워크플로우 글에 심어도', () => {
    const raws = rawValues(a);
    expect(raws.length).toBeGreaterThan(0);
    const html = renderReport(v);
    expect(raws.filter((x) => html.includes(x)).length).toBe(0);
    const plantedA = liveAnalysis((r) => {
      const overall = r.overall as Record<string, unknown>;
      overall.text = '- ' + raws.join(' / ');
      overall.next_text = '- ' + raws[0];
      (r.findings as Record<string, unknown>[])[0].risk_reason = raws[1];
    });
    const ph = renderReport(reportView(reportSafeAnalysis(plantedA)));
    expect(raws.filter((x) => ph.includes(x)).length).toBe(0);
  });

  it('검토 기록 — 서버 이력 줄 그대로(내보내기 줄 포함), 08 구역', () => {
    const withHistory = liveAnalysis(undefined, {
      ...NEW_REVIEW,
      history: [
        { id: 'S1', at: '2026-11-04T01:00:00+00:00', actor: '시스템', kind: 'ai', target: '분석 건', change: '자동 분석 완료', reason: '' },
        { id: 'H2', at: '2026-11-04T02:00:00+00:00', actor: '이지은', kind: 'export', target: 'iMASK_DG-20261102-AB12_검토결과.json', change: 'JSON · 22KB · 다운로드 요청', reason: '민감한 값 마스킹' },
      ],
    });
    const hv = reportView(reportSafeAnalysis(withHistory));
    expect(hv.history.map((h) => [h.kind, h.at, h.change])).toEqual([
      [HKIND.ai, '2026.11.04 10:00', '자동 분석 완료'],
      ['결과 내보내기', '2026.11.04 11:00', 'JSON · 22KB · 다운로드 요청'],
    ]);
    expect(text(renderReport(hv))).toContain('결과 내보내기');
  });
});

describe('아주 긴 원문 값(V-T2-1 V1 회귀) — 보고서 모델 · 렌더', () => {
  const big = (seed: number, len: number) => {
    const out: string[] = [];
    for (let i = 0; i < len; i++) out.push(String.fromCodePoint(0xac00 + ((i * 7 + seed) % 11172)));
    return out.join('');
  };

  for (const len of [65536, 262144]) {
    it(`${len} 코드 포인트 값 — 예외 없이 그리고 HTML 에 원문 값이 없다`, () => {
      const value = big(len, len);
      const a = liveAnalysis((r) => {
        const findings = r.findings as Record<string, unknown>[];
        findings[0].value = value;
        findings[0].masked = '***';
        findings[1].risk_reason = '근거 ' + value;
        const overall = r.overall as Record<string, unknown>;
        overall.text = '- 사유 ' + value + '\n- 둘째';
        overall.next_text = '- 조치 ' + value;
      });
      const v = reportView(reportSafeAnalysis(a));
      expect(v.reasons).toEqual(['사유 ***', '둘째']);
      expect(v.recs).toEqual(['조치 ***']);
      const html = renderReport(v);
      expect(h2s(html)).toHaveLength(8);
      expect(html.includes(value.slice(3000, 3064))).toBe(false);
      expect(rawValues(a).filter((x) => html.includes(x)).length).toBe(0);
    });
  }
});

describe('수정 표의 수정 시각 — 이력 대상이 번호와 같거나 \'번호 + 공백\'으로 시작', () => {
  it('targetsFinding', () => {
    expect(targetsFinding('D1-10', 'D1-10')).toBe(true);
    expect(targetsFinding('D1-10 주민등록번호', 'D1-10')).toBe(true);
    expect(targetsFinding('D1-100 주민등록번호', 'D1-10')).toBe(false);
    expect(targetsFinding('D1-1', 'D1-10')).toBe(false);
    expect(targetsFinding('F-10 성명', 'F-1')).toBe(false);
  });

  it('D1-10 이 D1-100 줄의 시각을 잡지 않는다', () => {
    const many = liveAnalysis((r) => {
      const f0 = (r.findings as Record<string, unknown>[])[0];
      r.findings = Array.from({ length: 100 }, (_, k) => ({ ...f0, id: `0:f${k}`, field: `f${k}` }));
    }, {
      ...NEW_REVIEW,
      findings: { '0:f9': { status: 'false_positive', fp_type: '이미 가려진 값', fp_note: '가림' } },
      history: [
        { id: 'H1', at: '2026-11-04T01:00:00+00:00', actor: '이지은', kind: 'fp', target: 'D1-10 성명', change: 'x', reason: '' },
        { id: 'H2', at: '2026-11-04T03:00:00+00:00', actor: '이지은', kind: 'fp', target: 'D1-100 성명', change: 'x', reason: '' },
      ],
    });
    expect(many.findings[99].id).toBe('D1-100');
    const cv = reportView(reportSafeAnalysis(many));
    const row = cv.changes.find((c) => c.id === 'D1-10');
    expect(row?.at).toBe('2026.11.04 10:00');
  });

  it('데모 — 수정 시각 결과가 바꾸기 전과 같다(F-10 · F-12)', async () => {
    const svc = createService();
    await getDemoControls(svc)?.prepare('report');
    const a = await svc.get('A1');
    if (!a) throw new Error('A1');
    const before = BEFORE.view['A1-report'] as ReportView;
    expect(reportView(a).changes).toEqual(before.changes);
  });
});

/* ---------- 데모 값 그대로 ---------- */

interface Before {
  view: Record<string, unknown>;
  html: Record<string, { sha256: string; length: number }>;
}
const BEFORE: Before = JSON.parse(readFileSync(new URL('./fixtures/demo-report-before.json', import.meta.url), 'utf8'));

describe('데모 보고서 — 바꾸기 전(main e99c75a)과 같다', () => {
  const CASES: [string, string, 'report' | undefined][] = [
    ['A1', 'A1', undefined],
    ['A1-report', 'A1', 'report'],
    ['A2', 'A2', undefined],
    ['A3', 'A3', undefined],
    ['A4', 'A4', undefined],
    ['A5', 'A5', undefined],
    ['A6', 'A6', undefined],
  ];
  for (const [key, id, state] of CASES) {
    it(`${key} — reportView 의 원래 필드 값과 구역 HTML(sha256)`, async () => {
      const svc = createService();
      if (state) await getDemoControls(svc)?.prepare(state);
      const a = await svc.get(id);
      if (!a) throw new Error(id);
      expect(reportSafeAnalysis(a)).toBe(a);
      const v = reportView(a);
      expect(v).toMatchObject(BEFORE.view[key] as object);
      expect(v.live).toBe(false);
      expect(v.cards).toHaveLength(4);
      const html = renderReport(v);
      expect(html.length).toBe(BEFORE.html[key].length);
      expect(createHash('sha256').update(html, 'utf8').digest('hex')).toBe(BEFORE.html[key].sha256);
      expect(v.footer).toEqual([
        '이 보고서는 iMASK 데모 환경에서 만든 예시입니다. 위험 규칙 ID와 위험 기준은 데모용이며, 실측 정확도나 공식 인증 결과가 아닙니다.',
        FOOTER_MASKED,
      ]);
    });
  }

  it('새로 더한 필드의 데모 값', async () => {
    const a = await createService().get('A1');
    if (!a) throw new Error('A1');
    const v = reportView(a);
    expect(v.sections).toEqual({ summary: 1, reasons: 2, docs: 3, findings: 4, remaining: 5, recs: 6, memo: 7, history: 8 });
    expect(v.docOpenCol).toBe(true);
    expect(v.catUnratedCol).toBe(false);
    expect(v.noRecsText).toBe('분석이 끝나면 권장 조치가 표시됩니다.');
  });
});
