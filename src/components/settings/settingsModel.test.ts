import { describe, expect, it } from 'vitest';
import { workflowLabel } from './settingsModel';

const base = { agent_id: 'agt_x', config_id: '60', agent_name: null, config_name: null };

describe('workflowLabel', () => {
  it('이름이 있으면 이름 · 설정 번호', () => {
    expect(workflowLabel({ ...base, agent_name: 'v2_full', config_name: '최종' })).toBe('v2_full · 설정 60');
  });

  it('이름을 못 읽으면 설정 번호만', () => {
    expect(workflowLabel(base)).toBe('설정 60');
  });
});
