import { describe, expect, it } from 'vitest';
import { clamp, fmtDT, fmtSize, nowStr, pad2, utf8Len } from './format';

describe('pad2', () => {
  it('한 자리를 두 자리로 채운다', () => {
    expect(pad2(7)).toBe('07');
    expect(pad2(12)).toBe('12');
    expect(pad2('3')).toBe('03');
  });
});

describe('nowStr', () => {
  it("'YYYY-MM-DD HH:mm' 형식", () => {
    expect(nowStr(new Date(2026, 9, 3, 9, 5))).toBe('2026-10-03 09:05');
  });
  it('인자가 없으면 지금 시각', () => {
    expect(nowStr()).toMatch(/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$/);
  });
});

describe('fmtDT', () => {
  it('하이픈을 점으로 바꾸고 분까지 자른다', () => {
    expect(fmtDT('2026-10-30 14:22')).toBe('2026.10.30 14:22');
    expect(fmtDT('2026-10-30 14:22:59')).toBe('2026.10.30 14:22');
  });
  it('값이 없으면 -', () => {
    expect(fmtDT('')).toBe('-');
    expect(fmtDT(null)).toBe('-');
    expect(fmtDT(undefined)).toBe('-');
  });
});

describe('fmtSize', () => {
  it('1MB 미만은 KB(최소 1KB)', () => {
    expect(fmtSize(0)).toBe('1KB');
    expect(fmtSize(418611)).toBe('409KB');
    expect(fmtSize(1048575)).toBe('1024KB');
  });
  it('1MB 이상은 소수 한 자리 MB', () => {
    expect(fmtSize(1048576)).toBe('1.0MB');
    expect(fmtSize(1258291)).toBe('1.2MB');
    expect(fmtSize(20 * 1048576)).toBe('20.0MB');
  });
  it('값이 없으면 -', () => {
    expect(fmtSize(null)).toBe('-');
    expect(fmtSize(undefined)).toBe('-');
  });
});

describe('clamp', () => {
  it('범위 안으로 자른다', () => {
    expect(clamp(5, 1, 3)).toBe(3);
    expect(clamp(-1, 0, 10)).toBe(0);
    expect(clamp(4, 0, 10)).toBe(4);
  });
});

describe('utf8Len', () => {
  it('UTF-8 바이트 수', () => {
    expect(utf8Len('abc')).toBe(3);
    expect(utf8Len('가')).toBe(3);
    expect(utf8Len('﻿')).toBe(3);
    expect(utf8Len('')).toBe(0);
  });
});
