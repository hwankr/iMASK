import { describe, expect, it } from 'vitest';
import { NEXT_KEY, PREV_KEY, shouldIgnoreShortcut } from './DevStateBar';

const key = (k: string, extra: Partial<Parameters<typeof shouldIgnoreShortcut>[0]> = {}) => ({
  key: k,
  altKey: false,
  ctrlKey: false,
  metaKey: false,
  repeat: false,
  defaultPrevented: false,
  isComposing: false,
  ...extra,
});

describe('미리보기 막대 단축키 [ ]', () => {
  it('대괄호만 받는다', () => {
    expect(shouldIgnoreShortcut(key(PREV_KEY), null)).toBe(false);
    expect(shouldIgnoreShortcut(key(NEXT_KEY), null)).toBe(false);
    expect(shouldIgnoreShortcut(key('ArrowRight'), null)).toBe(true);
    expect(shouldIgnoreShortcut(key('Enter'), null)).toBe(true);
  });

  it('조합 키 · 길게 누름 · 이미 처리된 키 · 한글 조합 중에는 무시', () => {
    expect(shouldIgnoreShortcut(key(NEXT_KEY, { ctrlKey: true }), null)).toBe(true);
    expect(shouldIgnoreShortcut(key(NEXT_KEY, { altKey: true }), null)).toBe(true);
    expect(shouldIgnoreShortcut(key(NEXT_KEY, { metaKey: true }), null)).toBe(true);
    expect(shouldIgnoreShortcut(key(NEXT_KEY, { repeat: true }), null)).toBe(true);
    expect(shouldIgnoreShortcut(key(NEXT_KEY, { defaultPrevented: true }), null)).toBe(true);
    expect(shouldIgnoreShortcut(key(NEXT_KEY, { isComposing: true }), null)).toBe(true);
  });
});
