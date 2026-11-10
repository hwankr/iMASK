/* 위험등급별 탐지 분포 막대 — 실제 분석은 미평가 조각을 마지막에(1건 이상일 때), 데모는 상 · 중 · 하만(바꾸기 전과 같다).
   실제 분석은 합성 고정 자료(fixtures/done-result.json — 상 2 · 미평가 17) → toAnalysis → 안전한 사본 순서로 만든다.
   원문 값은 테스트 출력에 옮기지 않는다(개수 · 등급만). */
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { DEV_STATES } from '@/dev/states';
import { RISK } from '@/display/rules';
import { createService, getDemoControls } from '@/services';
import { toAnalysis } from '@/services/api/mapping';
import { analysisOut, contractResult } from '@/services/api/testing';
import { reportSafeAnalysis } from '@/services/report-safe';
import type { Analysis } from '@/services/types';
import { reportView, type DistSegment, type ReportView } from './reportModel';
import { ReportSummary } from './ReportSummary';

const NEW_REVIEW = { status: 'needed', memo: '', memo_at: null, reviewer: '', reviewed_at: null, completion_note: '', findings: {}, history: [], version: 1 };

type ContractFinding = Record<string, unknown>;

function liveAnalysis(edit?: (findings: ContractFinding[]) => ContractFinding[] | void): Analysis {
  const result = contractResult();
  const findings = result.findings as ContractFinding[];
  const out = edit?.(findings);
  if (out) result.findings = out;
  return toAnalysis(analysisOut({ status: 'done', result, upstage_job_id: 'job_test', upstage_status: 'completed', review: structuredClone(NEW_REVIEW) }));
}

const liveView = (edit?: (findings: ContractFinding[]) => ContractFinding[] | void): ReportView => reportView(reportSafeAnalysis(liveAnalysis(edit)));

/** 워크플로우가 등급을 주지 않은 항목(미평가) */
const unrate = (f: ContractFinding) => {
  f.risk_source = null;
  f.risk = null;
};
const rate = (f: ContractFinding, risk: 'high' | 'medium' | 'low') => {
  f.risk_source = 'workflow';
  f.risk = risk;
};

const segs = (v: ReportView) => v.dist.map((d) => [d.key, d.label, d.n, d.color, d.index]);

/** 01 결과 요약 HTML 의 막대 조각 style · 범례 글자 · aria */
function renderDist(v: ReportView) {
  const html = renderToStaticMarkup(createElement(ReportSummary, { v }));
  const bar = /<div role="img" aria-label="([^"]*)"[^>]*>(.*?)<\/div>/.exec(html);
  const styles = bar ? [...bar[2].matchAll(/<span[^>]*style="([^"]*)"/g)].map((m) => m[1]) : [];
  const legend = [...html.matchAll(/<span class="[^"]*legendItem[^"]*">(.*?<\/strong>)<\/span>/g)].map((m) => m[1].replace(/<!-- -->/g, '').replace(/<[^>]+>/g, ''));
  return { html, aria: bar ? bar[1] : null, styles, legend };
}

describe('실제 분석 — 분포 막대에 미평가 조각', () => {
  it('고정 자료(상 2 · 미평가 17) — 상 · 미평가 두 조각, 미평가는 마지막(index 1) · aria 같은 규칙', () => {
    const v = liveView();
    expect(v.live).toBe(true);
    expect(segs(v)).toEqual([
      ['high', '상', 2, RISK.high.solid, 0],
      ['unrated', RISK.unrated.label, 17, RISK.unrated.solid, 1],
    ]);
    expect(RISK.unrated.label).toBe('미평가');
    expect(v.distAria).toBe('위험등급별 탐지 분포: 상 2건, 미평가 17건');
    expect(v.nFind).toBe(19);
    // 조각 합 = 탐지 수(머리 '탐지 19건 기준'과 맞는다)
    expect(v.dist.reduce((s, d) => s + d.n, 0)).toBe(v.nFind);

    const r = renderDist(v);
    expect(r.aria).toBe('위험등급별 탐지 분포: 상 2건, 미평가 17건');
    expect(r.styles).toEqual(['--seg-n:2;--seg-color:var(--hi-solid);--seg-i:0', '--seg-n:17;--seg-color:var(--na-solid);--seg-i:1']);
    expect(r.legend).toEqual(['상 2건', '미평가 17건']);
    expect(r.html).toContain('탐지 19건 기준');
  });

  it('모두 미평가(26건) — 미평가 한 조각, 막대가 보인다', () => {
    const v = liveView((fs) => {
      const out: ContractFinding[] = [];
      for (let i = 0; i < 26; i++) out.push({ ...fs[i % fs.length], id: `${(fs[i % fs.length] as { document_index: number }).document_index}:u${i}` });
      out.forEach(unrate);
      return out;
    });
    expect(v.nFind).toBe(26);
    expect(segs(v)).toEqual([['unrated', '미평가', 26, RISK.unrated.solid, 0]]);
    expect(v.distAria).toBe('위험등급별 탐지 분포: 미평가 26건');
    const r = renderDist(v);
    expect(r.aria).toBe('위험등급별 탐지 분포: 미평가 26건');
    expect(r.styles).toEqual(['--seg-n:26;--seg-color:var(--na-solid);--seg-i:0']);
    expect(r.legend).toEqual(['미평가 26건']);
    expect(r.html).toContain('위험등급별 탐지 분포</strong>');
    expect(r.html).toContain('탐지 26건 기준');
  });

  it('탐지 0건 — 조각 없음 · 막대 없음 · aria 는 탐지 없음', () => {
    const v = liveView(() => []);
    expect(v.nFind).toBe(0);
    expect(v.dist).toEqual([]);
    expect(v.distAria).toBe('위험등급별 탐지 분포: 탐지 없음');
    const r = renderDist(v);
    expect(r.aria).toBeNull();
    expect(r.html).not.toContain('위험등급별 탐지 분포');
  });

  it('미평가 0건 — 지금과 같다(상 · 중 · 하 중 1건 이상인 조각만, 미평가 조각 없음)', () => {
    const v = liveView((fs) => {
      fs.forEach((f, i) => rate(f, i < 2 ? 'high' : i < 5 ? 'low' : 'medium'));
    });
    expect(segs(v)).toEqual([
      ['high', '상', 2, RISK.high.solid, 0],
      ['medium', '중', 14, RISK.medium.solid, 1],
      ['low', '하', 3, RISK.low.solid, 2],
    ]);
    expect(v.distAria).toBe('위험등급별 탐지 분포: 상 2건, 중 14건, 하 3건');
    const only = liveView((fs) => fs.forEach((f) => rate(f, 'low')));
    expect(segs(only)).toEqual([['low', '하', 19, RISK.low.solid, 0]]);
    expect(only.distAria).toBe('위험등급별 탐지 분포: 하 19건');
  });

  it('네 등급이 모두 있으면 상 · 중 · 하 · 미평가 차례(index 0~3)', () => {
    const v = liveView((fs) => {
      fs.forEach((f, i) => (i === 0 ? rate(f, 'high') : i === 1 ? rate(f, 'medium') : i === 2 ? rate(f, 'low') : unrate(f)));
    });
    expect(v.dist.map((d) => [d.key, d.n, d.index])).toEqual([
      ['high', 1, 0],
      ['medium', 1, 1],
      ['low', 1, 2],
      ['unrated', 16, 3],
    ]);
    expect(v.distAria).toBe('위험등급별 탐지 분포: 상 1건, 중 1건, 하 1건, 미평가 16건');
    expect(renderDist(v).styles.map((s) => s.split(';')[2])).toEqual(['--seg-i:0', '--seg-i:1', '--seg-i:2', '--seg-i:3']);
  });
});

/* ---------- 데모 — 상 · 중 · 하만(바꾸기 전 규칙) ---------- */

const OLD_LEVELS = ['high', 'medium', 'low'] as const;

/** 바꾸기 전 규칙 — 상 · 중 · 하 중 1건 이상인 조각, index 는 남은 차례 */
function oldDist(a: Analysis): DistSegment[] {
  return OLD_LEVELS.map((key) => ({ key, label: RISK[key].label, n: a.findings.filter((f) => f.risk === key).length, color: RISK[key].solid }))
    .filter((d) => d.n > 0)
    .map((d, index) => ({ ...d, index }));
}
const oldAria = (d: DistSegment[]) => '위험등급별 탐지 분포: ' + (d.length ? d.map((x) => x.label + ' ' + x.n + '건').join(', ') : '탐지 없음');

describe('데모 — 분포 막대가 바꾸기 전 규칙(상 · 중 · 하만)과 같다', () => {
  it('처음 샘플의 모든 분석 건', async () => {
    const svc = createService();
    const list = await svc.list();
    expect(list.length).toBeGreaterThan(0);
    for (const item of list) {
      const a = await svc.get(item.id);
      if (!a) throw new Error(item.id);
      expect(a.raw, item.id).toBeUndefined();
      const v = reportView(a);
      expect(v.live, item.id).toBe(false);
      expect(v.dist, item.id).toEqual(oldDist(a));
      expect(v.distAria, item.id).toBe(oldAria(oldDist(a)));
      expect(v.dist.some((d) => d.key === 'unrated'), item.id).toBe(false);
    }
  });

  it('/dev/states 의 모든 상태가 고른 분석 건(prepare 뒤 서비스 값)', async () => {
    let seen = 0;
    for (const s of DEV_STATES) {
      const svc = createService();
      const { analysisId } = (await getDemoControls(svc)?.prepare(s.id)) ?? {};
      if (!analysisId) continue;
      const a = await svc.get(analysisId);
      if (!a) throw new Error(s.id);
      const v = reportView(a);
      expect(v.dist, s.id).toEqual(oldDist(a));
      expect(v.distAria, s.id).toBe(oldAria(oldDist(a)));
      seen++;
    }
    expect(seen).toBeGreaterThan(10);
  });

  it('데모 분석에 미평가 항목이 있어도 막대에 넣지 않는다(실제 분석만 미평가 조각)', async () => {
    const a = await createService().get('A1');
    if (!a) throw new Error('A1');
    const unrated: Analysis = { ...a, findings: a.findings.map((f, i) => (i < 3 ? { ...f, risk: 'unrated' as const } : f)) };
    expect(unrated.findings.filter((f) => f.risk === 'unrated')).toHaveLength(3);
    const v = reportView(unrated);
    expect(v.live).toBe(false);
    expect(v.dist).toEqual(oldDist(unrated));
    expect(v.dist.some((d) => d.key === 'unrated')).toBe(false);
    expect(v.distAria).not.toContain('미평가');
  });
});
