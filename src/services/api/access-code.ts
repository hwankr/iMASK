/* ==========================================================================
   접근 코드 — 공개 주소 보호용 코드(팀에서 받은 값)를 이 탭의 sessionStorage 에만 둔다.
   - 키 'imask:demo-code'. 탭을 닫으면 지워진다. localStorage·쿠키에는 두지 않는다.
   - 브라우저가 아니면(서버 렌더·테스트) 빈 값을 돌려주고 아무것도 하지 않는다.
   - 저장소를 바꿔 끼울 수 있다(테스트는 가짜 저장소를 넘긴다).
   - 입력한 그대로 저장한다(입력 중 공백이 사라지지 않게). 요청 헤더에 넣을 때 앞뒤 공백을 뗀다.
   - 같은 탭 안의 변경은 subscribeAccessCode 로 알린다(sessionStorage 는 같은 탭에 storage 이벤트가 없다).
   ========================================================================== */

/** sessionStorage 키 */
export const ACCESS_CODE_KEY = 'imask:demo-code';

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

const listeners = new Set<() => void>();

function notify(): void {
  for (const listener of Array.from(listeners)) listener();
}

/** 저장한 접근 코드(입력한 그대로). 없으면 '' */
export function readAccessCode(storage: KeyValueStorage | null = browserSessionStorage()): string {
  if (!storage) return '';
  try {
    return storage.getItem(ACCESS_CODE_KEY) ?? '';
  } catch {
    return '';
  }
}

/** 접근 코드를 저장한다. 빈 값(공백만 포함)이면 지운다. */
export function saveAccessCode(code: string, storage: KeyValueStorage | null = browserSessionStorage()): void {
  if (!storage) return;
  try {
    if (code.trim()) storage.setItem(ACCESS_CODE_KEY, code);
    else storage.removeItem(ACCESS_CODE_KEY);
  } catch {
    /* 저장 공간이 막힘 — 이번 입력만 쓰지 못한다 */
  }
  notify();
}

/** 접근 코드를 지운다 */
export function clearAccessCode(storage: KeyValueStorage | null = browserSessionStorage()): void {
  if (!storage) return;
  try {
    storage.removeItem(ACCESS_CODE_KEY);
  } catch {
    /* 무시 */
  }
  notify();
}

/** 같은 탭에서 접근 코드가 바뀌면 부른다. 구독 해제 함수를 돌려준다. */
export function subscribeAccessCode(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

/** 요청 헤더에 넣을 값 — 앞뒤 공백을 뗀다 */
export function accessCodeForHeader(storage?: KeyValueStorage | null): string {
  return readAccessCode(storage === undefined ? browserSessionStorage() : storage).trim();
}
