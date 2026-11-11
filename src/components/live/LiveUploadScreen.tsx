'use client';

/* ==========================================================================
   새 분석 — 실제 분석 모드(/analyses/new, 실제 모드 빌드 · 주소 기준 모드 'api')
   - 분석명 · 파일 여러 개(한 번에 LIVE_MAX_FILES 개까지 · 파일마다 PDF·PNG·JPEG, 20MB 이하)를 받는다. 파일 하나 = 분석 1건.
     고를 때마다 목록 뒤에 더하고(이미 담긴 파일은 건너뜀), 못 담은 파일은 이유마다 한 줄로 알린다(liveModel addLiveFiles ·
     pickErrorLines — 다음 고르기 · 빼기 · 분석 시작 때 지움). 담긴 파일은 목록으로 보이고 행마다 빼기 버튼이 있다
     (요청 중에는 막힘, 시작함 · 시작 결과 모름 행에는 없음 — 뺀 뒤 포커스는 가까운 빼기 버튼, 없으면 파일 입력).
   - 분석 시작: 보낼 행(담김 · 실패)을 목록 순서대로 하나씩 서비스의 requestAnalysis(파일 1개)로 보낸다(liveBatch runLiveBatch).
     서비스가 만들기 → 서명 업로드 → 시작을 하고 단계마다 onProgress 로 알린다 — 화면은 지금 보내는 파일의 진행 단계와
     행마다의 상태(대기 · 돌림 표시 · 시작함 · 실패 문구 · 시작 결과 모름)를 보인다. 하나가 실패해도 다음 행으로 간다.
     분석명은 analysisNameFor(입력, 파일 이름, 누른 때 행이 2개 이상인지).
   - 요청 중에는 입력을 잠근다. 끝난 뒤(liveBatch batchOutcome): 모든 행이 시작했으면 행 1개 → 상세(/analyses/{id}),
     2개 이상 → 목록(/ — 기억한 필터 없이). 하나라도 실패 · 시작 결과 모름이면 화면에 남아 위쪽 오류 상자를 보이고 그리로 포커스 —
     잠금이 풀려 실패한 행을 빼거나 파일을 더 담거나 다시 시작할 수 있다(다시 시작하면 담김 · 실패 행만 보내고 오류 상자를 지운다.
     상자는 고르기 · 빼기로는 지우지 않는다).
   - 업로드까지 끝낸 뒤 시작 결과를 모르는 오류(5xx·네트워크·시간 초과)면 서비스가 오류에 분석 id 를 담아 준다 —
     행이 1개면 오류 상자에, 여러 개면 그 행에 '분석 건 확인하기'(상세 → 실제 상태)를 보인다. 성공했다고 표시하지 않는다.
   - 화면을 떠나면 아직 시작하지 않은 행은 보내지 않는다(진행 중이던 한 행은 끝까지 가고, 그 뒤 상태 · 토스트 · 이동은 없다).
   - 데이터는 서비스 인터페이스로만 다룬다.
   - 이동 주소(목록 · 상세)는 기준 경로 함수(src/lib/routes.ts · useRouteBase)로 만든다 — 이 화면은 `/demo` 밖에서만
     그려지므로 기준이 '' 이고 주소는 예전과 같다.
   ========================================================================== */

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useEffect, useId, useRef, useState, type ChangeEvent, type FormEvent } from 'react';
import { Button, Icon, IconButton, Spinner, TextField, VisuallyHidden, buttonClass, cx, useToast } from '@/components/ui';
import { fmtSize } from '@/lib/format';
import { detailHref, listHref } from '@/lib/routes';
import { apiErrorAnalysisId } from '@/services';
import type { RequestStep } from '@/services/analysis-service';
import { useRouteBase, useService } from '@/services/react';
import {
  LABEL_CHECK_CREATED,
  LABEL_STARTED,
  LABEL_STARTED_LIST,
  LABEL_WAITING,
  MSG_CREATED_UNKNOWN,
  MSG_ROW_UNKNOWN,
  READY,
  batchBarText,
  batchOutcome,
  canRemove,
  focusAfterRemove,
  rowStatus,
  runLiveBatch,
  sendableRows,
  type BatchPos,
  type LiveRowState,
} from './liveBatch';
import {
  LIVE_ACCEPT,
  LIVE_MAX_FILES,
  LIVE_MAX_FILE_MB,
  LIVE_NAME_MAX,
  MSG_PICK_FILE,
  addLiveFiles,
  analysisNameFor,
  fileExt,
  pickErrorLines,
  progressSteps,
} from './liveModel';
import styles from './LiveUploadScreen.module.css';

/** 담긴 파일 한 행 */
interface Row {
  key: string;
  file: File;
  state: LiveRowState;
}

/** 위쪽 오류 상자 */
interface FormAlert {
  message: string;
  createdId: string | null;
  startedLink: boolean;
  /** 행 1개 때 만든 상자 — 그 행의 상태 글은 숨긴다 */
  rowKey: string | null;
}

/** 요청 중 — 지금 보내는 행의 자리와 단계 */
interface Run {
  pos: BatchPos;
  step: RequestStep;
}

type FocusTarget = { target: 'file' } | { target: 'alert' } | { target: 'remove'; key: string };

export function LiveUploadScreen() {
  const router = useRouter();
  const base = useRouteBase();
  const service = useService();
  const toast = useToast();
  const [name, setName] = useState('');
  const [rows, setRows] = useState<Row[]>([]);
  /** 파일 상자 아래 오류 줄(못 담은 이유 · 고를 파일 없음) */
  const [fileLines, setFileLines] = useState<string[]>([]);
  const [alert, setAlert] = useState<FormAlert | null>(null);
  const [run, setRun] = useState<Run | null>(null);
  const [focus, setFocus] = useState<(FocusTarget & { n: number }) | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const alertRef = useRef<HTMLDivElement>(null);
  const listRef = useRef<HTMLUListElement>(null);
  const alive = useRef(true);
  /** 묶음 하나만 — 두 번 눌러도 */
  const lock = useRef(false);
  const keySeq = useRef(0);
  const fileHelpId = useId();
  const busy = run !== null;

  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);

  /* 오류를 보인 뒤 · 행을 뺀 뒤(잠금이 풀린 다음 그리기에서) 갈 곳으로 포커스 */
  useEffect(() => {
    if (!focus) return;
    if (focus.target === 'file') fileRef.current?.focus();
    else if (focus.target === 'alert') alertRef.current?.focus();
    else listRef.current?.querySelector<HTMLButtonElement>(`[data-remove="${focus.key}"]`)?.focus();
  }, [focus]);
  const focusOn = (target: FocusTarget) => setFocus((f) => ({ ...target, n: (f?.n ?? 0) + 1 }));

  const onPick = (e: ChangeEvent<HTMLInputElement>) => {
    const picked = Array.from(e.target.files ?? []);
    try {
      e.target.value = ''; // 같은 파일을 다시 골라도 change 가 오게
    } catch {
      /* 무시 */
    }
    if (!picked.length || busy) return;
    const result = addLiveFiles(
      rows.map((r) => r.file),
      picked,
    );
    const added = result.added.map((file): Row => ({ key: `f${(keySeq.current += 1)}`, file, state: READY }));
    setRows((rs) => [...rs, ...added]);
    setFileLines(pickErrorLines(result));
  };

  const onRemove = (key: string) => {
    if (busy) return;
    const at = rows.findIndex((r) => r.key === key);
    if (at < 0) return;
    const next = rows.filter((r) => r.key !== key);
    setRows(next);
    setFileLines([]);
    const target = focusAfterRemove(next, at);
    focusOn(target ? { target: 'remove', key: target } : { target: 'file' });
  };

  const onSubmit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (busy || lock.current || !service) return;
    const queue = sendableRows(rows);
    if (!queue.length) {
      setFileLines([MSG_PICK_FILE]);
      focusOn({ target: 'file' });
      return;
    }
    lock.current = true;
    const snapshot = rows;
    const multi = snapshot.length >= 2;
    const nameNow = name;
    setFileLines([]);
    setAlert(null);
    setRun({ pos: { index: 1, total: queue.length }, step: 'create' });
    void runLiveBatch(snapshot, {
      send: (row, onStep) => {
        const f = row.file;
        const ext = fileExt(f.name).toUpperCase();
        return service.requestAnalysis({
          name: analysisNameFor(nameNow, f.name, multi),
          files: [{ id: 'live-file', name: f.name, ext: ext === 'JPEG' ? 'JPG' : ext, size: f.size, kind: 'user', state: 'ready', error: '', file: f }],
          onProgress: onStep,
        });
      },
      alive: () => alive.current,
      onState: (key, state, pos) => {
        setRows((rs) => rs.map((r) => (r.key === key ? { ...r, state } : r)));
        if (state.kind === 'sending') setRun({ pos, step: state.step });
      },
      analysisIdOf: apiErrorAnalysisId,
    }).then((res) => {
      if (res.stopped || !alive.current) return;
      // 이번에 보낸 행은 끝난 상태로, 보내지 않은 행(시작함 · 시작 결과 모름)은 그대로 — 요청 중에는 목록이 바뀌지 않는다
      const outcome = batchOutcome(snapshot.map((r) => ({ key: r.key, state: res.states.get(r.key) ?? r.state })));
      if (outcome.kind === 'detail') {
        toast(outcome.toast);
        router.push(detailHref(base, outcome.id));
        return;
      }
      if (outcome.kind === 'list') {
        toast(outcome.toast);
        router.push(listHref(base));
        return;
      }
      lock.current = false;
      setRun(null);
      setAlert({ message: outcome.message, createdId: outcome.createdId, startedLink: outcome.startedLink, rowKey: outcome.rowKey });
      focusOn({ target: 'alert' });
    });
  };

  const steps = progressSteps(run ? run.step : null);
  const current = steps.find((s) => s.state === 'current');
  const hasFiles = rows.length > 0;

  return (
    <div className={styles.screen}>
      <form className={styles.form} onSubmit={onSubmit} noValidate aria-busy={busy || undefined}>
        <div className={styles.content}>
          <div className={styles.head}>
            <div>
              <Link href={listHref(base)} className={cx(styles.back, busy && styles.backOff)} aria-disabled={busy || undefined} tabIndex={busy ? -1 : undefined}>
                <Icon name="dg-i-arrow-left" size={17} strokeWidth={2.2} />
                문서 분석
              </Link>
            </div>
            <div className={styles.titles}>
              <span className={styles.eyebrow}>새 분석 · 실제 분석</span>
              <h1 className={styles.title}>분석할 서류 묶음을 올려 주세요</h1>
              <p className={styles.lead}>예상 시간 1분 내외</p>
            </div>
          </div>

          {alert ? (
            <div ref={alertRef} role="alert" tabIndex={-1} className={styles.alert}>
              <span className={styles.alertIcon}>
                <Icon name="dg-i-x-circle" size={18} strokeWidth={2.1} />
              </span>
              <span className={styles.alertText}>
                <span>{alert.message}</span>
                {alert.createdId ? (
                  <>
                    <span className={styles.alertNote}>{MSG_CREATED_UNKNOWN}</span>
                    <Link href={detailHref(base, alert.createdId)} className={styles.alertLink}>
                      {LABEL_CHECK_CREATED}
                      <Icon name="dg-i-chev-right" size={15} strokeWidth={2.2} />
                    </Link>
                  </>
                ) : null}
                {alert.startedLink ? (
                  <Link href={listHref(base)} className={styles.alertLink}>
                    {LABEL_STARTED_LIST}
                    <Icon name="dg-i-chev-right" size={15} strokeWidth={2.2} />
                  </Link>
                ) : null}
              </span>
            </div>
          ) : null}

          <TextField
            label="분석명"
            labelNote="(선택)"
            value={name}
            onChange={(e) => setName(e.target.value)}
            disabled={busy}
            maxLength={LIVE_NAME_MAX}
            showCount
            autoComplete="off"
            placeholder="예: 합성 대출 서류 묶음"
          />

          <div className={styles.fileSection}>
            <div className={styles.fileHead}>
              <span className={styles.fileLabel}>
                문서 파일{' '}
                <span aria-hidden="true" className={styles.req}>
                  *
                </span>
              </span>
              <span className={styles.limits}>
                최대 {LIVE_MAX_FILES}개 · PDF·PNG·JPEG · 파일당 {LIVE_MAX_FILE_MB}MB 이하
              </span>
            </div>
            {/* 빨간 상자는 담긴 파일이 없을 때만 — 담긴 파일이 있으면 못 담은 이유는 아래 줄로만(담긴 파일까지 잘못된 것처럼 보이지 않게) */}
            <div className={cx(styles.fileBox, hasFiles && styles.fileBoxFull, !hasFiles && fileLines.length > 0 && styles.fileBoxError)}>
              {hasFiles ? (
                <ul ref={listRef} className={styles.fileList} aria-label={`고른 파일 ${rows.length}개`}>
                  {rows.map((r) => {
                    const status = rowStatus(r.state, { busy, hidden: alert?.rowKey === r.key });
                    return (
                      <li key={r.key} className={styles.fileRow}>
                        <span className={styles.fileIcon} aria-hidden="true">
                          <Icon name="dg-i-file" size={18} strokeWidth={2} />
                        </span>
                        <span className={styles.fileInfo}>
                          <strong className={styles.fileRowName}>{r.file.name}</strong>
                          <span className={styles.fileMeta}>
                            <span>{fmtSize(r.file.size)}</span>
                            {status.kind === 'waiting' ? <span className={styles.rowWaiting}>{LABEL_WAITING}</span> : null}
                            {status.kind === 'sending' ? (
                              <span className={styles.rowSending}>
                                <Spinner size={14} />
                              </span>
                            ) : null}
                            {status.kind === 'started' ? (
                              <span className={styles.rowStarted}>
                                <Icon name="dg-i-check-circle" size={15} strokeWidth={2.2} />
                                {LABEL_STARTED}
                              </span>
                            ) : null}
                            {status.kind === 'failed' ? <span className={styles.rowFailed}>{status.message}</span> : null}
                            {status.kind === 'unknown' ? (
                              <span className={styles.rowFailed}>
                                {MSG_ROW_UNKNOWN}
                                <Link href={detailHref(base, status.id)} className={styles.rowLink}>
                                  {LABEL_CHECK_CREATED}
                                </Link>
                              </span>
                            ) : null}
                          </span>
                        </span>
                        {canRemove(r.state) ? (
                          <IconButton
                            label={`${r.file.name} 빼기`}
                            icon="dg-i-x"
                            size={36}
                            iconSize={18}
                            strokeWidth={2.2}
                            variant="muted"
                            tooltip="none"
                            className={styles.remove}
                            disabled={busy}
                            onClick={() => onRemove(r.key)}
                            data-remove={r.key}
                          />
                        ) : null}
                      </li>
                    );
                  })}
                </ul>
              ) : (
                <span className={styles.filePlaceholder}>여러 서류를 한 PDF 로 묶은 파일을 고르세요. 파일마다 따로 분석합니다.</span>
              )}
              <label className={buttonClass({ variant: 'dark', size: 'lg', withIcon: true, className: cx(styles.pick, busy && styles.pickOff) })}>
                <input
                  ref={fileRef}
                  type="file"
                  multiple
                  accept={LIVE_ACCEPT}
                  onChange={onPick}
                  disabled={busy}
                  className={styles.fileInput}
                  aria-describedby={fileLines.length ? fileHelpId : undefined}
                  aria-invalid={fileLines.length ? true : undefined}
                />
                <Icon name="dg-i-upload" size={17} strokeWidth={2.2} />
                {hasFiles ? '파일 추가' : '파일 선택'}
              </label>
            </div>
            {fileLines.length ? (
              <span id={fileHelpId} className={styles.fileHelpLines}>
                {fileLines.map((line) => (
                  <span key={line} className={cx(styles.fileHelp, styles.fileHelpError)}>
                    {line}
                  </span>
                ))}
              </span>
            ) : null}
          </div>

          {busy ? (
            <ol className={styles.steps} aria-label="진행 단계">
              {steps.map((s) => (
                <li key={s.step} className={cx(styles.step, styles[`step-${s.state}`])} aria-current={s.state === 'current' ? 'step' : undefined}>
                  <span className={styles.stepIcon} aria-hidden="true">
                    {s.state === 'done' ? <Icon name="dg-i-check-circle" size={16} /> : s.state === 'current' ? <Spinner size={14} /> : <Icon name="dg-i-circle" size={16} />}
                  </span>
                  {s.label}
                  {/* 끝난 단계는 체크 아이콘으로만 보인다 — 화면 낭독기에는 '완료'를 읽어 준다 */}
                  {s.state === 'done' ? <VisuallyHidden> 완료</VisuallyHidden> : null}
                </li>
              ))}
            </ol>
          ) : null}
        </div>

        <div className={styles.bar}>
          <div className={styles.barInner}>
            <span aria-live="polite" className={styles.barText}>
              {run && current ? batchBarText(current.label, run.pos) : null}
            </span>
            <div className={styles.buttons}>
              <Button variant="secondary" size="xl" onClick={() => router.push(listHref(base))} disabled={busy}>
                취소
              </Button>
              <Button type="submit" variant="primary" size="xl" className={styles.start} loading={busy}>
                {busy ? '분석 요청 중…' : '분석 시작'}
              </Button>
            </div>
          </div>
        </div>
      </form>
    </div>
  );
}
