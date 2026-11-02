/* ==========================================================================
   이 탭에서 만든 실제 분석 id 목록 — sessionStorage 'imask:api-analyses'(JSON 문자열 배열)
   - 최신이 앞, 같은 id 는 한 번만, 최대 50개(넘으면 오래된 것부터 버린다).
   - 백엔드에는 목록 경로가 없다(공용 접근 코드 하나로 남의 분석까지 보이지 않게). 목록 화면은 이 id 들만 조회한다.
   - 브라우저가 아니면 빈 목록. 저장소를 바꿔 끼울 수 있다(테스트).
   ========================================================================== */

import { browserSessionStorage, type KeyValueStorage } from './access-code';

export const SESSION_LIST_KEY = 'imask:api-analyses';
export const SESSION_LIST_MAX = 50;

/** 저장한 id 목록(최신이 앞). 없거나 모양이 깨졌으면 [] */
export function readSessionIds(storage: KeyValueStorage | null = browserSessionStorage()): string[] {
  if (!storage) return [];
  let parsed: unknown;
  try {
    parsed = JSON.parse(storage.getItem(SESSION_LIST_KEY) ?? '[]');
  } catch {
    return [];
  }
  if (!Array.isArray(parsed)) return [];
  const ids = parsed.filter((v): v is string => typeof v === 'string' && v.length > 0);
  return Array.from(new Set(ids)).slice(0, SESSION_LIST_MAX);
}

function write(ids: string[], storage: KeyValueStorage): void {
  try {
    storage.setItem(SESSION_LIST_KEY, JSON.stringify(ids));
  } catch {
    /* 저장 공간이 막힘 — 목록에 보이지 않을 뿐 분석은 그대로 */
  }
}

/** id 를 맨 앞에 넣는다(이미 있으면 앞으로 옮김). 바뀐 목록을 돌려준다. */
export function addSessionId(id: string, storage: KeyValueStorage | null = browserSessionStorage()): string[] {
  if (!storage || !id) return readSessionIds(storage);
  const next = [id, ...readSessionIds(storage).filter((v) => v !== id)].slice(0, SESSION_LIST_MAX);
  write(next, storage);
  return next;
}

/** id 를 뺀다(백엔드에 없는 분석). 바뀐 목록을 돌려준다. */
export function removeSessionIds(ids: readonly string[], storage: KeyValueStorage | null = browserSessionStorage()): string[] {
  const current = readSessionIds(storage);
  if (!storage || !ids.length) return current;
  const drop = new Set(ids);
  const next = current.filter((v) => !drop.has(v));
  if (next.length !== current.length) write(next, storage);
  return next;
}
