/* 가린 PDF — 가림 계획(maskPlan) · 칠할 사각형(maskRects) · 파일 이름 · 문구. 고정 자료(fixtures/done-result.json) → toAnalysis. */
import { describe, expect, it } from 'vitest';
import { MIN_BOX_PX } from '@/lib/pageBox';
import { toAnalysis } from '@/services/api/mapping';
import { analysisOut, contractResult } from '@/services/api/testing';
import type { Analysis, Finding, FindingBox } from '@/services/types';
import {
  MASK_PAD_PT,
  MASK_PDF_DONE,
  MASK_PDF_FAILED,
  PREVIEW_PAPER_PX,
  maskPdfMissedText,
  maskPdfName,
  maskPlan,
  maskRects,
  maskSourceOf,
  safeNamePart,
  type MaskPlan,
} from './maskPdf';
import type { LiveFileState } from './liveFile';
import type { OpenedPdf } from './pdfRuntime';

const NEW_REVIEW = { status: 'needed', memo: '', memo_at: null, reviewer: '', reviewed_at: null, completion_note: '', findings: {}, history: [], version: 0 };

/** 완료 + 공통 계약 결과(고정 자료 — 6쪽 PDF, 서류 6개, 탐지 19개 · 상자 29개, D3-02 page 없음 · D5-03 상자 없음) */
function liveAnalysis(): Analysis {
  return toAnalysis(analysisOut({ status: 'done', result: contractResult(), upstage_job_id: 'job_test', upstage_status: 'completed', review: structuredClone(NEW_REVIEW) }));
}

/** 쪽별 상자 수 */
const counts = (p: MaskPlan) => p.pages.map((t) => t.length);

/** 항목 하나를 고친 분석 */
function withFinding(a: Analysis, id: string, patch: Partial<Finding>): Analysis {
  return { ...a, findings: a.findings.map((f) => (f.id === id ? { ...f, ...patch } : f)) };
}

const allOff = (a: Analysis) => Object.fromEntries(a.findings.map((f) => [f.id, false]));

describe('maskPlan — 고른 항목의 상자를 파일 쪽별로', () => {
  const a = liveAnalysis();

  it('고정 자료 확인 — 서류 6개(파일 1~6쪽), 탐지 19개, 상자 29개', () => {
    expect(a.docs.map((d) => [d.source?.pageStart, d.source?.pageEnd])).toEqual([1, 2, 3, 4, 5, 6].map((p) => [p, p]));
    expect(a.findings).toHaveLength(19);
    expect(a.findings.reduce((n, f) => n + (f.boxes?.length ?? 0), 0)).toBe(29);
  });

  it('기본 선택(고른 적 없음 = 오탐이 아닌 항목 모두) — 쪽별 상자 수, 위치 없는 D3-02 · D5-03 은 가리지 못함', () => {
    const p = maskPlan(a, {}, 6);
    expect(p.pageCount).toBe(6);
    expect(counts(p)).toEqual([14, 4, 1, 7, 3, 0]);
    expect(p.picked).toHaveLength(19);
    expect(p.missed).toEqual(['D3-02', 'D5-03']);
    // 상자는 위치 ID · 항목 ID 와 함께, 꼭짓점은 복사본(원래 값과 같은 값)
    const first = p.pages[0][0];
    const f = a.findings.find((x) => x.id === first.findingId)!;
    expect(first.anchor).toBe(f.boxes![0].a);
    expect(first.points).toEqual(f.boxes![0].points);
    expect(first.points).not.toBe(f.boxes![0].points);
  });

  it('일부 해제 — 주소(D1-05, 상자 6개)를 보이게 고르면 1쪽에서 6개가 빠진다', () => {
    const p = maskPlan(a, { 'D1-05': false }, 6);
    expect(counts(p)).toEqual([8, 4, 1, 7, 3, 0]);
    expect(p.pages[0].some((t) => t.findingId === 'D1-05')).toBe(false);
    expect(p.picked).not.toContain('D1-05');
  });

  it('오탐은 기본으로 빠지고, 가리게 고르면 들어간다', () => {
    const fp = withFinding(a, 'D4-03', { status: 'false_positive' });
    expect(counts(maskPlan(fp, {}, 6))).toEqual([14, 4, 1, 2, 3, 0]);
    expect(counts(maskPlan(fp, { 'D4-03': true }, 6))).toEqual([14, 4, 1, 7, 3, 0]);
  });

  it('모두 해제 — 칠할 상자도 가리지 못한 항목도 없다(쪽은 그대로 6쪽)', () => {
    const p = maskPlan(a, allOff(a), 6);
    expect(counts(p)).toEqual([0, 0, 0, 0, 0, 0]);
    expect(p.picked).toEqual([]);
    expect(p.missed).toEqual([]);
  });

  it('모두 해제 뒤 서로 다른 쪽의 두 항목만 — 그 상자만', () => {
    const p = maskPlan(a, { ...allOff(a), 'D1-02': true, 'D4-02': true }, 6);
    expect(counts(p)).toEqual([1, 0, 0, 1, 0, 0]);
    expect(p.pages[0][0].findingId).toBe('D1-02');
    expect(p.pages[3][0].findingId).toBe('D4-02');
  });

  it('파일 쪽 = 서류 pageStart + (항목 쪽 − 1) — 서류가 파일 뒤쪽에 있거나 여러 쪽이면', () => {
    const moved: Analysis = {
      ...a,
      docs: a.docs.map((d) => (d.id === 'doc-1' && d.source ? { ...d, source: { ...d.source, pageStart: 5, pageEnd: 6 } } : d)),
      // D2-02 는 그 서류 2쪽(= 파일 6쪽)
      findings: a.findings.map((f) => (f.id === 'D2-02' ? { ...f, page: 2 } : f)),
    };
    const p = maskPlan(moved, {}, 6);
    expect(p.pages[4].filter((t) => t.findingId === 'D2-01')).toHaveLength(1);
    expect(p.pages[5].filter((t) => t.findingId === 'D2-02')).toHaveLength(3);
    expect(p.pages[1]).toEqual([]);
  });

  it('파일 쪽 범위 밖(원본이 4쪽뿐) — 5쪽 서류의 항목은 가리지 못함', () => {
    const p = maskPlan(a, {}, 4);
    expect(counts(p)).toEqual([14, 4, 1, 7]);
    expect(p.missed).toEqual(['D3-02', 'D5-01', 'D5-02', 'D5-03']);
  });

  it('원본 쪽 수가 잘못되면(0 · 정수 아님) 쪽이 없고 고른 항목은 모두 가리지 못함', () => {
    for (const n of [0, -1, 2.5, NaN]) {
      const p = maskPlan(a, {}, n);
      expect(p.pageCount).toBe(0);
      expect(p.pages).toEqual([]);
      expect(p.missed).toHaveLength(19);
    }
  });

  it('항목 쪽이 서류 범위 밖 · 정수 아님이면 가리지 못함(미리보기도 그리지 않음)', () => {
    for (const page of [0, 2, 1.5, NaN]) {
      const p = maskPlan(withFinding(a, 'D3-01', { page }), {}, 6);
      expect(p.missed).toContain('D3-01');
      expect(p.pages[2]).toEqual([]);
    }
  });

  it('서류가 없거나 서류 source 가 없으면 가리지 못함', () => {
    expect(maskPlan(withFinding(a, 'D3-01', { docId: 'doc-x' }), {}, 6).missed).toContain('D3-01');
    const noSrc: Analysis = { ...a, docs: a.docs.map((d) => (d.id === 'doc-2' ? { ...d, source: undefined } : d)) };
    expect(maskPlan(noSrc, {}, 6).missed).toContain('D3-01');
  });

  it('잘못된 꼭짓점 · 쪽 밖 상자는 버리고, 하나라도 남으면 가린 것으로 센다', () => {
    const bad: FindingBox[] = [
      { a: 'D1-01#1', points: [{ x: NaN, y: 0.1 }, { x: 0.2, y: 0.2 }] },
      { a: 'D1-01#2', points: [{ x: 0.5, y: 0.5 }] },
      { a: 'D1-01#3', points: [{ x: 1.2, y: 1.1 }, { x: 1.5, y: 1.4 }] },
      { a: 'D1-01#4', points: [{ x: Infinity, y: 0.1 }, { x: 0.3, y: 0.3 }] },
    ];
    const none = maskPlan(withFinding(a, 'D1-01', { boxes: bad }), {}, 6);
    expect(none.missed).toContain('D1-01');
    expect(none.pages[0].some((t) => t.findingId === 'D1-01')).toBe(false);
    // 쪽에 걸친 상자(일부만 쪽 안)는 그린다 — 미리보기와 같은 기준
    const edge: FindingBox = { a: 'D1-01#5', points: [{ x: 0.9, y: 0.9 }, { x: 1.3, y: 1.2 }] };
    const some = maskPlan(withFinding(a, 'D1-01', { boxes: [...bad, edge] }), {}, 6);
    expect(some.missed).not.toContain('D1-01');
    expect(some.pages[0].filter((t) => t.findingId === 'D1-01').map((t) => t.anchor)).toEqual(['D1-01#5']);
  });
});

describe('maskRects — 실제 캔버스 크기 기준 사각형 · 여백 · 쪽 안 자르기', () => {
  const page = { width: 595, height: 842 };
  const canvas = { width: 1190, height: 1684 }; // 배율 2 → 1pt = 2px

  it('꼭짓점을 감싼 사각형 + 여백(1.5pt = 3px)을 바깥쪽 정수 픽셀로', () => {
    const r = maskRects([{ points: [{ x: 0.1, y: 0.1 }, { x: 0.2, y: 0.1 }, { x: 0.2, y: 0.12 }, { x: 0.1, y: 0.12 }] }], canvas, page);
    // x 119 ~ 238, y 168.4 ~ 202.08 → 여백 3 → 116 ~ 241, 165.4 ~ 205.08
    expect(r).toEqual([{ x: 116, y: 165, w: 125, h: 41 }]);
    expect(MASK_PAD_PT * (canvas.width / page.width)).toBe(3);
  });

  it('기울어진 사각형도 꼭짓점을 모두 덮는다', () => {
    const pts = [{ x: 0.3, y: 0.42 }, { x: 0.5, y: 0.4 }, { x: 0.52, y: 0.45 }, { x: 0.32, y: 0.47 }];
    const [r] = maskRects([{ points: pts }], canvas, page);
    for (const p of pts) {
      expect(p.x * canvas.width).toBeGreaterThanOrEqual(r.x);
      expect(p.x * canvas.width).toBeLessThanOrEqual(r.x + r.w);
      expect(p.y * canvas.height).toBeGreaterThanOrEqual(r.y);
      expect(p.y * canvas.height).toBeLessThanOrEqual(r.y + r.h);
    }
  });

  it('쪽 가장자리 · 쪽에 걸친 상자는 쪽 안으로 자른다', () => {
    const [r] = maskRects([{ points: [{ x: -0.1, y: 0.95 }, { x: 0.05, y: 1.3 }] }], canvas, page);
    expect(r.x).toBe(0);
    expect(r.y + r.h).toBe(canvas.height);
    expect(r.x + r.w).toBeLessThanOrEqual(canvas.width);
  });

  it('최소 크기는 미리보기 이상 — 넓이 0 인 상자도 미리보기 최소(종이 폭 대비) + 여백', () => {
    const [r] = maskRects([{ points: [{ x: 0.5, y: 0.5 }, { x: 0.5, y: 0.5 }] }], canvas, page);
    const previewMin = (MIN_BOX_PX / PREVIEW_PAPER_PX) * canvas.width;
    expect(r.w).toBeGreaterThanOrEqual(previewMin + 2 * 3);
    expect(r.h).toBeGreaterThanOrEqual(previewMin + 2 * 3);
  });

  it('같은 비율 상자는 실제 캔버스 크기에 따라 커진다(상한으로 줄어든 캔버스 포함)', () => {
    const pts = [{ x: 0.25, y: 0.25 }, { x: 0.75, y: 0.5 }];
    const [big] = maskRects([{ points: pts }], canvas, page);
    const [small] = maskRects([{ points: pts }], { width: 595, height: 842 }, page);
    // 바깥쪽 정수 픽셀(floor)
    expect(big.x).toBe(Math.floor(0.25 * 1190 - 3));
    expect(small.x).toBe(Math.floor(0.25 * 595 - 1.5));
    expect(big.w / small.w).toBeGreaterThan(1.9);
  });

  it('그릴 수 없는 상자는 빠지고, 캔버스 크기가 잘못되면 빈 목록', () => {
    const ok = { points: [{ x: 0.1, y: 0.1 }, { x: 0.2, y: 0.2 }] };
    expect(maskRects([{ points: [{ x: 1.5, y: 1.5 }, { x: 2, y: 2 }] }, ok, { points: [] }], canvas, page)).toHaveLength(1);
    expect(maskRects([ok], { width: 0, height: 10 }, page)).toEqual([]);
    expect(maskRects([ok], { width: NaN, height: 10 }, page)).toEqual([]);
    // 쪽 크기를 모르면 여백 1px 로 계산(사각형은 나온다)
    expect(maskRects([ok], canvas, { width: 0, height: 0 })).toHaveLength(1);
  });

  it('고정 자료 1쪽 — 계획의 상자마다 사각형 하나', () => {
    const plan = maskPlan(liveAnalysis(), {}, 6);
    expect(maskRects(plan.pages[0], canvas, page)).toHaveLength(14);
  });
});

describe('maskSourceOf — 버튼을 열어 둘 원본인지', () => {
  /** 쪽 수만 다른 가짜 연 PDF */
  const pdfOf = (pageCount: number): LiveFileState => ({
    status: 'ready',
    kind: 'pdf',
    pdf: { pageCount, pageSize: async () => ({ width: 1, height: 1 }), render: () => ({ promise: Promise.resolve(null), cancel: () => {} }), close: () => {} } as OpenedPdf,
    pageCount,
  });
  const image = (width: number, height: number): LiveFileState => ({ status: 'ready', kind: 'image', url: 'blob:test/1', width, height, pageCount: 1 });

  it('받는 중 · 실패 · 데모(null)는 준비되지 않음', () => {
    expect(maskSourceOf(null)).toBeNull();
    expect(maskSourceOf({ status: 'loading' })).toBeNull();
    expect(maskSourceOf({ status: 'error', message: '원문을 표시하지 못했습니다.' })).toBeNull();
  });

  it('PDF — 쪽 수가 양의 정수일 때만(열리지만 0쪽인 PDF 는 막는다)', () => {
    expect(maskSourceOf(pdfOf(4))).toMatchObject({ kind: 'pdf', pageCount: 4 });
    for (const n of [0, -1, 1.5, NaN]) expect(maskSourceOf(pdfOf(n))).toBeNull();
  });

  it('이미지 — 크기가 양의 유한한 값일 때만', () => {
    expect(maskSourceOf(image(800, 600))).toEqual({ kind: 'image', url: 'blob:test/1', width: 800, height: 600 });
    expect(maskSourceOf(image(0, 600))).toBeNull();
    expect(maskSourceOf(image(800, Infinity))).toBeNull();
  });
});

describe('파일 이름 · 문구', () => {
  it("'iMASK_<분석 번호>_마스킹.pdf'", () => {
    expect(maskPdfName('DG-20261105-AB12')).toBe('iMASK_DG-20261105-AB12_마스킹.pdf');
  });

  it('파일 이름에 쓸 수 없는 글자 · 제어 문자는 _ , 비면 대신 글자', () => {
    expect(maskPdfName('DG/2026:11*05?')).toBe('iMASK_DG_2026_11_05__마스킹.pdf');
    expect(maskPdfName('a\u0001b\u007fc')).toBe('iMASK_a_b_c_마스킹.pdf');
    expect(maskPdfName('  ..  ')).toBe('iMASK_analysis_마스킹.pdf');
    expect(safeNamePart('<>|"', 'x')).toBe('____');
    expect(safeNamePart('x'.repeat(200))).toHaveLength(80);
  });

  it('토스트 문구 — 원문 값 · 기술적 오류 내용 없음', () => {
    expect(MASK_PDF_DONE).toBe('가린 PDF를 내려받았습니다.');
    expect(maskPdfMissedText(2)).toBe('가린 PDF를 내려받았습니다. 위치가 없는 2건은 가리지 못했습니다.');
    expect(MASK_PDF_FAILED).toBe('가린 PDF를 만들지 못했습니다. 다시 시도해 주세요.');
  });
});
