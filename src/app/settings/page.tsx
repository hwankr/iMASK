import type { Metadata } from 'next';
import { WorkflowSettingsScreen } from '@/components/settings/WorkflowSettingsScreen';

export const metadata: Metadata = { title: '워크플로우 설정' };

/** /settings 워크플로우 설정(실제 분석 모드만). `<main>` 은 AppShell 이 그린다. */
export default function SettingsPage() {
  return <WorkflowSettingsScreen />;
}
