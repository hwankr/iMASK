'use client';

/* ==========================================================================
   워크플로우 설정 — 분석에 쓸 Upstage 에이전트 ID · 설정 번호를 재배포 없이 바꾼다(실제 분석 모드만)
   - 비밀번호로 연 뒤 지금 적용 값 · 등록해 둔 목록 · 등록 폼을 보인다. 비밀번호는 이 화면의 상태에만 두고 저장하지 않는다.
   - 적용 = 고른 항목의 값을 저장 경로(saveWorkflowSettings)로 지금 적용 값에 복사한다. 등록 · 삭제는 지금 적용 값을 바꾸지 않는다.
   - 값 검사(꼴 · Upstage 에 있는지 · 이름)는 서버가 하고, 화면은 서버 문장을 그대로 보인다. 실패하면 화면의 값은 바뀌지 않는다.
   - 요청 중에는 모든 버튼을 막는다. 포커스를 잃지 않게 disabled 대신 aria-disabled · readOnly 를 쓰고,
     눌렀던 버튼이 사라지면(적용 · 삭제) 다음 그림 뒤에 포커스를 옮긴다.
   - 데모 모드(데모 빌드 · `/demo`)에는 백엔드가 없어 이 화면이 없다(404).
   ========================================================================== */

import { notFound } from 'next/navigation';
import { useEffect, useRef, useState, type FormEvent } from 'react';
import { Button, Icon, TextField, useToast } from '@/components/ui';
import { createApiClient, type WorkflowPresetOut, type WorkflowSettingsOut } from '@/services/api/client';
import { useServiceMode } from '@/services/react';
import { isCurrentPreset, workflowLabel } from './settingsModel';
import styles from './WorkflowSettingsScreen.module.css';

const client = createApiClient();
const MSG_FAILED = '요청을 처리하지 못했습니다. 잠시 후 다시 시도해 주세요.';
const APPLIED_TOAST = '다음 분석부터 적용됩니다.';
const ADDED_TOAST = '등록했습니다.';
const DELETED_TOAST = '삭제했습니다.';

/* 제목 이어 주기 · 포커스를 옮길 곳의 id */
const ID_CURRENT = 'settings-current';
const ID_LIST_TITLE = 'settings-presets-title';
const ID_ADD_TITLE = 'settings-add-title';
const ID_NAME = 'settings-preset-name';
const idPresetMark = (id: string) => `settings-preset-current-${id}`;

/* 진행 중인 동작 · 오류 자리의 열쇠 */
const KEY_OPEN = 'open';
const KEY_ADD = 'add';
const keyApply = (id: string) => `apply:${id}`;
const keyDelete = (id: string) => `delete:${id}`;

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
  const [presets, setPresets] = useState<WorkflowPresetOut[]>([]);
  const [name, setName] = useState('');
  const [agentId, setAgentId] = useState('');
  const [configId, setConfigId] = useState('');
  const [pending, setPending] = useState<string | null>(null);
  const [error, setError] = useState<{ key: string; message: string } | null>(null);
  const busy = pending !== null;

  // 다음 그림 뒤에 포커스를 옮길 요소 id
  const focusNext = useRef<string | null>(null);
  useEffect(() => {
    if (focusNext.current === null) return;
    document.getElementById(focusNext.current)?.focus();
    focusNext.current = null;
  });

  const run = async (key: string, work: () => Promise<void>) => {
    setPending(key);
    setError(null);
    try {
      await work();
    } catch (err) {
      setError({ key, message: messageOf(err) });
    } finally {
      setPending(null);
    }
  };

  const onOpen = (e: FormEvent) => {
    e.preventDefault();
    void run(KEY_OPEN, async () => {
      const { presets: list, ...workflow } = await client.openWorkflowSettings(password);
      setCurrent(workflow);
      setPresets(list);
      focusNext.current = ID_CURRENT;
    });
  };

  const onAdd = (e: FormEvent) => {
    e.preventDefault();
    void run(KEY_ADD, async () => {
      const out = await client.addWorkflowPreset({ password, name, agent_id: agentId, config_id: configId });
      setPresets(out.presets);
      setName('');
      setAgentId('');
      setConfigId('');
      toast(ADDED_TOAST);
    });
  };

  const onApply = (preset: WorkflowPresetOut) => {
    void run(keyApply(preset.id), async () => {
      setCurrent(await client.saveWorkflowSettings({ password, agent_id: preset.agent_id, config_id: preset.config_id }));
      focusNext.current = idPresetMark(preset.id);
      toast(APPLIED_TOAST);
    });
  };

  const onDelete = (preset: WorkflowPresetOut) => {
    void run(keyDelete(preset.id), async () => {
      const out = await client.deleteWorkflowPreset({ password, id: preset.id });
      setPresets(out.presets);
      focusNext.current = out.presets.length > 0 ? ID_LIST_TITLE : ID_NAME;
      toast(DELETED_TOAST);
    });
  };

  /** 그 동작의 오류 — 눌렀던 자리 가까이에 보인다(목록이 길어도 눈에 들어오게) */
  const alertFor = (...keys: string[]) =>
    error && keys.includes(error.key) ? (
      <div role="alert" className={styles.alert}>
        <span className={styles.alertIcon}>
          <Icon name="dg-i-x-circle" size={18} strokeWidth={2.1} />
        </span>
        <span>{error.message}</span>
      </div>
    ) : null;

  return (
    <div className={styles.screen}>
      <div className={styles.content}>
        <h1 className={styles.title}>워크플로우 설정</h1>
        {current ? (
          <>
            <p id={ID_CURRENT} tabIndex={-1} className={styles.current}>
              <span className={styles.currentLabel}>지금 적용</span>
              <strong className={styles.currentValue}>{workflowLabel(current)}</strong>
            </p>

            {presets.length > 0 ? (
              <section className={styles.section} aria-labelledby={ID_LIST_TITLE}>
                <h2 id={ID_LIST_TITLE} tabIndex={-1} className={styles.sectionTitle}>
                  워크플로우 목록
                </h2>
                <ul className={styles.list} aria-busy={busy || undefined}>
                  {presets.map((preset) => (
                    <li key={preset.id} className={styles.row}>
                      <div className={styles.rowMain}>
                        <div className={styles.rowHead}>
                          <span className={styles.rowName}>{preset.name}</span>
                          <span className={styles.rowConfig}>설정 {preset.config_id}</span>
                        </div>
                        <div className={styles.rowAgent}>{preset.agent_id}</div>
                      </div>
                      <div className={styles.rowActions}>
                        {isCurrentPreset(preset, current) ? (
                          <span id={idPresetMark(preset.id)} tabIndex={-1} className={styles.rowCurrent}>
                            지금 적용
                          </span>
                        ) : (
                          <Button
                            variant="secondary"
                            size="sm"
                            aria-label={`${preset.name} 적용`}
                            aria-disabled={busy || undefined}
                            loading={pending === keyApply(preset.id)}
                            onClick={() => onApply(preset)}
                          >
                            적용
                          </Button>
                        )}
                        <Button
                          variant="ghost"
                          size="sm"
                          aria-label={`${preset.name} 삭제`}
                          aria-disabled={busy || undefined}
                          loading={pending === keyDelete(preset.id)}
                          onClick={() => onDelete(preset)}
                        >
                          삭제
                        </Button>
                      </div>
                      {alertFor(keyApply(preset.id), keyDelete(preset.id))}
                    </li>
                  ))}
                </ul>
              </section>
            ) : null}

            <form className={styles.form} onSubmit={onAdd} noValidate aria-busy={busy || undefined} aria-labelledby={ID_ADD_TITLE}>
              <h2 id={ID_ADD_TITLE} className={styles.sectionTitle}>
                워크플로우 등록
              </h2>
              {alertFor(KEY_ADD)}
              <TextField id={ID_NAME} label="이름" value={name} onChange={(e) => setName(e.target.value)} readOnly={busy} autoComplete="off" />
              <TextField label="에이전트 ID" value={agentId} onChange={(e) => setAgentId(e.target.value)} readOnly={busy} autoComplete="off" />
              <TextField
                label="설정 번호"
                value={configId}
                onChange={(e) => setConfigId(e.target.value)}
                readOnly={busy}
                inputMode="numeric"
                autoComplete="off"
              />
              <div className={styles.actions}>
                <Button type="submit" variant="primary" size="lg" aria-disabled={busy || undefined} loading={pending === KEY_ADD}>
                  등록
                </Button>
              </div>
            </form>
          </>
        ) : (
          <form className={styles.form} onSubmit={onOpen} noValidate aria-busy={busy || undefined}>
            {alertFor(KEY_OPEN)}
            <TextField
              label="비밀번호"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              readOnly={busy}
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
