import type { WorkflowSettingsOut } from '@/services/api/client';

/** 지금 적용 중인 워크플로우 글 — 'v2_full · 설정 60'. 이름을 못 읽으면 에이전트 ID 는 입력칸에 있으니 설정 번호만 */
export function workflowLabel(workflow: WorkflowSettingsOut): string {
  const config = `설정 ${workflow.config_id}`;
  return workflow.agent_name ? `${workflow.agent_name} · ${config}` : config;
}
