/* ==========================================================================
   실제 분석 서비스 — AnalysisService 를 FastAPI 백엔드(T2 'API 계약')로 구현한다.
   - requestAnalysis: 파일 1개 → 만들기(POST /analyses) → 서명 업로드(Supabase) → 시작(POST …/start).
     시작이 409(이미 시작)여도, failed 행을 돌려줘도 id 를 돌려준다(상세 화면이 상태·오류를 보여 준다).
     성공하면 id 를 이 탭의 목록(sessionStorage)에 넣고 구독자에게 알린다.
     업로드까지 끝낸 뒤 시작이 5xx·네트워크·시간 초과로 실패하면 시작이 실제로는 됐을 수 있다(예: 502
     '분석 시작 결과를 확인하지 못했습니다…'). 그때도 id 를 목록에 넣고 알린 뒤, 그 id 를 담은 ApiError
     (analysisId)로 거절한다 — 화면은 오류와 함께 '분석 건 확인하기'(상세 → 실제 상태)를 보여 준다.
     만들기·업로드 실패는 id 를 넣지 않는다(파일이 올라가지 않아 시작될 수 없음).
   - get: GET /analyses/{id} → 매핑. 404 → null, 그 밖 오류는 ApiError 를 던진다. 알림은 보내지 않는다
     (진행 확인 폴링은 상세 화면이 3초마다 한다 — 조회할 때마다 백엔드가 Upstage 상태를 한 번 확인한다).
   - list: 접근 코드가 없으면 [](요청 없음). 있으면 이 탭에서 만든 id 들을 조회해 요청 시각 최신순.
     404 는 목록에서 빼고 건너뛴다. 401 등 그 밖 오류는 던진다.
   - 같은 id 를 같은 접근 코드로 동시에 조회하면(헤더 숫자 + 목록 화면 + 상세 폴링) 요청 하나를 나눠 쓴다.
     접근 코드를 고친 뒤의 조회는 이전 코드의 진행 중 요청에 합치지 않고 새로 보낸다.
   - 검토·내보내기·다시 분석은 아직 백엔드가 없다 — '실제 분석에서는 아직 지원하지 않는 기능입니다.' 로 거절한다.
     다만 retry 는 거절하지 않고 { ok: false, message: 그 문구 } 로 끝낸다 — 목록 화면(그대로 둠)의 '재시도'가
     거절을 받지 않아 처리되지 않은 오류가 되므로, 실패 결과로 돌려주면 기존 토스트가 이유를 보여 준다.
   - 분석 완료 이벤트(ServiceEvent 'done')는 보내지 않는다(탐지 0건 완료 토스트가 오해를 준다).
   - 데이터를 메모리에 두지 않는다(id 목록만 sessionStorage) — 조회 결과는 요청마다 새로 만든 값이다.
   ========================================================================== */

import type { AnalysisService, Pending, RequestAnalysisInput, ServiceEvent } from '../analysis-service';
import type { Analysis, UploadFile } from '../types';
import { accessCodeForHeader, browserSessionStorage, type KeyValueStorage } from './access-code';
import { ApiError, createApiClient, isApiError, type AnalysisOut, type ApiClient } from './client';
import { toAnalysis } from './mapping';
import { addSessionId, readSessionIds, removeSessionIds } from './session-list';
import { UploadConfigError, uploadWithSupabase, type Uploader } from './upload';

export const MSG_ONE_FILE = '실제 분석에는 파일 1개를 올려 주세요.';
export const MSG_UNSUPPORTED_FORMAT = 'PDF·PNG·JPEG 파일만 분석할 수 있습니다.';
export const MSG_UPLOAD_FAILED = '파일을 올리지 못했습니다. 잠시 후 새 분석으로 다시 시도해 주세요.';
export const MSG_UNSUPPORTED = '실제 분석에서는 아직 지원하지 않는 기능입니다.';

/** 목록을 조회할 때 동시에 보내는 요청 수 */
const LIST_CONCURRENCY = 4;

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
  /** id 목록·접근 코드 저장소(기본: 이 탭의 sessionStorage) */
  storage?: KeyValueStorage | null;
}

type Listener = (event?: ServiceEvent) => void;

const EMPTY_PENDING = (): Pending => ({ openF: [], openI: [], openL: [], any: false });

const unsupported = (): Promise<never> => Promise.reject(new Error(MSG_UNSUPPORTED));

/** 요청할 파일 하나 — 정확히 1개이고 브라우저 File 이 있어야 한다 */
function pickFile(files: readonly UploadFile[] | undefined): File {
  const list = files ?? [];
  const file = list.length === 1 ? list[0].file : undefined;
  if (!file) throw new Error(MSG_ONE_FILE);
  return file;
}

export function createApiService(deps: ApiServiceDeps = {}): AnalysisService {
  const storage = deps.storage === undefined ? browserSessionStorage() : deps.storage;
  const client = deps.client ?? createApiClient({ getAccessCode: () => accessCodeForHeader(storage) });
  const upload = deps.upload ?? uploadWithSupabase;
  const listeners = new Set<Listener>();
  const inflight = new Map<string, Promise<AnalysisOut>>();

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

  /**
   * GET 하나 — 같은 id 를 같은 접근 코드로 보낸 요청이 진행 중이면 그 요청을 나눠 쓴다.
   * 키에 지금 접근 코드를 넣어, 코드를 고친 뒤의 조회가 이전 코드의 요청(예: 401 이 될 요청)에 합쳐지지 않게 한다
   * (키는 메모리에만 있고 기록하지 않는다).
   */
  const fetchOne = (id: string): Promise<AnalysisOut> => {
    const key = JSON.stringify([accessCodeForHeader(storage), id]);
    const running = inflight.get(key);
    if (running) return running;
    const p = client.getAnalysis(id).finally(() => {
      if (inflight.get(key) === p) inflight.delete(key);
    });
    inflight.set(key, p);
    return p;
  };

  /** 조회 — 404 는 null */
  const getOrNull = async (id: string): Promise<Analysis | null> => {
    try {
      return toAnalysis(await fetchOne(id));
    } catch (err) {
      if (isApiError(err) && err.code === 'not_found') return null;
      throw err;
    }
  };

  const service: AnalysisService = {
    async list() {
      if (!accessCodeForHeader(storage)) return [];
      const ids = readSessionIds(storage);
      const found: { analysis: Analysis; order: number }[] = [];
      const missing: string[] = [];
      let next = 0;
      const worker = async () => {
        while (next < ids.length) {
          const order = next++;
          const id = ids[order];
          const analysis = await getOrNull(id);
          if (analysis) found.push({ analysis, order });
          else missing.push(id);
        }
      };
      await Promise.all(Array.from({ length: Math.min(LIST_CONCURRENCY, ids.length) }, worker));
      if (missing.length) removeSessionIds(missing, storage);
      // 요청 시각 최신순 — 같은 분(minute)이면 이 탭에서 나중에 만든 것(목록 앞)이 먼저
      found.sort((a, b) => (a.analysis.submittedAt === b.analysis.submittedAt ? a.order - b.order : a.analysis.submittedAt < b.analysis.submittedAt ? 1 : -1));
      return found.map((f) => f.analysis);
    },

    get: (id) => getOrNull(id),

    pending: async () => EMPTY_PENDING(),

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
          addSessionId(id, storage);
          emit();
          throw new ApiError(err.status, err.code, err.message, id);
        } else {
          throw err;
        }
      }

      addSessionId(id, storage);
      emit();
      return id;
    },

    /* ---------- 아직 백엔드가 없는 기능 ---------- */
    retry: async () => ({ ok: false, message: MSG_UNSUPPORTED }),
    setStatus: unsupported,
    confirmMany: unsupported,
    markFalsePositive: unsupported,
    restore: unsupported,
    reclassify: unsupported,
    saveFindingMemo: unsupported,
    resolveItem: unsupported,
    reopenItem: unsupported,
    decideLink: unsupported,
    saveMemo: unsupported,
    completeReview: unsupported,
    reopenReview: unsupported,
    buildExport: unsupported,
    logExport: unsupported,

    subscribe(listener) {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
  };
  return service;
}
