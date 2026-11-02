/* ==========================================================================
   FastAPI 백엔드 클라이언트 — fetch 래퍼(T2 'API 계약' 그대로)
   - 기본 주소는 같은 출처의 '/api/py'(로컬은 Next rewrites → uvicorn, 배포는 같은 Vercel 프로젝트의 Python 함수).
   - 모든 분석 요청에 X-Demo-Code(이 탭에 저장한 접근 코드)를 붙인다. 코드가 비었으면 헤더를 빼고 보낸다
     (서버가 401 로 답한다). 이 헤더는 이 클라이언트만 붙인다 — Supabase 업로드 요청에는 붙지 않는다.
   - 오류는 ApiError { status, code, message }. message 는 서버가 준 detail(한국어) 또는 기본 문구.
     네트워크 오류·시간 초과도 한국어 문구의 ApiError(code 'network', status 0)다.
   - 시간 제한(기본 60초)은 응답 헤더가 아니라 본문을 다 읽을 때까지 걸린다.
   ========================================================================== */

import { accessCodeForHeader } from './access-code';

/** 오류 종류 */
export type ApiErrorCode = 'unauthorized' | 'not_found' | 'conflict' | 'bad_request' | 'server' | 'network';

/** 백엔드 요청 오류 */
export class ApiError extends Error {
  /** HTTP 상태(네트워크 오류는 0) */
  readonly status: number;
  readonly code: ApiErrorCode;
  /**
   * 이미 만든 분석 건 id — 분석 요청이 업로드까지 끝낸 뒤 시작 요청이 5xx·네트워크·시간 초과로 실패했을 때만.
   * 시작이 실제로는 됐을 수 있으므로 화면은 이 id 의 상세(실제 상태)로 가는 길을 함께 보여 준다.
   */
  readonly analysisId: string | null;

  constructor(status: number, code: ApiErrorCode, message: string, analysisId: string | null = null) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.analysisId = analysisId;
  }
}

/** ApiError 인지 */
export function isApiError(error: unknown): error is ApiError {
  return error instanceof ApiError;
}

/** 오류 종류(ApiError 가 아니면 null) — 화면이 401·404 를 가를 때 */
export function apiErrorCode(error: unknown): ApiErrorCode | null {
  return isApiError(error) ? error.code : null;
}

/** 오류에 담긴 '이미 만든 분석 건' id(없으면 null) — 시작 결과를 모를 때 화면이 상세로 가는 길을 보여 준다 */
export function apiErrorAnalysisId(error: unknown): string | null {
  return isApiError(error) ? error.analysisId : null;
}

/* ---------- 기본 문구 ---------- */

export const MSG_UNAUTHORIZED = '접근 코드가 맞지 않습니다.';
export const MSG_NOT_FOUND = '분석 건을 찾을 수 없습니다.';
export const MSG_CONFLICT = '이미 시작한 분석입니다.';
export const MSG_BAD_REQUEST = '요청 형식이 올바르지 않습니다.';
export const MSG_SERVER = '서버 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.';
export const MSG_NETWORK = '서버에 연결하지 못했습니다. 네트워크 상태를 확인하고 다시 시도해 주세요.';
export const MSG_TIMEOUT = '서버 응답이 너무 늦습니다. 잠시 후 다시 시도해 주세요.';
export const MSG_BAD_RESPONSE = '서버 응답을 읽지 못했습니다. 잠시 후 다시 시도해 주세요.';

/** HTTP 상태 → 오류 종류 */
export function codeForStatus(status: number): ApiErrorCode {
  if (status === 401) return 'unauthorized';
  if (status === 404) return 'not_found';
  if (status === 409) return 'conflict';
  if (status >= 400 && status < 500) return 'bad_request';
  return 'server';
}

const DEFAULT_MESSAGE: Record<ApiErrorCode, string> = {
  unauthorized: MSG_UNAUTHORIZED,
  not_found: MSG_NOT_FOUND,
  conflict: MSG_CONFLICT,
  bad_request: MSG_BAD_REQUEST,
  server: MSG_SERVER,
  network: MSG_NETWORK,
};

/* ---------- 계약의 모양(T2 'API 계약') ---------- */

/** documents 행 */
export interface DocumentOut {
  id: string;
  filename: string;
  size_bytes: number;
  mime_type: string;
  upstage_file_id: string | null;
  created_at: string;
}

/** 분석 건 — AnalysisOut */
export interface AnalysisOut {
  id: string;
  name: string;
  status: string;
  upstage_job_id: string | null;
  error: string | null;
  /** analyses.result 에서 원본(response)을 뺀 것 */
  result: unknown | null;
  created_at: string;
  updated_at: string;
  documents: DocumentOut[];
  /** GET 응답에서만 — 이번 조회에서 본 Upstage 상태 */
  upstage_status: string | null;
  /** GET 응답에서만 — 이번 조회에서 Upstage 확인이 실패했을 때 */
  poll_error: string | null;
}

/** 서명 업로드 정보 — token·signed_url 은 기록·출력하지 않는다 */
export interface UploadTicket {
  bucket: string;
  path: string;
  token: string;
  signed_url: string;
}

/** POST /analyses 응답 */
export interface CreateAnalysisOut {
  analysis: AnalysisOut;
  upload: UploadTicket;
}

/** POST /analyses 요청 */
export interface CreateAnalysisIn {
  name: string;
  filename: string;
  size: number;
  mime_type: string;
}

/* ---------- 클라이언트 ---------- */

export interface ApiClientOptions {
  /** 기본 '/api/py' */
  baseUrl?: string;
  /** 기본 전역 fetch */
  fetch?: typeof fetch;
  /** 접근 코드(기본: 이 탭의 sessionStorage) */
  getAccessCode?: () => string;
  /** 요청 하나의 시간 제한(밀리초). 기본 60초(시작 요청은 Upstage 올리기까지 기다린다) */
  timeoutMs?: number;
}

export interface ApiClient {
  /** POST /api/py/analyses → 201 */
  createAnalysis(input: CreateAnalysisIn): Promise<CreateAnalysisOut>;
  /** POST /api/py/analyses/{id}/start → 200(실패해도 failed 행) */
  startAnalysis(id: string): Promise<AnalysisOut>;
  /** GET /api/py/analyses/{id} → 200 */
  getAnalysis(id: string): Promise<AnalysisOut>;
}

export const DEFAULT_BASE_URL = '/api/py';
export const DEFAULT_TIMEOUT_MS = 60_000;
/** 헤더에 넣을 수 있는 접근 코드 글자(공백 ~ '~') */
const PRINTABLE_ASCII = /^[\x20-\x7e]+$/;

/** 응답 본문의 detail(한국어 문장) — 없거나 문자열이 아니면 '' */
async function readDetail(response: Response): Promise<string> {
  try {
    const body: unknown = await response.json();
    if (body && typeof body === 'object' && 'detail' in body) {
      const detail = (body as { detail: unknown }).detail;
      if (typeof detail === 'string' && detail.trim()) return detail.trim();
    }
  } catch {
    /* JSON 이 아님(예: 백엔드가 꺼져 있어 Next 가 HTML 오류를 줌) */
  }
  return '';
}

export function createApiClient(options: ApiClientOptions = {}): ApiClient {
  const base = (options.baseUrl ?? DEFAULT_BASE_URL).replace(/\/+$/, '');
  const getCode = options.getAccessCode ?? (() => accessCodeForHeader());
  const timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS;
  const doFetch: typeof fetch = options.fetch ?? ((input, init) => fetch(input, init));

  async function request<T>(method: 'GET' | 'POST', path: string, body?: unknown): Promise<T> {
    const headers: Record<string, string> = { Accept: 'application/json' };
    const code = getCode().trim();
    // 헤더 값은 ASCII 만 보낼 수 있다(그 밖이면 fetch 가 TypeError) — 그런 코드는 맞을 수 없으므로 401 로 본다
    if (code && !PRINTABLE_ASCII.test(code)) throw new ApiError(401, 'unauthorized', MSG_UNAUTHORIZED);
    if (code) headers['X-Demo-Code'] = code;
    if (body !== undefined) headers['Content-Type'] = 'application/json';

    // 시간 제한은 헤더가 아니라 본문(오류 detail·정상 JSON)을 다 읽을 때까지 — 헤더 뒤 본문이 멈춰도 끝난다.
    // 시간이 되면 요청을 끊고(signal), 본문 읽기는 deadline 과 경주시켜 signal 을 무시하는 fetch 에서도 끝나게 한다.
    const controller = typeof AbortController === 'undefined' ? null : new AbortController();
    let timedOut = false;
    let expire: (error: ApiError) => void = () => {};
    const deadline = new Promise<never>((_, reject) => {
      expire = reject;
    });
    deadline.catch(() => {}); // 경주에 쓰이지 않은 채 끝나도 처리되지 않은 거절로 남지 않게
    const timer = setTimeout(() => {
      timedOut = true;
      expire(new ApiError(0, 'network', MSG_TIMEOUT));
      controller?.abort();
    }, timeoutMs);
    const timeoutOr = <V,>(work: Promise<V>): Promise<V> => Promise.race([work, deadline]);

    try {
      let response: Response;
      try {
        response = await timeoutOr(
          doFetch(base + path, {
            method,
            headers,
            body: body === undefined ? undefined : JSON.stringify(body),
            cache: 'no-store',
            credentials: 'same-origin',
            signal: controller?.signal,
          }),
        );
      } catch {
        throw new ApiError(0, 'network', timedOut ? MSG_TIMEOUT : MSG_NETWORK);
      }

      if (!response.ok) {
        const code = codeForStatus(response.status);
        const detail = await timeoutOr(readDetail(response));
        if (timedOut) throw new ApiError(0, 'network', MSG_TIMEOUT); // 본문 읽기가 끊겨 '' 가 된 경우
        throw new ApiError(response.status, code, detail || DEFAULT_MESSAGE[code]);
      }
      try {
        return (await timeoutOr(response.json())) as T;
      } catch {
        if (timedOut) throw new ApiError(0, 'network', MSG_TIMEOUT); // 본문을 읽는 중 시간 초과(AbortError 포함)
        throw new ApiError(response.status, 'server', MSG_BAD_RESPONSE);
      }
    } finally {
      clearTimeout(timer);
    }
  }

  const idPath = (id: string) => '/analyses/' + encodeURIComponent(id);

  return {
    createAnalysis: (input) => request<CreateAnalysisOut>('POST', '/analyses', input),
    startAnalysis: (id) => request<AnalysisOut>('POST', idPath(id) + '/start'),
    getAnalysis: (id) => request<AnalysisOut>('GET', idPath(id)),
  };
}
