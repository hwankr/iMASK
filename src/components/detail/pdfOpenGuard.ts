/* ==========================================================================
   PDF 열기 지킴이 — 열기가 끝나기 전의 실패 · 시간 초과 · 취소를 한곳에서 처리한다(pdf.js 를 import 하지 않음, 테스트 대상).
   - pdfRuntime.ts 가 워커(port)와 loading task 를 만든 직후 이 함수에 넘기고, 돌려받은 { promise, close } 를 곧바로
     화면(liveFile.ts)에 준다 — 그래서 화면 정리(언마운트 · 다시 시도 · 분석 바뀜)가 **여는 중에도** 정리할 수 있다.
   - 직접 만든 Worker 의 error · messageerror 를 듣는다: pdf.js 는 바깥에서 받은 port 의 오류를 열기 실패로 바꾸지 않아
     (워커 스크립트 404 등) 그대로 두면 '받는 중'에서 멈춘다. 오류 · 시간 초과면 고정 한국어 문구로 거절하고 바로 정리한다.
   - 성공 · 실패 · 취소 어느 길이든 리스너와 타이머를 해제한다. 정리는 한 번만 한다(여러 번 불러도 됨).
   - 정리: 여는 중 · 실패면 바로(loading task destroy → PDFWorker destroy → Worker terminate),
     연 뒤 닫을 때는 문서 정리를 최대 graceMs 기다린 뒤 끝낸다(워커에 정리 요청을 보낼 틈).
     정리가 먼저 끝나면 그 자리에서 끝내고 대기 타이머를 해제한다(어느 쪽이 먼저든 종료는 정확히 한 번, 남는 타이머 없음).
   ========================================================================== */

import { PDF_CANCELLED, PDF_OPEN_TIMEOUT, PDF_WORKER_FAILED } from './liveViewerModel';

/** 워커 초기화 · PDF 열기 제한 시간(밀리초). 이유는 보고서 — 워커 스크립트(약 1MB) 받기 + 문서 구조 읽기에 느린 휴대폰 망도 넉넉한 값 */
export const PDF_OPEN_TIMEOUT_MS = 30_000;
/** 연 문서를 닫을 때 문서 정리를 기다리는 최대 시간(밀리초) — 넘으면 그냥 끝낸다 */
export const PDF_CLOSE_GRACE_MS = 1_000;

/** 오류 이벤트를 듣고 끝낼 수 있는 워커(브라우저 Worker 와 같은 모양) */
export interface GuardPort {
  addEventListener(type: 'error' | 'messageerror', listener: () => void): void;
  removeEventListener(type: 'error' | 'messageerror', listener: () => void): void;
  terminate(): void;
}

export interface GuardParts<T> {
  port: GuardPort;
  /** 문서 열기 결과(loading task 의 promise) */
  opened: Promise<T>;
  /** loading task 정리(destroy) — 끝나면 풀린다 */
  destroyTask: () => Promise<unknown>;
  /** PDFWorker 정리(destroy) */
  destroyWorker: () => void;
  /** 열기 실패 오류 → 화면에 보일 고정 문구의 Error */
  mapError: (err: unknown) => Error;
}

export interface GuardOptions {
  timeoutMs?: number;
  graceMs?: number;
  /** 테스트용 타이머 */
  setTimer?: (fn: () => void, ms: number) => unknown;
  clearTimer?: (id: unknown) => void;
}

export interface GuardedOpen<T> {
  /** 열리면 문서, 실패 · 시간 초과면 고정 문구 Error, 닫으면(여는 중) PDF_CANCELLED Error 로 끝난다 */
  promise: Promise<T>;
  /** 정리 — 여는 중이면 열기를 멈추고 바로 끝내고, 연 뒤면 문서를 닫는다. 여러 번 불러도 된다 */
  close: () => void;
}

/** 열기를 지키며 시작한다 — 곧바로(동기) 정리 손잡이를 돌려준다 */
export function guardOpen<T>(parts: GuardParts<T>, opts: GuardOptions = {}): GuardedOpen<T> {
  const timeoutMs = opts.timeoutMs ?? PDF_OPEN_TIMEOUT_MS;
  const graceMs = opts.graceMs ?? PDF_CLOSE_GRACE_MS;
  const setTimer = opts.setTimer ?? ((fn: () => void, ms: number) => setTimeout(fn, ms));
  const clearTimer = opts.clearTimer ?? ((id: unknown) => clearTimeout(id as ReturnType<typeof setTimeout>));

  let state: 'opening' | 'open' | 'done' = 'opening';
  let ended = false;
  let resolve!: (v: T) => void;
  let reject!: (e: Error) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });

  const onWorkerError = () => fail(new Error(PDF_WORKER_FAILED));
  const timer = setTimer(() => fail(new Error(PDF_OPEN_TIMEOUT)), timeoutMs);
  parts.port.addEventListener('error', onWorkerError);
  parts.port.addEventListener('messageerror', onWorkerError);

  /** 리스너 · 타이머 해제 */
  const detach = () => {
    clearTimer(timer);
    parts.port.removeEventListener('error', onWorkerError);
    parts.port.removeEventListener('messageerror', onWorkerError);
  };

  /** 워커를 끝낸다 — graceful 이면 문서 정리를 잠깐 기다린다 */
  const end = (graceful: boolean) => {
    if (ended) return;
    ended = true;
    const finish = () => {
      try {
        parts.destroyWorker();
      } catch {
        /* 이미 정리됨 */
      }
      parts.port.terminate();
    };
    let destroyed: Promise<unknown>;
    try {
      destroyed = Promise.resolve(parts.destroyTask()).catch(() => undefined);
    } catch {
      destroyed = Promise.resolve();
    }
    if (!graceful) {
      finish();
      return;
    }
    // 문서 정리와 graceMs 대기 중 먼저 끝나는 쪽에서 한 번만 끝낸다 — 정리가 먼저 끝나면 대기 타이머를 해제한다
    let graceTimer: unknown = null;
    let finished = false;
    const finishOnce = () => {
      if (finished) return;
      finished = true;
      if (graceTimer !== null) clearTimer(graceTimer);
      graceTimer = null;
      finish();
    };
    graceTimer = setTimer(finishOnce, graceMs);
    destroyed.then(finishOnce, finishOnce);
  };

  function fail(err: Error) {
    if (state !== 'opening') return;
    state = 'done';
    detach();
    end(false);
    reject(err);
  }

  parts.opened.then(
    (value) => {
      if (state !== 'opening') return;
      state = 'open';
      detach();
      resolve(value);
    },
    (err: unknown) => {
      if (state !== 'opening') return;
      fail(parts.mapError(err));
    },
  );

  const close = () => {
    if (state === 'opening') {
      state = 'done';
      detach();
      end(false);
      reject(new Error(PDF_CANCELLED));
      return;
    }
    if (state === 'open') {
      state = 'done';
      end(true);
    }
  };

  return { promise, close };
}
