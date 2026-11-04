/* ==========================================================================
   실제 분석 서비스 — AnalysisService 를 FastAPI 백엔드(T2 'API 계약')로 구현한다.
   - requestAnalysis: 파일 1개 → 만들기(POST /analyses) → 서명 업로드(Supabase) → 시작(POST …/start).
     시작이 409(이미 시작)여도, failed 행을 돌려줘도 id 를 돌려준다(상세 화면이 상태·오류를 보여 준다).
     성공하면 구독자에게 알린다(서버 목록에 새 분석이 생겼으므로 — 나눠 쓰던 목록 요청은 알리기 전에 뗀다).
     업로드까지 끝낸 뒤 시작이 5xx·네트워크·시간 초과로 실패하면 시작이 실제로는 됐을 수 있다(예: 502
     '분석 시작 결과를 확인하지 못했습니다…'). 그때도 알린 뒤, 그 id 를 담은 ApiError(analysisId)로 거절한다 —
     화면은 오류와 함께 '분석 건 확인하기'(상세 → 실제 상태)를 보여 준다. 만들기·업로드 실패는 알리지 않는다.
   - list: GET /analyses 하나(서버 목록 — 최근 100건, 누구나 같은 목록) → 가벼운 항목 매핑(mapping.ts readAnalysisList),
     서버 순서 그대로. 응답 모양이 틀리면 ApiError('서버 응답을 읽지 못했습니다…')로 거절한다(목록 화면의 불러오기 실패).
     같은 때의 list() 들(헤더 숫자 + 목록 화면)은 요청 하나를 나눠 쓴다(결과 객체는 부를 때마다 새로 만든다).
   - get: GET /analyses/{id} → 매핑. 404 → null, 그 밖 오류는 ApiError 를 던진다
     (진행 확인 폴링은 상세 화면 · 목록 화면이 3초마다 한다 — 조회할 때마다 백엔드가 Upstage 상태를 한 번 확인한다).
     같은 id 를 동시에 조회하면(헤더 · 목록 화면 · 상세 폴링 · 검토 동작 전 조회) 요청 하나를 나눠 쓴다.
   - 완료 한 번 알림: 조회(get · list · 검토 동작 전 조회 모두)에서 진행 중(대기 · 분석 중)으로 본 분석이 끝난 것(완료 · 일부 실패 ·
     실패)을 처음 보면 응답 하나당 한 번 알린다 — 헤더 '검토 필요' 숫자 · 목록이 다시 불러와 완료를 바로 반영한다.
     처음 본 분석 · 끝난 것으로 본 분석은 알리지 않는다. 요청마다 보낸 순번을 매겨, 분석마다 마지막으로 반영한 응답보다 먼저 보낸
     요청의 응답(늦게 온 옛 값)은 무시한다. 완료(done)는 되돌리지 않는다(백엔드가 바꾸지 않음). 실패는 다시 분석으로
     대기 · 분석 중이 될 수 있다(그 뒤의 완료도 한 번 알린다).
   - 쓰기(분석 요청 · 삭제 · 다시 분석 · 검토 동작) 뒤에는 알리기 전에 그 분석의 진행 중 조회와 나눠 쓰던 목록 요청을 뗀다 —
     쓰기 전에 시작한 요청은 쓰기 전 값을 줄 수 있으므로, 알림을 받은 구독자들은 새 요청을 시작하고 그 새 요청끼리 다시 나눠 쓴다
     (떼어 낸 옛 요청은 끝날 때 같은 항목 검사로 새 항목을 지우지 않는다).
   - retry(id) = POST /analyses/{id}/retry 본문 { actor: CONFIG.user.name }(docId 무시). 거절하지 않는다(목록이 .then 만 건다):
     200 · 행 상태 failed·partial → { ok: false, started: false, message: 그 행의 error(비면 '실패 이유를 받지 못했습니다.') }.
     200 · 그 밖 → { ok: true, started: true, message: '' } — 그 분석을 다시 '진행 중으로 본 것'으로 적는다(완료 한 번 알림이 다시
     걸린다 · 다시 분석 전에 보낸 조회의 늦은 '실패' 응답은 순번으로 무시). 결과 표는 응답이 객체 · 요청한 id · 알려진 분석 상태일
     때만 적용한다 — 그 밖 모양(null · 배열 · 스칼라 · status 없음 · 모르는 값 · 다른 id)은 { ok: false, started: false,
     message: '서버 응답을 읽지 못했습니다…' }(떼기 · 알림 한 번은 하고, 진행 중으로 적지 않는다). ApiError(409 · 404 · 5xx · 네트워크 · 시간 초과) →
     { ok: false, started: false, message: err.message }(404 면 gone: true). 응답을 받았으면(성공 · 실패 모두, 네트워크 오류 ·
     시간 초과 제외) 떼고 한 번 알린다.
   - deleteAnalysis(id) = DELETE /analyses/{id}(204). 성공하면 떼고 · 상태 기록을 지우고 · 한 번 알린다. 실패는 그 ApiError 로 거절
     (404 도 거절하되 떼고 · 지우고 · 알린다 — 목록에서 빠지게).
   - 검토 동작(setStatus · confirmMany · markFalsePositive · restore · reclassify · saveFindingMemo · saveMemo ·
     completeReview · reopenReview) = POST /analyses/{id}/review-actions 하나. 분석을 조회해(위와 같이 나눠 씀)
     화면 번호(Finding.id, D1-01)를 계약 id(Finding.live.id)로 바꿔 보낸다 — 없는 번호면 요청 없이 거절.
     처리자(actor)는 CONFIG.user.name, 빠진 사유 · 메모는 ''. 성공하면 바뀌었든 아니든 떼고 한 번 알린다(데모 write 와 같다 —
     훅이 저장 뒤 값을 새로 불러온다). 409(겹침 · 상태) · 404(지워짐 — 보내기 전 조회가 404 인 때도, 요청 없이 ApiError not_found)
     로 실패하면 그 분석의 진행 중 조회를 떼고 한 번 알린 뒤 같은 오류로 거절한다(화면이 최신 상태를 다시 불러온다).
     그 밖 실패는 떼지도 알리지도 않고 그 오류로 거절한다. reclassify 는 응답의 changed 를 돌려준다.
     confirmMany 는 빈 목록이면 요청 · 알림 없이 끝낸다.
   - pending = 조회한 분석의 미확인(open) 탐지 항목(검토사항 · 연결은 아직 없어 빈 목록). 없는 분석이면 빈 값.
   - 내보내기 파일(buildExport(id, format)): 분석을 조회해(위와 같이 나눠 씀) 없으면(404) 검토 동작처럼 ApiError(not_found)로(알림 한 번),
     보고서 대상(report-safe.ts isReportTarget — 완료 + 공통 계약 결과 + 검토 기록을 읽음)이 아니면 MSG_NO_REPORT 로 거절한다
     (화면은 기존 실패 문구를 보인다). 대상이면 원문 값을 지운 안전한 사본(reportSafeAnalysis)으로 공용 모듈(export-file.ts
     buildExportFile)이 파일을 만든다 — 브랜드는 늘 CONFIG.brandName(brand 인자는 쓰지 않는다 — 서버가 받는 파일 이름 꼴),
     생성 시각은 서울 시각, live: true. 데모 코어 · 샘플은 import 하지 않는다.
   - 내보내기 기록(logExport) = 검토 동작과 같은 보내기(sendReview) 하나 — 본문 { type: 'log_export', actor, format, size, state,
     file_name }(크기 = file.size, 이름 = file.name). 보내기 전 조회는 하지 않는다. 성공 · 409 · 404 · 그 밖 실패의 떼기 · 알림은
     검토 동작과 같다(성공하면 보고서의 검토 기록 구역이 다시 그려진다).
   - 검토사항(resolveItem · reopenItem) · 연결 판단(decideLink)은 아직 백엔드가 없다 —
     '실제 분석에서는 아직 지원하지 않는 기능입니다.' 로 거절한다.
   - 분석 완료 이벤트(ServiceEvent 'done')는 보내지 않는다(탐지 0건 완료 토스트가 오해를 준다) — 위의 알림은 모두
     이벤트 없는 listener() 다.
   - 분석 데이터를 메모리 · 브라우저 저장소에 두지 않는다(목록은 서버가 준다) — 조회 결과는 요청마다 새로 만든 값이다.
     메모리에는 진행 중 요청과 분석별 마지막 상태(완료 알림용)만 둔다.
   - 실제 분석 전용 통로(LiveExtras — 화면은 getLiveExtras()/useLiveExtras() 로 받는다):
     loadFile(id) = 부를 때마다 GET …/file 로 새 서명 주소(10분 유효)를 받고 그 주소에서 내용을 받는다
     (주소 검사·크기 한도·시간 제한·고정 오류 문구는 file-download.ts). 캐시는 화면이 한다.
     /file 요청 오류도 경계에서 새 ApiError 로 바꾼다(fileInfoError — 401·404 는 안전한 detail 만, 그 밖은 고정 문구).
     loadStages(id) = GET …/{id}?include=stages 의 result.stages(배열이 아니면 null). 404 는 null 이 아니라
     ApiError(not_found, 백엔드 detail)로 거절한다 — 화면이 문구를 보인다.
   ========================================================================== */

import { CONFIG } from '@/config/app';
import type { AnalysisService, LiveExtras, LiveFile, Pending, RequestAnalysisInput, RetryResult, ServiceEvent } from '../analysis-service';
import { buildExportFile } from '../export-file';
import { isReportTarget, reportSafeAnalysis } from '../report-safe';
import type { Analysis, UploadFile } from '../types';
import {
  ApiError,
  MSG_BAD_RESPONSE,
  MSG_NETWORK,
  createApiClient,
  isApiError,
  type AnalysisListOut,
  type AnalysisOut,
  type ApiClient,
  type ReviewActionIn,
  type ReviewActionOut,
} from './client';
import { downloadFile, fileInfoError } from './file-download';
import { readAnalysisList, seoulNow, toAnalysis } from './mapping';
import { UploadConfigError, uploadWithSupabase, type Uploader } from './upload';

export const MSG_ONE_FILE = '실제 분석에는 파일 1개를 올려 주세요.';
export const MSG_UNSUPPORTED_FORMAT = 'PDF·PNG·JPEG 파일만 분석할 수 있습니다.';
export const MSG_UPLOAD_FAILED = '파일을 올리지 못했습니다. 잠시 후 새 분석으로 다시 시도해 주세요.';
export const MSG_UNSUPPORTED = '실제 분석에서는 아직 지원하지 않는 기능입니다.';
/** 검토 동작 — 조회한 분석이 없을 때(요청하지 않는다) */
export const MSG_NO_ANALYSIS = '분석 건을 찾을 수 없습니다.';
/** 검토 동작 — 화면 번호의 탐지 항목이 지금 분석에 없을 때(요청하지 않는다) */
export const MSG_NO_FINDING = '탐지 항목을 찾을 수 없습니다.';
/** 내보내기 — 보고서 대상이 아닌 분석(대기 · 분석 중 · 실패 · 옛 형식 · 검토 기록을 읽지 못함). 화면은 기존 실패 문구를 보인다 */
export const MSG_NO_REPORT = '보고서를 만들 수 없는 분석입니다.';
/** 다시 분석이 시작하다 실패했는데 이유(error)가 비었을 때 — 실제 분석 실패 띠와 같은 문구 */
export const MSG_NO_REASON = '실패 이유를 받지 못했습니다.';

const MIME_BY_EXT: Record<string, string> = {
  pdf: 'application/pdf',
  png: 'image/png',
  jpg: 'image/jpeg',
  jpeg: 'image/jpeg',
};

/** 파일 이름의 확장자 → MIME 형식(백엔드가 받는 셋만). 모르면 '' */
export function mimeForName(name: string): string {
  const m = /\.([a-z0-9]+)$/i.exec(name);
  return (m && MIME_BY_EXT[m[1].toLowerCase()]) || '';
}

export interface ApiServiceDeps {
  /** 백엔드 클라이언트(기본: 같은 출처 /api/py) */
  client?: ApiClient;
  /** 서명 업로드(기본: supabase-js) */
  upload?: Uploader;
  /** 원본 파일(서명 다운로드 주소)을 받을 fetch(기본: 전역 fetch) — 테스트용 */
  fileFetch?: typeof fetch;
  /** 원본 파일 받기 시간 제한(밀리초, 기본 60초 — 본문을 다 읽을 때까지) — 테스트용 */
  fileTimeoutMs?: number;
}

/** 실제 분석 서비스 — 서비스 인터페이스 + 실제 분석 전용 통로 */
export type ApiService = AnalysisService & LiveExtras;

/** 이 모듈이 만든 실제 분석 서비스 — getLiveExtras 의 판별용 */
const apiServices = new WeakSet<object>();

/** 실제 분석 서비스인지 확인한다(이 모듈이 만든 객체만 true) */
export function isApiService(service: unknown): service is ApiService {
  return typeof service === 'object' && service !== null && apiServices.has(service);
}

const str = (v: unknown): string => (typeof v === 'string' ? v : '');
const isObj = (v: unknown): v is Record<string, unknown> => !!v && typeof v === 'object' && !Array.isArray(v);

type Listener = (event?: ServiceEvent) => void;

const EMPTY_PENDING = (): Pending => ({ openF: [], openI: [], openL: [], any: false });

/** 끝난 분석 상태 */
const SETTLED_STATUSES: ReadonlySet<string> = new Set(['done', 'partial', 'failed']);

/** 알려진 분석 상태(다시 분석 응답 검사) */
const KNOWN_STATUSES: ReadonlySet<string> = new Set(['queued', 'running', 'done', 'partial', 'failed']);

const unsupported = (): Promise<never> => Promise.reject(new Error(MSG_UNSUPPORTED));

/** 검토 동작 본문 — 종류별 필드(처리자는 보낼 때 붙인다) */
type WithoutActor<T> = T extends unknown ? Omit<T, 'actor'> : never;
type ReviewBody = WithoutActor<ReviewActionIn>;

/** 나눠 쓰는 요청 하나 — ticket = 보낸 순번(늦게 온 옛 응답을 가를 때) */
interface Shared<T> {
  promise: Promise<T>;
  ticket: number;
}

/** 분석 하나를 마지막으로 본 상태 */
interface Seen {
  status: string;
  /** 끝난 상태(완료 · 일부 실패 · 실패)인지 */
  settled: boolean;
  /** 그 상태를 준 요청의 순번 */
  ticket: number;
}

/** 화면 번호 → 계약 id(그 분석에 없으면 null) */
function contractId(a: Analysis, fid: string): string | null {
  const f = a.findings.find((x) => x.id === fid);
  const id = f?.live?.id;
  return typeof id === 'string' ? id : null;
}

/** 요청할 파일 하나 — 정확히 1개이고 브라우저 File 이 있어야 한다 */
function pickFile(files: readonly UploadFile[] | undefined): File {
  const list = files ?? [];
  const file = list.length === 1 ? list[0].file : undefined;
  if (!file) throw new Error(MSG_ONE_FILE);
  return file;
}

export function createApiService(deps: ApiServiceDeps = {}): ApiService {
  const client = deps.client ?? createApiClient();
  const upload = deps.upload ?? uploadWithSupabase;
  const listeners = new Set<Listener>();
  /** 분석별 진행 중 GET */
  const inflight = new Map<string, Shared<AnalysisOut>>();
  /** 진행 중 목록 GET */
  let listInflight: Shared<AnalysisListOut> | null = null;
  /** 요청 순번 */
  let ticketSeq = 0;

  const emit = () => {
    for (const listener of Array.from(listeners)) {
      if (!listeners.has(listener)) continue;
      try {
        listener();
      } catch (err) {
        queueMicrotask(() => {
          throw err;
        });
      }
    }
  };

  /** GET 하나 — 같은 id 로 보낸 요청이 진행 중이면 그 요청을 나눠 쓴다 */
  const fetchOne = (id: string): Shared<AnalysisOut> => {
    const running = inflight.get(id);
    if (running) return running;
    const ticket = ++ticketSeq;
    const promise = client.getAnalysis(id).finally(() => {
      if (inflight.get(id)?.promise === promise) inflight.delete(id);
    });
    const entry: Shared<AnalysisOut> = { ticket, promise };
    inflight.set(id, entry);
    return entry;
  };

  /** 목록 GET — 진행 중이면 그 요청을 나눠 쓴다 */
  const fetchList = (): Shared<AnalysisListOut> => {
    if (listInflight) return listInflight;
    const ticket = ++ticketSeq;
    const promise = client.listAnalyses().finally(() => {
      if (listInflight?.promise === promise) listInflight = null;
    });
    listInflight = { ticket, promise };
    return listInflight;
  };

  /** 쓰기 뒤 — 그 분석의 진행 중 GET 과 진행 중 목록 GET 을 나눠 쓰지 않게 뗀다 */
  const detach = (id: string | null) => {
    if (id !== null) inflight.delete(id);
    listInflight = null;
  };

  /** 분석별 마지막으로 본 상태 */
  const seen = new Map<string, Seen>();
  /**
   * ticket 번 요청이 준 상태를 적고, 진행 중으로 본 분석이 이번에 끝났으면 true.
   * 마지막으로 적은 것보다 먼저 보낸 요청의 응답(늦게 온 옛 값)과 완료 뒤의 다른 상태는 무시한다.
   */
  const noteSettled = (id: string, status: string, ticket: number): boolean => {
    const was = seen.get(id);
    if (was && (ticket < was.ticket || was.status === 'done')) return false;
    const now = SETTLED_STATUSES.has(status);
    seen.set(id, { status, settled: now, ticket });
    return was !== undefined && !was.settled && now;
  };

  /**
   * 조회 — 404 는 null. 진행 중으로 본 분석이 끝난 것을 보면(상세 · 목록 화면의 3초 조회 등) 한 번 알린다 — 헤더 '검토 필요'
   * 숫자·목록이 다시 불러와 완료(검토 필요)를 바로 반영하게(데모는 진행이 바뀔 때 알린다). 처음 본 분석은 알리지 않는다.
   */
  const getOrNull = async (id: string): Promise<Analysis | null> => {
    const req = fetchOne(id);
    let analysis: Analysis;
    try {
      analysis = toAnalysis(await req.promise);
    } catch (err) {
      if (isApiError(err) && err.code === 'not_found') return null;
      throw err;
    }
    if (noteSettled(id, analysis.status, req.ticket)) emit();
    return analysis;
  };

  /** 검토 동작이 409 · 404 로 실패했을 때 — 진행 중 조회를 떼고 한 번 알린다(화면이 최신 상태를 다시 불러오게) */
  const refreshAfterConflict = (id: string, err: unknown) => {
    if (isApiError(err) && (err.code === 'conflict' || err.code === 'not_found')) {
      detach(id);
      emit();
    }
  };

  /** 검토 동작에 쓸 분석 — 없으면(404) 요청 없이 ApiError(not_found)로 거절(알림 한 번), 그 밖 조회 오류는 그대로 */
  const reviewTarget = async (id: string): Promise<Analysis> => {
    const a = await getOrNull(id);
    if (!a) {
      const err = new ApiError(404, 'not_found', MSG_NO_ANALYSIS);
      refreshAfterConflict(id, err);
      throw err;
    }
    return a;
  };

  /** 화면 번호 하나 → 계약 id. 없으면 요청 없이 거절 */
  const findingTarget = async (id: string, fid: string): Promise<string> => {
    const key = contractId(await reviewTarget(id), fid);
    if (key === null) throw new Error(MSG_NO_FINDING);
    return key;
  };

  /**
   * 검토 동작 하나를 보내고, 성공하면(바뀌었든 아니든) 한 번 알린다. 409 · 404 면 떼고 알린 뒤 그 오류로, 그 밖 실패는
   * 알리지 않고 그 오류로 거절.
   */
  const sendReview = async (id: string, body: ReviewBody): Promise<ReviewActionOut> => {
    let out: ReviewActionOut;
    try {
      out = await client.reviewAction(id, { ...body, actor: CONFIG.user.name } as ReviewActionIn);
    } catch (err) {
      refreshAfterConflict(id, err);
      throw err;
    }
    detach(id);
    emit();
    return out;
  };

  /** /file 의 mime_type 이 비었을 때 — 분석의 파일 형식(documents 첫 행), 그것도 없으면 파일 이름의 확장자 */
  const fallbackMime = async (id: string, filename: string): Promise<string> => {
    try {
      const out = await fetchOne(id).promise;
      const first: unknown = Array.isArray(out?.documents) ? out.documents[0] : undefined;
      const mime = isObj(first) ? str(first.mime_type).trim() : '';
      if (mime) return mime;
    } catch {
      /* 형식을 모를 뿐 — 이름으로 짐작한다 */
    }
    return mimeForName(filename);
  };

  const service: ApiService = {
    async list() {
      const req = fetchList();
      const list = readAnalysisList(await req.promise);
      if (!list) throw new ApiError(200, 'server', MSG_BAD_RESPONSE);
      // 응답 하나당 알림은 한 번 — 같은 응답을 나눠 쓴 다른 list() 는 이미 적힌 상태를 보고 알리지 않는다
      let finished = false;
      for (const a of list) {
        if (noteSettled(a.id, a.status, req.ticket)) finished = true;
      }
      if (finished) emit();
      return list;
    },

    get: (id) => getOrNull(id),

    async pending(id) {
      const a = await getOrNull(id);
      if (!a) return EMPTY_PENDING();
      const openF = a.findings.filter((f) => f.status === 'open');
      return { openF, openI: [], openL: [], any: openF.length > 0 };
    },

    sampleFiles: async () => [],

    async requestAnalysis(input: RequestAnalysisInput) {
      const file = pickFile(input.files);
      const mime = mimeForName(file.name);
      if (!mime) throw new Error(MSG_UNSUPPORTED_FORMAT);
      const step = input.onProgress ?? (() => {});

      step('create');
      const created = await client.createAnalysis({ name: (input.name ?? '').trim(), filename: file.name, size: file.size, mime_type: mime });
      const id = created.analysis.id;

      step('upload');
      try {
        await upload(created.upload, file, mime);
      } catch (err) {
        if (err instanceof UploadConfigError) throw err;
        throw new Error(MSG_UPLOAD_FAILED);
      }

      step('start');
      try {
        await client.startAnalysis(id); // 실패해도 200 failed 행 — 상세 화면이 오류를 보여 준다
      } catch (err) {
        if (isApiError(err) && err.code === 'conflict') {
          // 409 = 이미 시작함 → 그대로 진행
        } else if (isApiError(err) && (err.code === 'server' || err.code === 'network')) {
          // 시작 결과를 모른다(5xx·네트워크·시간 초과) — 만든 분석으로 갈 길을 남기고 오류로 끝낸다(성공으로 보이지 않게)
          detach(id);
          emit();
          throw new ApiError(err.status, err.code, err.message, id);
        } else {
          throw err;
        }
      }

      detach(id);
      emit();
      return id;
    },

    async retry(id): Promise<RetryResult> {
      let out: AnalysisOut;
      try {
        out = await client.retryAnalysis(id, { actor: CONFIG.user.name });
      } catch (err) {
        const e = isApiError(err) ? err : new ApiError(0, 'network', MSG_NETWORK);
        if (e.code !== 'network') {
          detach(id);
          emit();
        }
        return e.code === 'not_found' ? { ok: false, started: false, gone: true, message: e.message } : { ok: false, started: false, message: e.message };
      }
      detach(id);
      // 응답 모양 검사 — 객체 · 요청한 id · 알려진 분석 상태일 때만 결과 표를 적용한다. 그 밖(null · 배열 · 스칼라 · status 없음 ·
      // 모르는 값 · 다른 id)은 응답을 읽지 못한 것 — 알림은 한 번 하되 '진행 중으로 본 것'으로 적지 않는다
      const row: unknown = out;
      const status = isObj(row) ? str(row.status) : '';
      if (!isObj(row) || str(row.id) !== id || !KNOWN_STATUSES.has(status)) {
        emit();
        return { ok: false, started: false, message: MSG_BAD_RESPONSE };
      }
      const ticket = ++ticketSeq;
      if (status === 'failed' || status === 'partial') {
        seen.set(id, { status, settled: true, ticket });
        emit();
        const reason = str(out.error);
        return { ok: false, started: false, message: reason.trim() ? reason : MSG_NO_REASON };
      }
      // 다시 '진행 중으로 본 것' — 완료 한 번 알림이 다시 걸린다. 이보다 먼저 보낸 조회의 늦은 응답은 무시된다(순번)
      seen.set(id, { status, settled: false, ticket });
      emit();
      return { ok: true, started: true, message: '' };
    },

    async deleteAnalysis(id) {
      try {
        await client.deleteAnalysis(id);
      } catch (err) {
        if (isApiError(err) && err.code === 'not_found') {
          detach(id);
          seen.delete(id);
          emit();
        }
        throw err;
      }
      detach(id);
      seen.delete(id);
      emit();
    },

    /* ---------- 검토 동작(POST …/review-actions) ---------- */

    async setStatus(id, fid, status, reason) {
      const findingId = await findingTarget(id, fid);
      await sendReview(id, { type: 'set_status', finding_id: findingId, status, reason: reason ?? '' });
    },

    async confirmMany(id, fids) {
      if (!fids.length) return;
      const a = await reviewTarget(id);
      const ids = new Set<string>(); // 넣은 순서대로 · 중복 없이(백엔드는 중복을 400 으로 거절)
      for (const fid of fids) {
        const key = contractId(a, fid);
        if (key === null) throw new Error(MSG_NO_FINDING);
        ids.add(key);
      }
      await sendReview(id, { type: 'confirm_many', finding_ids: [...ids] });
    },

    async markFalsePositive(id, fid, reasonType, note) {
      const findingId = await findingTarget(id, fid);
      await sendReview(id, { type: 'mark_false_positive', finding_id: findingId, reason_type: reasonType, note });
    },

    async restore(id, fid, note) {
      const findingId = await findingTarget(id, fid);
      await sendReview(id, { type: 'restore', finding_id: findingId, note: note ?? '' });
    },

    async reclassify(id, fid, patch, reason) {
      const findingId = await findingTarget(id, fid);
      const body: Extract<ReviewBody, { type: 'reclassify' }> = { type: 'reclassify', finding_id: findingId, reason };
      if (patch.cat !== undefined) body.category = patch.cat;
      if (patch.subject !== undefined) body.subject = patch.subject;
      if (patch.exposure !== undefined) body.exposure = patch.exposure;
      const out = await sendReview(id, body);
      return isObj(out) && out.changed === true;
    },

    async saveFindingMemo(id, fid, text) {
      const findingId = await findingTarget(id, fid);
      await sendReview(id, { type: 'save_finding_memo', finding_id: findingId, text });
    },

    async saveMemo(id, text) {
      await reviewTarget(id);
      await sendReview(id, { type: 'save_memo', text });
    },

    async completeReview(id, note) {
      await reviewTarget(id);
      await sendReview(id, { type: 'complete_review', note });
    },

    async reopenReview(id, reason) {
      await reviewTarget(id);
      await sendReview(id, { type: 'reopen_review', reason });
    },

    /* ---------- 내보내기(파일은 화면 쪽 공용 모듈 · 기록은 POST …/review-actions log_export) ---------- */

    async buildExport(id, format) {
      const a = await reviewTarget(id); // 없으면(404) 요청 없이 ApiError(not_found) — 떼고 한 번 알린다(화면이 목록으로)
      if (!isReportTarget(a)) throw new Error(MSG_NO_REPORT);
      return buildExportFile(reportSafeAnalysis(a), format, { brand: CONFIG.brandName, generatedAt: seoulNow(), live: true });
    },

    async logExport(id, file, state) {
      await sendReview(id, { type: 'log_export', format: file.format, size: file.size, state, file_name: file.name });
    },

    /* ---------- 아직 백엔드가 없는 기능 ---------- */
    resolveItem: unsupported,
    reopenItem: unsupported,
    decideLink: unsupported,

    subscribe(listener) {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },

    /* ---------- 실제 분석 전용(LiveExtras) ---------- */

    async loadFile(id: string): Promise<LiveFile> {
      let info: unknown;
      try {
        info = await client.getFile(id);
      } catch (err) {
        // 경계 — 늘 새 ApiError. 401·404 는 안전한 detail 만 보존, 그 밖은 고정 문구(원래 오류·cause·스택은 버림)
        throw fileInfoError(err);
      }
      const o = isObj(info) ? info : {};
      // 서명 주소는 여기서만 쓰고 기록하지 않는다
      const bytes = await downloadFile(o.url, { fetch: deps.fileFetch, timeoutMs: deps.fileTimeoutMs });
      const filename = str(o.filename);
      const mime = str(o.mime_type).trim() || (await fallbackMime(id, filename));
      return { bytes, mime, filename };
    },

    async loadStages(id: string): Promise<unknown[] | null> {
      const out: unknown = await client.getAnalysis(id, { includeStages: true }); // 404 도 ApiError 로 거절
      const result = isObj(out) ? out.result : null;
      return isObj(result) && Array.isArray(result.stages) ? result.stages : null;
    },
  };
  apiServices.add(service);
  return service;
}
