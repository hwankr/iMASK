'use client';

/* ==========================================================================
   새 분석 — 실제 분석 모드(/analyses/new, NEXT_PUBLIC_IMASK_SERVICE=api)
   - 접근 코드 · 분석명 · 파일 1개(PDF·PNG·JPEG, 20MB 이하)를 받아 서비스의 requestAnalysis 로 보낸다.
     서비스가 만들기 → 서명 업로드 → 시작을 하고 단계마다 onProgress 로 알린다(화면은 진행 단계를 보여 준다).
   - 요청 중에는 입력을 잠근다. 성공하면 상세(/analyses/{id})로 간다 — 상세 화면이 3초마다 상태를 확인한다.
   - 401 이면 접근 코드 칸에 '접근 코드가 맞지 않습니다.' 를 보이고 그 칸으로 포커스, 그 밖은 위쪽 오류 상자.
   - 업로드까지 끝낸 뒤 시작 결과를 모르는 오류(5xx·네트워크·시간 초과)면 서비스가 오류에 분석 id 를 담아 준다 —
     오류 상자에 '분석 건 확인하기'(상세 → 실제 상태)를 함께 보인다. 성공했다고 표시하지 않는다.
   - 데이터는 서비스 인터페이스로만 다룬다(접근 코드 저장만 예외 — src/services 의 함수).
   ========================================================================== */

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useEffect, useId, useRef, useState, type ChangeEvent, type FormEvent } from 'react';
import { Button, Icon, Spinner, TextField, buttonClass, cx, useToast } from '@/components/ui';
import { fmtSize } from '@/lib/format';
import { apiErrorAnalysisId, apiErrorCode } from '@/services';
import type { RequestStep } from '@/services/analysis-service';
import { useService } from '@/services/react';
import { AccessCodeField } from './AccessCodeField';
import { useAccessCode } from './liveHooks';
import {
  LIVE_ACCEPT,
  LIVE_MAX_FILE_MB,
  LIVE_NAME_MAX,
  MSG_NEED_CODE,
  MSG_PICK_FILE,
  analysisNameFor,
  checkLiveFiles,
  fileExt,
  progressSteps,
} from './liveModel';
import styles from './LiveUploadScreen.module.css';

const MSG_WRONG_CODE = '접근 코드가 맞지 않습니다.';
const MSG_REQUEST_FAILED = '분석을 시작하지 못했습니다. 잠시 후 다시 시도해 주세요.';
const MSG_CREATED_UNKNOWN = '분석 건은 만들어졌지만 시작됐는지 확인하지 못했습니다. 상세 화면에서 실제 상태를 확인하세요.';
const STARTED_TOAST = '분석을 시작했습니다. 이 화면에서 3초마다 진행 상태를 확인합니다.';

type FocusTarget = 'code' | 'file' | 'alert';

export function LiveUploadScreen() {
  const router = useRouter();
  const service = useService();
  const toast = useToast();
  const code = useAccessCode();
  const [name, setName] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [fileError, setFileError] = useState('');
  const [codeError, setCodeError] = useState('');
  const [formError, setFormError] = useState('');
  /** 오류가 났지만 이미 만든 분석 건(시작 결과를 모를 때) — 상세로 가는 길을 보인다 */
  const [createdId, setCreatedId] = useState<string | null>(null);
  const [step, setStep] = useState<RequestStep | null>(null);
  const [focus, setFocus] = useState<{ target: FocusTarget; n: number } | null>(null);
  const codeRef = useRef<HTMLInputElement | HTMLTextAreaElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const alertRef = useRef<HTMLDivElement>(null);
  const alive = useRef(true);
  const fileHelpId = useId();
  const busy = step !== null;

  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);

  /* 오류를 보인 뒤(잠금이 풀린 다음 그리기에서) 고칠 곳으로 포커스 */
  useEffect(() => {
    if (!focus) return;
    if (focus.target === 'code') codeRef.current?.focus();
    else if (focus.target === 'file') fileRef.current?.focus();
    else alertRef.current?.focus();
  }, [focus]);
  const focusOn = (target: FocusTarget) => setFocus((f) => ({ target, n: (f?.n ?? 0) + 1 }));

  const onPick = (e: ChangeEvent<HTMLInputElement>) => {
    const picked = Array.from(e.target.files ?? []);
    try {
      e.target.value = ''; // 같은 파일을 다시 골라도 change 가 오게
    } catch {
      /* 무시 */
    }
    if (!picked.length) return;
    const check = checkLiveFiles(picked.map((f) => ({ name: f.name, size: f.size, type: f.type })));
    if (check.ok) {
      setFile(picked[0]);
      setFileError('');
    } else {
      setFile(null);
      setFileError(check.error);
    }
    setFormError('');
    setCreatedId(null);
  };

  const onSubmit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (busy || !service) return;
    let bad: FocusTarget | null = null;
    if (!code.trim()) {
      setCodeError(MSG_NEED_CODE);
      bad = 'code';
    }
    if (!file) {
      setFileError((err) => err || MSG_PICK_FILE);
      bad = bad ?? 'file';
    }
    if (bad || !file) {
      focusOn(bad ?? 'file');
      return;
    }
    setFormError('');
    setCreatedId(null);
    setCodeError('');
    setStep('create');
    const ext = fileExt(file.name).toUpperCase();
    service
      .requestAnalysis({
        name: analysisNameFor(name, file.name),
        files: [{ id: 'live-file', name: file.name, ext: ext === 'JPEG' ? 'JPG' : ext, size: file.size, kind: 'user', state: 'ready', error: '', file }],
        onProgress: (s) => {
          if (alive.current) setStep(s);
        },
      })
      .then(
        (id) => {
          if (!alive.current) return;
          toast(STARTED_TOAST);
          router.push('/analyses/' + encodeURIComponent(id));
        },
        (err: unknown) => {
          if (!alive.current) return;
          setStep(null);
          if (apiErrorCode(err) === 'unauthorized') {
            setCodeError(MSG_WRONG_CODE);
            focusOn('code');
            return;
          }
          setFormError(err instanceof Error && err.message ? err.message : MSG_REQUEST_FAILED);
          setCreatedId(apiErrorAnalysisId(err));
          focusOn('alert');
        },
      );
  };

  const steps = progressSteps(step);

  return (
    <div className={styles.screen}>
      <form className={styles.form} onSubmit={onSubmit} noValidate aria-busy={busy || undefined}>
        <div className={styles.content}>
          <div className={styles.head}>
            <div>
              <Link href="/" className={cx(styles.back, busy && styles.backOff)} aria-disabled={busy || undefined} tabIndex={busy ? -1 : undefined}>
                <Icon name="dg-i-arrow-left" size={17} strokeWidth={2.2} />
                문서 분석
              </Link>
            </div>
            <div className={styles.titles}>
              <span className={styles.eyebrow}>새 분석 · 실제 분석</span>
              <h1 className={styles.title}>분석할 서류 묶음을 올려 주세요</h1>
              <p className={styles.lead}>올린 파일은 Upstage 워크플로우가 실제로 분석합니다. 서류 분류 · 민감정보 추출 · 필수항목 검증 · 위험도 판정까지 보통 1~3분 걸립니다.</p>
            </div>
          </div>

          <div className={styles.warn}>
            <span className={styles.warnIcon}>
              <Icon name="dg-i-alert" size={17} strokeWidth={2.1} />
            </span>
            <span>
              <strong className={styles.warnStrong}>합성 자료만 올려 주세요.</strong> 실제 고객 서류나 본인 서류는 올리지 마세요. 올린 파일은 분석을 위해 Supabase 저장소와 Upstage
              서버로 보내집니다.
            </span>
          </div>

          {formError ? (
            <div ref={alertRef} role="alert" tabIndex={-1} className={styles.alert}>
              <span className={styles.alertIcon}>
                <Icon name="dg-i-x-circle" size={18} strokeWidth={2.1} />
              </span>
              <span className={styles.alertText}>
                <span>{formError}</span>
                {createdId ? (
                  <>
                    <span className={styles.alertNote}>{MSG_CREATED_UNKNOWN}</span>
                    <Link href={'/analyses/' + encodeURIComponent(createdId)} className={styles.alertLink}>
                      분석 건 확인하기
                      <Icon name="dg-i-chev-right" size={15} strokeWidth={2.2} />
                    </Link>
                  </>
                ) : null}
              </span>
            </div>
          ) : null}

          <AccessCodeField
            error={codeError || undefined}
            disabled={busy}
            inputRef={codeRef}
            onEdit={() => {
              if (codeError) setCodeError('');
            }}
          />

          <TextField
            label="분석명"
            labelNote="(선택 · 비우면 파일 이름)"
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
              <span className={styles.limits}>파일 1개 · PDF·PNG·JPEG · {LIVE_MAX_FILE_MB}MB 이하</span>
            </div>
            <div className={cx(styles.fileBox, fileError && styles.fileBoxError)}>
              {file ? (
                <span className={styles.fileName}>
                  <Icon name="dg-i-file" size={18} strokeWidth={2} />
                  <span className={styles.fileText}>
                    <strong>{file.name}</strong>
                    <span className={styles.fileSize}>{fmtSize(file.size)}</span>
                  </span>
                </span>
              ) : (
                <span className={styles.filePlaceholder}>여러 서류를 한 PDF 로 묶은 파일을 고르세요.</span>
              )}
              <label className={buttonClass({ variant: 'dark', size: 'lg', withIcon: true, className: cx(styles.pick, busy && styles.pickOff) })}>
                <input
                  ref={fileRef}
                  type="file"
                  accept={LIVE_ACCEPT}
                  onChange={onPick}
                  disabled={busy}
                  className={styles.fileInput}
                  aria-describedby={fileHelpId}
                  aria-invalid={fileError ? true : undefined}
                />
                <Icon name="dg-i-upload" size={17} strokeWidth={2.2} />
                {file ? '다른 파일 고르기' : '파일 선택'}
              </label>
            </div>
            <span id={fileHelpId} className={cx(styles.fileHelp, fileError && styles.fileHelpError)}>
              {fileError || '여러 서류가 한 파일에 묶여 있어도 워크플로우가 서류별로 나눠 분석합니다.'}
            </span>
          </div>

          {busy ? (
            <ol className={styles.steps} aria-label="진행 단계">
              {steps.map((s) => (
                <li key={s.step} className={cx(styles.step, styles[`step-${s.state}`])} aria-current={s.state === 'current' ? 'step' : undefined}>
                  <span className={styles.stepIcon} aria-hidden="true">
                    {s.state === 'done' ? <Icon name="dg-i-check-circle" size={16} /> : s.state === 'current' ? <Spinner size={14} /> : <Icon name="dg-i-circle" size={16} />}
                  </span>
                  {s.label}
                  {s.state === 'done' ? <span className={styles.stepDone}> · 끝남</span> : null}
                </li>
              ))}
            </ol>
          ) : null}
        </div>

        <div className={styles.bar}>
          <div className={styles.barInner}>
            <span aria-live="polite" className={styles.barText}>
              {busy ? steps.find((s) => s.state === 'current')?.label + '…' : '분석 시작을 누르면 파일을 올리고 바로 분석을 시작합니다.'}
            </span>
            <div className={styles.buttons}>
              <Button variant="secondary" size="xl" onClick={() => router.push('/')} disabled={busy}>
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
