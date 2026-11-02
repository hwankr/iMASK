import { describe, expect, it } from 'vitest';
import { getDemoControls, createService } from './index';
import { SERVICE_MODE, resolveServiceMode } from './mode';

describe('서비스 모드', () => {
  it("정확히 'api' 일 때만 실제 분석, 그 밖(없음 포함)은 데모", () => {
    expect(resolveServiceMode('api')).toBe('api');
    for (const v of [undefined, null, '', 'demo', 'API', ' api', 'api ', 'true']) expect(resolveServiceMode(v)).toBe('demo');
  });

  it('테스트 환경(값 없음)은 데모 — createService 가 데모 서비스를 준다', () => {
    expect(SERVICE_MODE).toBe('demo');
    const service = createService() as ReturnType<typeof createService> & { dispose?: () => void };
    expect(getDemoControls(service)).not.toBeNull();
    service.dispose?.();
  });
});
