'use client';

/* ==========================================================================
   실제 분석 원본 파일 — 상세 화면에서 한 번 받아 메모리에 두고(문서 여러 개가 같은 파일), 쪽을 바꿔도 다시 받지 않는다.
   - loadFile(id) 는 부를 때마다 새 서명 주소로 받는다 — '다시 시도' 때만 다시 부른다(attempt).
   - PDF 면 pdf.js 를 그때 동적 import 해서 연다(pdfRuntime.ts). PNG · JPEG 는 object URL 로 <img> 에 그린다.
   - 화면을 떠나면 PDF 문서 · 워커를 정리하고 object URL 을 해제한다. 정리 뒤에 도착한 결과는 버린다(setState 없음).
     PDF 는 열기 시작과 동시에 정리 손잡이를 받으므로(pdfRuntime openPdf → { promise, close }) **여는 중에도**
     언마운트 · 다시 시도 · 분석 바뀜이면 loading task 와 워커를 바로 끝낸다. 워커 오류 · 열기 시간 초과는 고정 문구 오류.
   - 받은 바이트는 ref 에 둔다 — 개발 모드 Strict Mode 가 효과를 두 번 돌려도 다시 받지 않고, PDF 를 다시 열 때
     복사본을 넘긴다(pdf.js 가 넘긴 버퍼를 비운다).
   - 오류 문구: 서비스 오류(ApiError — 주소 · 토큰 없는 한국어)는 그대로, PDF 열기 실패는 고정 문구, 그 밖은 고정 문구.
   ========================================================================== */

import { useCallback, useEffect, useRef, useState } from 'react';
import { apiErrorCode, type LiveExtras, type LiveFile } from '@/services';
import { FILE_FAILED, FILE_UNSUPPORTED, fileKind, isKnownFileMessage } from './liveViewerModel';
import type { OpenedPdf } from './pdfRuntime';

/** 원본 파일 상태 */
export type LiveFileState =
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'ready'; kind: 'pdf'; pdf: OpenedPdf; pageCount: number }
  | { status: 'ready'; kind: 'image'; url: string; width: number; height: number; pageCount: 1 };

/**
 * pdf.js 묶음을 불러온다 — 실제 분석 모드에서만.
 * NEXT_PUBLIC_IMASK_SERVICE 는 빌드 때 글자로 들어가므로 데모 빌드에서는 이 분기가 빠져 pdf.js 묶음이 생기지 않는다
 * (SERVICE_MODE 와 같은 판단 — mode.ts resolveServiceMode 는 정확히 'api' 일 때만 실제 분석).
 */
function loadPdfRuntime(): Promise<typeof import('./pdfRuntime')> {
  if (process.env.NEXT_PUBLIC_IMASK_SERVICE === 'api') return import('./pdfRuntime');
  return Promise.reject(new Error(FILE_FAILED));
}

/** 이미지 원래 크기 */
function imageSize(url: string): Promise<{ width: number; height: number }> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => (img.naturalWidth > 0 && img.naturalHeight > 0 ? resolve({ width: img.naturalWidth, height: img.naturalHeight }) : reject(new Error(FILE_UNSUPPORTED)));
    img.onerror = () => reject(new Error(FILE_UNSUPPORTED));
    img.src = url;
  });
}

/** 화면에 보일 오류 문구 — 서비스 오류 · 알려진 고정 문구만 그대로, 그 밖은 고정 문구 */
function messageOf(err: unknown): string {
  if (err instanceof Error && err.message && (apiErrorCode(err) !== null || isKnownFileMessage(err.message))) return err.message;
  return FILE_FAILED;
}

export interface LiveFileHandle {
  state: LiveFileState;
  /** '다시 시도' — loadFile 을 다시 부른다(새 서명 주소) */
  retry: () => void;
}

const LOADING: LiveFileState = { status: 'loading' };

/**
 * 실제 분석 원본 파일을 받아 연다. id 나 extras 가 없으면(데모) 아무것도 하지 않고 늘 '받는 중' 상태다(쓰지 않음).
 */
export function useLiveFile(id: string | null, extras: LiveExtras | null): LiveFileHandle {
  const [attempt, setAttempt] = useState(0);
  const [result, setResult] = useState<{ attempt: number; state: LiveFileState } | null>(null);
  /** 이번 시도에서 받은(받는 중인) 파일 — 같은 시도면 다시 받지 않는다 */
  const download = useRef<{ key: string; promise: Promise<LiveFile> } | null>(null);

  useEffect(() => {
    if (!id || !extras) return;
    let alive = true;
    /** 여는 중 · 연 PDF 의 정리 손잡이 — 열기를 시작하자마자 채운다 */
    let closePdf: (() => void) | null = null;
    let url: string | null = null;
    const key = `${id}#${attempt}`;
    if (!download.current || download.current.key !== key) download.current = { key, promise: extras.loadFile(id) };
    const done = (state: LiveFileState) => {
      if (alive) setResult({ attempt, state });
    };

    download.current.promise
      .then(async (file) => {
        if (!alive) return;
        const kind = fileKind(file.mime, file.filename);
        if (kind === 'pdf') {
          const runtime = await loadPdfRuntime();
          if (!alive) return;
          const opening = runtime.openPdf(file.bytes);
          closePdf = opening.close;
          const pdf: OpenedPdf = await opening.promise;
          if (!alive) {
            opening.close();
            return;
          }
          done({ status: 'ready', kind: 'pdf', pdf, pageCount: pdf.pageCount });
          return;
        }
        if (kind === 'image') {
          url = URL.createObjectURL(new Blob([file.bytes], { type: file.mime || 'application/octet-stream' }));
          const size = await imageSize(url);
          done({ status: 'ready', kind: 'image', url, width: size.width, height: size.height, pageCount: 1 });
          return;
        }
        throw new Error(FILE_UNSUPPORTED);
      })
      .catch((err: unknown) => done({ status: 'error', message: messageOf(err) }));

    return () => {
      alive = false;
      closePdf?.();
      if (url) URL.revokeObjectURL(url);
    };
  }, [id, extras, attempt]);

  const retry = useCallback(() => {
    setAttempt((n) => n + 1);
  }, []);

  const state = result && result.attempt === attempt ? result.state : LOADING;
  return { state, retry };
}
