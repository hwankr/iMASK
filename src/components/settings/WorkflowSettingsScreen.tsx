'use client';

/* ==========================================================================
   워크플로우 설정 — 분석에 쓸 Upstage 에이전트 ID · 설정 번호를 재배포 없이 바꾼다(실제 분석 모드만)
   - 비밀번호로 연 뒤 지금 값을 채운 입력칸을 보인다. 비밀번호는 이 화면의 상태에만 두고 저장하지 않는다.
   - 값 검사(꼴 · Upstage 에 있는지)는 서버가 하고, 화면은 서버 문장을 그대로 보인다.
   - 데모 모드(데모 빌드 · `/demo`)에는 백엔드가 없어 이 화면이 없다(404).
   ========================================================================== */

import { notFound } from 'next/navigation';
import { useState, type FormEvent } from 'react';
import { Button, Icon, TextField, useToast } from '@/components/ui';
import { createApiClient, type WorkflowSettingsOut } from '@/services/api/client';
import { useServiceMode } from '@/services/react';
import { workflowLabel } from './settingsModel';
import styles from './WorkflowSettingsScreen.module.css';

const client = createApiClient();
const MSG_FAILED = '요청을 처리하지 못했습니다. 잠시 후 다시 시도해 주세요.';
const SAVED_TOAST = '저장했습니다. 다음 분석부터 적용됩니다.';

const messageOf = (err: unknown): string => (err instanceof Error && err.message ? err.message : MSG_FAILED);

export function WorkflowSettingsScreen() {
  const mode = useServiceMode();
  if (mode !== 'api') notFound();
  return <SettingsForms />;
}

function SettingsForms() {
  const toast = useToast();
  const [password, setPassword] = useState('');
  const [current, setCurrent] = useState<WorkflowSettingsOut | null>(null);
  const [agentId, setAgentId] = useState('');
  const [configId, setConfigId] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const show = (workflow: WorkflowSettingsOut) => {
    setCurrent(workflow);
    setAgentId(workflow.agent_id);
    setConfigId(workflow.config_id);
  };

  const run = async (work: () => Promise<void>) => {
    setBusy(true);
    setError('');
    try {
      await work();
    } catch (err) {
      setError(messageOf(err));
    } finally {
      setBusy(false);
    }
  };

  const onOpen = (e: FormEvent) => {
    e.preventDefault();
    void run(async () => show(await client.openWorkflowSettings(password)));
  };

  const onSave = (e: FormEvent) => {
    e.preventDefault();
    void run(async () => {
      show(await client.saveWorkflowSettings({ password, agent_id: agentId, config_id: configId }));
      toast(SAVED_TOAST);
    });
  };

  const alert = error ? (
    <div role="alert" className={styles.alert}>
      <span className={styles.alertIcon}>
        <Icon name="dg-i-x-circle" size={18} strokeWidth={2.1} />
      </span>
      <span>{error}</span>
    </div>
  ) : null;

  return (
    <div className={styles.screen}>
      <div className={styles.content}>
        <h1 className={styles.title}>워크플로우 설정</h1>
        {current ? (
          <form className={styles.form} onSubmit={onSave} noValidate aria-busy={busy || undefined}>
            <p className={styles.current}>
              <span className={styles.currentLabel}>지금 적용</span>
              <strong>{workflowLabel(current)}</strong>
            </p>
            {alert}
            <TextField label="에이전트 ID" value={agentId} onChange={(e) => setAgentId(e.target.value)} disabled={busy} autoComplete="off" />
            <TextField
              label="설정 번호"
              value={configId}
              onChange={(e) => setConfigId(e.target.value)}
              disabled={busy}
              inputMode="numeric"
              autoComplete="off"
            />
            <div className={styles.actions}>
              <Button type="submit" variant="primary" size="lg" loading={busy}>
                저장
              </Button>
            </div>
          </form>
        ) : (
          <form className={styles.form} onSubmit={onOpen} noValidate aria-busy={busy || undefined}>
            {alert}
            <TextField
              label="비밀번호"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              disabled={busy}
              autoFocus
              autoComplete="off"
            />
            <div className={styles.actions}>
              <Button type="submit" variant="primary" size="lg" loading={busy}>
                열기
              </Button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
