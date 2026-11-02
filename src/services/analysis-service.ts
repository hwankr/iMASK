/* ==========================================================================
   ④ 데이터 서비스 인터페이스 — 실제 API로 바꾸는 계약.
   - 메서드는 프로토타입 createDemoService()와 같다. 모든 메서드는 Promise를 돌려준다
     (subscribe 만 예외).
   - 화면은 이 인터페이스만 쓰고 샘플 데이터를 직접 import하지 않는다.
   - 조회 결과는 복사본이다. 고쳐도 서비스 상태는 바뀌지 않는다.
   - 위험등급과 판단 근거는 서비스가 준 값을 그대로 표시하며 화면에서 계산하지 않는다.
   - 실제 분석은 백엔드(FastAPI)가 Upstage Studio 워크플로우를 호출해 실행하고,
     화면은 분석 상태 · 결과 · 검토 기록만 주고받는다.
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
  /** 분석 목록을 가져온다(최근 요청 순). 실제: GET /analyses */
  list(): Promise<Analysis[]>;
  /** 분석 건 하나를 가져온다. 없으면 null. 실제: GET /analyses/{id} */
  get(id: string): Promise<Analysis | null>;
  /** 검토 완료 전에 남은 항목(미확인 탐지·미해결 검토사항·확인 필요 연결)을 계산한다. 실제: GET /analyses/{id}/pending */
  pending(id: string): Promise<Pending>;
  /** 샘플 문서 3개를 업로드 파일 형태로 준다. 실제: 샘플 파일 목록 조회(데모 전용 기능) */
  sampleFiles(): Promise<UploadFile[]>;
  /** 분석을 요청하고 분석 ID를 돌려준다. 실제: 파일 업로드 → 분석 실행 요청 → ID 반환, 이후 상태 조회로 진행 확인 */
  requestAnalysis(input: RequestAnalysisInput): Promise<string>;
  /** 실패한 문서(docId 없으면 전부)를 다시 분석한다. 데모에서는 같은 이유로 다시 실패한다. 실제: POST /analyses/{id}/retry */
  retry(id: string, docId?: string): Promise<RetryResult>;
  /** 탐지 항목 하나를 확인함·미확인으로 바꾼다(이력 기록). 실제: PATCH /analyses/{id}/findings/{fid} */
  setStatus(id: string, fid: string, status: 'open' | 'confirmed', reason?: string): Promise<void>;
  /** 미확인 탐지 항목 여러 개를 한 번에 확인함으로 바꾼다. 실제: POST /analyses/{id}/findings/confirm */
  confirmMany(id: string, fids: string[]): Promise<void>;
  /** 탐지 항목을 오탐으로 표시한다(사유·메모 기록). 실제: POST /analyses/{id}/findings/{fid}/false-positive */
  markFalsePositive(id: string, fid: string, reasonType: FpReason, note: string): Promise<void>;
  /** 오탐 표시를 취소한다. 분류를 고친 적이 있으면 '분류 수정'으로 돌아간다. 실제: DELETE …/false-positive */
  restore(id: string, fid: string, note?: string): Promise<void>;
  /** 정보 종류·정보 주체·노출 상태를 고친다. 바뀐 값이 없으면 false. 실제: PATCH /analyses/{id}/findings/{fid}/classification */
  reclassify(id: string, fid: string, patch: ReclassifyPatch, reason: string): Promise<boolean>;
  /** 탐지 항목 메모를 저장한다(빈 문자열이면 삭제). 실제: PUT /analyses/{id}/findings/{fid}/memo */
  saveFindingMemo(id: string, fid: string, text: string): Promise<void>;
  /** 검토사항을 해결로 표시한다(처리 내용 기록). 실제: POST /analyses/{id}/items/{rid}/resolve */
  resolveItem(id: string, rid: string, note: string): Promise<void>;
  /** 해결한 검토사항을 다시 연다. 실제: POST /analyses/{id}/items/{rid}/reopen */
  reopenItem(id: string, rid: string): Promise<void>;
  /** 문서 간 연결을 판단하고, 그 연결에 묶인 검토사항을 함께 해결한다. 실제: POST /analyses/{id}/links/{lid}/decision */
  decideLink(id: string, lid: string, decision: LinkDecision, note: string): Promise<void>;
  /** 분석 건의 검토 메모를 저장한다(빈 문자열이면 삭제). 실제: PUT /analyses/{id}/memo */
  saveMemo(id: string, text: string): Promise<void>;
  /** 검토를 완료한다. 검토 상태와 기록만 바꾸고 위험등급·최초 탐지 결과는 유지한다. 실제: POST /analyses/{id}/complete */
  completeReview(id: string, note: string): Promise<void>;
  /** 완료한 검토를 다시 연다(사유 기록). 실제: POST /analyses/{id}/reopen */
  reopenReview(id: string, reason: string): Promise<void>;
  /** 내보내기 파일(CSV·JSON)을 만든다. 마스킹된 표시값만 담는다. 실제: GET /analyses/{id}/export?format= */
  buildExport(id: string, format: ExportFormat, brand?: string): Promise<ExportFile>;
  /** 내보내기 결과를 검토 이력에 남긴다. 실제: POST /analyses/{id}/export-log */
  logExport(id: string, file: ExportFile, state: ExportLogState): Promise<void>;
  /** 유일한 예외: 변경 알림 구독. 구독 해제 함수를 돌려준다. 실제 API에서는 폴링이나 SSE로 구현한다. */
  subscribe(listener: (event?: ServiceEvent) => void): () => void;
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
