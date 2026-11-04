/* ==========================================================================
   ④ 데이터 서비스 인터페이스 — 실제 API로 바꾸는 계약.
   - 메서드는 프로토타입 createDemoService()와 같다. 모든 메서드는 Promise를 돌려준다
     (subscribe 만 예외).
   - 화면은 이 인터페이스만 쓰고 샘플 데이터를 직접 import하지 않는다.
   - 조회 결과는 복사본이다. 고쳐도 서비스 상태는 바뀌지 않는다.
   - 위험등급과 판단 근거는 서비스가 준 값을 그대로 표시하며 화면에서 계산하지 않는다.
   - 실제 분석은 백엔드(FastAPI)가 Upstage Studio 워크플로우를 호출해 실행하고,
     화면은 분석 상태 · 결과 · 검토 기록만 주고받는다.
   - 메서드마다 '실제:' 주석은 실제 분석 서비스(src/services/api/service.ts)가 부르는 경로다.
     아직 백엔드가 없는 것(문서 간 연결)은 '실제 분석에서는 아직 지원하지 않음'(거절)이라고 적었다.
   - 로그인이 없다 — 실제 분석은 주소를 아는 누구나 같은 목록을 보고 · 검토하고 · 지울 수 있다(대회용).
   ========================================================================== */

import type { ExportFormat, Exposure, FpReason, InfoCategory, InfoSubject } from '@/display/rules';
import type {
  Analysis,
  DocLink,
  ExportFile,
  Finding,
  LinkDecision,
  ReviewItem,
  UploadFile,
} from './types';

export type { LinkDecision } from './types';

/** 검토 완료 전에 남은 항목 */
export interface Pending {
  /** 미확인 탐지 항목 */
  openF: Finding[];
  /** 미해결 검토사항 */
  openI: ReviewItem[];
  /** 판단하지 않은 '연결 확인 필요' 연결 */
  openL: DocLink[];
  /** 하나라도 남았는지 */
  any: boolean;
}

/** 분석 요청 단계 — create 분석 건 만들기 / upload 파일 올리기 / start 분석 시작 */
export type RequestStep = 'create' | 'upload' | 'start';

/** 분석 요청 입력 */
export interface RequestAnalysisInput {
  /** 분석 이름 */
  name: string;
  /** 준비가 끝난(ready) 파일 */
  files: UploadFile[];
  /**
   * 단계가 바뀔 때마다 부른다(선택). 실제 분석 서비스만 쓴다 — 데모 화면은 넘기지 않는다
   * (데모 서비스는 입력을 structuredClone 하므로 함수를 넘기면 복사에 실패한다).
   */
  onProgress?: (step: RequestStep) => void;
}

/** 다시 분석 결과 */
export interface RetryResult {
  ok: boolean;
  /** 실패 이유(성공이면 빈 문자열) */
  message: string;
  /**
   * 다시 분석을 시작했는지 — 실제 분석만 채운다(데모는 넣지 않는다: 끝난 뒤 { ok: false, message: 이유 }).
   * true 면 분석이 대기·분석 중으로 돌아갔다. false 면 시작하지 못했다(message = 이유).
   */
  started?: boolean;
  /** 실제 분석만 — 시작하지 못한 이유가 '분석이 없음'(404, 이미 지워짐)일 때 true */
  gone?: boolean;
}

/** 분류 수정 — 바꿀 값만 넣는다 */
export type ReclassifyPatch = Partial<{
  cat: InfoCategory;
  subject: InfoSubject;
  exposure: Exposure;
}>;

/** 내보내기 기록 상태 — saved 저장 완료 / handed 다운로드 요청 */
export type ExportLogState = 'saved' | 'handed';

/** 서비스 변경 알림 — 분석 완료 시 토스트용 */
export interface ServiceEvent {
  type: 'done';
  /** 분석 건 ID */
  id: string;
  /** 분석 이름 */
  name: string;
  /** 검토사항 수 */
  items: number;
  /** 탐지 항목 수 */
  findings: number;
}

/** /dev/states 의 상태 25개 ID(디자인 states.md · Tweaks 시작 상태 순서) */
export type StateId =
  | 'list'
  | 'list-empty'
  | 'list-noresults'
  | 'upload'
  | 'upload-selected'
  | 'upload-unsupported'
  | 'upload-limit'
  | 'upload-failed'
  | 'upload-requesting'
  | 'detail'
  | 'detail-queued'
  | 'detail-running'
  | 'detail-partial'
  | 'detail-failed'
  | 'detail-completed'
  | 'detail-nolocation'
  | 'detail-review'
  | 'detail-links'
  | 'detail-edit'
  | 'detail-complete'
  | 'detail-docs'
  | 'detail-results'
  | 'report'
  | 'report-saved'
  | 'report-failed';

export interface AnalysisService {
  /**
   * 분석 목록을 가져온다(최근 요청 순). 실제: GET /api/py/analyses 하나(서버가 최근 100건 — 누구나 같은 목록).
   * 목록 항목은 가벼운 값이다(탐지 항목 · 이력 없음 — 상세는 get).
   */
  list(): Promise<Analysis[]>;
  /** 분석 건 하나를 가져온다. 없으면 null. 실제: GET /api/py/analyses/{id}(404 → null, review 블록을 덧씌움) */
  get(id: string): Promise<Analysis | null>;
  /** 검토 완료 전에 남은 항목(미확인 탐지·미해결 검토사항·확인 필요 연결)을 계산한다. 실제: GET /api/py/analyses/{id} 의 미확인 탐지 항목 · 미해결 검토사항(연결은 빈 목록) */
  pending(id: string): Promise<Pending>;
  /** 샘플 문서 3개를 업로드 파일 형태로 준다(데모 전용 기능). 실제 분석에서는 빈 목록 */
  sampleFiles(): Promise<UploadFile[]>;
  /** 분석을 요청하고 분석 ID를 돌려준다. 실제: POST /api/py/analyses → Supabase 서명 업로드 → POST /api/py/analyses/{id}/start → ID 반환, 이후 GET 조회로 진행 확인 */
  requestAnalysis(input: RequestAnalysisInput): Promise<string>;
  /**
   * 실패한 문서(docId 없으면 전부)를 다시 분석한다. 데모에서는 같은 이유로 다시 실패한다.
   * 실제: POST /api/py/analyses/{id}/retry(본문 { actor } — 같은 원본으로 Upstage 작업을 새로 만든다, docId 는 무시).
   * 거절하지 않는다 — 시작했으면 { ok: true, started: true }, 못 했으면 { ok: false, started: false, message: 이유 }.
   */
  retry(id: string, docId?: string): Promise<RetryResult>;
  /**
   * 분석을 지운다(원본 파일 · 검토 기록 포함, 되돌릴 수 없음). 없는 분석이면 ApiError(not_found)로 거절한다(두 모드 같음).
   * 실제: DELETE /api/py/analyses/{id}(204). 데모: 메모리에서 지운다('샘플 다시 불러오기'로 되살아난다).
   */
  deleteAnalysis(id: string): Promise<void>;
  /** 탐지 항목 하나를 확인함·미확인으로 바꾼다(이력 기록). 실제: POST /api/py/analyses/{id}/review-actions(type set_status) */
  setStatus(id: string, fid: string, status: 'open' | 'confirmed', reason?: string): Promise<void>;
  /** 미확인 탐지 항목 여러 개를 한 번에 확인함으로 바꾼다. 실제: POST /api/py/analyses/{id}/review-actions(type confirm_many) */
  confirmMany(id: string, fids: string[]): Promise<void>;
  /** 탐지 항목을 오탐으로 표시한다(사유·메모 기록). 실제: POST /api/py/analyses/{id}/review-actions(type mark_false_positive) */
  markFalsePositive(id: string, fid: string, reasonType: FpReason, note: string): Promise<void>;
  /** 오탐 표시를 취소한다. 분류를 고친 적이 있으면 '분류 수정'으로 돌아간다. 실제: POST /api/py/analyses/{id}/review-actions(type restore) */
  restore(id: string, fid: string, note?: string): Promise<void>;
  /** 정보 종류·정보 주체·노출 상태를 고친다. 바뀐 값이 없으면 false. 실제: POST /api/py/analyses/{id}/review-actions(type reclassify — 응답의 changed) */
  reclassify(id: string, fid: string, patch: ReclassifyPatch, reason: string): Promise<boolean>;
  /** 탐지 항목 메모를 저장한다(빈 문자열이면 삭제). 실제: POST /api/py/analyses/{id}/review-actions(type save_finding_memo) */
  saveFindingMemo(id: string, fid: string, text: string): Promise<void>;
  /** 검토사항을 해결로 표시한다(처리 내용 기록). 실제: POST /api/py/analyses/{id}/review-actions(type resolve_item — 화면 번호를 계약 id 로) */
  resolveItem(id: string, rid: string, note: string): Promise<void>;
  /** 해결한 검토사항을 다시 연다. 실제: POST /api/py/analyses/{id}/review-actions(type reopen_item — 화면 번호를 계약 id 로) */
  reopenItem(id: string, rid: string): Promise<void>;
  /** 문서 간 연결을 판단하고, 그 연결에 묶인 검토사항을 함께 해결한다. 실제 분석에서는 아직 지원하지 않음 */
  decideLink(id: string, lid: string, decision: LinkDecision, note: string): Promise<void>;
  /** 분석 건의 검토 메모를 저장한다(빈 문자열이면 삭제). 실제: POST /api/py/analyses/{id}/review-actions(type save_memo) */
  saveMemo(id: string, text: string): Promise<void>;
  /** 검토를 완료한다. 검토 상태와 기록만 바꾸고 위험등급·최초 탐지 결과는 유지한다. 실제: POST /api/py/analyses/{id}/review-actions(type complete_review) */
  completeReview(id: string, note: string): Promise<void>;
  /** 완료한 검토를 다시 연다(사유 기록). 실제: POST /api/py/analyses/{id}/review-actions(type reopen_review) */
  reopenReview(id: string, reason: string): Promise<void>;
  /**
   * 내보내기 파일(CSV·JSON)을 만든다. 마스킹된 표시값만 담는다(계산은 공용 모듈 src/services/export-file.ts).
   * 실제: GET /api/py/analyses/{id} 로 지금 분석을 받아 보고서 대상(완료 + 공통 계약 결과 + 검토 기록)만 — 원문 값을 지운 사본으로
   * 화면에서 만든다(brand 인자는 쓰지 않는다 · 생성 시각은 서울). 없으면(404) · 대상이 아니면 거절
   */
  buildExport(id: string, format: ExportFormat, brand?: string): Promise<ExportFile>;
  /** 내보내기 결과를 검토 이력에 남긴다. 실제: POST /api/py/analyses/{id}/review-actions(type log_export — 형식 · 크기 · 결과 · 파일 이름) */
  logExport(id: string, file: ExportFile, state: ExportLogState): Promise<void>;
  /**
   * 유일한 예외: 변경 알림 구독. 구독 해제 함수를 돌려준다.
   * 실제: 분석 요청 · 다시 분석(응답을 받으면) · 삭제(성공 · 404) · 검토 동작 · 내보내기 기록(성공 · 409 · 404) 뒤, 그리고 조회(list · get)에서
   * 진행 중으로 본 분석이 끝난 것을 처음 볼 때 한 번(이벤트 없는 알림). 진행은 상세 화면 · 목록 화면이 3초마다 조회한다.
   */
  subscribe(listener: (event?: ServiceEvent) => void): () => void;
}

/** 실제 분석의 원본 파일 내용 */
export interface LiveFile {
  /** 파일 내용 */
  bytes: ArrayBuffer;
  /** MIME 형식(application/pdf · image/png · image/jpeg) */
  mime: string;
  /** 파일 이름(없으면 빈 문자열) */
  filename: string;
}

/**
 * 실제 분석 전용 통로 — 서비스 인터페이스 밖의 실제 분석 기능. 화면은 useLiveExtras() 로 받는다(데모면 null).
 * 오류는 한국어 문구의 ApiError.
 * - loadFile: 없음 404 는 안전한 백엔드 문구만 보이고, 주소 · 서명 · 키 · 긴 토큰 모양이 섞이면
 *   고정 안내 문구로 바꾼다. 그 밖 오류(5xx · 네트워크 · 시간 초과 · 받기 실패 등)는 늘 고정 문구다.
 * - loadStages: 다른 조회와 같은 규칙(404 는 백엔드 문구 그대로).
 */
export interface LiveExtras {
  /** 원본 파일 내용을 받는다. 부를 때마다 새 서명 주소를 받는다(10분 만료 대비 — 캐시는 화면이 한다). 실제: GET /api/py/analyses/{id}/file → 서명 주소 */
  loadFile(id: string): Promise<LiveFile>;
  /** 단계별 결과 JSON(result.stages). 없으면 null. 실제: GET /api/py/analyses/{id}?include=stages */
  loadStages(id: string): Promise<unknown[] | null>;
}

/** 데모 전용 조작 — 화면 컴포넌트는 쓰지 않는다(예외: '샘플 다시 불러오기' 버튼, /dev/**). */
export interface DemoControls {
  /** 샘플 분석 6건과 미리 해 둔 검토 동작으로 되돌린다. */
  reset(): Promise<void>;
  /** 분석 이력을 모두 지운다(목록 비어 있음 상태). */
  clearAll(): Promise<void>;
  /** /dev/states 의 상태를 만들고, 상세·보고서 상태면 열 분석 ID를 돌려준다. */
  prepare(state: StateId): Promise<{ analysisId?: string }>;
}
