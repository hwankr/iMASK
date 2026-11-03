/* ==========================================================================
   서비스 모드 — 데모(브라우저 안 샘플) / 실제 분석(FastAPI + Upstage 워크플로우). 주소 기준으로 정한다.
   - 빌드 모드(SERVICE_MODE): NEXT_PUBLIC_IMASK_SERVICE 가 정확히 'api' 면 실제 분석, 그 밖(없음 포함)은 데모.
     Next 가 빌드 때 값을 넣도록 process.env.NEXT_PUBLIC_IMASK_SERVICE 를 글자 그대로 참조한다
     (process.env[name] 처럼 쓰면 브라우저 코드에 값이 들어가지 않는다). 비밀값이 아니다. 값을 바꾸면 다시 빌드(배포)해야 한다.
     이 환경변수를 읽는 곳은 이 파일뿐이다(pdf.js 묶음을 빼는 liveFile.ts 의 빌드 분기만 예외).
   - 화면의 모드(modeForPath): `/demo` 아래 주소는 빌드 모드와 상관없이 언제나 데모, 그 밖은 빌드 모드.
     그래서 실제 모드 빌드(운영)에서도 `/demo` 로 들어가면 데모가 그대로 동작한다.
   - SERVICE_MODE 는 src/services 안(이 파일 · index.ts · react.tsx 의 ServiceProvider)에서만 읽는다.
     화면은 useServiceMode()(src/services/react.tsx — 주소 기준 모드)를 쓴다.
   ========================================================================== */

import { isDemoPath } from '@/lib/routes';

export type ServiceMode = 'demo' | 'api';

/** 환경변수 값 → 모드. 정확히 'api' 일 때만 실제 분석 */
export function resolveServiceMode(value: string | null | undefined): ServiceMode {
  return value === 'api' ? 'api' : 'demo';
}

/** 이 빌드의 서비스 모드(빌드 모드) */
export const SERVICE_MODE: ServiceMode = resolveServiceMode(process.env.NEXT_PUBLIC_IMASK_SERVICE);

/** 주소 → 화면의 서비스 모드. `/demo` 아래면 'demo', 그 밖은 빌드 모드 */
export function modeForPath(pathname: string | null | undefined, buildMode: ServiceMode): ServiceMode {
  return isDemoPath(pathname) ? 'demo' : buildMode;
}
