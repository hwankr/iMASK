/* ==========================================================================
   서비스 모드 — 데모(브라우저 안 샘플) / 실제 분석(FastAPI + Upstage 워크플로우)
   - NEXT_PUBLIC_IMASK_SERVICE 가 정확히 'api' 면 실제 분석, 그 밖(없음 포함)은 데모.
   - Next 가 빌드 때 값을 넣도록 process.env.NEXT_PUBLIC_IMASK_SERVICE 를 글자 그대로 참조한다
     (process.env[name] 처럼 쓰면 브라우저 코드에 값이 들어가지 않는다). 비밀값이 아니다.
   - 값을 바꾸면 다시 빌드(배포)해야 한다.
   ========================================================================== */

export type ServiceMode = 'demo' | 'api';

/** 환경변수 값 → 모드. 정확히 'api' 일 때만 실제 분석 */
export function resolveServiceMode(value: string | null | undefined): ServiceMode {
  return value === 'api' ? 'api' : 'demo';
}

/** 이 빌드의 서비스 모드 */
export const SERVICE_MODE: ServiceMode = resolveServiceMode(process.env.NEXT_PUBLIC_IMASK_SERVICE);
