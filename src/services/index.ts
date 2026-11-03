/* ==========================================================================
   서비스 고르기 — 화면이 쓰는 데이터 서비스를 모드에 따라 만든다(src/services/mode.ts).
   - createServiceFor(mode): 'api' 면 실제 분석 서비스(FastAPI 백엔드 + Upstage 워크플로우),
     'demo' 면 데모 서비스(브라우저 메모리의 샘플 데이터).
     모드는 주소 기준이다 — ServiceProvider(react.tsx)가 modeForPath(경로, 빌드 모드)로 정한다(`/demo` 아래는 언제나 데모).
     createService() 는 빌드 모드의 서비스(테스트용 — 테스트 환경은 값이 없어 데모).
   - createServiceCache(factory): 모드마다 서비스 하나(처음 쓸 때 만들고 그 뒤로는 같은 것)를 주는 작은 캐시.
     react.tsx 가 브라우저 싱글턴(데모 하나 · 실제 분석 하나)으로 쓴다.
   - getDemoControls(): 데모 서비스일 때만 데모 전용 조작(샘플 다시 불러오기 · /dev/states)을 준다.
     실제 분석 서비스에서는 null 이 되어 데모 버튼 · 개발용 화면이 저절로 빠진다.
   - getLiveExtras(): 실제 분석 서비스일 때만 실제 분석 전용 통로(원본 파일 · 단계별 JSON)를 준다. 데모면 null.
   - 실제 분석 화면이 쓰는 오류 판별도 여기서 다시 내보낸다(화면은 데이터를 서비스 인터페이스로만 다루고, 이것만 예외로 가져다 쓴다).
   - 빌드 모드 상수(SERVICE_MODE)는 다시 내보내지 않는다 — 화면은 주소 기준 모드(useServiceMode)만 쓴다.
   ========================================================================== */

import type { AnalysisService, DemoControls, LiveExtras } from './analysis-service';
import { createApiService, isApiService } from './api';
import { createDemoService, isDemoService } from './demo';
import { SERVICE_MODE, type ServiceMode } from './mode';

export type { AnalysisService, DemoControls, LiveExtras, LiveFile } from './analysis-service';
export type { ServiceMode } from './mode';
export { apiErrorAnalysisId, apiErrorCode, type ApiErrorCode } from './api';

/** 데이터 서비스를 만든다 — 'api' 면 실제 분석 서비스, 'demo' 면 데모 서비스 */
export function createServiceFor(mode: ServiceMode): AnalysisService {
  return mode === 'api' ? createApiService() : createDemoService();
}

/**
 * 빌드 모드(SERVICE_MODE)의 서비스를 만든다 — 테스트(값 없음 = 데모)가 쓴다.
 * 화면은 쓰지 않는다: ServiceProvider 가 주소 기준 모드로 createServiceFor 를 부른다.
 */
export function createService(): AnalysisService {
  return createServiceFor(SERVICE_MODE);
}

/** 모드별 서비스 캐시 */
export interface ServiceCache {
  /** 그 모드의 서비스 — 처음 부를 때 factory 로 만들고, 그 뒤로는 같은 객체를 돌려준다 */
  get(mode: ServiceMode): AnalysisService;
}

/**
 * 모드마다 서비스 하나. 쓰지 않은 모드의 서비스는 만들지 않는다
 * (실제 모드 빌드에서 `/demo` 만 다니면 실제 분석 서비스가 없고, `/` 만 다니면 데모 서비스 · 타이머가 없다).
 */
export function createServiceCache(factory: (mode: ServiceMode) => AnalysisService = createServiceFor): ServiceCache {
  const made = new Map<ServiceMode, AnalysisService>();
  return {
    get(mode) {
      let service = made.get(mode);
      if (!service) {
        service = factory(mode);
        made.set(mode, service);
      }
      return service;
    },
  };
}

/** 데모 서비스일 때만 데모 조작 객체를 돌려준다(그 밖에는 null). */
export function getDemoControls(service: AnalysisService | null | undefined): DemoControls | null {
  return isDemoService(service) ? service : null;
}

/** 실제 분석 서비스일 때만 실제 분석 전용 통로를 돌려준다(데모 · 그 밖에는 null). */
export function getLiveExtras(service: AnalysisService | null | undefined): LiveExtras | null {
  return isApiService(service) ? service : null;
}
