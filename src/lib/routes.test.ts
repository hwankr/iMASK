import { describe, expect, it } from 'vitest';
import { DEMO_BASE, detailHref, isDemoPath, listHref, newAnalysisHref, reportHref, routeBaseFor, withBase, type RouteBase } from './routes';

describe('isDemoPath · routeBaseFor — `/demo` 아래인지', () => {
  const YES = ['/demo', '/demo/', '/demo/analyses', '/demo/analyses/A1', '/demo/analyses/A1/report', '/demo/analyses/new', '/demo/x/y'];
  const NO: (string | null | undefined)[] = ['/demox', '/demo-x', '/Demo', '/DEMO', '/Demo/analyses', '/analyses/demo', '/dev/demo', 'demo', 'demo/analyses', '/', '/analyses/new', '/dev/states', '', null, undefined];

  it('정확히 /demo 이거나 /demo/ 로 시작하면 true(기준 /demo)', () => {
    for (const p of YES) {
      expect(isDemoPath(p), p).toBe(true);
      expect(routeBaseFor(p), p).toBe('/demo');
    }
  });

  it('비슷한 글자 · 대소문자 · 중간의 demo · 빈 값은 false(루트 기준)', () => {
    for (const p of NO) {
      expect(isDemoPath(p), String(p)).toBe(false);
      expect(routeBaseFor(p), String(p)).toBe('');
    }
  });

  it('DEMO_BASE 는 /demo', () => {
    expect(DEMO_BASE).toBe('/demo');
  });
});

describe('withBase — 기준 경로 붙이기', () => {
  const TABLE: [string, string, string][] = [
    // [앱 경로, 기준 '' 결과, 기준 /demo 결과]
    ['/', '/', '/demo'],
    ['/?q=1', '/?q=1', '/demo?q=1'],
    ['/#h', '/#h', '/demo#h'],
    ['/?review=needed&sort=risk', '/?review=needed&sort=risk', '/demo?review=needed&sort=risk'],
    ['/analyses/new', '/analyses/new', '/demo/analyses/new'],
    ['/analyses/new?sample=1', '/analyses/new?sample=1', '/demo/analyses/new?sample=1'],
    ['/analyses/A1', '/analyses/A1', '/demo/analyses/A1'],
    ['/analyses/A1/report', '/analyses/A1/report', '/demo/analyses/A1/report'],
  ];

  it('루트 기준은 그대로, /demo 는 앞에 붙인다(/ · /? · /# 는 /demo · /demo? · /demo#)', () => {
    for (const [path, root, demo] of TABLE) {
      expect(withBase('', path), path).toBe(root);
      expect(withBase('/demo', path), path).toBe(demo);
    }
  });

  it('/ 로 시작하지 않는 경로는 프로그래밍 실수 — 예외', () => {
    for (const bad of ['', 'analyses/new', '?q=1', '#h', 'https://example.com/', ' /']) {
      for (const base of ['', '/demo'] as const) expect(() => withBase(base, bad), JSON.stringify(bad)).toThrow();
    }
  });
});

describe('이동 주소 — 루트 기준 결과는 예전 화면의 글자 만들기와 바이트 단위로 같다', () => {
  /** 예전 코드가 직접 만들던 글자(바뀌기 전 화면의 식 그대로) */
  const legacy = {
    list: (q: string) => (q ? '/?' + q : '/'),
    newAnalysis: '/analyses/new',
    trySample: '/analyses/new?sample=1',
    detail: (id: string) => `/analyses/${encodeURIComponent(id)}`,
    detailConcat: (id: string) => '/analyses/' + encodeURIComponent(id),
    report: (id: string) => `/analyses/${encodeURIComponent(id)}/report`,
  };
  const IDS = ['A1', 'A 1/2?#%', '대출상담-서류', '', 'done-pdf', '../x', 'a+b&c=d'];
  const QUERIES = ['', 'review=needed', 'q=%EB%8C%80%EC%B6%9C&risk=high&sort=risk'];

  it('목록 · 새 분석', () => {
    expect(listHref('')).toBe('/');
    for (const q of QUERIES) expect(listHref('', q)).toBe(legacy.list(q));
    expect(newAnalysisHref('')).toBe(legacy.newAnalysis);
    expect(newAnalysisHref('', { sample: false })).toBe(legacy.newAnalysis);
    expect(newAnalysisHref('', { sample: true })).toBe(legacy.trySample);
  });

  it('상세 · 보고서 — 특수 문자 · 한글 · 빈 id 도 encodeURIComponent 그대로', () => {
    for (const id of IDS) {
      expect(detailHref('', id), id).toBe(legacy.detail(id));
      expect(detailHref('', id), id).toBe(legacy.detailConcat(id));
      expect(reportHref('', id), id).toBe(legacy.report(id));
    }
    expect(detailHref('', 'A 1/2?#%')).toBe('/analyses/A%201%2F2%3F%23%25');
    expect(reportHref('', '대출')).toBe('/analyses/%EB%8C%80%EC%B6%9C/report');
    expect(detailHref('', '')).toBe('/analyses/');
  });

  it('기준 /demo — 같은 글자 앞에 /demo', () => {
    const base: RouteBase = '/demo';
    expect(listHref(base)).toBe('/demo');
    expect(listHref(base, 'review=needed')).toBe('/demo?review=needed');
    expect(newAnalysisHref(base)).toBe('/demo/analyses/new');
    expect(newAnalysisHref(base, { sample: true })).toBe('/demo/analyses/new?sample=1');
    for (const id of IDS) {
      expect(detailHref(base, id), id).toBe('/demo' + legacy.detail(id));
      expect(reportHref(base, id), id).toBe('/demo' + legacy.report(id));
    }
    expect(detailHref(base, 'A 1/2?#%')).toBe('/demo/analyses/A%201%2F2%3F%23%25');
  });

  it('만든 주소는 다시 같은 기준으로 읽힌다', () => {
    for (const base of ['', '/demo'] as const) {
      for (const href of [listHref(base), newAnalysisHref(base), detailHref(base, 'A1'), reportHref(base, 'A1')]) {
        expect(routeBaseFor(href.split(/[?#]/)[0]), href).toBe(base);
      }
    }
  });
});
