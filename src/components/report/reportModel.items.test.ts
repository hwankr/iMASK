/* 실제 분석 보고서 — 서버가 계산한 검토사항이 든 결과(fixtures/items-result.json, 합성) + 해결 기록 → toAnalysis → 안전한 사본 →
   reportView · 구역 렌더. 카드 3장 · 구역 01~08 · 대상 문서 표의 남은 검토사항 열 · 05 구역 · 원문 값 없음.
   원문 값은 테스트 출력에 옮기지 않는다(있음/없음 · 개수만). */
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { toAnalysis } from '@/services/api/mapping';
import { analysisOut, itemsResult } from '@/services/api/testing';
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

function liveAnalysis(items: Obj = {}, edit?: (r: Obj) => void): Analysis {
  const result = itemsResult();
  edit?.(result);
  return toAnalysis(analysisOut({ status: 'done', result, upstage_job_id: 'job_test', upstage_status: 'completed', review: review(items) }));
}

const SECTIONS = [ReportSummary, ReportReasons, ReportDocTable, ReportFindings, ReportRemaining, ReportRecs, ReportMemo, ReportHistory];
function renderReport(v: ReportView): string {
  return [
    renderToStaticMarkup(createElement(ReportHead, { v, generatedAt: '2026.11.04 09:00' })),
    ...SECTIONS.map((C) => renderToStaticMarkup(createElement(C, { v }))),
  ].join('\n');
}
const text = (html: string) => html.replace(/<!-- -->/g, '').replace(/<[^>]+>/g, '|');
const h2s = (html: string) => [...html.matchAll(/<h2 id="(rp-s\d)"[^>]*><span[^>]*>(\d\d)<\/span>([^<]*)<\/h2>/g)].map((m) => `${m[1]} ${m[2]} ${m[3]}`);
const heads = (html: string) => [...html.matchAll(/<th scope="col"[^>]*>(.*?)<\/th>/g)].map((m) => m[1]);
const rawValues = (a: Analysis) =>
  a.findings.map((f) => f.live?.value ?? '').filter((v, i) => v && Array.from(v).length >= 2 && v !== a.findings[i].masked);

describe('실제 분석 보고서 — 검토사항이 든 결과', () => {
  const a = liveAnalysis({ 'missing:1:applicant_name_detected': { resolved: true, note: '원본에 성명 있음', resolved_at: '2026-11-04T01:00:00Z', resolved_by: '이지은' } });
  const v = reportView(reportSafeAnalysis(a));
  const html = renderReport(v);

  it('카드 3장 — 키 · 라벨 · 숫자 · 아랫줄(남은 검토사항은 주의 색)', () => {
    expect(v.cards.map((c) => [c.key, c.label])).toEqual([
      ['findings', '탐지 항목'],
      ['reviewed', '담당자 확인'],
      ['remaining', '남은 검토사항'],
    ]);
    expect(v.cards[2]).toEqual({ key: 'remaining', label: '남은 검토사항', num: 7, unit: '건', after: '', sub: '전체 8건 중 해결 1건', warn: true });
    expect(html).not.toContain('문서 간 연결');
  });

  it('카드 3장 배치 — 카드 묶음에 3장용 클래스(데스크톱 3열 · 휴대폰은 셋째 카드가 한 줄)', () => {
    const summary = renderToStaticMarkup(createElement(ReportSummary, { v }));
    expect(summary).toMatch(/class="[^"]*cardsThree[^"]*"/);
    expect(summary).not.toContain('cardsTwo');
  });

  it('구역 01~08(데모와 같은 번호 · id)', () => {
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
  });

  it('대상 문서 표 — 남은 검토사항 열과 서류별 미해결 수', () => {
    expect(v.docOpenCol).toBe(true);
    expect(heads(html).slice(0, 7)).toEqual(['문서', '형식·페이지', '처리 상태', '탐지', '높음', '담당자 확인', '남은 검토사항']);
    expect(v.docs.map((d) => [d.id, d.open])).toEqual([
      ['doc-0', 1],
      ['doc-1', 0],
      ['doc-2', 2],
      ['doc-3', 1],
      ['doc-4', 2],
      ['doc-5', 1],
    ]);
  });

  it('05 남아 있는 검토사항 — 미해결만(서버 순서) · 종류 라벨 · 제목 · 서류 쪽 · 할 일', () => {
    expect(v.remaining.map((r) => r.id)).toEqual(['R-01', 'R-03', 'R-04', 'R-05', 'R-06', 'R-07', 'R-08']);
    const docT = (id: string) => a.docs.find((d) => d.id === id)?.title;
    expect(v.remaining[0]).toEqual({ id: 'R-01', type: '인식 확인 필요', title: '인식 신뢰도가 낮은 항목 3건', where: docT('doc-0') + ' 1쪽', next: '원본과 값을 비교해 확인해 주세요.' });
    expect(v.remaining[6]).toEqual({ id: 'R-08', type: '기타 서류', title: '기타 서류로 분류된 문서', where: docT('doc-5') + ' 1쪽', next: '원본에 개인정보가 있는지 직접 확인해 주세요.' });
    const t = text(html);
    expect(t).toContain('|R-03|');
    expect(t).not.toContain('남아 있는 검토사항이 없습니다');
    expect(t).not.toContain('|R-02|'); // 해결한 항목은 05 에 없다
  });

  it('모두 해결하면 05 는 데모 문구 · 카드는 0건(주의 색 아님)', () => {
    const items = Object.fromEntries((itemsResult().items as { id: string }[]).map((i) => [i.id, { resolved: true, note: 'n' }]));
    const all = reportView(reportSafeAnalysis(liveAnalysis(items)));
    expect(all.remaining).toEqual([]);
    expect(all.cards[2]).toMatchObject({ num: 0, sub: '전체 8건 중 해결 8건', warn: false });
    expect(text(renderReport(all))).toContain('남아 있는 검토사항이 없습니다.');
    expect(all.docs.every((d) => d.open === 0)).toBe(true);
  });

  it('렌더한 HTML 에 원문 값이 없다 — 검토사항 글(제목 · 설명 · 할 일)에 심어도 masked 로', () => {
    const raws = rawValues(a);
    expect(raws.length).toBeGreaterThan(3);
    expect(raws.filter((x) => html.includes(x)).length).toBe(0);
    const planted = liveAnalysis({}, (r) => {
      const items = r.items as Obj[];
      items[0].title = '제목 ' + raws[0];
      items[0].desc = '설명 ' + raws[1];
      items[0].next = '할 일 ' + raws[2];
      (items[0].evidence as Obj[])[0].label = raws[3] + ' 열기';
    });
    expect(planted.items[0].title.includes(raws[0])).toBe(true);
    const ph = renderReport(reportView(reportSafeAnalysis(planted)));
    expect(raws.filter((x) => ph.includes(x)).length).toBe(0);
  });
});
