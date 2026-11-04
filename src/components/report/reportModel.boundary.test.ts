/* 최종 흐름 글의 경계 — 원문 값 가리기 × 길이 한도 × 짝 없는 서로게이트(V-T4-2 F1). 함수 순서가 아니라 **최종 출력의 성질**을 본다:
   - 원문 값이 2,000 경계를 가로지르는 글을 연결 다섯 자리 · 판정 reason · review_reasons 에 넣어도 연결 카드 마크업 · 보고서 HTML ·
     JSON · CSV 내보내기 어디에도 원문 값의 8 코드 포인트 이상 조각이 없다.
   - masked 치환 결과가 아주 길거나 짝 없는 서로게이트를 가져도 최종 글은 한도 안이고 서로게이트가 없다(넘으면 버린다).
   - 정상 값(짧은 글 · 정상 서로게이트 쌍)은 그대로.
   고정 자료 fixtures/final-flow-result.json(손으로 만든 합성 자료). 원문 값은 테스트 출력에 옮기지 않는다(개수 · 여부만). */
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { CONFIG } from '@/config/app';
import { READ_ONLY_ACTIONS } from '@/components/detail/detailActions';
import { detailFacts, resultsModel } from '@/components/detail/detailModel';
import { createDetailState } from '@/components/detail/detailState';
import { LinkCards } from '@/components/detail/LinkCards';
import { decisionRows } from '@/components/live/liveModel';
import { MAX_TEXT } from '@/services/api/contract';
import { toAnalysis } from '@/services/api/mapping';
import { analysisOut, finalFlowResult } from '@/services/api/testing';
import { buildExportFile } from '@/services/export-file';
import { reportSafeAnalysis } from '@/services/report-safe';
import type { Analysis } from '@/services/types';
import { reportView } from './reportModel';
import { ReportHead } from './ReportHead';
import { ReportHistory } from './ReportHistory';
import { ReportMemo, ReportReasons, ReportRecs, ReportRemaining } from './ReportLists';
import { ReportSummary } from './ReportSummary';
import { ReportDocTable, ReportFindings } from './ReportTables';

type Obj = Record<string, unknown>;
type RawLink = { title: string; basis: string[]; missing: string; check: string; docs: { fields: string }[] };
type RawFinding = { id: string; value: string; masked: string };

/** 조각 길이(코드 포인트) */
const FRAG = 8;
const cps = (s: string) => Array.from(s).length;
const lone = (s: string) => /[\uD800-\uDFFF]/u.test(s);

const REVIEW = { status: 'needed', memo: '', memo_at: null, reviewer: '', reviewed_at: null, completion_note: '', findings: {}, items: {}, history: [], version: 1 };
const live = (result: Obj): Analysis => toAnalysis(analysisOut({ status: 'done', result, upstage_job_id: 'job_test', upstage_status: 'completed', review: structuredClone(REVIEW) }));

/** 원문 값(masked 와 다르고 FRAG 코드 포인트 이상) — 겹치지 않게 */
const rawsOf = (r: Obj): string[] => [...new Set((r.findings as RawFinding[]).filter((f) => f.value && f.value !== f.masked && cps(f.value) >= FRAG).map((f) => f.value))];
/** 원문 값들의 FRAG 코드 포인트 조각 모두 */
function fragments(raws: readonly string[]): string[] {
  const out = new Set<string>();
  for (const v of raws) {
    const a = Array.from(v);
    for (let i = 0; i + FRAG <= a.length; i++) out.add(a.slice(i, i + FRAG).join(''));
  }
  return [...out];
}
const leaks = (text: string, frags: readonly string[]) => frags.filter((f) => text.includes(f)).length;

/** 연결 다섯 자리(모든 연결 · 모든 서류) · 판정 reason · review_reasons 에 글을 심는다 */
function plant(r: Obj, text: (slot: number) => string): Obj {
  (r.links as RawLink[]).forEach((l, i) => {
    l.title = text(i * 10);
    l.basis = [text(i * 10 + 1), '근거'];
    l.missing = text(i * 10 + 2);
    l.check = text(i * 10 + 3);
    l.docs.forEach((d, k) => (d.fields = text(i * 10 + 4 + k)));
  });
  const d = r.decision as Obj;
  d.reason = text(100);
  d.review_reasons = [text(101), '검토 사유'];
  return r;
}

function cardMarkup(a: Analysis): string {
  const s = { ...createDetailState(a).state, tab: 'links' as const };
  const rs = resultsModel(a, s, detailFacts(a, s));
  return renderToStaticMarkup(createElement(LinkCards, { links: rs.links, locked: rs.locked, intro: rs.linksIntro, onPickDoc: () => {}, actions: READ_ONLY_ACTIONS }));
}
const SECTIONS = [ReportSummary, ReportReasons, ReportDocTable, ReportFindings, ReportRemaining, ReportRecs, ReportMemo, ReportHistory];
function reportMarkup(a: Analysis): string {
  const v = reportView(reportSafeAnalysis(a));
  return [renderToStaticMarkup(createElement(ReportHead, { v, generatedAt: '2026.11.04 09:00' })), ...SECTIONS.map((C) => renderToStaticMarkup(createElement(C, { v })))].join('\n');
}
const exported = (a: Analysis, format: 'csv' | 'json') => buildExportFile(reportSafeAnalysis(a), format, { brand: CONFIG.brandName, generatedAt: '2026-11-04 15:07', live: true }).text;
const everyOutput = (a: Analysis) => [cardMarkup(a), reportMarkup(a), exported(a, 'json'), exported(a, 'csv')].join('\n');

/** 연결 · 판정에서 나온 최종 글 — masked: 원문 값을 가려야 하는 글(상세 연결 · 안전한 사본 · 주요 위험 사유 · JSON),
 *  detail: 상세 판정 표(원래 글을 보여도 되는 곳 — 최종 규칙만) */
function finalStrings(a: Analysis): { masked: string[]; detail: string[] } {
  const safe = reportSafeAnalysis(a);
  const linkTexts = (ls: Analysis['links']) => ls.flatMap((l) => [l.title, l.missing, l.check, ...l.basis, ...l.docs.map((d) => d.fields)]);
  const json = JSON.parse(exported(a, 'json')) as { 주요위험사유: string[]; 문서간연결: { 내용: string; 근거: string[] }[] };
  return {
    masked: [
      ...linkTexts(a.links),
      ...linkTexts(safe.links),
      ...a.riskReasons,
      ...safe.riskReasons,
      ...json.주요위험사유,
      ...json.문서간연결.flatMap((l) => [l.내용, ...l.근거]),
    ],
    detail: decisionRows(a.raw?.decision)?.map((x) => x.value) ?? [],
  };
}

describe('원문 값이 2,000 코드 포인트 경계를 가로지르는 글', () => {
  const raws = rawsOf(finalFlowResult());
  const frags = fragments(raws);

  it('고정 자료에는 경계 시험에 쓸 원문 값이 있고, 정상 출력에는 그 조각이 없다', () => {
    expect(raws.length).toBeGreaterThanOrEqual(3);
    expect(leaks(everyOutput(live(finalFlowResult())), frags)).toBe(0);
  });

  it('연결 다섯 자리 · 판정 reason · review_reasons — 카드 · 보고서 HTML · JSON · CSV 어디에도 원문 8자 조각이 없다(넘는 글은 통째로 버림)', () => {
    let cases = 0;
    for (const v of raws) {
      for (const before of [1, Math.floor(cps(v) / 2), cps(v) - 1]) {
        // 원문 값이 MAX_TEXT − before 번째 코드 포인트에서 시작해 경계(MAX_TEXT)를 가로지른다
        const straddle = 'q'.repeat(MAX_TEXT - before) + v + ' 끝';
        const a = live(plant(finalFlowResult(), () => straddle));
        expect(leaks(everyOutput(a), frags)).toBe(0);
        // 상세 판정 표(원래 글을 보여도 되는 곳)도 최종 규칙을 지나 한도를 넘는 글은 '-'
        const rows = decisionRows(a.raw?.decision);
        expect(rows?.find((x) => x.key === 'reason')?.value).toBe('-');
        expect(leaks(JSON.stringify(rows), frags)).toBe(0);
        cases++;
      }
    }
    expect(cases).toBe(raws.length * 3);
  });

  it('가린 결과가 한도 안이면 그 글은 보이고(masked 로), 원문 조각은 없다 — 경계 바로 안쪽', () => {
    const fs = finalFlowResult().findings as RawFinding[];
    for (const v of raws) {
      const masked = fs.find((f) => f.value === v)!.masked;
      const inside = 'q'.repeat(MAX_TEXT - cps(v)) + v; // 정확히 MAX_TEXT 코드 포인트
      const a = live(plant(finalFlowResult(), () => inside));
      const out = everyOutput(a);
      expect(leaks(out, frags)).toBe(0);
      expect(a.links[0].title === 'q'.repeat(MAX_TEXT - cps(v)) + masked).toBe(true);
      expect(cardMarkup(a).includes(masked)).toBe(true);
      expect(reportSafeAnalysis(a).riskReasons[0] === 'q'.repeat(MAX_TEXT - cps(v)) + masked).toBe(true);
    }
  });
});

describe('masked 치환 결과가 아주 길거나 짝 없는 서로게이트를 가질 때', () => {
  it('최종 글은 늘 한도 안 · 짝 없는 서로게이트 없음 — 넘으면 버리고, 서로게이트는 U+FFFD', () => {
    const v = rawsOf(finalFlowResult())[0];
    for (const bad of ['*'.repeat(MAX_TEXT + 30) + '\uD800', 'M\uD800', '\uDC00', 'N'.repeat(MAX_TEXT - 5)]) {
      const r = plant(finalFlowResult(), () => '사유 ' + v);
      for (const f of r.findings as RawFinding[]) if (f.value === v) f.masked = bad;
      const a = live(r);
      const { masked, detail } = finalStrings(a);
      const strings = [...masked, ...detail];
      expect(masked.length).toBeGreaterThan(20);
      expect(detail.length).toBe(5);
      expect(strings.filter((s) => cps(s) > MAX_TEXT).length).toBe(0);
      expect(strings.filter(lone).length).toBe(0);
      expect(masked.filter((s) => s.includes(v)).length).toBe(0);
      if (cps(bad) + 3 > MAX_TEXT) {
        // 가린 결과가 넘는다 — 그 글은 비고(근거 줄 · 사유 줄은 빠진다), 고정 글만 남는다
        expect([a.links[0].title, a.links[0].missing]).toEqual(['', '']);
        expect(a.links[0].basis).toEqual(['근거']);
        expect(reportSafeAnalysis(a).riskReasons).toEqual(['검토 사유']);
      } else {
        expect(a.links[0].title.startsWith('사유 ')).toBe(true);
      }
    }
  });
});

describe('정상 값은 그대로', () => {
  it('짧은 글 · 정상 서로게이트 쌍 · 한글 — 연결 · 판정 · 보고서 사유가 받은 글 그대로', () => {
    const ok = (slot: number) => `😀 정상 근거 ${slot} — 𝒜𝒷`;
    const a = live(plant(finalFlowResult(), ok));
    expect(a.links[0].title).toBe(ok(0));
    expect(a.links[0].basis).toEqual([ok(1), '근거']);
    expect(a.links[1].docs[1].fields).toBe(ok(15));
    expect(a.raw?.decision?.reason).toBe(ok(100));
    expect(reportSafeAnalysis(a).riskReasons).toEqual([ok(100), ok(101), '검토 사유']);
    expect(JSON.parse(exported(a, 'json')).주요위험사유).toEqual([ok(100), ok(101), '검토 사유']);
  });

  it('고정 자료 그대로 — 연결 글 · 주요 위험 사유가 응답 값과 같다', () => {
    const r = finalFlowResult();
    const a = live(r);
    const raw = r.links as RawLink[];
    expect(a.links.map((l) => [l.title, l.basis, l.missing, l.check, l.docs.map((d) => d.fields)])).toEqual(raw.map((l) => [l.title, l.basis, l.missing, l.check, l.docs.map((d) => d.fields)]));
    const d = r.decision as { reason: string; review_reasons: string[] };
    expect(reportSafeAnalysis(a).riskReasons).toEqual([d.reason, ...d.review_reasons]);
  });
});
