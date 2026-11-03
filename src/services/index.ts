/* ==========================================================================
   서비스 고르기 — 화면이 쓰는 데이터 서비스를 모드에 따라 만든다(src/services/mode.ts).
   - createService(): NEXT_PUBLIC_IMASK_SERVICE=api 면 실제 분석 서비스(FastAPI 백엔드 + Upstage 워크플로우),
     그 밖(기본)은 데모 서비스(브라우저 메모리의 샘플 데이터).
   - getDemoControls(): 데모 서비스일 때만 데모 전용 조작(샘플 다시 불러오기 · /dev/states)을 준다.
     실제 분석 서비스에서는 null 이 되어 데모 버튼 · 개발용 화면이 저절로 빠진다.
   - getLiveExtras(): 실제 분석 서비스일 때만 실제 분석 전용 통로(원본 파일 · 단계별 JSON)를 준다. 데모면 null.
   - 실제 분석 화면이 쓰는 접근 코드 저장 함수와 오류 판별도 여기서 다시 내보낸다
     (화면은 데이터를 서비스 인터페이스로만 다루고, 이 둘만 예외로 가져다 쓴다).
   ========================================================================== */

import type { AnalysisService, DemoControls, LiveExtras } from './analysis-service';
import { createApiService, isApiService } from './api';
import { createDemoService, isDemoService } from './demo';
import { SERVICE_MODE } from './mode';

export type { AnalysisService, DemoControls, LiveExtras, LiveFile } from './analysis-service';
export { SERVICE_MODE, type ServiceMode } from './mode';
export { readAccessCode, saveAccessCode, clearAccessCode, subscribeAccessCode, apiErrorAnalysisId, apiErrorCode, type ApiErrorCode } from './api';

/** 데이터 서비스를 만든다 — 모드에 따라 실제 분석 서비스 또는 데모 서비스 */
export function createService(): AnalysisService {
  return SERVICE_MODE === 'api' ? createApiService() : createDemoService();
}

/** 데모 서비스일 때만 데모 조작 객체를 돌려준다(그 밖에는 null). */
export function getDemoControls(service: AnalysisService | null | undefined): DemoControls | null {
  return isDemoService(service) ? service : null;
}

/** 실제 분석 서비스일 때만 실제 분석 전용 통로를 돌려준다(데모 · 그 밖에는 null). */
export function getLiveExtras(service: AnalysisService | null | undefined): LiveExtras | null {
  return isApiService(service) ? service : null;
}
