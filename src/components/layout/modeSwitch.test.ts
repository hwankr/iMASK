import { describe, expect, it } from 'vitest';
import { modeSwitchLink, TO_DEMO, TO_LIVE } from './modeSwitch';

describe('헤더 모드 전환 링크', () => {
  it('실제 분석 화면(실제 모드 빌드의 루트)에서는 데모로 간다', () => {
    expect(modeSwitchLink('api', 'api')).toBe(TO_DEMO);
    expect(TO_DEMO.href).toBe('/demo');
    expect(TO_DEMO.label).toBe('데모 체험하기');
    expect(TO_DEMO.short).toBe('데모');
  });

  it('실제 모드 빌드의 /demo 아래에서는 실제 분석 목록으로 돌아간다', () => {
    expect(modeSwitchLink('demo', 'api')).toBe(TO_LIVE);
    expect(TO_LIVE.href).toBe('/');
    expect(TO_LIVE.label).toBe('실제 분석으로');
    expect(TO_LIVE.short).toBe('실제');
  });

  it('데모 빌드에는 전환 링크가 없다(루트도 데모)', () => {
    expect(modeSwitchLink('demo', 'demo')).toBeNull();
  });

  it('글자는 비어 있지 않고, 짧은 글자는 긴 글자보다 짧다', () => {
    for (const l of [TO_DEMO, TO_LIVE]) {
      expect(l.label.length).toBeGreaterThan(0);
      expect(l.title.length).toBeGreaterThan(0);
      expect(l.short.length).toBeLessThan(l.label.length);
    }
  });
});
