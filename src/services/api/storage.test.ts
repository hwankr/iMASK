import { describe, expect, it } from 'vitest';
import { browserSessionStorage } from './browser-storage';
import { SESSION_LIST_KEY, SESSION_LIST_MAX, addSessionId, readSessionIds, removeSessionIds } from './session-list';
import { memoryStorage } from './testing';

describe('이 탭의 저장소(browser-storage)', () => {
  it('Node(브라우저 아님)에서는 null', () => {
    expect(browserSessionStorage()).toBeNull();
  });
});

describe('이 탭의 분석 id 목록', () => {
  it('최신이 앞, 같은 id 는 앞으로 옮긴다', () => {
    const s = memoryStorage();
    addSessionId('a', s);
    addSessionId('b', s);
    expect(addSessionId('a', s)).toEqual(['a', 'b']);
    expect(JSON.parse(s.data.get(SESSION_LIST_KEY) as string)).toEqual(['a', 'b']);
  });

  it(`최대 ${SESSION_LIST_MAX}개 — 오래된 것부터 버린다`, () => {
    const s = memoryStorage();
    for (let i = 0; i < SESSION_LIST_MAX + 5; i++) addSessionId('id' + i, s);
    const ids = readSessionIds(s);
    expect(ids).toHaveLength(SESSION_LIST_MAX);
    expect(ids[0]).toBe('id' + (SESSION_LIST_MAX + 4));
    expect(ids).not.toContain('id0');
  });

  it('빼기 — 없는 id 는 그대로', () => {
    const s = memoryStorage({ [SESSION_LIST_KEY]: JSON.stringify(['a', 'b', 'c']) });
    expect(removeSessionIds(['b', 'z'], s)).toEqual(['a', 'c']);
    expect(readSessionIds(s)).toEqual(['a', 'c']);
  });

  it('깨진 값 · 문자열 아닌 항목은 버린다', () => {
    expect(readSessionIds(memoryStorage({ [SESSION_LIST_KEY]: '{깨짐' }))).toEqual([]);
    expect(readSessionIds(memoryStorage({ [SESSION_LIST_KEY]: '{"a":1}' }))).toEqual([]);
    expect(readSessionIds(memoryStorage({ [SESSION_LIST_KEY]: JSON.stringify(['a', 1, '', null, 'a', 'b']) }))).toEqual(['a', 'b']);
  });

  it('저장소가 없으면 빈 목록', () => {
    expect(readSessionIds(null)).toEqual([]);
    expect(addSessionId('a', null)).toEqual([]);
    expect(removeSessionIds(['a'], null)).toEqual([]);
  });
});
