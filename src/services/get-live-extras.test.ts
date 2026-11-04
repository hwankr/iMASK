import { describe, expect, it } from 'vitest';
import type { AnalysisService } from './analysis-service';
import { createApiService } from './api';
import { createDemoService } from './demo';
import { getDemoControls, getLiveExtras } from './index';

describe('getLiveExtras — 실제 분석 전용 통로', () => {
  it('실제 분석 서비스면 그 서비스(loadFile · loadStages)', () => {
    const api = createApiService({ upload: async () => {} });
    const extras = getLiveExtras(api);
    expect(extras).toBe(api);
    expect(typeof extras?.loadFile).toBe('function');
    expect(typeof extras?.loadStages).toBe('function');
    expect(getDemoControls(api)).toBeNull();
  });

  it('데모 서비스 · null · undefined · 흉내 낸 객체면 null', () => {
    const demo = createDemoService();
    try {
      expect(getLiveExtras(demo)).toBeNull();
      expect(getDemoControls(demo)).toBe(demo);
    } finally {
      demo.dispose();
    }
    expect(getLiveExtras(null)).toBeNull();
    expect(getLiveExtras(undefined)).toBeNull();
    const fake = { loadFile: async () => null, loadStages: async () => null } as unknown as AnalysisService;
    expect(getLiveExtras(fake)).toBeNull();
  });
});
