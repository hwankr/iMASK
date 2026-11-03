/* ==========================================================================
   실제 분석 원본 PDF 열기 · 쪽 그리기 — pdf.js(pdfjs-dist)를 정적으로 불러오는 유일한 모듈.
   - 이 모듈은 liveFile.ts 가 실제 분석 모드(NEXT_PUBLIC_IMASK_SERVICE=api)에서, 원본이 PDF 일 때만 동적 import 한다.
     그래서 데모 빌드에는 들어가지 않고, 실제 분석 모드에서도 첫 화면 · 목록 · 새 분석 묶음에 들어가지 않는다.
   - 워커: 문서마다 모듈 워커를 하나 만들어 PDFWorker 의 port 로 넘긴다(전역 GlobalWorkerOptions 를 쓰지 않음).
     `new Worker(new URL('pdfjs-dist/build/pdf.worker.min.mjs', import.meta.url), { type: 'module' })` 는
     번들러(Turbopack · webpack)가 알아보는 모양이라 워커 파일을 따로 묶어 같은 출처의 정적 파일로 내보낸다
     (next dev · next build 둘 다). pdf.js 공식 번들러 안내(pdfjs-dist/webpack.mjs)와 같은 방식이고, 다른 점은
     전역 하나 대신 문서마다 만들고 화면을 떠나면 끝낸다는 것뿐이다.
   - 안전: 캔버스에만 그린다(주석 레이어 · 텍스트 레이어 · 폼 · XFA · 스크립트 없음). 이 버전(6.x)에는 eval 로 글꼴을
     만드는 경로와 `isEvalSupported` 옵션이 없다(빌드 파일에 new Function · eval( 이 없음 — 보고서 참고).
     로그는 오류만(VerbosityLevel.ERRORS). 오류 문구는 고정 한국어 문구로만 바꾼다(원래 오류 내용을 보이지 않음).
   - pdf.js 는 받은 버퍼를 워커로 넘기며 비운다(transfer) — 호출하는 쪽 버퍼를 지키려고 늘 복사해서 넘긴다.
   - openPdf 는 워커 · loading task 를 만들자마자 정리 손잡이({ promise, close })를 동기적으로 돌려준다(pdfOpenGuard).
     여는 중에도 close 하면 loading task destroy · 워커 terminate 를 바로 하고, 워커 오류(스크립트 404 등) ·
     제한 시간 초과는 고정 문구로 실패한다 — 화면이 '다시 시도'를 보인다.
   ========================================================================== */

import {
  AnnotationMode,
  getDocument,
  PDFWorker,
  RenderingCancelledException,
  VerbosityLevel,
  type PDFDocumentProxy,
  type RenderTask,
} from 'pdfjs-dist';
import { PDF_OPEN_FAILED, PDF_PASSWORD, PDF_RENDER_FAILED, PDF_WORKER_FAILED } from './liveViewerModel';
import { guardOpen, type GuardedOpen } from './pdfOpenGuard';

/** 연 PDF 하나 — 쪽 수와 쪽 그리기, 정리 */
export interface OpenedPdf {
  pageCount: number;
  /** 쪽(파일 기준 1부터) 크기(PDF 단위, 회전 반영) */
  pageSize(pageNo: number): Promise<{ width: number; height: number }>;
  /**
   * 쪽을 새 캔버스에 그린다. scale = PDF 단위 1 당 캔버스 픽셀.
   * 돌려준 cancel 로 그리기를 멈추면 promise 는 null 로 끝난다(오류 아님).
   */
  render(pageNo: number, scale: number): { promise: Promise<HTMLCanvasElement | null>; cancel: () => void };
  /** 문서 · 워커를 정리한다(여러 번 불러도 된다) */
  close(): void;
}


/**
 * PDFWorker 생성자 — pdfjs-dist 의 타입 선언(d.ts)이 port 를 null 로만 적어 두었다(문서 주석과 실제 코드는 Worker).
 * 실제 인자 모양으로 타입만 바로잡는다.
 */
const PdfWorkerWithPort = PDFWorker as unknown as new (init: { port: Worker; verbosity?: number }) => PDFWorker;

function openError(err: unknown): Error {
  const name = err && typeof err === 'object' && 'name' in err ? String((err as { name: unknown }).name) : '';
  return new Error(name === 'PasswordException' ? PDF_PASSWORD : PDF_OPEN_FAILED);
}

/**
 * PDF 바이트를 열기 시작한다 — 곧바로 { promise, close } 를 돌려준다.
 * promise: 열리면 OpenedPdf, 실패 · 워커 오류 · 시간 초과면 고정 문구 Error, 여는 중 close 면 PDF_CANCELLED Error.
 * close: 여는 중이면 열기를 멈추고 바로 정리, 연 뒤면 문서 · 워커 정리(OpenedPdf.close 와 같다). 여러 번 불러도 된다.
 */
export function openPdf(bytes: ArrayBuffer): GuardedOpen<OpenedPdf> {
  let port: Worker;
  try {
    port = new Worker(new URL('pdfjs-dist/build/pdf.worker.min.mjs', import.meta.url), { type: 'module', name: 'imask-pdf' });
  } catch {
    return { promise: Promise.reject(new Error(PDF_WORKER_FAILED)), close: () => {} };
  }
  const worker = new PdfWorkerWithPort({ port, verbosity: VerbosityLevel.ERRORS });
  let task: ReturnType<typeof getDocument> | null = null;
  let opened: Promise<PDFDocumentProxy>;
  try {
    task = getDocument({
      // 복사본을 넘긴다 — pdf.js 가 워커로 넘기며 원래 버퍼를 비우기 때문
      data: new Uint8Array(bytes.slice(0)),
      worker,
      verbosity: VerbosityLevel.ERRORS,
      enableXfa: false,
      // 쪽 그리기를 또 다른 워커로 보내지 않는다(renderer 워커 설정 없음 — 본 스레드 캔버스에 그린다)
      disableWorkerRendering: true,
      stopAtErrors: false,
    });
    opened = task.promise;
  } catch (err) {
    opened = Promise.reject(err);
  }
  const loading = task;
  const guarded = guardOpen<PDFDocumentProxy>({
    port,
    opened,
    destroyTask: () => (loading ? loading.destroy() : Promise.resolve()),
    destroyWorker: () => worker.destroy(),
    mapError: openError,
  });
  return { promise: guarded.promise.then((doc) => wrap(doc, guarded.close)), close: guarded.close };
}

/** 연 문서 → OpenedPdf */
function wrap(doc: PDFDocumentProxy, close: () => void): OpenedPdf {
  return {
    pageCount: doc.numPages,
    async pageSize(pageNo) {
      const page = await doc.getPage(pageNo);
      const vp = page.getViewport({ scale: 1 });
      return { width: vp.width, height: vp.height };
    },
    render(pageNo, scale) {
      let task: RenderTask | null = null;
      let cancelled = false;
      const promise = (async () => {
        const page = await doc.getPage(pageNo);
        if (cancelled) return null;
        const viewport = page.getViewport({ scale });
        const canvas = document.createElement('canvas');
        canvas.width = Math.max(1, Math.floor(viewport.width));
        canvas.height = Math.max(1, Math.floor(viewport.height));
        // 주석은 모양(appearance)만 캔버스에 그린다 — 폼 입력칸 · 주석 레이어(DOM)는 만들지 않는다
        task = page.render({ canvas, viewport, annotationMode: AnnotationMode.ENABLE });
        try {
          await task.promise;
        } catch (err) {
          if (cancelled || err instanceof RenderingCancelledException) return null;
          throw new Error(PDF_RENDER_FAILED);
        }
        return cancelled ? null : canvas;
      })().catch((err: unknown) => {
        if (cancelled) return null;
        throw err instanceof Error && err.message === PDF_RENDER_FAILED ? err : new Error(PDF_RENDER_FAILED);
      });
      return {
        promise,
        cancel: () => {
          cancelled = true;
          task?.cancel();
        },
      };
    },
    close,
  };
}
