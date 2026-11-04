/* 실제 분석 검토사항 — 안전한 사본(report-safe.ts)과 내보내기 파일(export-file.ts). 고정 자료 fixtures/items-result.json(합성).
   검토사항 글(제목 · 설명 · 할 일 · 근거 이름)의 원문 값은 masked 로 · 처리 내용은 그대로, JSON 의 검토사항 키 자리 · 모양,
   문서간연결 없음, CSV 는 그대로. 원문 값은 테스트 출력에 옮기지 않는다(있음/없음 · 개수만). */
import { describe, expect, it } from 'vitest';
import { CONFIG } from '@/config/app';
import { toAnalysis } from './api/mapping';
import { analysisOut, contractResult, itemsResult } from './api/testing';
import { buildExportFile } from './export-file';
import { reportSafeAnalysis } from './report-safe';
import type { Analysis } from './types';

type Obj = Record<string, unknown>;

function review(items: Obj = {}): Obj {
  return { status: 'needed', memo: '', memo_at: null, reviewer: '', reviewed_at: null, completion_note: '', findings: {}, items, history: [], version: 1 };
}
const live = (result: Obj, items: Obj = {}): Analysis =>
  toAnalysis(analysisOut({ status: 'done', result, upstage_job_id: 'job_test', upstage_status: 'completed', review: review(items) }));
const rawValues = (a: Analysis) =>
  a.findings.map((f) => f.live?.value ?? '').filter((v, i) => v && Array.from(v).length >= 2 && v !== a.findings[i].masked);
const file = (a: Analysis, format: 'csv' | 'json') => buildExportFile(reportSafeAnalysis(a), format, { brand: CONFIG.brandName, generatedAt: '2026-11-04 15:07', live: true });

/** 원문 값을 검토사항 글 · 근거 이름 · 처리 내용에 심은 분석 */
function planted(): { a: Analysis; raws: string[] } {
  const raws = rawValues(live(itemsResult()));
  const r = itemsResult();
  const items = r.items as Obj[];
  items[0].title = '제목 ' + raws[0] + ' 끝';
  items[0].desc = raws[1];
  items[0].next = '할 일 ' + raws[2];
  (items[0].evidence as Obj[])[0].label = raws[3] + ' 쪽';
  items[7].title = raws[0] + raws[1];
  const a = live(r, { 'lowconf:0': { resolved: true, note: '담당자 메모 ' + raws[4], resolved_at: '2026-11-04T01:00:00Z', resolved_by: '이지은' } });
  return { a, raws };
}

describe('안전한 사본 — 검토사항 글', () => {
  it('제목 · 설명 · 할 일 · 근거 이름의 원문 값은 masked 로, 처리 내용 · 처리자는 그대로, 원래 객체는 그대로', () => {
    const { a, raws } = planted();
    const before = structuredClone(a.items);
    const safe = reportSafeAnalysis(a);
    const masked = (raw: string) => a.findings.find((f) => f.live?.value === raw)?.masked ?? '';
    expect(safe.items[0].title).toBe('제목 ' + masked(raws[0]) + ' 끝');
    expect(safe.items[0].desc).toBe(masked(raws[1]));
    expect(safe.items[0].next).toBe('할 일 ' + masked(raws[2]));
    expect(safe.items[0].evidence[0].label).toBe(masked(raws[3]) + ' 쪽');
    expect(safe.items[7].title).toBe(masked(raws[0]) + masked(raws[1]));
    // 담당자가 쓴 처리 내용 · 처리자는 바꾸지 않는다
    expect(safe.items[0].note).toBe(a.items[0].note);
    expect(safe.items[0].note.includes(raws[4])).toBe(true);
    expect(safe.items[0].resolvedBy).toBe('이지은');
    // 위치 · 번호 · 계약 id 는 그대로
    expect(safe.items.map((i) => [i.id, i.live?.id, i.docId, i.page, i.evidence.map((e) => e.anchors)])).toEqual(a.items.map((i) => [i.id, i.live?.id, i.docId, i.page, i.evidence.map((e) => e.anchors)]));
    expect(a.items).toEqual(before);
    expect(safe.items).not.toBe(a.items);
  });

  it('원문 값이 없는 글은 그대로(서버 고정 문구)', () => {
    const a = live(itemsResult());
    const safe = reportSafeAnalysis(a);
    expect(safe.items.map((i) => [i.title, i.desc, i.next, i.evidence.map((e) => e.label)])).toEqual(a.items.map((i) => [i.title, i.desc, i.next, i.evidence.map((e) => e.label)]));
  });
});

describe('내보내기 — 실제 분석 검토사항', () => {
  const a = live(itemsResult(), { 'missing:1:applicant_name_detected': { resolved: true, note: '원본에 성명 있음', resolved_at: '2026-11-04T01:00:00Z', resolved_by: '이지은' } });

  it('JSON 최상위 키 — 보고서 · 분석 · 대상문서 · 주요위험사유 · 탐지항목 · 검토사항 · 권장조치 · 검토메모 · 검토이력(문서간연결 없음)', () => {
    const obj = JSON.parse(file(a, 'json').text);
    expect(Object.keys(obj)).toEqual(['보고서', '분석', '대상문서', '주요위험사유', '탐지항목', '검토사항', '권장조치', '검토메모', '검토이력']);
    expect(obj).not.toHaveProperty('문서간연결');
    expect(obj.보고서.데모데이터).toBe(false);
  });

  it('검토사항 항목 모양 — 데모와 같은 키(ID · 유형 · 내용 · 상태 · 처리내용) · 서버 순서', () => {
    const obj = JSON.parse(file(a, 'json').text);
    expect(obj.검토사항).toHaveLength(8);
    expect(obj.검토사항.every((r: Obj) => Object.keys(r).join(',') === 'ID,유형,내용,상태,처리내용')).toBe(true);
    expect(obj.검토사항[0]).toEqual({ ID: 'R-01', 유형: '인식 확인 필요', 내용: '인식 신뢰도가 낮은 항목 3건', 상태: '미해결', 처리내용: '' });
    expect(obj.검토사항[1]).toEqual({ ID: 'R-02', 유형: '필수 항목 없음', 내용: '신청인 성명이 없습니다', 상태: '해결', 처리내용: '원본에 성명 있음' });
    expect(obj.검토사항.map((r: Obj) => r.유형)).toEqual(['인식 확인 필요', '필수 항목 없음', '위치 확인 필요', '인식 확인 필요', '인식 확인 필요', '위치 확인 필요', '인식 확인 필요', '기타 서류']);
  });

  it('원문 값 없음 — 검토사항 글에 심어도 CSV · JSON 어디에도 없다(처리 내용에 담당자가 쓴 값은 예외 — 담당자 글)', () => {
    const { a: p, raws } = planted();
    for (const format of ['csv', 'json'] as const) {
      const t = file(p, format).text;
      const leaked = raws.slice(0, 4).filter((x) => t.includes(x));
      expect(leaked.length, format).toBe(0);
    }
    const plain = file(a, 'json').text;
    expect(rawValues(a).filter((x) => plain.includes(x)).length).toBe(0);
  });

  it('CSV 는 그대로 — 검토사항이 있어도 없을 때와 같은 글', () => {
    const withItems = file(a, 'csv');
    const old = live(contractResult());
    const without = buildExportFile(reportSafeAnalysis({ ...old, code: a.code }), 'csv', { brand: CONFIG.brandName, generatedAt: '2026-11-04 15:07', live: true });
    expect(withItems.text).toBe(without.text);
    expect(withItems.text.includes('R-01')).toBe(false);
  });
});
