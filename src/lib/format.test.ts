/* 형식 도우미 테스트. fmtSize 는 백엔드와 같이 쓰는 크기 표(tests/fmt_size_cases.json — 파이썬 fmt_size 도 같은 표로
   확인한다)의 모든 줄과 같은 글자를 내야 한다(내보내기 이력 줄의 크기 표기 = 화면 표기). */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import { clamp, fmtDT, fmtSize, nowStr, pad2, utf8Len } from './format';

const SIZE_CASES_PATH = fileURLToPath(new URL('../../tests/fmt_size_cases.json', import.meta.url));

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
  it('공유 크기 표(tests/fmt_size_cases.json)의 모든 줄과 같다 — 백엔드 fmt_size 와 같은 표', () => {
    const cases: unknown = JSON.parse(readFileSync(SIZE_CASES_PATH, 'utf8'));
    // 표 모양: [[정수 바이트, "글자"], …] — 비지 않고, 바이트는 0 이상 정수 오름차순(겹침 없음)
    expect(Array.isArray(cases)).toBe(true);
    const rows = cases as unknown[];
    expect(rows.length).toBeGreaterThan(0);
    let last = -1;
    for (const row of rows) {
      expect(Array.isArray(row) && row.length === 2).toBe(true);
      const [bytes, text] = row as [unknown, unknown];
      expect(Number.isSafeInteger(bytes) && (bytes as number) >= 0).toBe(true);
      expect(typeof text).toBe('string');
      expect(bytes as number).toBeGreaterThan(last);
      last = bytes as number;
    }
    const got = (rows as [number, string][]).map(([bytes]) => [bytes, fmtSize(bytes)]);
    expect(got).toEqual(rows);
    // 동점 경계(KB 2,560 · MB 소수 첫째 자리 1,310,720)가 표에 있다 — JS 의 '절반은 올림'
    expect(rows).toContainEqual([2560, '3KB']);
    expect(rows).toContainEqual([1310720, '1.3MB']);
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
