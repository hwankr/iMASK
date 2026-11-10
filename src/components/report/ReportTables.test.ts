import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { FSTATUS, RISK } from '@/display/rules';
import { createService, getDemoControls } from '@/services';
import { reportView, type ReportView } from './reportModel';
import { CHANGE_TABLE_TITLE, ReportChangeTable, ReportDocTable, ReportFindings } from './ReportTables';

async function view(): Promise<ReportView> {
  const svc = createService();
  await getDemoControls(svc)?.prepare('report');
  const a = await svc.get('A1');
  if (!a) throw new Error('A1 없음');
  return reportView(a);
}

/** 보고서 표 4개(03 문서 · 04 정보 종류 · 04 전체 탐지 · 08 수정)를 서버 렌더한 HTML */
function render(v: ReportView): string {
  return [ReportDocTable, ReportFindings, ReportChangeTable].map((C) => renderToStaticMarkup(createElement(C, { v }))).join('');
}

const captions = (html: string) => [...html.matchAll(/<caption>(.*?)<\/caption>/g)].map((m) => m[1].replace(/<[^>]+>/g, ''));
const heads = (html: string) => [...html.matchAll(/<th scope="col"[^>]*>(.*?)<\/th>/g)].map((m) => m[1]);

describe('보고서 표 — 표 이름과 머리 라벨', () => {
  it('표 4개에 서로 다른 이름(<caption>, 화면에는 숨김)이 있다', async () => {
    const v = await view();
    const html = render(v);
    expect(captions(html)).toEqual([
      '대상 문서와 문서별 확인 결과',
      '정보 종류별 탐지 항목 요약',
      `전체 탐지 항목 ${v.nFind}건 (표시값 마스킹)`,
      CHANGE_TABLE_TITLE,
    ]);
    expect(new Set(captions(html)).size).toBe(4);
    // 캡션 글자는 공통 VisuallyHidden 숨김 규칙 안에 있다(화면 배치 그대로)
    expect(html.match(/<caption><span class="[^"]+">/g)).toHaveLength(4);
  });

  it('등급·오탐 열 머리는 ② 라벨 — ② 를 바꾸면 표 머리도 바뀐다', async () => {
    const v = await view();
    expect(heads(render(v))).toEqual(
      expect.arrayContaining([RISK.high.label, RISK.medium.label, RISK.low.label, FSTATUS.false_positive.label]),
    );
    const risk = RISK as unknown as Record<'high' | 'medium' | 'low', { label: string }>;
    const fstatus = FSTATUS as unknown as Record<'false_positive', { label: string }>;
    const saved = [risk.high.label, risk.medium.label, risk.low.label, fstatus.false_positive.label];
    try {
      risk.high.label = '검증 상';
      risk.medium.label = '검증 중';
      risk.low.label = '검증 하';
      fstatus.false_positive.label = '검증 오탐';
      const h = heads(render(v));
      // 03 문서 표의 상 열 + 04 정보 종류 표의 상·중·하·오탐 열
      expect(h.filter((x) => x === '검증 상')).toHaveLength(2);
      expect(h).toEqual(expect.arrayContaining(['검증 중', '검증 하', '검증 오탐']));
      // 원래 ② 라벨이 표 머리에 남아 있지 않다
      expect(h.some((x) => saved.includes(x))).toBe(false);
    } finally {
      [risk.high.label, risk.medium.label, risk.low.label, fstatus.false_positive.label] = saved;
    }
  });
});
