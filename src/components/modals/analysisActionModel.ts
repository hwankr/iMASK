/* ==========================================================================
   분석 건 삭제 · 다시 분석 — 문구(한 곳)와 결과 토스트 고르기(순수 함수). 목록 · 상세(데모 · 실제)가 같이 쓴다.
   - 문구는 정해진 것만(BRIEF §5.8). 데모의 다시 분석 결과 문구는 그대로(reviewModalModel retryFailedText).
   - 다시 분석 토스트: started true → '다시 분석을 시작했습니다.' / started false → 404(gone)면 '이미 지워진 분석입니다.',
     그 밖은 '다시 분석을 시작하지 못했습니다 · <이유>'(오류) / started 없음(데모) → 이유가 있으면 '다시 분석했지만 실패했습니다 · <이유>'.
   - 삭제 실패 토스트: 404(이미 지워짐)면 '이미 지워진 분석입니다.', 그 밖은 '분석을 지우지 못했습니다. 잠시 후 다시 시도해 주세요.'.
   ========================================================================== */

import { apiErrorCode } from '@/services';
import type { RetryResult } from '@/services/analysis-service';
import { retryFailedText } from './reviewModalModel';

/** 삭제 버튼 · 확인 창 버튼 */
export const DELETE_LABEL = '삭제';
/** 확인 창 제목 */
export const DELETE_TITLE = '이 분석을 지울까요?';
/** 확인 창 본문(한 줄) */
export const DELETE_BODY = '원본 파일과 검토 기록이 함께 지워지며 되돌릴 수 없습니다.';
/** 확인 창 취소 버튼 */
export const DELETE_CANCEL = '취소';
/** 삭제 성공 토스트 */
export const DELETED_TEXT = '분석을 지웠습니다.';
/** 삭제 실패 토스트(오류) */
export const DELETE_FAILED_TEXT = '분석을 지우지 못했습니다. 잠시 후 다시 시도해 주세요.';
/** 이미 지워진 분석(삭제 · 다시 분석 · 검토 동작의 404, 오류) */
export const GONE_TEXT = '이미 지워진 분석입니다.';
/** 실제 분석 — 다시 분석 시작 토스트 */
export const RETRY_STARTED_TEXT = '다시 분석을 시작했습니다.';
/** 실제 분석 — 다시 분석을 시작하지 못함(오류) */
export const retryNotStartedText = (reason: string) => '다시 분석을 시작하지 못했습니다 · ' + reason;
/** 실제 분석 실패 상세 띠의 버튼 */
export const RETRY_LABEL = '다시 분석';

/** 토스트 하나 */
export interface ActionToast {
  text: string;
  kind: 'ok' | 'error';
}

/** 다시 분석 결과 → 토스트(띄울 것이 없으면 null) */
export function retryToast(r: RetryResult | null | undefined): ActionToast | null {
  if (!r) return null;
  if (r.started === true) return { text: RETRY_STARTED_TEXT, kind: 'ok' };
  if (r.started === false) return r.gone ? { text: GONE_TEXT, kind: 'error' } : { text: retryNotStartedText(r.message), kind: 'error' };
  // 데모 — 지금 그대로(이유가 있을 때만)
  return r.message ? { text: retryFailedText(r.message), kind: 'error' } : null;
}

/** 오류가 '분석이 없음'(404 — 이미 지워짐)인지 */
export function isGoneError(err: unknown): boolean {
  return apiErrorCode(err) === 'not_found';
}

/** 삭제 실패 → 토스트 문구 */
export function deleteFailedText(err: unknown): string {
  return isGoneError(err) ? GONE_TEXT : DELETE_FAILED_TEXT;
}
