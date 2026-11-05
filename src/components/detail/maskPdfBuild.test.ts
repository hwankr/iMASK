/* 가린 PDF 만들기(실행부) — 가짜 캔버스 · 가짜 연 PDF · 가짜 환경으로 쪽 순서 · 칠하기 · 실패 · 취소 · 캔버스 놓기를 확인한다. */
import { describe, expect, it } from 'vitest';
import { MAX_CANVAS_AREA, MAX_CANVAS_SIDE } from '@/lib/pageBox';
import { MASK_PDF_FAILED, maskRects, type MaskPlan, type MaskTarget } from './maskPdf';
import { MASK_JPEG_QUALITY, MASK_PDF_SCALE, buildMaskedPdf, type MaskEnv, type MaskSource } from './maskPdfBuild';
import type { OpenedPdf } from './pdfRuntime';

/* 색 대신 쓰는 가짜 토큰 값(TS 에 색 문자열을 쓰지 않는다) — 가짜 캔버스는 'see-through' 만 반투명으로 칠한다 */
const MASK = 'mask-token-value';
const PAPER = 'paper-token-value';
const SEE_THROUGH = 'see-through';

interface Op {
  op: 'fill' | 'clear' | 'image';
  x: number;
  y: number;
  w: number;
  h: number;
  style: string;
  alpha: number;
  comp: string;
}

/** 가짜 캔버스 — 칠한 것을 기록한다 */
class FakeCanvas {
  ops: Op[] = [];
  private ctx: Record<string, unknown> | null = null;
  constructor(
    public width: number,
    public height: number,
  ) {}
  getContext() {
    if (this.ctx) return this.ctx;
    const ops = this.ops;
    const stack: Record<string, unknown>[] = [];
    const ctx: Record<string, unknown> = {
      fillStyle: '',
      globalAlpha: 0.5,
      globalCompositeOperation: 'multiply',
      save: () => stack.push({ fillStyle: ctx.fillStyle, globalAlpha: ctx.globalAlpha, globalCompositeOperation: ctx.globalCompositeOperation }),
      restore: () => Object.assign(ctx, stack.pop()),
      setTransform: () => {},
      clearRect: (x: number, y: number, w: number, h: number) => ops.push({ op: 'clear', x, y, w, h, style: '', alpha: 1, comp: '' }),
      fillRect: (x: number, y: number, w: number, h: number) =>
        ops.push({ op: 'fill', x, y, w, h, style: String(ctx.fillStyle), alpha: Number(ctx.globalAlpha), comp: String(ctx.globalCompositeOperation) }),
      drawImage: (_img: unknown, x: number, y: number, w: number, h: number) => ops.push({ op: 'image', x, y, w, h, style: '', alpha: 1, comp: '' }),
      getImageData: () => {
        const last = ops.filter((o) => o.op === 'fill').pop();
        return { data: [0, 0, 0, last && last.style !== SEE_THROUGH && last.alpha === 1 ? 255 : 128] };
      },
    };
    this.ctx = ctx;
    return ctx;
  }
}

const asCanvas = (c: FakeCanvas) => c as unknown as HTMLCanvasElement;

/** 가짜 환경 — 만든 JPEG 마다 그 순간의 캔버스 크기 · 칠한 것을 남긴다 */
function fakeEnv(opts: { tokens?: Record<string, string>; jpegNullAt?: number; imageFails?: boolean } = {}) {
  const jpegs: { width: number; height: number; ops: Op[]; quality: number }[] = [];
  const made: FakeCanvas[] = [];
  const tokens = opts.tokens ?? { '--doc-mask': MASK, '--paper': PAPER };
  const env: MaskEnv = {
    token: (name) => tokens[name] ?? '',
    createCanvas: () => {
      const c = new FakeCanvas(300, 150);
      made.push(c);
      return asCanvas(c);
    },
    loadImage: async () => {
      if (opts.imageFails) throw new Error('load');
      return {} as CanvasImageSource;
    },
    toJpeg: async (canvas, quality) => {
      const c = canvas as unknown as FakeCanvas;
      jpegs.push({ width: c.width, height: c.height, ops: [...c.ops], quality });
      if (opts.jpegNullAt === jpegs.length) return null;
      return new Uint8Array([0xff, 0xd8, jpegs.length, 0xff, 0xd9]);
    },
  };
  return { env, jpegs, made };
}

/** 가짜 연 PDF — 쪽 크기(pt, 회전 반영)대로 캔버스를 만든다 */
function fakePdf(sizes: { width: number; height: number }[], opts: { failAt?: number; hangAt?: number } = {}) {
  const renders: { page: number; scale: number; canvas: FakeCanvas | null; cancelled: boolean }[] = [];
  const pdf: OpenedPdf = {
    pageCount: sizes.length,
    pageSize: async (p) => sizes[p - 1],
    render: (p, scale) => {
      const s = sizes[p - 1];
      const rec = { page: p, scale, canvas: null as FakeCanvas | null, cancelled: false };
      renders.push(rec);
      let resolveHang: (v: null) => void = () => {};
      const promise: Promise<HTMLCanvasElement | null> =
        opts.failAt === p
          ? Promise.reject(new Error('render'))
          : opts.hangAt === p
            ? new Promise((r) => (resolveHang = r))
            : Promise.resolve().then(() => {
                rec.canvas = new FakeCanvas(Math.max(1, Math.floor(s.width * scale)), Math.max(1, Math.floor(s.height * scale)));
                return asCanvas(rec.canvas);
              });
      return {
        promise,
        cancel: () => {
          rec.cancelled = true;
          resolveHang(null);
        },
      };
    },
    close: () => {},
  };
  return { pdf, renders };
}

const box = (findingId: string, x0: number, y0: number, x1: number, y1: number): MaskTarget => ({
  findingId,
  anchor: findingId + '#1',
  points: [{ x: x0, y: y0 }, { x: x1, y: y0 }, { x: x1, y: y1 }, { x: x0, y: y1 }],
});

function planOf(pages: MaskTarget[][], missed: string[] = []): MaskPlan {
  return { pageCount: pages.length, pages, picked: [], missed };
}

/** 바이트 → latin1 */
const latin1 = (b: Uint8Array): string => Array.from(b, (c) => String.fromCharCode(c)).join('');
const mediaBoxes = (b: Uint8Array) => [...latin1(b).matchAll(/\/MediaBox \[0 0 ([\d.]+) ([\d.]+)\]/g)].map((m) => [Number(m[1]), Number(m[2])]);
/** 보이는 쪽 크기 = MediaBox × UserUnit(없으면 1) — 소수 둘째 자리 */
const visibleSizes = (b: Uint8Array) =>
  [...latin1(b).matchAll(/\/MediaBox \[0 0 ([\d.]+) ([\d.]+)\]( \/UserUnit ([\d.]+))?/g)].map((m) => {
    const u = m[4] ? Number(m[4]) : 1;
    return [Math.round(Number(m[1]) * u * 100) / 100, Math.round(Number(m[2]) * u * 100) / 100];
  });

describe('buildMaskedPdf — PDF 원본', () => {
  const sizes = [
    { width: 595, height: 842 },
    { width: 842, height: 595 }, // 회전한 쪽(pageSize 가 회전을 반영한 크기)
    { width: 300, height: 400 },
  ];

  it('모든 쪽을 원래 순서로 배율 2 에 그리고, 고른 상자만 불투명하게 칠한 뒤 그림 PDF 로', async () => {
    const { pdf, renders } = fakePdf(sizes);
    const { env, jpegs } = fakeEnv();
    const plan = planOf([[box('A', 0.1, 0.1, 0.2, 0.12), box('B', 0.5, 0.5, 0.6, 0.55)], [], [box('C', 0.4, 0.4, 0.5, 0.5)]], ['X']);
    const res = await buildMaskedPdf({ kind: 'pdf', pdf, pageCount: 3 }, plan, env).promise;
    expect(res).not.toBeNull();
    expect(res!.missed).toBe(1);
    expect(renders.map((r) => [r.page, r.scale])).toEqual([
      [1, MASK_PDF_SCALE],
      [2, MASK_PDF_SCALE],
      [3, MASK_PDF_SCALE],
    ]);
    // 쪽 크기(MediaBox) = 회전 반영 · 배율 1 크기
    expect(mediaBoxes(res!.bytes)).toEqual(sizes.map((s) => [s.width, s.height]));
    // 칠한 것 — 실제 캔버스 크기 기준 사각형, 마스크 토큰 색 · 불투명 · 기본 합성
    expect(jpegs.map((j) => j.ops.filter((o) => o.op === 'fill').length)).toEqual([2, 0, 1]);
    jpegs.forEach((j, i) => {
      const want = maskRects(plan.pages[i], j, sizes[i]);
      expect(j.ops.filter((o) => o.op === 'fill').map(({ x, y, w, h }) => ({ x, y, w, h }))).toEqual(want);
      for (const o of j.ops) if (o.op === 'fill') expect([o.style, o.alpha, o.comp]).toEqual([MASK, 1, 'source-over']);
      expect(j.quality).toBe(MASK_JPEG_QUALITY);
    });
    // 다 쓴 캔버스는 놓는다
    expect(renders.every((r) => r.canvas && r.canvas.width === 0 && r.canvas.height === 0)).toBe(true);
  });

  it('아주 큰 쪽은 캔버스 상한으로 줄여 그리고, 사각형은 줄어든 실제 캔버스 크기로 계산한다', async () => {
    const big = [{ width: 14400, height: 10000 }];
    const { pdf, renders } = fakePdf(big);
    const { env, jpegs } = fakeEnv();
    const plan = planOf([[box('A', 0.5, 0.5, 0.75, 0.75)]]);
    const res = await buildMaskedPdf({ kind: 'pdf', pdf, pageCount: 1 }, plan, env).promise;
    expect(res).not.toBeNull();
    expect(renders[0].scale).toBeLessThan(1);
    const j = jpegs[0];
    expect(j.width).toBeLessThanOrEqual(MAX_CANVAS_SIDE);
    expect(j.width * j.height).toBeLessThanOrEqual(MAX_CANVAS_AREA);
    const [f] = j.ops.filter((o) => o.op === 'fill');
    expect(f.x + f.w).toBeLessThanOrEqual(j.width);
    expect(f.x).toBeCloseTo(0.5 * j.width, -1);
    expect(mediaBoxes(res!.bytes)).toEqual([[14400, 10000]]);
    expect(latin1(res!.bytes)).not.toContain('/UserUnit');
  });

  it('보이는 크기가 14400pt 를 넘는 쪽(원본 UserUnit 2 — pageSize 18000×12000)도 줄이지 않는다 — /UserUnit', async () => {
    const { pdf } = fakePdf([{ width: 595, height: 842 }, { width: 18000, height: 12000 }]);
    const { env } = fakeEnv();
    const res = await buildMaskedPdf({ kind: 'pdf', pdf, pageCount: 2 }, planOf([[], [box('A', 0.4, 0.4, 0.6, 0.6)]]), env).promise;
    expect(res).not.toBeNull();
    expect(visibleSizes(res!.bytes)).toEqual([
      [595, 842],
      [18000, 12000],
    ]);
    expect(mediaBoxes(res!.bytes)[1]).toEqual([14400, 9600]);
  });

  it('한 쪽이라도 그리지 못하면 전체 실패(PDF 없음) — 뒤 쪽은 그리지 않는다', async () => {
    const { pdf, renders } = fakePdf(sizes, { failAt: 2 });
    const { env, jpegs } = fakeEnv();
    await expect(buildMaskedPdf({ kind: 'pdf', pdf, pageCount: 3 }, planOf([[], [], []]), env).promise).rejects.toThrow(MASK_PDF_FAILED);
    expect(renders.map((r) => r.page)).toEqual([1, 2]);
    expect(jpegs).toHaveLength(1);
  });

  it('JPEG 로 바꾸지 못하면(toBlob null) 전체 실패', async () => {
    const { pdf } = fakePdf(sizes);
    const { env } = fakeEnv({ jpegNullAt: 3 });
    await expect(buildMaskedPdf({ kind: 'pdf', pdf, pageCount: 3 }, planOf([[], [], []]), env).promise).rejects.toThrow(MASK_PDF_FAILED);
  });

  it('가림 색 토큰이 없거나 반투명이면 시작하지 않고 실패', async () => {
    const cases: Record<string, string>[] = [{ '--paper': PAPER }, { '--doc-mask': SEE_THROUGH, '--paper': PAPER }];
    for (const tokens of cases) {
      const { pdf, renders } = fakePdf(sizes);
      const { env } = fakeEnv({ tokens });
      await expect(buildMaskedPdf({ kind: 'pdf', pdf, pageCount: 3 }, planOf([[], [], []]), env).promise).rejects.toThrow(MASK_PDF_FAILED);
      expect(renders).toHaveLength(0);
    }
  });

  it('계획의 쪽 수가 원본과 다르거나 0쪽이면 실패', async () => {
    const { pdf } = fakePdf(sizes);
    await expect(buildMaskedPdf({ kind: 'pdf', pdf, pageCount: 3 }, planOf([[], []]), fakeEnv().env).promise).rejects.toThrow(MASK_PDF_FAILED);
    const empty = fakePdf([]);
    await expect(buildMaskedPdf({ kind: 'pdf', pdf: empty.pdf, pageCount: 0 }, planOf([]), fakeEnv().env).promise).rejects.toThrow(MASK_PDF_FAILED);
  });

  it('그리는 중 취소하면 그리기를 멈추고 null(오류 아님) — 다음 쪽은 그리지 않는다', async () => {
    const { pdf, renders } = fakePdf(sizes, { hangAt: 2 });
    const { env, jpegs } = fakeEnv();
    const job = buildMaskedPdf({ kind: 'pdf', pdf, pageCount: 3 }, planOf([[], [], []]), env);
    // 2쪽 그리기가 시작될 때까지
    while (renders.length < 2) await new Promise((r) => setTimeout(r, 0));
    job.cancel();
    await expect(job.promise).resolves.toBeNull();
    expect(renders[1].cancelled).toBe(true);
    expect(renders).toHaveLength(2);
    expect(jpegs).toHaveLength(1);
  });
});

describe('buildMaskedPdf — 이미지 원본', () => {
  const src = (width: number, height: number): MaskSource => ({ kind: 'image', url: 'blob:test/1', width, height });

  it('원래 픽셀 크기 캔버스에 종이색 바탕 · 그림 · 가림 순서로, 쪽 크기는 px × 72/96', async () => {
    const { env, jpegs } = fakeEnv();
    const plan = planOf([[box('A', 0.2, 0.2, 0.4, 0.3)]]);
    const res = await buildMaskedPdf(src(800, 600), plan, env).promise;
    expect(res).not.toBeNull();
    const j = jpegs[0];
    expect([j.width, j.height]).toEqual([800, 600]);
    expect(j.ops.map((o) => o.op)).toEqual(['fill', 'image', 'fill']);
    expect(j.ops[0]).toMatchObject({ x: 0, y: 0, w: 800, h: 600, style: PAPER });
    expect(j.ops[2]).toMatchObject({ style: MASK, alpha: 1, comp: 'source-over' });
    expect(mediaBoxes(res!.bytes)).toEqual([[600, 450]]);
  });

  it('아주 큰 이미지는 캔버스 상한으로 줄인다(쪽 크기는 원래 px 기준)', async () => {
    const { env, jpegs } = fakeEnv();
    const res = await buildMaskedPdf(src(12000, 9000), planOf([[]]), env).promise;
    expect(res).not.toBeNull();
    expect(jpegs[0].width * jpegs[0].height).toBeLessThanOrEqual(MAX_CANVAS_AREA);
    expect(mediaBoxes(res!.bytes)).toEqual([[9000, 6750]]);
  });

  it('14400pt 를 넘는 이미지(24000×800px = 보이는 18000×600pt)도 쪽 크기를 줄이지 않는다 — /UserUnit', async () => {
    const { env, jpegs } = fakeEnv();
    const res = await buildMaskedPdf(src(24000, 800), planOf([[box('A', 0.1, 0.2, 0.3, 0.6)]]), env).promise;
    expect(res).not.toBeNull();
    expect(visibleSizes(res!.bytes)).toEqual([[18000, 600]]);
    expect(mediaBoxes(res!.bytes)[0][0]).toBeLessThanOrEqual(14400);
    // 캔버스는 상한(한 변 8192)으로 줄고, 칠한 사각형은 그 실제 캔버스 기준
    expect(jpegs[0].width).toBeLessThanOrEqual(MAX_CANVAS_SIDE);
    const [f] = jpegs[0].ops.filter((o) => o.op === 'fill' && o.style === MASK);
    expect(f.x + f.w).toBeLessThanOrEqual(jpegs[0].width);
  });

  it('종이색 토큰이 없거나 이미지를 불러오지 못하면 실패', async () => {
    await expect(buildMaskedPdf(src(10, 10), planOf([[]]), fakeEnv({ tokens: { '--doc-mask': MASK } }).env).promise).rejects.toThrow(MASK_PDF_FAILED);
    await expect(buildMaskedPdf(src(10, 10), planOf([[]]), fakeEnv({ imageFails: true }).env).promise).rejects.toThrow(MASK_PDF_FAILED);
  });

  it('다 쓴 캔버스는 놓는다(시험 칠 캔버스 포함)', async () => {
    const { env, made } = fakeEnv();
    await buildMaskedPdf(src(50, 40), planOf([[box('A', 0.1, 0.1, 0.5, 0.5)]]), env).promise;
    expect(made.length).toBe(2);
    expect(made.every((c) => c.width === 0 && c.height === 0)).toBe(true);
  });
});
