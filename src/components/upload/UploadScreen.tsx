'use client';

import { useRouter, useSearchParams } from 'next/navigation';
import {
  Suspense,
  useCallback,
  useEffect,
  useRef,
  useState,
  type ChangeEvent,
  type DragEvent,
  type FormEvent,
} from 'react';
import { Icon, TextField, useToast } from '@/components/ui';
import { CONFIG } from '@/config/app';
import type { AnalysisService } from '@/services/analysis-service';
import { useService } from '@/services/react';
import type { UploadFile } from '@/services/types';
import { DropZone } from './DropZone';
import { FileList } from './FileList';
import { SampleCard } from './SampleCard';
import { UploadAlertBox } from './UploadAlertBox';
import { UploadFooter } from './UploadFooter';
import {
  REQUESTED_TOAST,
  SAMPLE_ANALYSIS_NAME,
  UPLOAD_LIMITS,
  acceptAttr,
  addFiles,
  applySampleFiles,
  checkStart,
  dismissAlert,
  finishRetry,
  hasUserFiles,
  initUpload,
  markReady,
  removeFile,
  retryFile,
  sampleToast,
  uid,
  uploadView,
  type PickedFile,
  type UploadAlertId,
  type UploadState,
} from './uploadModel';
import styles from './UploadScreen.module.css';

export interface UploadScreenProps {
  /**
   * /dev/states 용 처음 상태(분석명 · 파일 목록 · 경고 · requesting · touched · frozen).
   * frozen 이면 요청 중 모습만 보여 주고 서비스를 부르지 않는다(프로토타입과 같음).
   */
  initial?: Partial<UploadState>;
  /** `?sample=1` 이면 샘플 파일을 담아 시작한다(프로토타입 goUpload(true)) — /analyses/new 라우트만 켠다 */
  sampleFromQuery?: boolean;
}

/** 요청이 실패했을 때(실제 API 대비 — 데모 서비스는 실패하지 않는다) */
const REQUEST_FAILED_TOAST = '분석을 요청하지 못했습니다. 잠시 후 다시 시도해 주세요.';

/** 키보드로 누른 버튼이 사라진 뒤 포커스를 옮길 곳 */
type PendingFocus = { kind: 'row'; index: number } | { kind: 'remove'; id: string } | { kind: 'alert'; index: number };

/**
 * /analyses/new 새 분석 — 프로토타입 Main.dc.html 240–327(마크업) · 1677–1729(동작) · 1992–2035(uploadVM).
 * 데이터는 서비스(sampleFiles · requestAnalysis)로만 다룬다. 실제 업로드는 하지 않는다.
 */
export function UploadScreen({ initial, sampleFromQuery = false }: UploadScreenProps) {
  const router = useRouter();
  const service = useService();
  const toast = useToast();
  const [up, setUp] = useState<UploadState>(() => initUpload(initial));
  const later = useLater();
  const alive = useAliveRef();
  const contentRef = useRef<HTMLDivElement>(null);
  const zoneRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLUListElement>(null);
  const pendingFocus = useRef<PendingFocus | null>(null);

  const vm = uploadView(up);
  const busy = vm.busy;

  /* 누른 버튼(제거 · 다시 올리기 · 경고 닫기)이 사라지면 가까운 곳으로 포커스를 옮긴다 */
  useEffect(() => {
    const target = pendingFocus.current;
    if (!target) return;
    pendingFocus.current = null;
    let el: HTMLElement | null | undefined = null;
    if (target.kind === 'row') {
      const buttons = listRef.current?.querySelectorAll<HTMLButtonElement>('[data-remove]');
      if (buttons && buttons.length) el = buttons[Math.min(target.index, buttons.length - 1)];
    } else if (target.kind === 'remove') {
      el = listRef.current?.querySelector<HTMLButtonElement>(`[data-remove="${CSS.escape(target.id)}"]`);
    } else {
      const closes = contentRef.current?.querySelectorAll<HTMLButtonElement>('[data-alert-close]');
      if (closes && closes.length) el = closes[Math.min(target.index, closes.length - 1)];
    }
    (el ?? inputRef.current)?.focus();
  }, [up]);

  /* 상자 밖에 파일을 떨어뜨려도 브라우저가 그 파일을 열며 화면을 떠나지 않게 한다 */
  useEffect(() => {
    const hasFiles = (e: globalThis.DragEvent) => !!e.dataTransfer && Array.from(e.dataTransfer.types).includes('Files');
    const onOver = (e: globalThis.DragEvent) => {
      if (!hasFiles(e)) return;
      e.preventDefault();
      const zone = zoneRef.current;
      if (e.dataTransfer && !(zone && e.target instanceof Node && zone.contains(e.target))) e.dataTransfer.dropEffect = 'none';
    };
    const onDropOutside = (e: globalThis.DragEvent) => {
      if (hasFiles(e)) e.preventDefault();
    };
    window.addEventListener('dragover', onOver);
    window.addEventListener('drop', onDropOutside);
    return () => {
      window.removeEventListener('dragover', onOver);
      window.removeEventListener('drop', onDropOutside);
    };
  }, []);

  /* ---------- 파일 선택 검사(원본 addFiles) ---------- */
  const add = (picked: PickedFile[]) => {
    // 상태 갱신 함수가 두 번 불려도(Strict Mode) 같은 ID 가 쓰이도록 미리 만든다
    const ids = picked.map(() => uid('f'));
    setUp((s) => addFiles(s, picked, UPLOAD_LIMITS, ids).next);
    if (ids.length) later(CONFIG.sim.uploadMs, () => setUp((s) => markReady(s, ids)));
  };

  const onPick = (e: ChangeEvent<HTMLInputElement>) => {
    add(toPicked(e.target.files));
    try {
      e.target.value = '';
    } catch {
      /* 무시 */
    }
  };

  const onDragOver = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    if (!busy && !up.drag) setUp((s) => (s.drag ? s : { ...s, drag: true }));
  };
  const onDragLeave = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    const rt = e.relatedTarget;
    if (rt instanceof Node && e.currentTarget.contains(rt)) return;
    if (up.drag) setUp((s) => (s.drag ? { ...s, drag: false } : s));
  };
  const onDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    if (busy) return;
    add(toPicked(e.dataTransfer ? e.dataTransfer.files : null));
  };

  /* ---------- 목록 ---------- */
  const onRemove = (id: string) => {
    pendingFocus.current = { kind: 'row', index: up.files.findIndex((f) => f.id === id) };
    setUp((s) => removeFile(s, id));
  };
  const onRetry = (id: string) => {
    pendingFocus.current = { kind: 'remove', id };
    setUp((s) => retryFile(s, id));
    later(CONFIG.sim.uploadRetryMs, () => setUp((s) => finishRetry(s, id)));
  };
  const onDismiss = (id: UploadAlertId) => {
    pendingFocus.current = { kind: 'alert', index: up.alerts.findIndex((a) => a.id === id) };
    setUp((s) => dismissAlert(s, id));
  };

  /* ---------- 샘플(원본 loadSampleFiles · goUpload(true)) ---------- */
  const loadSample = () => {
    if (!service || busy) return;
    const hadUser = hasUserFiles(up);
    void service.sampleFiles().then((files) => {
      if (!alive.current) return;
      setUp((s) => applySampleFiles(s, files));
      toast(sampleToast(files.length, hadUser));
    });
  };
  const startWithSample = useCallback((files: UploadFile[]) => {
    setUp(initUpload({ name: SAMPLE_ANALYSIS_NAME, files }));
  }, []);

  /* ---------- 이동 · 시작(원본 cancel · startAnalysis) ---------- */
  const cancel = () => {
    if (!busy) router.push('/');
  };

  const onSubmit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const check = checkStart(up);
    if (!check.ok) {
      if (check.reason === 'invalid') setUp((s) => ({ ...s, touched: true }));
      return;
    }
    if (up.frozen) {
      setUp((s) => ({ ...s, requesting: true, touched: true }));
      return;
    }
    if (!service) return;
    setUp((s) => ({ ...s, requesting: true, touched: true }));
    service.requestAnalysis({ name: check.name, files: check.files }).then(
      (id) => {
        if (!alive.current) return;
        router.push('/analyses/' + encodeURIComponent(id));
        toast(REQUESTED_TOAST);
      },
      () => {
        if (!alive.current) return;
        setUp((s) => ({ ...s, requesting: false }));
        toast(REQUEST_FAILED_TOAST, { kind: 'error' });
      },
    );
  };

  return (
    <div className={styles.screen}>
      {sampleFromQuery ? (
        // useSearchParams 는 Suspense 안에서만 — 화면은 정적으로 그리고 이 부분만 브라우저에서 읽는다
        <Suspense fallback={null}>
          <SampleQuery service={service} onFiles={startWithSample} />
        </Suspense>
      ) : null}
      <form className={styles.form} onSubmit={onSubmit} noValidate>
        <div ref={contentRef} className={styles.content}>
          <div className={styles.head}>
            <div>
              <button type="button" className={styles.back} onClick={cancel} disabled={busy}>
                <Icon name="dg-i-arrow-left" size={17} strokeWidth={2.2} />
                문서 분석
              </button>
            </div>
            <div className={styles.titles}>
              <span className={styles.eyebrow}>새 분석</span>
              <h1 className={styles.title}>함께 검토할 문서를 올려 주세요</h1>
              <p className={styles.lead}>한 번에 올린 파일은 하나의 분석 건으로 묶여, 문서 사이의 정보까지 함께 확인합니다.</p>
            </div>
          </div>

          <SampleCard onLoad={loadSample} disabled={busy} />

          <TextField
            className={styles.name}
            label="분석명"
            required
            value={up.name}
            onChange={(e) => {
              const name = e.target.value;
              setUp((s) => ({ ...s, name }));
            }}
            disabled={busy}
            maxLength={60}
            autoComplete="off"
            placeholder="예: 김○○ 대출상담 서류"
            help={vm.nameInvalid ? undefined : vm.nameHelp}
            error={vm.nameInvalid ? vm.nameHelp : undefined}
          />

          <DropZone
            compact={vm.compact}
            drag={up.drag}
            error={vm.fileError}
            title={vm.dropTitle}
            limitsText={vm.limitsText}
            hintText={vm.hintText}
            accept={acceptAttr()}
            busy={busy}
            zoneRef={zoneRef}
            inputRef={inputRef}
            onPick={onPick}
            onDragOver={onDragOver}
            onDragLeave={onDragLeave}
            onDrop={onDrop}
          />

          {up.alerts.map((al) => (
            <UploadAlertBox key={al.key} alert={al} onDismiss={() => onDismiss(al.id)} />
          ))}

          {vm.hasFiles ? (
            <FileList listRef={listRef} rows={vm.rows} count={vm.count} total={vm.total} busy={busy} onRemove={onRemove} onRetry={onRetry} />
          ) : null}

          {vm.userNotice ? (
            <div className={styles.notice}>
              <span className={styles.noticeIcon}>
                <Icon name="dg-i-info" size={17} strokeWidth={2} />
              </span>
              <span>
                <strong className={styles.noticeStrong}>데모 환경 안내</strong> · 직접 올린 파일은 이 데모에서 분석하지 않고 ‘대기’ 상태로만 등록합니다. 탐지
                결과를 체험하려면 샘플 문서를 사용하세요.
              </span>
            </div>
          ) : null}
        </div>

        <UploadFooter text={vm.footText} error={vm.footError} busy={busy} startDisabled={vm.startDisabled} cantStart={vm.cantStart} onCancel={cancel} />
      </form>
    </div>
  );
}

/** `?sample=1` 을 읽고, 서비스가 생기면 샘플 파일을 받아 넘긴다(한 번) */
function SampleQuery({ service, onFiles }: { service: AnalysisService | null; onFiles: (files: UploadFile[]) => void }) {
  const wanted = useSearchParams().get('sample') === '1';
  useEffect(() => {
    if (!wanted || !service) return;
    let on = true;
    void service.sampleFiles().then((files) => {
      if (on) onFiles(files);
    });
    return () => {
      on = false;
    };
  }, [wanted, service, onFiles]);
  return null;
}

/** 브라우저 File 목록 → 이름 · 크기만(내용은 읽지 않는다) */
function toPicked(list: FileList | null): PickedFile[] {
  return Array.from(list ?? [], (f) => ({ name: f.name, size: f.size }));
}

/** 원본 later(ms, fn) — 화면이 사라지면 남은 타이머를 지운다 */
function useLater() {
  const timers = useRef(new Set<ReturnType<typeof setTimeout>>());
  useEffect(() => {
    const set = timers.current;
    return () => {
      set.forEach(clearTimeout);
      set.clear();
    };
  }, []);
  return useCallback((ms: number, fn: () => void) => {
    const t = setTimeout(() => {
      timers.current.delete(t);
      fn();
    }, ms);
    timers.current.add(t);
  }, []);
}

/** 화면이 살아 있는지(늦게 온 응답을 버린다) */
function useAliveRef() {
  const alive = useRef(true);
  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);
  return alive;
}
