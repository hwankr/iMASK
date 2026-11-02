import { describe, expect, it, vi } from 'vitest';
import { ACCESS_CODE_KEY, accessCodeForHeader, clearAccessCode, readAccessCode, saveAccessCode, subscribeAccessCode } from './access-code';
import { SESSION_LIST_KEY, SESSION_LIST_MAX, addSessionId, readSessionIds, removeSessionIds } from './session-list';
import { memoryStorage } from './testing';

describe('접근 코드(sessionStorage)', () => {
  it('키 imask:demo-code 에 입력한 그대로 저장하고 읽는다', () => {
    const s = memoryStorage();
    expect(readAccessCode(s)).toBe('');
    saveAccessCode(' ab cd ', s);
    expect(s.data.get(ACCESS_CODE_KEY)).toBe(' ab cd ');
    expect(readAccessCode(s)).toBe(' ab cd ');
    expect(accessCodeForHeader(s)).toBe('ab cd');
  });

  it('빈 값(공백만)을 저장하면 지운다 · clear 도 지운다', () => {
    const s = memoryStorage({ [ACCESS_CODE_KEY]: 'x' });
    saveAccessCode('   ', s);
    expect(s.data.has(ACCESS_CODE_KEY)).toBe(false);
    saveAccessCode('y', s);
    clearAccessCode(s);
    expect(readAccessCode(s)).toBe('');
  });

  it('저장소가 없으면(서버 렌더) 빈 값이고 아무것도 하지 않는다', () => {
    expect(readAccessCode(null)).toBe('');
    expect(() => saveAccessCode('x', null)).not.toThrow();
    expect(() => clearAccessCode(null)).not.toThrow();
    expect(accessCodeForHeader(null)).toBe('');
  });

  it('기본 저장소 — Node(브라우저 아님)에서는 빈 값', () => {
    expect(readAccessCode()).toBe('');
  });

  it('저장소가 예외를 던져도 앱이 멈추지 않는다', () => {
    const broken = {
      getItem: () => {
        throw new Error('막힘');
      },
      setItem: () => {
        throw new Error('가득 참');
      },
      removeItem: () => {
        throw new Error('막힘');
      },
    };
    expect(readAccessCode(broken)).toBe('');
    expect(() => saveAccessCode('x', broken)).not.toThrow();
    expect(() => clearAccessCode(broken)).not.toThrow();
  });

  it('같은 탭의 변경을 구독자에게 알리고, 해제하면 멈춘다', () => {
    const s = memoryStorage();
    const fn = vi.fn();
    const off = subscribeAccessCode(fn);
    saveAccessCode('a', s);
    clearAccessCode(s);
    expect(fn).toHaveBeenCalledTimes(2);
    off();
    saveAccessCode('b', s);
    expect(fn).toHaveBeenCalledTimes(2);
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
