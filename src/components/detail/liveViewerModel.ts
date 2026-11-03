/* ==========================================================================
   실제 분석 원문 뷰어 — 순수 도우미(React · pdf.js 없음). 테스트 대상.
   - 원본 파일 종류(PDF · 이미지), 서류 안 쪽 → 파일 기준 쪽, 문서 목록 메타 줄, 안내 문구 정리, 고정 오류 문구.
   - 이 파일은 pdf.js 를 import 하지 않는다(pdfRuntime.ts 가 이 파일의 문구를 가져다 쓴다).
   ========================================================================== */

import type { DocSource } from '@/services/types';

/* ---------- 고정 문구(주소 · 토큰 · 원래 오류 내용을 담지 않는다) ---------- */

export const FILE_FAILED = '원문을 표시하지 못했습니다. 잠시 후 다시 시도해 주세요.';
export const FILE_UNSUPPORTED = '원문을 표시할 수 없는 파일 형식입니다(PDF · PNG · JPEG 만 표시합니다).';
export const PDF_OPEN_FAILED = '원본 파일을 PDF 로 열지 못했습니다. 파일이 손상되었을 수 있습니다.';
export const PDF_PASSWORD = '암호가 걸린 PDF 라 원문을 표시할 수 없습니다.';
export const PDF_RENDER_FAILED = '이 쪽을 그리지 못했습니다.';
/** 원문 보기 워커(스크립트)를 불러오거나 시작하지 못함 */
export const PDF_WORKER_FAILED = '원문 보기 도구를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.';
/** 워커 초기화 · PDF 열기가 제한 시간을 넘음 */
export const PDF_OPEN_TIMEOUT = '원문을 여는 데 시간이 너무 오래 걸립니다. 잠시 후 다시 시도해 주세요.';
/** 화면 정리로 열기를 멈춤(화면에 보이지 않는다 — 정리 뒤 결과는 버린다) */
export const PDF_CANCELLED = '원문 열기를 멈췄습니다.';

/** 화면이 그대로 보여도 되는 고정 문구인지 */
export function isKnownFileMessage(message: string): boolean {
  return [FILE_FAILED, FILE_UNSUPPORTED, PDF_OPEN_FAILED, PDF_PASSWORD, PDF_RENDER_FAILED, PDF_WORKER_FAILED, PDF_OPEN_TIMEOUT].includes(message);
}

/** 서류의 쪽이 원본 파일에 없을 때 */
export function pageMissingText(filePage: number, pageCount: number): string {
  return `이 서류의 쪽(파일 ${filePage}쪽)이 원본 파일(${pageCount}쪽)에 없습니다.`;
}

/* ---------- 파일 종류 ---------- */

export type LiveFileKind = 'pdf' | 'image' | 'unknown';

/** MIME 형식(없으면 파일 이름 확장자)으로 원문 그리는 방법을 고른다 */
export function fileKind(mime: string, filename: string): LiveFileKind {
  const m = (mime || '').trim().toLowerCase();
  if (m === 'application/pdf' || m === 'application/x-pdf') return 'pdf';
  if (m === 'image/png' || m === 'image/jpeg' || m === 'image/jpg' || m === 'image/pjpeg') return 'image';
  if (m) return 'unknown';
  const ext = /\.([a-z0-9]+)$/i.exec(filename || '')?.[1]?.toLowerCase() ?? '';
  if (ext === 'pdf') return 'pdf';
  if (ext === 'png' || ext === 'jpg' || ext === 'jpeg') return 'image';
  return 'unknown';
}

/* ---------- 쪽 ---------- */

/** 서류 안 쪽(1부터) → 파일 기준 쪽 = pageStart + (쪽 − 1). 서류 범위 밖이면 범위 안으로 */
export function filePageOf(source: Pick<DocSource, 'pageStart' | 'pageEnd'>, page: number): number {
  const count = Math.max(1, source.pageEnd - source.pageStart + 1);
  const p = Number.isFinite(page) ? Math.min(Math.max(1, Math.floor(page)), count) : 1;
  return source.pageStart + p - 1;
}

/** 문서 목록 메타 줄 — '1페이지 · 파일 3쪽' · '2페이지 · 파일 3–4쪽'(묶음 파일 크기는 서류마다 보이지 않는다) */
export function liveDocMeta(source: Pick<DocSource, 'pageStart' | 'pageEnd'>): string {
  const count = Math.max(1, source.pageEnd - source.pageStart + 1);
  const range = source.pageEnd > source.pageStart ? `${source.pageStart}–${source.pageEnd}` : `${source.pageStart}`;
  return `${count}페이지 · 파일 ${range}쪽`;
}

/* ---------- 안내 문구 ---------- */

/** 인용 표시(【†3】 · 【3†source】 등) */
const CITATION = /【[^】]*】/g;

/**
 * 워크플로우 Markdown 을 글자 그대로 보이기 위한 정리 — HTML 로 바꾸지 않는다.
 * 줄바꿈(CRLF · CR → LF)은 지키고 인용 표시만 지운다. 줄 끝 공백을 떼고, 빈 줄이 셋 이상 이어지면 둘로, 앞뒤 빈 줄은 뺀다.
 * 문자열이 아니면 ''.
 */
export function guideText(md: unknown): string {
  if (typeof md !== 'string') return '';
  return md
    .replace(/\r\n|\r/g, '\n')
    .replace(CITATION, '')
    .split('\n')
    .map((l) => l.replace(/[ \t]+$/, ''))
    .join('\n')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
}
