/* ==========================================================================
   실제 API로 바꿀 때 이 함수만 바꾼다(FastAPI 백엔드 클라이언트를 같은 인터페이스로 구현).
   - createService(): 화면이 쓰는 데이터 서비스를 만든다. 지금은 데모 서비스(메모리 상태)다.
   - getDemoControls(): 데모 서비스일 때만 데모 전용 조작(샘플 다시 불러오기 · /dev/states)을 준다.
     실제 API 클라이언트에서는 null 이 되어 데모 버튼 · 개발용 화면이 저절로 빠진다.
   ========================================================================== */

import type { AnalysisService, DemoControls } from './analysis-service';
import { createDemoService, isDemoService } from './demo';

export type { AnalysisService, DemoControls } from './analysis-service';

/** 데이터 서비스를 만든다. 실제 API 단계에서는 여기서 API 클라이언트를 돌려준다. */
export function createService(): AnalysisService {
  return createDemoService();
}

/** 데모 서비스일 때만 데모 조작 객체를 돌려준다(그 밖에는 null). */
export function getDemoControls(service: AnalysisService | null | undefined): DemoControls | null {
  return isDemoService(service) ? service : null;
}
