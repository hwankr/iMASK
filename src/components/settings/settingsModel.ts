import type { WorkflowPresetOut, WorkflowSettingsOut } from '@/services/api/client';

/** 지금 적용 중인 워크플로우 글 — 'v2_full · 설정 60'. 이름을 못 읽으면 설정 번호만 */
export function workflowLabel(workflow: WorkflowSettingsOut): string {
  const config = `설정 ${workflow.config_id}`;
  return workflow.agent_name ? `${workflow.agent_name} · ${config}` : config;
}

/** 목록의 이 항목이 지금 적용 값과 같은가 — 에이전트 ID · 설정 번호 둘 다 같아야 한다 */
export function isCurrentPreset(preset: WorkflowPresetOut, current: WorkflowSettingsOut): boolean {
  return preset.agent_id === current.agent_id && preset.config_id === current.config_id;
}
