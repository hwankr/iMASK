/* ==========================================================================
   가린 PDF 만들기 — 브라우저 실행부(캔버스). '가린 PDF 내려받기'를 누를 때만 동적 import 한다(첫 화면 묶음에 넣지 않음).
   - 원본 파일의 모든 쪽을 원래 순서로 그림으로 그린다: PDF 는 이미 연 문서(OpenedPdf.render — 미리보기와 같은 viewport,
     쪽 회전 반영)를 약 144dpi(배율 2, canvasScale 상한), PNG · JPEG 는 원래 픽셀 크기(같은 상한) 캔버스에 종이색 바탕 위로.
   - 쪽마다 가림 계획(maskPdf.ts maskPlan)의 상자를 실제 캔버스 크기 기준 사각형(maskRects)으로 불투명하게 칠한다:
     색은 --doc-mask 토큰(실행 중에 읽음 · 1px 시험 칠로 불투명한지 확인), globalAlpha 1, 기본 합성(source-over).
   - 칠한 캔버스를 JPEG(품질 0.9)로 바꿔 그림 PDF(src/lib/imagePdf.ts)에 넣는다 — 글자 레이어 없음(진짜 가림).
     쪽의 보이는 크기(pt) = PDF 는 pageSize(회전 · UserUnit 반영 · 배율 1), 이미지는 px × 72/96 — 줄이지 않는다
     (한 변이 14400pt 를 넘으면 작성기가 /UserUnit 으로 같은 크기를 적는다).
   - 쪽을 하나씩 처리하고 다 쓴 캔버스는 바로 놓는다(width · height 0).
   - 한 쪽이라도 그리기 · 인코딩에 실패하면 전체 실패(MASK_PDF_FAILED Error) — 가리지 않은 쪽이나 빠진 쪽이 든 파일을 만들지 않는다.
   - cancel 하면 그리던 쪽을 멈추고 promise 는 null 로 끝난다(오류 아님). 오류 문구는 고정 문구뿐(원문 값 · 기술 내용 없음).
   ========================================================================== */

import { buildImagePdf, type ImagePdfPage } from '@/lib/imagePdf';
import { canvasScale } from '@/lib/pageBox';
import { MASK_PDF_FAILED, maskRects, type MaskPlan, type MaskSource } from './maskPdf';

export { maskPlan, type MaskSource } from './maskPdf';

/** 만든 결과 */
export interface MaskedPdf {
  bytes: Uint8Array;
  /** 가리지 못한 항목 수(plan.missed) */
  missed: number;
}

export interface MaskJob {
  /** 끝나면 결과, cancel 하면 null, 실패하면 MASK_PDF_FAILED Error */
  promise: Promise<MaskedPdf | null>;
  cancel: () => void;
}

/** PDF 쪽 배율(PDF 단위 1 = 1/72 인치 → 2 배 ≈ 144dpi) */
export const MASK_PDF_SCALE = 2;
/** JPEG 품질 */
export const MASK_JPEG_QUALITY = 0.9;
/** 이미지 px → pt(96dpi 기준) */
const PX_TO_PT = 72 / 96;

/** 바꿔 끼울 수 있는 브라우저 기능(브라우저 확인 도구 · 시험용) */
export interface MaskEnv {
  /** CSS 토큰 값(예 '--doc-mask') */
  token: (name: string) => string;
  createCanvas: () => HTMLCanvasElement;
  loadImage: (url: string) => Promise<CanvasImageSource>;
  toJpeg: (canvas: HTMLCanvasElement, quality: number) => Promise<Uint8Array | null>;
}

function browserEnv(): MaskEnv {
  return {
    token: (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim(),
    createCanvas: () => document.createElement('canvas'),
    loadImage: (url) =>
      new Promise((resolve, reject) => {
        const img = new Image();
        img.onload = () => resolve(img);
        img.onerror = () => reject(new Error(MASK_PDF_FAILED));
        img.src = url;
      }),
    toJpeg: (canvas, quality) =>
      new Promise((resolve) => {
        try {
          canvas.toBlob(
            (blob) => {
              if (!blob) return resolve(null);
              blob.arrayBuffer().then(
                (buf) => resolve(new Uint8Array(buf)),
                () => resolve(null),
              );
            },
            'image/jpeg',
            quality,
          );
        } catch {
          resolve(null);
        }
      }),
  };
}

const fail = (): Error => new Error(MASK_PDF_FAILED);

function ctx2d(canvas: HTMLCanvasElement): CanvasRenderingContext2D {
  const ctx = canvas.getContext('2d');
  if (!ctx) throw fail();
  return ctx;
}

/** 캔버스를 놓는다 — 큰 픽셀 버퍼를 바로 돌려준다 */
function release(canvas: HTMLCanvasElement | null) {
  if (!canvas) return;
  canvas.width = 0;
  canvas.height = 0;
}

/** 가림 색이 불투명하게 칠해지는지 1px 시험 칠로 확인한다(토큰이 비었거나 반투명이면 실패) */
function checkOpaque(env: MaskEnv, color: string) {
  if (!color) throw fail();
  const probe = env.createCanvas();
  probe.width = 1;
  probe.height = 1;
  try {
    const c = ctx2d(probe);
    c.globalAlpha = 1;
    c.globalCompositeOperation = 'source-over';
    c.clearRect(0, 0, 1, 1);
    c.fillStyle = color;
    c.fillRect(0, 0, 1, 1);
    if (c.getImageData(0, 0, 1, 1).data[3] !== 255) throw fail();
  } finally {
    release(probe);
  }
}

/** 칠할 사각형을 불투명하게 칠한다 */
function paint(canvas: HTMLCanvasElement, rects: { x: number; y: number; w: number; h: number }[], color: string) {
  if (!rects.length) return;
  const c = ctx2d(canvas);
  c.save();
  c.setTransform(1, 0, 0, 1, 0, 0);
  c.globalAlpha = 1;
  c.globalCompositeOperation = 'source-over';
  c.fillStyle = color;
  for (const r of rects) c.fillRect(r.x, r.y, r.w, r.h);
  c.restore();
}

/**
 * 가린 PDF 를 만든다. plan.pageCount 는 원본 쪽 수와 같아야 한다(다르면 실패).
 */
export function buildMaskedPdf(src: MaskSource, plan: MaskPlan, env: MaskEnv = browserEnv()): MaskJob {
  let cancelled = false;
  /** 지금 그리는 PDF 쪽의 취소 손잡이 */
  let current: { cancel: () => void } | null = null;

  const promise = (async (): Promise<MaskedPdf | null> => {
    const count = src.kind === 'pdf' ? src.pageCount : 1;
    if (!Number.isInteger(count) || count < 1 || plan.pageCount !== count) throw fail();
    const mask = env.token('--doc-mask');
    checkOpaque(env, mask);

    const pages: ImagePdfPage[] = [];
    for (let p = 1; p <= count; p++) {
      if (cancelled) return null;
      let canvas: HTMLCanvasElement | null = null;
      try {
        let size: { width: number; height: number };
        if (src.kind === 'pdf') {
          size = await src.pdf.pageSize(p);
          if (cancelled) return null;
          const job = src.pdf.render(p, canvasScale(size.width, size.height, MASK_PDF_SCALE));
          current = job;
          canvas = await job.promise;
          current = null;
          if (cancelled) return null;
          if (!canvas) throw fail();
        } else {
          size = { width: src.width * PX_TO_PT, height: src.height * PX_TO_PT };
          const img = await env.loadImage(src.url);
          if (cancelled) return null;
          const s = canvasScale(src.width, src.height, 1);
          canvas = env.createCanvas();
          canvas.width = Math.max(1, Math.floor(src.width * s));
          canvas.height = Math.max(1, Math.floor(src.height * s));
          const c = ctx2d(canvas);
          // 투명한 부분은 미리보기 종이색(--paper) 위에 그린다(JPEG 는 투명을 검게 바꾼다)
          const paper = env.token('--paper');
          if (!paper) throw fail();
          c.fillStyle = paper;
          c.fillRect(0, 0, canvas.width, canvas.height);
          c.drawImage(img, 0, 0, canvas.width, canvas.height);
        }
        if (!(size.width > 0 && size.height > 0)) throw fail();

        paint(canvas, maskRects(plan.pages[p - 1], canvas, size), mask);

        const jpeg = await env.toJpeg(canvas, MASK_JPEG_QUALITY);
        if (cancelled) return null;
        if (!jpeg || jpeg.length < 2) throw fail();
        // 보이는 쪽 크기 그대로 — 14400pt 를 넘으면 작성기가 /UserUnit 으로 적는다(크기를 줄이지 않는다)
        pages.push({ width: size.width, height: size.height, jpeg, pixelWidth: canvas.width, pixelHeight: canvas.height });
      } finally {
        current = null;
        release(canvas);
      }
    }
    if (cancelled) return null;
    return { bytes: buildImagePdf(pages), missed: plan.missed.length };
  })().catch(() => {
    if (cancelled) return null;
    // 고정 문구로만 실패한다(원래 오류 내용을 넘기지 않음)
    throw fail();
  });

  return {
    promise,
    cancel: () => {
      cancelled = true;
      current?.cancel();
    },
  };
}
