/* ==========================================================================
   원본 파일 받기 — GET /analyses/{id}/file 이 준 서명 다운로드 주소(Supabase Storage)에서 내용을 받는다.
   - 주소 검사: https: 이거나, http: 이면서 호스트가 localhost·127.0.0.1(로컬 가짜 백엔드)일 때만 받는다.
     그 밖(javascript:·data:·원격 http: 등)은 요청하지 않고 오류.
   - 받기 요청에는 사용자 지정 헤더를 붙이지 않는다(X-Demo-Code 없음 · credentials omit · cache no-store · referrer 없음).
   - 시간 제한(기본 60초 — 백엔드 클라이언트와 같다)은 응답 헤더가 아니라 본문을 다 읽을 때까지 걸린다.
   - 2xx 아님 · 빈 본문 · 20MB(20,971,520 바이트) 초과는 오류. 본문은 조각씩 읽으며 한도를 넘는 순간 멈춘다.
   - 오류는 고정 한국어 문구의 '새' ApiError 다. 서명 주소·토큰은 문구·cause·스택·콘솔 어디에도 넣지 않는다.
     · 받기 안에서 알고 있는 실패는 모듈 안 전용 표식(FileFailure)으로만 던지고, 바깥 경계에서 새 ApiError 로 바꾼다.
       그 밖의 모든 오류는 종류와 상관없이(ApiError 여도) 버리고 고정 문구로 바꾼다 — 바깥 오류 객체를 다시 던지지 않는다.
     · /file 요청 오류도 fileInfoError 로 새 ApiError 로 바꾼다. 401·404 의 백엔드 detail 은 안전한 문장일 때만
       보존하고(isSafeDetail), 그 밖은 고정 문구로 바꾼다.
   ========================================================================== */

import { ApiError, DEFAULT_TIMEOUT_MS, MSG_NETWORK, MSG_TIMEOUT, MSG_UNAUTHORIZED, isApiError, type ApiErrorCode } from './client';

/** 원본 파일 최대 크기(업로드 한도와 같은 20MB) */
export const FILE_MAX_BYTES = 20 * 1024 * 1024;

export const MSG_FILE_BAD_URL = '원본 파일 주소를 받지 못했습니다. 잠시 후 다시 시도해 주세요.';
export const MSG_FILE_NOT_FOUND = '원본 파일을 찾을 수 없습니다.';
export const MSG_FILE_DOWNLOAD = '원본 파일을 받지 못했습니다. 잠시 후 다시 시도해 주세요.';
export const MSG_FILE_EMPTY = '원본 파일이 비어 있어 열 수 없습니다.';
export const MSG_FILE_TOO_LARGE = '원본 파일이 20MB 를 넘어 열 수 없습니다.';
export const MSG_FILE_TIMEOUT = '원본 파일을 받는 데 시간이 너무 오래 걸립니다. 잠시 후 다시 시도해 주세요.';

/* ---------- /file 요청 오류 → 안전한 새 오류 ---------- */

/** 주소 · 서명 표지 · JWT 모양 · sb_ 키 모양 · 20자 넘는 영숫자 덩어리 */
const UNSAFE_DETAIL: readonly RegExp[] = [
  /:\/\//, // 주소
  /www\./i,
  /token/i, // 서명 표지
  /sig=/i,
  /signature/i,
  /eyJ[A-Za-z0-9_-]*\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+/, // JWT 모양(점 세 덩어리)
  /sb_[A-Za-z0-9]/i, // sb_secret_… · sb_publishable_… 같은 키 모양
  /[A-Za-z0-9_-]{21,}/, // 20자 넘는 영숫자 · - · _ 덩어리
];

/**
 * 백엔드 detail 을 화면에 그대로 보여도 되는 문장인지 — 순수 함수.
 * 비었거나 문자열이 아니거나, 주소·토큰·서명·JWT·sb_ 키 모양·20자 넘는 영숫자 덩어리가 하나라도 있으면 false.
 */
export function isSafeDetail(detail: unknown): detail is string {
  if (typeof detail !== 'string' || !detail.trim()) return false;
  return !UNSAFE_DETAIL.some((re) => re.test(detail));
}

/**
 * /file 요청(client.getFile)이 던진 오류 → 새 ApiError — 순수 함수. 원래 오류 객체 · cause · 스택은 넘기지 않는다.
 * - 401 · 404: 백엔드 detail 이 안전한 문장이면 그대로, 아니면 고정 문구(401 접근 코드 · 404 원본 파일 없음).
 * - 시간 초과 · 네트워크: 클라이언트의 고정 문구. 그 밖(5xx · 다른 4xx · 응답 읽기 실패 · ApiError 아님): 주소를 받지 못함.
 * code · status 는 원래 값을 따른다(ApiError 가 아니면 server · 0).
 */
export function fileInfoError(err: unknown): ApiError {
  if (!isApiError(err)) return new ApiError(0, 'server', MSG_FILE_BAD_URL);
  const status = typeof err.status === 'number' && Number.isFinite(err.status) ? err.status : 0;
  const code: ApiErrorCode = err.code;
  const detail = err.message;
  if (code === 'unauthorized') return new ApiError(status, code, isSafeDetail(detail) ? detail : MSG_UNAUTHORIZED);
  if (code === 'not_found') return new ApiError(status, code, isSafeDetail(detail) ? detail : MSG_FILE_NOT_FOUND);
  if (code === 'network') return new ApiError(status, code, detail === MSG_TIMEOUT ? MSG_TIMEOUT : MSG_NETWORK);
  return new ApiError(status, code, MSG_FILE_BAD_URL);
}

/* ---------- 주소 검사 ---------- */

/** http: 로 받아도 되는 호스트(로컬 가짜 백엔드) */
const LOCAL_HOSTS: ReadonlySet<string> = new Set(['localhost', '127.0.0.1']);

/** 받아도 되는 주소인지 — https:, 또는 http://localhost·127.0.0.1. 읽지 못하는 값은 false */
export function isAllowedFileUrl(value: unknown): value is string {
  if (typeof value !== 'string' || !value.trim()) return false;
  let url: URL;
  try {
    url = new URL(value.trim());
  } catch {
    return false; // 상대 주소 · 깨진 주소(오류 문구에 주소가 들어 있으므로 버린다)
  }
  if (url.protocol === 'https:') return true;
  return url.protocol === 'http:' && LOCAL_HOSTS.has(url.hostname);
}

/* ---------- 받기 ---------- */

/**
 * 받기 안에서 알고 있는 실패 — 이 모듈만 만든다(내보내지 않음). 문구는 늘 위의 고정 상수다.
 * 바깥 경계(downloadFile)가 이것만 골라 새 ApiError 로 바꾸고, 다른 오류는 모두 버린다.
 */
class FileFailure {
  constructor(
    readonly status: number,
    readonly code: ApiErrorCode,
    readonly message: string,
  ) {}
}

export interface DownloadOptions {
  /** 기본 전역 fetch */
  fetch?: typeof fetch;
  /** 기본 60초(본문을 다 읽을 때까지) */
  timeoutMs?: number;
}

/** 쓰지 않을 본문을 버린다(연결을 놓아 준다). 실패해도 조용히 */
function discard(response: Response): void {
  try {
    void response.body?.cancel().catch(() => {});
  } catch {
    /* 이미 읽는 중인 본문 등 — 무시 */
  }
}

/** 본문을 한도까지 읽는다 — 넘으면 읽기를 멈추고 FileFailure. onReader 로 시간 초과 때 끊을 함수를 넘긴다 */
async function readLimited(response: Response, onReader: (cancel: () => void) => void): Promise<ArrayBuffer> {
  const tooLarge = () => new FileFailure(response.status, 'server', MSG_FILE_TOO_LARGE);
  const body = response.body;
  if (!body) {
    const buf = await response.arrayBuffer();
    if (buf.byteLength > FILE_MAX_BYTES) throw tooLarge();
    return buf;
  }
  const reader = body.getReader();
  const cancel = () => {
    reader.cancel().catch(() => {});
  };
  onReader(cancel);
  const chunks: Uint8Array[] = [];
  let total = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    if (!value) continue;
    total += value.byteLength;
    if (total > FILE_MAX_BYTES) {
      cancel();
      throw tooLarge();
    }
    chunks.push(value);
  }
  const out = new Uint8Array(total);
  let offset = 0;
  for (const chunk of chunks) {
    out.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return out.buffer;
}

/**
 * 서명 다운로드 주소에서 파일 내용을 받는다. 실패하면 고정 문구의 새 ApiError
 * (주소 검사 실패·2xx 아님·빈 본문·크기 초과 → code 'server', 연결 실패·본문 읽기 실패·시간 초과 → code 'network').
 */
export async function downloadFile(urlValue: unknown, options: DownloadOptions = {}): Promise<ArrayBuffer> {
  if (!isAllowedFileUrl(urlValue)) throw new ApiError(0, 'server', MSG_FILE_BAD_URL);
  const url = urlValue.trim();
  const doFetch: typeof fetch = options.fetch ?? ((input, init) => fetch(input, init));
  const timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS;

  // 시간 제한은 본문을 다 읽을 때까지 — 백엔드 클라이언트(client.ts)와 같은 방식(signal + deadline 경주)
  const controller = typeof AbortController === 'undefined' ? null : new AbortController();
  let timedOut = false;
  let cancelBody: () => void = () => {};
  let expire: (failure: FileFailure) => void = () => {};
  const deadline = new Promise<never>((_, reject) => {
    expire = reject;
  });
  deadline.catch(() => {}); // 경주에 쓰이지 않은 채 끝나도 처리되지 않은 거절로 남지 않게
  const timer = setTimeout(() => {
    timedOut = true;
    expire(new FileFailure(0, 'network', MSG_FILE_TIMEOUT));
    controller?.abort();
    cancelBody();
  }, timeoutMs);
  const timeoutOr = <V,>(work: Promise<V>): Promise<V> => Promise.race([work, deadline]);

  /** 받기 본체 — 알고 있는 실패는 FileFailure 로만 던진다(그 밖의 오류는 바깥 경계가 버린다) */
  const run = async (): Promise<ArrayBuffer> => {
    const response = await timeoutOr(
      doFetch(url, {
        method: 'GET',
        credentials: 'omit',
        cache: 'no-store',
        referrerPolicy: 'no-referrer',
        signal: controller?.signal,
      }),
    );
    if (!response.ok) {
      discard(response);
      throw new FileFailure(response.status, 'server', MSG_FILE_DOWNLOAD);
    }
    const declared = Number(response.headers.get('content-length'));
    if (Number.isFinite(declared) && declared > FILE_MAX_BYTES) {
      discard(response);
      throw new FileFailure(response.status, 'server', MSG_FILE_TOO_LARGE);
    }
    const bytes = await timeoutOr(
      readLimited(response, (cancel) => {
        cancelBody = cancel;
      }),
    );
    if (bytes.byteLength === 0) throw new FileFailure(response.status, 'server', MSG_FILE_EMPTY);
    return bytes;
  };

  try {
    return await run();
  } catch (err) {
    // 바깥 경계 — 늘 새 ApiError(고정 문구). 원래 오류 객체 · cause 는 넘기지 않는다.
    if (timedOut) throw new ApiError(0, 'network', MSG_FILE_TIMEOUT);
    if (err instanceof FileFailure) throw new ApiError(err.status, err.code, err.message);
    throw new ApiError(0, 'network', MSG_FILE_DOWNLOAD); // 연결 실패 · 본문 읽기 실패(종류와 상관없이)
  } finally {
    clearTimeout(timer);
  }
}
