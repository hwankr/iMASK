/* ==========================================================================
   FastAPI 백엔드 클라이언트 — fetch 래퍼(T2 'API 계약' 그대로)
   - 기본 주소는 같은 출처의 '/api/py'(로컬은 Next rewrites → uvicorn, 배포는 같은 Vercel 프로젝트의 Python 함수).
   - 사용자 지정 헤더는 붙이지 않는다(Accept · Content-Type 만). 백엔드는 접근 코드를 받지 않는다(2026-11-03 없앰).
   - 오류는 ApiError { status, code, message }. message 는 서버가 준 detail(한국어) 또는 기본 문구.
     네트워크 오류·시간 초과도 한국어 문구의 ApiError(code 'network', status 0)다.
   - 시간 제한(기본 60초)은 응답 헤더가 아니라 본문을 다 읽을 때까지 걸린다.
   - getFile 이 주는 서명 다운로드 주소는 권한이다 — 이 파일도, 받는 쪽(file-download.ts)도 기록·출력하지 않는다.
   - reviewAction = 검토 동작 하나(POST /analyses/{id}/review-actions, JSON 본문 — 항목 id 는 어떤 문자든 올 수 있어
     주소가 아니라 본문에 담는다). 시간 제한 · 오류 모양은 다른 요청과 같다(413 은 bad_request).
   - AnalysisOut.review(검토 기록 블록)는 바깥 값이라 unknown 으로 두고 매핑(mapping.ts)이 방어적으로 읽는다.
   - listAnalyses = GET /analyses(서버 목록 — 최근 100건, 가벼운 항목). 응답 모양은 매핑(mapping.ts readAnalysisList)이 검사한다.
   - deleteAnalysis = DELETE /analyses/{id} → 204. 204 는 본문을 읽지 않는다(빈 본문을 JSON 으로 읽다 '응답을 읽지 못함'이 되지 않게).
   - retryAnalysis = POST /analyses/{id}/retry(본문 { actor }) → 200 다시 시작한(또는 시작하다 실패한) 분석.
   ========================================================================== */

import type { Exposure, FpReason, InfoCategory, InfoSubject } from '@/display/rules';

/** 오류 종류 */
export type ApiErrorCode = 'not_found' | 'conflict' | 'bad_request' | 'server' | 'network';

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

/** 오류 종류(ApiError 가 아니면 null) — 화면이 404 등을 가를 때 */
export function apiErrorCode(error: unknown): ApiErrorCode | null {
  return isApiError(error) ? error.code : null;
}

/** 오류에 담긴 '이미 만든 분석 건' id(없으면 null) — 시작 결과를 모를 때 화면이 상세로 가는 길을 보여 준다 */
export function apiErrorAnalysisId(error: unknown): string | null {
  return isApiError(error) ? error.analysisId : null;
}

/* ---------- 기본 문구 ---------- */

export const MSG_NOT_FOUND = '분석 건을 찾을 수 없습니다.';
export const MSG_CONFLICT = '이미 시작한 분석입니다.';
export const MSG_BAD_REQUEST = '요청 형식이 올바르지 않습니다.';
export const MSG_SERVER = '서버 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.';
export const MSG_NETWORK = '서버에 연결하지 못했습니다. 네트워크 상태를 확인하고 다시 시도해 주세요.';
export const MSG_TIMEOUT = '서버 응답이 너무 늦습니다. 잠시 후 다시 시도해 주세요.';
export const MSG_BAD_RESPONSE = '서버 응답을 읽지 못했습니다. 잠시 후 다시 시도해 주세요.';

/** HTTP 상태 → 오류 종류 */
export function codeForStatus(status: number): ApiErrorCode {
  if (status === 404) return 'not_found';
  if (status === 409) return 'conflict';
  if (status >= 400 && status < 500) return 'bad_request';
  return 'server';
}

const DEFAULT_MESSAGE: Record<ApiErrorCode, string> = {
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
  /** 마지막으로 분석을 시작한 시각(시작 선점 · 다시 분석 요청). 시작 전이거나 옛 분석이면 null. 옛 백엔드는 키가 없다 */
  started_at?: string | null;
  documents: DocumentOut[];
  /** GET 응답에서만 — 이번 조회에서 본 Upstage 상태 */
  upstage_status: string | null;
  /** GET 응답에서만 — 이번 조회에서 Upstage 확인이 실패했을 때 */
  poll_error: string | null;
  /**
   * 검토 기록(상태 · 메모 · 항목별 값 · 이력) — 검토할 수 있는 분석이면 객체, 그 밖이거나 읽지 못했으면 null.
   * 옛 백엔드는 키가 없다. 모양을 믿지 않는다(mapping.ts 가 목록 밖 · 타입 틀린 값을 버린다).
   */
  review?: unknown;
}

/** 목록 항목의 올린 파일(키 셋만) */
export interface ListDocumentOut {
  filename: string;
  size_bytes: number;
  mime_type: string;
}

/**
 * GET /analyses 항목 — 가벼운 분석(결과 JSON · 작업 번호 · 저장 경로 없음).
 * risk_level = result.summary.risk_level(문자열이 아니면 null), review = 검토 상태(done · needed · none).
 */
export interface AnalysisListItemOut {
  id: string;
  name: string;
  status: string;
  error: string | null;
  created_at: string;
  updated_at: string;
  started_at: string | null;
  documents: ListDocumentOut[];
  risk_level: string | null;
  review: string;
}

/** GET /analyses 응답 — 바깥 값이라 모양을 믿지 않는다(mapping.ts 가 검사) */
export interface AnalysisListOut {
  analyses: AnalysisListItemOut[];
}

/** POST /analyses/{id}/retry 본문 */
export interface RetryIn {
  actor: string;
}

/** 검토 동작 요청 공통 — actor = 처리자 이름(화면 CONFIG.user.name) */
interface ReviewActionBase {
  actor: string;
}

/**
 * POST /analyses/{id}/review-actions 본문 — 종류(type)마다 정확히 이 필드만(모두 필수, reclassify 의 분류 셋만 선택).
 * finding_id(s) = 계약 id(Finding.live.id — 화면 번호 D1-01 이 아니다).
 */
export type ReviewActionIn =
  | (ReviewActionBase & { type: 'set_status'; finding_id: string; status: 'open' | 'confirmed'; reason: string })
  | (ReviewActionBase & { type: 'confirm_many'; finding_ids: string[] })
  | (ReviewActionBase & { type: 'mark_false_positive'; finding_id: string; reason_type: FpReason; note: string })
  | (ReviewActionBase & { type: 'restore'; finding_id: string; note: string })
  | (ReviewActionBase & {
      type: 'reclassify';
      finding_id: string;
      category?: InfoCategory | null;
      subject?: InfoSubject | null;
      exposure?: Exposure | null;
      reason: string;
    })
  | (ReviewActionBase & { type: 'save_finding_memo'; finding_id: string; text: string })
  | (ReviewActionBase & { type: 'save_memo'; text: string })
  | (ReviewActionBase & { type: 'complete_review'; note: string })
  | (ReviewActionBase & { type: 'reopen_review'; reason: string });

/** 검토 동작 응답 — 갱신된 분석(조회와 같은 모양) + 실제로 바뀌었는지(분류 수정에서 바뀐 값이 없으면 false) */
export interface ReviewActionOut {
  analysis: AnalysisOut;
  changed: boolean;
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

/**
 * GET /analyses/{id}/file 응답 — 원본 파일의 서명 다운로드 주소(10분 유효).
 * url 은 권한이 담긴 주소다 — 기록·출력·오류 문구에 넣지 않는다.
 */
export interface FileOut {
  url: string;
  mime_type: string;
  filename: string;
}

/** getAnalysis 선택 */
export interface GetAnalysisOptions {
  /** 참이면 ?include=stages — result.stages(단계별 JSON)를 함께 받는다(기본 응답에는 없다) */
  includeStages?: boolean;
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
  /** 요청 하나의 시간 제한(밀리초). 기본 60초(시작 요청은 Upstage 올리기까지 기다린다) */
  timeoutMs?: number;
}

export interface ApiClient {
  /** POST /api/py/analyses → 201 */
  createAnalysis(input: CreateAnalysisIn): Promise<CreateAnalysisOut>;
  /** POST /api/py/analyses/{id}/start → 200(실패해도 failed 행) */
  startAnalysis(id: string): Promise<AnalysisOut>;
  /** GET /api/py/analyses/{id}(includeStages 면 ?include=stages) → 200 */
  getAnalysis(id: string, options?: GetAnalysisOptions): Promise<AnalysisOut>;
  /** GET /api/py/analyses/{id}/file → 200 서명 다운로드 주소 */
  getFile(id: string): Promise<FileOut>;
  /** POST /api/py/analyses/{id}/review-actions → 200 갱신된 분석 + changed */
  reviewAction(id: string, action: ReviewActionIn): Promise<ReviewActionOut>;
  /** GET /api/py/analyses → 200 { analyses: [...] }(서버 기본 100건 — limit 은 보내지 않는다) */
  listAnalyses(): Promise<AnalysisListOut>;
  /** DELETE /api/py/analyses/{id} → 204(본문 없음) */
  deleteAnalysis(id: string): Promise<void>;
  /** POST /api/py/analyses/{id}/retry(본문 { actor }) → 200 다시 시작한 분석(시작하다 실패하면 failed 행) */
  retryAnalysis(id: string, body: RetryIn): Promise<AnalysisOut>;
}

export const DEFAULT_BASE_URL = '/api/py';
export const DEFAULT_TIMEOUT_MS = 60_000;

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
  const timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS;
  const doFetch: typeof fetch = options.fetch ?? ((input, init) => fetch(input, init));

  async function request<T>(method: 'GET' | 'POST' | 'DELETE', path: string, body?: unknown): Promise<T> {
    const headers: Record<string, string> = { Accept: 'application/json' };
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
      // 204 = 본문 없음(삭제) — 읽지 않는다
      if (response.status === 204) return undefined as T;
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
    getAnalysis: (id, options) => request<AnalysisOut>('GET', idPath(id) + (options?.includeStages ? '?include=stages' : '')),
    getFile: (id) => request<FileOut>('GET', idPath(id) + '/file'),
    reviewAction: (id, action) => request<ReviewActionOut>('POST', idPath(id) + '/review-actions', action),
    listAnalyses: () => request<AnalysisListOut>('GET', '/analyses'),
    deleteAnalysis: (id) => request<void>('DELETE', idPath(id)),
    retryAnalysis: (id, body) => request<AnalysisOut>('POST', idPath(id) + '/retry', body),
  };
}
