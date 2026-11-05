/* ==========================================================================
   가린 PDF 내려받기 — 순수 도우미(React · pdf.js · 캔버스 없음). 테스트 대상.
   - 가림 계획(maskPlan): 누른 순간의 항목별 가림(maskPicked)이 참인 모든 탐지 항목의 위치 상자를 원본 파일 쪽별로 모은다.
     필터 · '현재 문서만 보기' · 지금 보는 서류와 무관하다(미리보기에서 검게 보이는 것과 같은 선택).
     파일 쪽 = filePageOf(서류 source, 항목 page), 상자 버림 기준은 미리보기(viewerModel liveBoxSrc · LivePaper boxRect)와 같다:
     항목 page 가 그 서류 쪽 범위 안 정수가 아니면 · 서류 source 가 없으면 · 파일 쪽이 원본 쪽 수 밖이면 그 항목은 상자가 없고,
     꼭짓점 2개 미만 · 유한하지 않은 값 · 쪽과 안 겹치는 상자(unitBoxOnPage 거짓)는 버린다.
     상자가 하나도 남지 않은 고른 항목은 '가리지 못한 항목'(missed)이다 — 상자가 하나라도 그려지면 가린 것으로 센다.
   - 칠할 사각형(maskRects): 실제 캔버스 크기(px)에서 꼭짓점을 감싼 축 정렬 사각형(boxRect — 최소 크기는 미리보기 이상)에
     여백 MASK_PAD_PT(쪽 단위 pt)를 더하고 쪽 안으로 자른 뒤 바깥쪽 정수 픽셀로 맞춘다(가장자리 반 픽셀이 회색으로 남지 않게).
   - 파일 이름 · 토스트 문구(원문 값 · 기술적 오류 내용 없음).
   ========================================================================== */

import { CONFIG } from '@/config/app';
import { MIN_BOX_PX, boxRect, unitBoxOnPage, type PxRect, type UnitPoint } from '@/lib/pageBox';
import type { Analysis } from '@/services/types';
import { maskPicked, type DetailUiState } from './detailState';
import type { LiveFileState } from './liveFile';
import { filePageOf } from './liveViewerModel';
import type { OpenedPdf } from './pdfRuntime';

/* ---------- 원본 파일 ---------- */

/** 가릴 원본 — 실제 분석 상세에서 이미 받아 연 파일(useLiveFile 의 ready 상태) */
export type MaskSource = { kind: 'pdf'; pdf: OpenedPdf; pageCount: number } | { kind: 'image'; url: string; width: number; height: number };

/**
 * 원본 파일 상태 → 가릴 원본. 받는 중 · 실패 · 쪽 수가 양의 정수가 아닌 PDF(열리지만 0쪽 등) · 크기가 잘못된 이미지는 null —
 * 버튼을 막는다(누르면 실패할 입력을 '준비됨'으로 보지 않는다).
 */
export function maskSourceOf(file: LiveFileState | null): MaskSource | null {
  if (!file || file.status !== 'ready') return null;
  if (file.kind === 'pdf') return Number.isInteger(file.pageCount) && file.pageCount > 0 ? { kind: 'pdf', pdf: file.pdf, pageCount: file.pageCount } : null;
  const size = (v: number) => Number.isFinite(v) && v > 0;
  return size(file.width) && size(file.height) ? { kind: 'image', url: file.url, width: file.width, height: file.height } : null;
}

/* ---------- 문구 ---------- */

/** 버튼 글자 */
export const MASK_PDF_LABEL = '가린 PDF 내려받기';
/** 만드는 동안 버튼 글자 */
export const MASK_PDF_BUSY_LABEL = 'PDF 만드는 중…';
/** 고른 항목을 모두 가렸다 */
export const MASK_PDF_DONE = '가린 PDF를 내려받았습니다.';
/** 만들지 못했다(기술적 오류 내용 없음) */
export const MASK_PDF_FAILED = '가린 PDF를 만들지 못했습니다. 다시 시도해 주세요.';

/** 위치가 없어 가리지 못한 항목이 있을 때 */
export function maskPdfMissedText(n: number): string {
  return `가린 PDF를 내려받았습니다. 위치가 없는 ${n}건은 가리지 못했습니다.`;
}

/* ---------- 파일 이름 ---------- */

/** 파일 이름에 쓸 수 없는 글자(Windows · macOS) — 제어 문자는 따로 거른다 */
const UNSAFE_CHAR = /[\\/:*?"<>|]/;

/** 쓸 수 없는 글자 · 제어 문자(0–31 · 127)면 '_' */
const safeChar = (ch: string): string => {
  const c = ch.charCodeAt(0);
  return c < 32 || c === 127 || UNSAFE_CHAR.test(ch) ? '_' : ch;
};

/** 파일 이름 조각을 안전하게 — 쓸 수 없는 글자는 '_', 앞뒤 공백 · 점은 뗀다. 비면 대신 글자 */
export function safeNamePart(s: string, fallback = 'analysis'): string {
  const v = Array.from(String(s ?? ''), safeChar)
    .join('')
    .replace(/\s+/g, ' ')
    .replace(/^[\s.]+|[\s.]+$/g, '')
    .slice(0, 80);
  return v || fallback;
}

/** '<브랜드>_<분석 번호>_마스킹.pdf' — 분석 번호는 화면 머리의 Analysis.code */
export function maskPdfName(code: string, brand: string = CONFIG.brandName): string {
  return safeNamePart(brand, 'iMASK') + '_' + safeNamePart(code) + '_마스킹.pdf';
}

/* ---------- 가림 계획 ---------- */

/** 가릴 상자 하나(0~1 비율 꼭짓점 — 쪽 크기 기준) */
export interface MaskTarget {
  findingId: string;
  /** 위치 ID */
  anchor: string;
  points: UnitPoint[];
}

export interface MaskPlan {
  /** 원본 파일 쪽 수(0 이하 · 정수 아님이면 0) */
  pageCount: number;
  /** 파일 쪽마다(index = 쪽 − 1) 가릴 상자 — 길이 = pageCount */
  pages: MaskTarget[][];
  /** 고른(가릴) 항목 ID — 탐지 항목 순서 */
  picked: string[];
  /** 고른 항목 가운데 그릴 상자가 하나도 없어 가리지 못한 항목 ID */
  missed: string[];
}

/**
 * 누른 순간의 선택으로 가림 계획을 만든다. pick = DetailUiState.maskPick(고른 적 없으면 오탐이 아닌 항목만 가림).
 */
export function maskPlan(a: Pick<Analysis, 'docs' | 'findings'>, pick: DetailUiState['maskPick'], pageCount: number): MaskPlan {
  const n = Number.isInteger(pageCount) && pageCount > 0 ? pageCount : 0;
  const pages: MaskTarget[][] = Array.from({ length: n }, () => []);
  const picked: string[] = [];
  const missed: string[] = [];
  for (const f of a.findings) {
    if (!maskPicked(pick, f)) continue;
    picked.push(f.id);
    const src = a.docs.find((d) => d.id === f.docId)?.source;
    // 미리보기는 서류 안 쪽(1 … 서류 쪽 수)과 항목 page 가 같을 때만 상자를 그린다
    const count = src ? Math.max(1, src.pageEnd - src.pageStart + 1) : 0;
    const inDoc = !!src && Number.isInteger(f.page) && f.page >= 1 && f.page <= count;
    const filePage = src && inDoc ? filePageOf(src, f.page) : 0;
    const boxes = filePage >= 1 && filePage <= n ? (f.boxes ?? []).filter((b) => !!b && unitBoxOnPage(b.points)) : [];
    if (!boxes.length) {
      missed.push(f.id);
      continue;
    }
    for (const b of boxes) pages[filePage - 1].push({ findingId: f.id, anchor: b.a, points: b.points.map((p) => ({ x: p.x, y: p.y })) });
  }
  return { pageCount: n, pages, picked, missed };
}

/* ---------- 칠할 사각형 ---------- */

/** 상자 둘레 여백(쪽 단위 pt) — 인식 상자 가장자리에 걸친 글자 조각(획 끝 · 안티앨리어싱)이 남지 않게. 1.5pt ≈ 0.5mm */
export const MASK_PAD_PT = 1.5;

/**
 * 미리보기 종이 폭(px) — tokens.css --paper-w 와 같은 값. 미리보기는 이 폭의 종이에서 상자를 최소 MIN_BOX_PX 로 그린다
 * (LivePaper — 배율은 CSS zoom 이라 쪽 폭 대비 비율이 같다). 가린 PDF 의 최소 크기는 같은 비율 이상이다.
 */
export const PREVIEW_PAPER_PX = 760;

const posFinite = (v: number) => typeof v === 'number' && Number.isFinite(v) && v > 0;

/**
 * 한 쪽에서 칠할 사각형(캔버스 px, 정수). canvas = 실제 캔버스 크기, page = 그 쪽의 보이는 크기(pt — 여백 환산).
 * 그릴 수 없는 상자(boxRect null)는 빠진다. 크기가 잘못되면 빈 목록.
 */
export function maskRects(targets: readonly Pick<MaskTarget, 'points'>[], canvas: { width: number; height: number }, page: { width: number; height: number }): PxRect[] {
  const W = canvas.width;
  const H = canvas.height;
  if (!posFinite(W) || !posFinite(H)) return [];
  // pt → 캔버스 px(쪽 크기를 모르면 1)
  const sx = posFinite(page.width) ? W / page.width : 1;
  const sy = posFinite(page.height) ? H / page.height : 1;
  const padX = MASK_PAD_PT * sx;
  const padY = MASK_PAD_PT * sy;
  const minPx = (MIN_BOX_PX * W) / PREVIEW_PAPER_PX;
  const out: PxRect[] = [];
  for (const t of targets) {
    const r = boxRect(t.points, { width: W, height: H }, minPx);
    if (!r) continue;
    const x0 = Math.max(0, Math.floor(r.x - padX));
    const y0 = Math.max(0, Math.floor(r.y - padY));
    const x1 = Math.min(W, Math.ceil(r.x + r.w + padX));
    const y1 = Math.min(H, Math.ceil(r.y + r.h + padY));
    if (x1 > x0 && y1 > y0) out.push({ x: x0, y: y0, w: x1 - x0, h: y1 - y0 });
  }
  return out;
}
