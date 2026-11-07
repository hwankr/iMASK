/* ==========================================================================
   주소 기준 경로 — 화면이 어느 기준(루트 '' / 데모 `/demo`) 아래에 있는지와, 그 기준의 이동 주소 만들기.
   - `/demo` 아래(정확히 `/demo` 이거나 `/demo/` 로 시작)는 언제나 데모 서비스로 그린다(src/services/mode.ts
     modeForPath). 그 밖은 빌드 모드(NEXT_PUBLIC_IMASK_SERVICE)를 따른다.
   - 화면 안 이동 주소(목록 · 새 분석 · 상세 · 보고서)는 모두 이 파일의 함수로 만든다 — `/demo` 아래에서는
     `/demo` 로 시작하고, 그 밖에서는 기준이 '' 라 예전에 화면이 직접 쓰던 글자와 바이트 단위로 같다.
   - 순수 함수만 둔다(React 없음). 기준 경로는 화면에서 useRouteBase()(src/services/react.tsx)로 받는다.
   ========================================================================== */

/** 데모 화면의 기준 경로 */
export const DEMO_BASE = '/demo';

/** 기준 경로 — '' = 루트(빌드 모드), `/demo` = 데모 */
export type RouteBase = '' | typeof DEMO_BASE;

/**
 * `/demo` 아래 경로인지 — 정확히 `/demo` 이거나 `/demo/` 로 시작할 때만 true.
 * 대소문자를 가린다(Next 경로가 가린다). 입력은 usePathname() 의 경로(쿼리 · 해시 없음).
 */
export function isDemoPath(pathname: string | null | undefined): boolean {
  if (!pathname) return false;
  return pathname === DEMO_BASE || pathname.startsWith(DEMO_BASE + '/');
}

/** 경로 → 기준 경로 */
export function routeBaseFor(pathname: string | null | undefined): RouteBase {
  return isDemoPath(pathname) ? DEMO_BASE : '';
}

/**
 * 앱 경로(`/` 로 시작, 쿼리 · 해시 포함 가능)에 기준 경로를 붙인다.
 * 기준 '' 이면 그대로. `/demo` 면 `/` → `/demo`, `/?q` → `/demo?q`, `/#h` → `/demo#h`, `/analyses/new` → `/demo/analyses/new`.
 * `/` 로 시작하지 않는 경로는 프로그래밍 실수라 예외를 던진다.
 */
export function withBase(base: RouteBase, path: string): string {
  if (!path.startsWith('/')) throw new Error(`withBase: 앱 경로는 '/' 로 시작해야 합니다 — ${JSON.stringify(path)}`);
  if (base === '') return path;
  const rest = path.slice(1);
  if (rest === '' || rest.startsWith('?') || rest.startsWith('#')) return base + rest;
  return base + path;
}

/* ---------- 이동 주소 ---------- */

/** 워크플로우 설정 — 실제 분석 모드에만 있다(`/demo` 아래에는 없다) */
export const SETTINGS_HREF = '/settings';

/** 목록 — query 는 정규형 검색 문자열(물음표 없음, listModel filtersToQuery). 비면 목록 첫 화면 */
export function listHref(base: RouteBase, query = ''): string {
  return withBase(base, query ? '/?' + query : '/');
}

/** 새 분석 — sample 이면 샘플 문서 3개를 담아 시작(`?sample=1`) */
export function newAnalysisHref(base: RouteBase, opts: { sample?: boolean } = {}): string {
  return withBase(base, opts.sample ? '/analyses/new?sample=1' : '/analyses/new');
}

/** 상세 검토 */
export function detailHref(base: RouteBase, id: string): string {
  return withBase(base, '/analyses/' + encodeURIComponent(id));
}

/** 검토 결과 보고서 */
export function reportHref(base: RouteBase, id: string): string {
  return withBase(base, '/analyses/' + encodeURIComponent(id) + '/report');
}
