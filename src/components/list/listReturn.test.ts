import { describe, expect, it } from 'vitest';
import { listHomeHref, listNavHref, listReturnHref, reviewNeededHref } from './listReturn';

const FULL = 'q=%EB%8C%80%EC%B6%9C&risk=high&status=done&review=needed&sort=risk';

describe('목록으로 돌아가는 주소 — 프로토타입 goList · nav · goHome', () => {
  it('기억이 없으면 모두 / (검토 필요는 ?review=needed)', () => {
    expect(listReturnHref('')).toBe('/');
    expect(listNavHref('')).toBe('/');
    expect(listHomeHref('')).toBe('/');
    expect(reviewNeededHref('')).toBe('/?review=needed');
  });

  it('상세 뒤로 · 새 분석 취소(goList)는 검색·필터·정렬을 그대로 둔다', () => {
    expect(listReturnHref(FULL)).toBe('/?' + FULL);
  });

  it("헤더 '문서 분석'은 '검토 필요' 필터만 푼다", () => {
    expect(listNavHref(FULL)).toBe('/?q=%EB%8C%80%EC%B6%9C&risk=high&status=done&sort=risk');
    // '검토 필요'가 아닌 검토 상태 필터는 그대로
    expect(listNavHref('review=done')).toBe('/?review=done');
  });

  it("헤더 '검토 필요'는 검색·위험·상태를 풀고 정렬만 둔다", () => {
    expect(reviewNeededHref(FULL)).toBe('/?review=needed&sort=risk');
  });

  it('로고(goHome)는 검색·필터를 모두 풀고 정렬만 둔다', () => {
    expect(listHomeHref(FULL)).toBe('/?sort=risk');
  });

  it('모르는 값은 버린다(정규형)', () => {
    expect(listReturnHref('risk=nope&foo=1&sort=recent')).toBe('/');
  });
});
