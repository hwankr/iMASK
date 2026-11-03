import { describe, expect, it } from 'vitest';
import type { AnalysisService } from './analysis-service';
import { getDemoControls, getLiveExtras, createService, createServiceCache, createServiceFor } from './index';
import { SERVICE_MODE, modeForPath, resolveServiceMode, type ServiceMode } from './mode';

type Disposable = AnalysisService & { dispose?: () => void };

describe('서비스 모드', () => {
  it("정확히 'api' 일 때만 실제 분석, 그 밖(없음 포함)은 데모", () => {
    expect(resolveServiceMode('api')).toBe('api');
    for (const v of [undefined, null, '', 'demo', 'API', ' api', 'api ', 'true']) expect(resolveServiceMode(v)).toBe('demo');
  });

  it('테스트 환경(값 없음)은 데모 — createService 가 데모 서비스를 준다', () => {
    expect(SERVICE_MODE).toBe('demo');
    const service = createService() as Disposable;
    expect(getDemoControls(service)).not.toBeNull();
    service.dispose?.();
  });
});

describe('주소 기준 모드 — modeForPath', () => {
  /** `/demo` 아래 — 빌드 모드와 상관없이 데모 */
  const DEMO_PATHS = ['/demo', '/demo/', '/demo/analyses/A1/report', '/demo/analyses/new'];
  /** 그 밖 — 빌드 모드를 따른다(비슷한 글자 · 대소문자 · 중간의 demo · 빈 값 포함) */
  const OTHER_PATHS: (string | null | undefined)[] = ['/demox', '/demo-x', '/Demo', '/DEMO/analyses', '/analyses/demo', '/', '/analyses/new', '/dev/states', '', null, undefined];

  for (const build of ['demo', 'api'] as const satisfies readonly ServiceMode[]) {
    it(`빌드 모드 '${build}' — /demo 아래는 'demo', 그 밖은 '${build}'`, () => {
      for (const p of DEMO_PATHS) expect(modeForPath(p, build), String(p)).toBe('demo');
      for (const p of OTHER_PATHS) expect(modeForPath(p, build), String(p)).toBe(build);
    });
  }
});

describe('모드별 서비스 캐시 — createServiceCache', () => {
  /** 만들기 횟수를 세는 가짜 공장 — 서비스 객체는 모드 이름만 가진 빈 객체 */
  function countingFactory() {
    const made: ServiceMode[] = [];
    const factory = (mode: ServiceMode) => {
      made.push(mode);
      return { mode } as unknown as AnalysisService;
    };
    return { made, factory };
  }

  it('처음 쓸 때만 만든다 — 같은 모드는 같은 객체', () => {
    const { made, factory } = countingFactory();
    const cache = createServiceCache(factory);
    expect(made).toEqual([]); // 만들기 전에는 아무것도 없다
    const a = cache.get('demo');
    expect(cache.get('demo')).toBe(a);
    expect(cache.get('demo')).toBe(a);
    expect(made).toEqual(['demo']);
  });

  it('두 모드는 다른 객체이고, 모드를 오가도 다시 만들지 않는다', () => {
    const { made, factory } = countingFactory();
    const cache = createServiceCache(factory);
    const demo = cache.get('demo');
    const api = cache.get('api');
    expect(api).not.toBe(demo);
    for (let i = 0; i < 3; i++) {
      expect(cache.get('api')).toBe(api);
      expect(cache.get('demo')).toBe(demo);
    }
    expect(made).toEqual(['demo', 'api']);
  });

  it('쓰지 않은 모드는 만들지 않는다(실제 분석만 쓰면 데모 서비스 · 타이머가 없다)', () => {
    const { made, factory } = countingFactory();
    const cache = createServiceCache(factory);
    cache.get('api');
    cache.get('api');
    expect(made).toEqual(['api']);
  });

  it('기본 공장(createServiceFor) — 모드별로 실제 서비스 종류가 맞다', () => {
    const cache = createServiceCache();
    const demo = cache.get('demo') as Disposable;
    const api = cache.get('api');
    try {
      expect(getDemoControls(demo)).toBe(demo);
      expect(getLiveExtras(demo)).toBeNull();
      expect(getLiveExtras(api)).toBe(api);
      expect(getDemoControls(api)).toBeNull();
      expect(cache.get('demo')).toBe(demo);
      expect(cache.get('api')).toBe(api);
    } finally {
      demo.dispose?.();
    }
  });

  it('createServiceFor — 부를 때마다 새 서비스(캐시는 Provider 쪽)', () => {
    const d1 = createServiceFor('demo') as Disposable;
    const d2 = createServiceFor('demo') as Disposable;
    try {
      expect(d1).not.toBe(d2);
      expect(getDemoControls(d1)).toBe(d1);
      expect(getLiveExtras(createServiceFor('api'))).not.toBeNull();
    } finally {
      d1.dispose?.();
      d2.dispose?.();
    }
  });
});
