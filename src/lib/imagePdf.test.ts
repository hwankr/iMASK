/* 그림 PDF 작성기 — 구조(머리 · 객체 · xref 오프셋 · trailer · 스트림 길이)와 pdf.js(Node 빌드)로 다시 열어 쪽 수 · 쪽 크기 · 글자 0개. */
import { describe, expect, it } from 'vitest';
import { IMAGE_PDF_INVALID, MAX_PAGE_PT, MAX_USER_UNIT, buildImagePdf, pageGeometry, pdfNum, type ImagePdfPage } from './imagePdf';

/** 가짜 JPEG — 머리(FF D8) · 채움 · 끝(FF D9). 구조 시험에는 그림을 풀지 않으므로 충분하다 */
function fakeJpeg(fill: number, n: number): Uint8Array {
  const out = new Uint8Array(n + 4);
  out.set([0xff, 0xd8], 0);
  out.fill(fill, 2, n + 2);
  out.set([0xff, 0xd9], n + 2);
  return out;
}

const A4: ImagePdfPage = { width: 595.28, height: 841.89, jpeg: fakeJpeg(0x11, 120), pixelWidth: 1190, pixelHeight: 1683 };
const WIDE: ImagePdfPage = { width: 400.5, height: 200, jpeg: fakeJpeg(0x22, 57), pixelWidth: 801, pixelHeight: 400 };

/** 바이트 → 한 바이트 한 글자(latin1) — 위치가 바이트 위치와 같다 */
const latin1 = (b: Uint8Array): string => Array.from(b, (c) => String.fromCharCode(c)).join('');

/** 스트림 밖 글자(사전 · 연산자)만 — 스트림 안 바이트를 지운 글 */
function outsideStreams(s: string): string {
  return s.replace(/stream\n[\s\S]*?\nendstream/g, 'stream\nendstream');
}

describe('buildImagePdf — 그림 PDF 구조', () => {
  const bytes = buildImagePdf([A4, WIDE]);
  const s = latin1(bytes);

  it('머리 %PDF-1.4 + 이진 주석 줄, 끝은 %%EOF', () => {
    expect(s.startsWith('%PDF-1.4\n%')).toBe(true);
    expect(Array.from(bytes.slice(10, 14)).every((c) => c >= 128)).toBe(true);
    expect(s.endsWith('%%EOF\n')).toBe(true);
  });

  it('xref 의 모든 오프셋이 그 "n 0 obj" 를 정확히 가리키고, trailer /Size · startxref 가 맞다', () => {
    const start = Number(/startxref\n(\d+)\n%%EOF\n$/.exec(s)?.[1]);
    expect(s.slice(start, start + 5)).toBe('xref\n');
    const head = /^xref\n0 (\d+)\n/.exec(s.slice(start))!;
    const size = Number(head[1]);
    // 객체 = Catalog · Pages + 쪽마다 셋
    expect(size).toBe(1 + 2 + 3 * 2);
    const lines = s.slice(start + head[0].length).split('\n').slice(0, size);
    expect(lines[0]).toBe('0000000000 65535 f ');
    for (let n = 1; n < size; n++) {
      // 한 줄 20바이트(줄바꿈 포함) — 10자리 오프셋 · 5자리 세대 · n · 공백
      expect(lines[n]).toMatch(/^\d{10} 00000 n $/);
      const off = Number(lines[n].slice(0, 10));
      expect(s.slice(off, off + `${n} 0 obj\n`.length)).toBe(`${n} 0 obj\n`);
    }
    expect(s).toContain(`trailer\n<< /Size ${size} /Root 1 0 R >>\nstartxref\n${start}\n%%EOF\n`);
  });

  it('스트림 /Length = 실제 바이트 수, 그림 바이트는 받은 JPEG 그대로', () => {
    const re = /\/Length (\d+) >>\nstream\n/g;
    let m: RegExpExecArray | null;
    const lens: number[] = [];
    while ((m = re.exec(s))) {
      const at = m.index + m[0].length;
      const len = Number(m[1]);
      expect(s.slice(at + len, at + len + '\nendstream\n'.length)).toBe('\nendstream\n');
      lens.push(len);
    }
    // 쪽마다 내용 스트림 · 그림 스트림
    expect(lens).toHaveLength(4);
    const imgAt = (jpeg: Uint8Array) => s.indexOf(latin1(jpeg));
    expect(imgAt(A4.jpeg)).toBeGreaterThan(0);
    expect(imgAt(WIDE.jpeg)).toBeGreaterThan(0);
    expect(lens).toContain(A4.jpeg.length);
    expect(lens).toContain(WIDE.jpeg.length);
  });

  it('쪽마다 MediaBox(pt) · 그림 Width/Height · DCTDecode · DeviceRGB, 내용은 그림 하나를 쪽 전체에 그리는 것뿐', () => {
    expect(s).toContain('/Type /Pages /Kids [3 0 R 6 0 R] /Count 2');
    // 14400pt 이하 쪽은 UserUnit 없음(MediaBox 바로 뒤가 /Resources) · 머리는 1.4
    expect(s).toContain('/MediaBox [0 0 595.28 841.89] /Resources');
    expect(s).toContain('/MediaBox [0 0 400.5 200] /Resources');
    expect(s).not.toContain('/UserUnit');
    expect(s.startsWith('%PDF-1.4\n')).toBe(true);
    expect(s).toContain('/MediaBox [0 0 400.5 200]');
    expect(s).toContain('/Width 1190 /Height 1683 /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode');
    expect(s).toContain('/Width 801 /Height 400 /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode');
    expect(s.match(/\/DCTDecode/g)).toHaveLength(2);
    expect(s).toContain('stream\nq\n595.28 0 0 841.89 0 0 cm\n/Im0 Do\nQ\n\nendstream');
    expect(s).toContain('stream\nq\n400.5 0 0 200 0 0 cm\n/Im0 Do\nQ\n\nendstream');
  });

  it('글꼴 · 글자 연산자 · 주석 · 폼 · 메타데이터가 없다', () => {
    const outside = outsideStreams(s);
    for (const bad of ['/Font', '/Annots', '/AcroForm', '/Info', '/Metadata', '/EmbeddedFiles', '/JavaScript', '/OpenAction'])
      expect(outside).not.toContain(bad);
    // 내용 스트림은 위에서 글자 그대로 확인 — BT/ET(글자 연산자)가 없다
    expect(outside).not.toMatch(/\bBT\b|\bET\b|\bTj\b|\bTJ\b/);
  });

  it('pdf.js(Node 빌드)로 다시 열면 쪽 수 · 쪽 크기가 같고 글자는 0개', async () => {
    const pdfjs = await import('pdfjs-dist/legacy/build/pdf.mjs');
    const doc = await pdfjs.getDocument({ data: bytes.slice(), verbosity: 0 }).promise;
    try {
      expect(doc.numPages).toBe(2);
      for (const [i, want] of [A4, WIDE].entries()) {
        const page = await doc.getPage(i + 1);
        const vp = page.getViewport({ scale: 1 });
        expect(vp.width).toBeCloseTo(want.width, 2);
        expect(vp.height).toBeCloseTo(want.height, 2);
        expect((await page.getTextContent()).items).toHaveLength(0);
      }
    } finally {
      await doc.loadingTask.destroy();
    }
  });
});

describe('buildImagePdf — 잘못된 입력은 고정 문구로 던진다', () => {
  const bad: [string, ImagePdfPage[]][] = [
    ['0쪽', []],
    ['폭 NaN', [{ ...A4, width: NaN }]],
    ['높이 Infinity', [{ ...A4, height: Infinity }]],
    ['폭 0', [{ ...A4, width: 0 }]],
    ['높이 음수', [{ ...A4, height: -10 }]],
    ['터무니없이 큰 쪽(UserUnit 상한 초과)', [{ ...A4, width: MAX_PAGE_PT * MAX_USER_UNIT + 1 }]],
    ['반올림하면 0 인 쪽', [{ ...A4, height: 0.0004 }]],
    ['빈 JPEG', [{ ...A4, jpeg: new Uint8Array(0) }]],
    ['JPEG 머리 없음', [{ ...A4, jpeg: new Uint8Array([0x89, 0x50, 0x4e, 0x47]) }]],
    ['픽셀 폭 0', [{ ...A4, pixelWidth: 0 }]],
    ['픽셀 높이 정수 아님', [{ ...A4, pixelHeight: 10.5 }]],
    ['둘째 쪽만 잘못', [A4, { ...WIDE, jpeg: new Uint8Array(0) }]],
  ];
  it.each(bad)('%s', (_name, pages) => {
    expect(() => buildImagePdf(pages)).toThrow(IMAGE_PDF_INVALID);
  });
});

/** pdf.js(Node 빌드)로 다시 열어 쪽마다 보이는 크기(getViewport scale 1 — UserUnit 반영) */
async function reopenSizes(bytes: Uint8Array): Promise<{ w: number; h: number }[]> {
  const pdfjs = await import('pdfjs-dist/legacy/build/pdf.mjs');
  const doc = await pdfjs.getDocument({ data: bytes.slice(), verbosity: 0 }).promise;
  try {
    const out: { w: number; h: number }[] = [];
    for (let p = 1; p <= doc.numPages; p++) {
      const vp = (await doc.getPage(p)).getViewport({ scale: 1 });
      out.push({ w: vp.width, h: vp.height });
    }
    return out;
  } finally {
    await doc.loadingTask.destroy();
  }
}

/** 쪽 사전의 MediaBox · UserUnit(쪽 순서) */
const pageDicts = (s: string) =>
  [...s.matchAll(/\/MediaBox \[0 0 ([\d.]+) ([\d.]+)\]( \/UserUnit ([\d.]+))? \/Resources/g)].map((m) => ({ w: Number(m[1]), h: Number(m[2]), u: m[4] ? Number(m[4]) : null }));

describe('buildImagePdf — 14400pt 넘는 쪽은 /UserUnit 으로 보이는 크기를 지킨다', () => {
  it('24000×800px 이미지(보이는 18000×600pt) — MediaBox 14400×480 · UserUnit 1.25 · 머리 1.6, pdf.js 로 다시 열면 18000×600', async () => {
    const page: ImagePdfPage = { width: 24000 * 0.75, height: 800 * 0.75, jpeg: fakeJpeg(0x33, 40), pixelWidth: 8192, pixelHeight: 273 };
    const bytes = buildImagePdf([page]);
    const s = latin1(bytes);
    expect(s.startsWith('%PDF-1.6\n%')).toBe(true);
    expect(pageDicts(s)).toEqual([{ w: 14400, h: 480, u: 1.25 }]);
    // 그림은 MediaBox 전체(사용자 공간 단위)
    expect(s).toContain('stream\nq\n14400 0 0 480 0 0 cm\n/Im0 Do\nQ\n\nendstream');
    const [vp] = await reopenSizes(bytes);
    expect(Math.abs(vp.w - 18000)).toBeLessThanOrEqual(1);
    expect(Math.abs(vp.h - 600)).toBeLessThanOrEqual(1);
  });

  it('보이는 18000×12000pt(원본 UserUnit 2 · MediaBox 9000×6000 과 같은 크기) — 같은 크기로 다시 열림, 다른 쪽은 UserUnit 없음', async () => {
    const big: ImagePdfPage = { width: 18000, height: 12000, jpeg: fakeJpeg(0x44, 30), pixelWidth: 3547, pixelHeight: 2365 };
    const bytes = buildImagePdf([A4, big, WIDE]);
    const s = latin1(bytes);
    expect(s.startsWith('%PDF-1.6\n')).toBe(true);
    expect(pageDicts(s)).toEqual([
      { w: 595.28, h: 841.89, u: null },
      { w: 14400, h: 9600, u: 1.25 },
      { w: 400.5, h: 200, u: null },
    ]);
    const sizes = await reopenSizes(bytes);
    [A4, big, WIDE].forEach((p, i) => {
      expect(Math.abs(sizes[i].w - p.width)).toBeLessThanOrEqual(1);
      expect(Math.abs(sizes[i].h - p.height)).toBeLessThanOrEqual(1);
    });
  });

  it('pageGeometry — MediaBox 는 늘 14400 이하, MediaBox × UserUnit 은 보이는 크기와 ±1pt(실제로는 0.05pt) 안', () => {
    const cases: [number, number][] = [
      [14400.0006, 100],
      [14400.4, 14400.4],
      [20000.123, 33333.333],
      [99999.9, 3],
      [123456.789, 98765.4321],
      [MAX_PAGE_PT * MAX_USER_UNIT, 500],
      [MAX_PAGE_PT * 37.3337, MAX_PAGE_PT * 12.1],
    ];
    for (const [w, h] of cases) {
      const g = pageGeometry(w, h);
      expect(g.userUnit).not.toBeNull();
      const u = Number(g.userUnit);
      expect(u).toBeGreaterThan(1);
      expect(u).toBeLessThanOrEqual(MAX_USER_UNIT);
      expect(Number(g.mediaWidth)).toBeLessThanOrEqual(MAX_PAGE_PT);
      expect(Number(g.mediaHeight)).toBeLessThanOrEqual(MAX_PAGE_PT);
      expect(Math.abs(Number(g.mediaWidth) * u - w)).toBeLessThanOrEqual(0.06);
      expect(Math.abs(Number(g.mediaHeight) * u - h)).toBeLessThanOrEqual(0.06);
    }
  });

  it('pageGeometry — 14400 이하(반올림 기준)는 UserUnit 없이 그대로', () => {
    expect(pageGeometry(595.28, 841.89)).toEqual({ mediaWidth: '595.28', mediaHeight: '841.89', userUnit: null });
    expect(pageGeometry(14400, 10000)).toEqual({ mediaWidth: '14400', mediaHeight: '10000', userUnit: null });
    expect(pageGeometry(14400.0004, 3)).toEqual({ mediaWidth: '14400', mediaHeight: '3', userUnit: null });
  });

  it('3pt 미만 아주 작은 쪽은 그대로 적고, pdf.js 도 그 크기로 연다', async () => {
    expect(pageGeometry(1, 2.5)).toEqual({ mediaWidth: '1', mediaHeight: '2.5', userUnit: null });
    const tiny: ImagePdfPage = { width: 1, height: 2.5, jpeg: fakeJpeg(0x55, 8), pixelWidth: 2, pixelHeight: 5 };
    const [vp] = await reopenSizes(buildImagePdf([tiny]));
    expect(vp.w).toBeCloseTo(1, 3);
    expect(vp.h).toBeCloseTo(2.5, 3);
  });

  it('UserUnit 상한(100) 초과 · 0 이하 · 유한하지 않으면 잘못된 입력', () => {
    expect(pageGeometry(MAX_PAGE_PT * MAX_USER_UNIT, 1).userUnit).toBe('100');
    for (const [w, h] of [
      [MAX_PAGE_PT * MAX_USER_UNIT + 1, 10],
      [0, 10],
      [-5, 10],
      [10, NaN],
      [Infinity, 10],
      [0.0004, 10],
    ])
      expect(() => pageGeometry(w, h)).toThrow(IMAGE_PDF_INVALID);
  });
});

describe('pdfNum — PDF 숫자', () => {
  it('소수 셋째 자리까지, 뒤 0 없음, 지수 표기 없음', () => {
    expect(pdfNum(595.2756)).toBe('595.276');
    expect(pdfNum(200)).toBe('200');
    expect(pdfNum(1000)).toBe('1000');
    expect(pdfNum(100.5)).toBe('100.5');
    expect(pdfNum(1e-7)).toBe('0');
    expect(pdfNum(-0)).toBe('0');
    expect(pdfNum(14400)).toBe('14400');
  });
  it('유한하지 않으면 던진다', () => {
    expect(() => pdfNum(NaN)).toThrow(IMAGE_PDF_INVALID);
    expect(() => pdfNum(Infinity)).toThrow(IMAGE_PDF_INVALID);
  });
});
