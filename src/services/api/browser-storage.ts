/* ==========================================================================
   이 탭의 문자열 저장소 — sessionStorage 와 같은 모양. 이 탭에서 만든 분석 id 목록(session-list.ts)이 쓴다.
   - 브라우저가 아니거나(서버 렌더 · 테스트) 저장소 사용이 막혀 있으면 null.
   - 테스트는 같은 모양의 가짜 저장소(testing.ts memoryStorage)를 넘긴다.
   ========================================================================== */

/** 문자열 저장소 — sessionStorage 와 같은 모양(테스트용 가짜도 이 모양) */
export interface KeyValueStorage {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
  removeItem(key: string): void;
}

/** 이 탭의 sessionStorage. 브라우저가 아니거나 막혀 있으면 null */
export function browserSessionStorage(): KeyValueStorage | null {
  if (typeof window === 'undefined') return null;
  try {
    return window.sessionStorage;
  } catch {
    return null; // 저장소 사용이 막힌 브라우저
  }
}
