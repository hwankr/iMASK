import { describe, expect, it } from 'vitest';
import { isCurrentPreset, workflowLabel } from './settingsModel';

const base = { agent_id: 'agt_x', config_id: '60', agent_name: null, config_name: null };

describe('workflowLabel', () => {
  it('이름이 있으면 이름 · 설정 번호', () => {
    expect(workflowLabel({ ...base, agent_name: 'v2_full', config_name: '최종' })).toBe('v2_full · 설정 60');
  });

  it('이름을 못 읽으면 설정 번호만', () => {
    expect(workflowLabel(base)).toBe('설정 60');
  });
});

describe('isCurrentPreset', () => {
  const preset = { id: 'a', name: '이름', agent_id: 'agt_x', config_id: '60' };

  it('에이전트 ID · 설정 번호가 둘 다 같아야 지금 적용이다', () => {
    expect(isCurrentPreset(preset, base)).toBe(true);
    expect(isCurrentPreset({ ...preset, agent_id: 'agt_y' }, base)).toBe(false);
    expect(isCurrentPreset({ ...preset, config_id: '61' }, base)).toBe(false);
  });

  it('이름은 보지 않는다 — 값이 같으면 다른 이름이어도 지금 적용', () => {
    expect(isCurrentPreset({ ...preset, name: '다른 이름' }, { ...base, agent_name: 'v2_full' })).toBe(true);
  });

  it('값을 다듬지 않고 그대로 비교한다', () => {
    expect(isCurrentPreset({ ...preset, config_id: '060' }, base)).toBe(false);
    expect(isCurrentPreset({ ...preset, agent_id: 'AGT_X' }, base)).toBe(false);
  });
});
