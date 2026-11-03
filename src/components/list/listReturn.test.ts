import { describe, expect, it } from 'vitest';
import { activeNav, listHomeHref, listNavHref, listReturnHref, reviewNeededHref } from './listReturn';

const FULL = 'q=%EB%8C%80%EC%B6%9C&risk=high&status=done&review=needed&sort=risk';

describe('목록으로 돌아가는 주소 — 프로토타입 goList · nav · goHome (루트 기준)', () => {
  it('기억이 없으면 모두 / (검토 필요는 ?review=needed)', () => {
    expect(listReturnHref('', '')).toBe('/');
    expect(listNavHref('', '')).toBe('/');
    expect(listHomeHref('', '')).toBe('/');
    expect(reviewNeededHref('', '')).toBe('/?review=needed');
  });

  it('상세 뒤로 · 새 분석 취소(goList)는 검색·필터·정렬을 그대로 둔다', () => {
    expect(listReturnHref('', FULL)).toBe('/?' + FULL);
  });

  it("헤더 '문서 분석'은 '검토 필요' 필터만 푼다", () => {
    expect(listNavHref('', FULL)).toBe('/?q=%EB%8C%80%EC%B6%9C&risk=high&status=done&sort=risk');
    // '검토 필요'가 아닌 검토 상태 필터는 그대로
    expect(listNavHref('', 'review=done')).toBe('/?review=done');
  });

  it("헤더 '검토 필요'는 검색·위험·상태를 풀고 정렬만 둔다", () => {
    expect(reviewNeededHref('', FULL)).toBe('/?review=needed&sort=risk');
  });

  it('로고(goHome)는 검색·필터를 모두 풀고 정렬만 둔다', () => {
    expect(listHomeHref('', FULL)).toBe('/?sort=risk');
  });

  it('모르는 값은 버린다(정규형)', () => {
    expect(listReturnHref('', 'risk=nope&foo=1&sort=recent')).toBe('/');
  });
});

describe('목록으로 돌아가는 주소 — /demo 기준', () => {
  it('기억이 없으면 모두 /demo (검토 필요는 /demo?review=needed)', () => {
    expect(listReturnHref('/demo', '')).toBe('/demo');
    expect(listNavHref('/demo', '')).toBe('/demo');
    expect(listHomeHref('/demo', '')).toBe('/demo');
    expect(reviewNeededHref('/demo', '')).toBe('/demo?review=needed');
  });

  it('같은 규칙 — 결과만 /demo 아래', () => {
    expect(listReturnHref('/demo', FULL)).toBe('/demo?' + FULL);
    expect(listNavHref('/demo', FULL)).toBe('/demo?q=%EB%8C%80%EC%B6%9C&risk=high&status=done&sort=risk');
    expect(listNavHref('/demo', 'review=done')).toBe('/demo?review=done');
    expect(reviewNeededHref('/demo', FULL)).toBe('/demo?review=needed&sort=risk');
    expect(listHomeHref('/demo', FULL)).toBe('/demo?sort=risk');
    expect(listReturnHref('/demo', 'risk=nope&foo=1&sort=recent')).toBe('/demo');
  });

  it('루트 기준 결과에 /demo 를 붙인 것과 같다', () => {
    for (const q of ['', FULL, 'review=done', 'sort=risk', 'risk=high']) {
      for (const fn of [listReturnHref, listNavHref, reviewNeededHref, listHomeHref]) {
        const root = fn('', q);
        expect(fn('/demo', q)).toBe(root === '/' ? '/demo' : '/demo' + root.slice(1));
      }
    }
  });
});

describe("헤더 주 메뉴 활성 — activeNav", () => {
  it("목록 경로(/ · /demo)에서 review=needed 일 때만 '검토 필요'", () => {
    expect(activeNav('/', 'needed')).toBe('review');
    expect(activeNav('/demo', 'needed')).toBe('review');
  });

  it("그 밖에는 '문서 분석'", () => {
    expect(activeNav('/', null)).toBe('analyses');
    expect(activeNav('/', 'done')).toBe('analyses');
    expect(activeNav('/demo', null)).toBe('analyses');
    expect(activeNav('/demo', 'all')).toBe('analyses');
    for (const p of ['/analyses/A1', '/analyses/new', '/demo/analyses/A1', '/demo/analyses/new', '/demox', '/Demo', '/dev/states']) {
      expect(activeNav(p, 'needed'), p).toBe('analyses');
    }
    expect(activeNav(null, 'needed')).toBe('analyses');
  });
});
