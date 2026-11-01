/* ==========================================================================
   새 분석 화면 모델 — 프로토타입 Main.dc.html
   - emptyUpload · userFile · alertType · alertLimit (1455–1458)
   - addFiles · removeFile · retryUpload · loadSampleFiles · startAnalysis (1677–1729)
   - uploadVM (1992–2035)
   순수 함수만 둔다(React·서비스 없음). 업로드 제한은 ① 설정값(CONFIG.upload)에서만 읽는다.
   실제 업로드는 하지 않는다 — 파일 내용은 읽지 않고 이름·크기만 쓴다.
   ========================================================================== */

import { CONFIG } from '@/config/app';
import type { IconName } from '@/display/icon-names';
import { fmtSize } from '@/lib/format';
import type { UploadFile } from '@/services/types';

/* ---------- 타입 ---------- */

/** 경고 종류 — type: 지원하지 않는 형식 / limit: 업로드 제한 */
export type UploadAlertId = 'type' | 'limit';

/** 경고 상자 하나(프로토타입 alertType · alertLimit) */
export interface UploadAlert {
  id: UploadAlertId;
  /** 화면 키 — 같은 종류의 경고가 새로 생기면 새 상자로 다시 나타난다(등장 움직임·낭독) */
  key: string;
  icon: IconName;
  title: string;
  items: string[];
  hint: string;
}

/** 업로드 화면 상태(프로토타입 emptyUpload + 행 등장 순서) */
export interface UploadState {
  /** 분석명 */
  name: string;
  files: UploadFile[];
  alerts: UploadAlert[];
  /** 파일을 끌어 상자 위에 올려 둔 중 */
  drag: boolean;
  /** 분석 요청 중(입력·버튼 잠금) */
  requesting: boolean;
  /** '분석 시작'을 한 번 눌렀다 — 빠진 값을 오류로 보여 준다 */
  touched: boolean;
  /** /dev/states 전용 — 요청 중 모습만 보여 주고 서비스를 부르지 않는다 */
  frozen: boolean;
  /** 파일 ID → 같이 들어온 묶음 안의 순번(행 차례 등장 지연) */
  enter: Record<string, number>;
}

/** 브라우저 File 에서 쓰는 값 — 이름과 크기만 */
export interface PickedFile {
  name: string;
  size: number;
}

/** 업로드 제한 — 기본은 ① 설정값 */
export interface UploadLimits {
  readonly maxFiles: number;
  readonly maxFileMB: number;
  readonly accept: readonly string[];
}

export const UPLOAD_LIMITS: UploadLimits = CONFIG.upload;

/* ---------- 문구·상수 ---------- */

/** 샘플 체험 분석명(goUpload(true) · loadSampleFiles) */
export const SAMPLE_ANALYSIS_NAME = '샘플 대출상담 서류';

/** 분석 요청 후 상세 화면에서 띄우는 토스트(startAnalysis) */
export const REQUESTED_TOAST = '분석을 요청했습니다. 이 화면에서 진행 상태를 확인할 수 있습니다.';

/** 샘플 불러오기 토스트(loadSampleFiles) — n = 불러온 샘플 수 */
export function sampleToast(n: number, hadUserFiles: boolean): string {
  return hadUserFiles ? '선택한 파일을 샘플 문서 ' + n + '개로 바꿨습니다.' : '샘플 문서 ' + n + '개를 불러왔습니다.';
}

const MB = 1048576;

/* ---------- 형식 ---------- */

/** 확장자(소문자) → 형식 표기. jpeg → 'JPG' */
export function extLabel(ext: string): string {
  return ext === 'jpeg' ? 'JPG' : ext.toUpperCase();
}

/** 허용 형식 표기(중복 없이, 설정 순서) — ['PDF', 'PNG', 'JPG'] */
export function formatLabels(accept: readonly string[] = UPLOAD_LIMITS.accept): string[] {
  const out: string[] = [];
  for (const ext of accept) {
    const label = extLabel(ext);
    if (!out.includes(label)) out.push(label);
  }
  return out;
}

const MIME: Readonly<Record<string, string>> = { pdf: 'application/pdf', png: 'image/png', jpg: 'image/jpeg', jpeg: 'image/jpeg' };

/** <input type="file" accept> — '.pdf,.png,.jpg,.jpeg,application/pdf,image/png,image/jpeg'(원본 280줄과 같음) */
export function acceptAttr(accept: readonly string[] = UPLOAD_LIMITS.accept): string {
  const mimes: string[] = [];
  for (const ext of accept) {
    const m = MIME[ext];
    if (m && !mimes.includes(m)) mimes.push(m);
  }
  return [...accept.map((e) => '.' + e), ...mimes].join(',');
}

/* ---------- 만들기 ---------- */

let seq = 0;
/** 원본 uid(p) — 화면에서 쓰는 임시 ID */
export function uid(prefix = 'id'): string {
  seq += 1;
  return prefix + '-' + seq + '-' + Date.now().toString(36);
}

/** 빈 업로드 상태(원본 emptyUpload) */
export function emptyUpload(): UploadState {
  return { name: '', files: [], alerts: [], drag: false, requesting: false, touched: false, frozen: false, enter: {} };
}

/** 처음 상태 — 빈 상태 위에 넘긴 값을 덮는다. 행 등장 순서가 없으면 목록 순서대로 */
export function initUpload(initial?: Partial<UploadState>): UploadState {
  const base = { ...emptyUpload(), ...initial };
  const enter: Record<string, number> = {};
  base.files.forEach((f, i) => {
    enter[f.id] = initial?.enter?.[f.id] ?? i;
  });
  return { ...base, enter };
}

/** 직접 올린 파일(원본 userFile) — 기본은 준비됨 */
export function userFile(name: string, ext: string, size: number, extra?: Partial<UploadFile>): UploadFile {
  return { id: uid('f'), name, ext, size, kind: 'user', state: 'ready', error: '', ...extra };
}

/** '지원하지 않는 형식' 경고(원본 alertType) */
export function alertType(items: string[], accept: readonly string[] = UPLOAD_LIMITS.accept): UploadAlert {
  return {
    id: 'type',
    key: uid('al'),
    icon: 'dg-i-x-circle',
    title: '지원하지 않는 형식의 파일 ' + items.length + '개를 추가하지 않았습니다',
    items,
    hint: formatLabels(accept).join(', ') + ' 파일만 올릴 수 있습니다. 문서 파일은 PDF로 저장해 올려 주세요.',
  };
}

/** '업로드 제한' 경고(원본 alertLimit) */
export function alertLimit(items: string[], n: number, maxF: number, maxMB: number): UploadAlert {
  return {
    id: 'limit',
    key: uid('al'),
    icon: 'dg-i-alert',
    title: '업로드 제한을 넘은 파일 ' + n + '개를 추가하지 않았습니다',
    items,
    hint: '파일당 최대 ' + maxMB + 'MB, 한 분석에 최대 ' + maxF + '개까지 올릴 수 있습니다. 제한은 설정에서 바꿀 수 있습니다.',
  };
}

/* ---------- 동작(원본 1677–1729) ---------- */

export interface AddFilesResult {
  next: UploadState;
  /** 목록에 더한 파일 ID — uploadMs 뒤 준비됨으로 바꾼다 */
  added: string[];
}

/**
 * 파일 선택 검사(원본 addFiles). 순서: 형식 → 파일당 크기 → 개수.
 * - 허용 확장자가 아니면 '지원하지 않는 형식'
 * - 파일당 maxFileMB 초과, 한 분석에 maxFiles 초과는 '업로드 제한'(넘친 파일 이름 3개까지 + 외 n개)
 * - 새 검사 결과가 이전 형식·제한 경고를 바꾼다
 * `ids` 를 주면 더한 파일에 차례로 쓴다(상태 갱신 함수를 여러 번 불러도 같은 결과가 나오게).
 */
export function addFiles(
  state: UploadState,
  picked: readonly PickedFile[],
  limits: UploadLimits = UPLOAD_LIMITS,
  ids?: readonly string[],
): AddFilesResult {
  if (!picked.length) return { next: { ...state, drag: false }, added: [] };
  const maxF = limits.maxFiles;
  const maxMB = limits.maxFileMB;
  const maxB = maxMB * MB;
  const files = state.files.slice();
  const badType: string[] = [];
  const tooBig: string[] = [];
  const over: string[] = [];
  const added: string[] = [];
  picked.forEach((file, i) => {
    const nm = String(file.name || '이름 없는 파일');
    const dot = nm.lastIndexOf('.');
    const ext = dot > 0 ? nm.slice(dot + 1).toLowerCase() : '';
    if (!limits.accept.includes(ext)) {
      badType.push(nm + ' — 지원하지 않는 형식 (' + (ext ? ext.toUpperCase() : '확장자 없음') + ')');
      return;
    }
    if (file.size > maxB) {
      tooBig.push(nm + ' (' + fmtSize(file.size) + ') — 파일당 최대 ' + maxMB + 'MB를 넘습니다');
      return;
    }
    if (files.length >= maxF) {
      over.push(nm);
      return;
    }
    const f = userFile(nm, extLabel(ext), file.size, { state: 'uploading' });
    if (ids?.[i]) f.id = ids[i];
    files.push(f);
    added.push(f.id);
  });
  const alerts = state.alerts.filter((x) => x.id !== 'type' && x.id !== 'limit');
  if (badType.length) alerts.push(alertType(badType, limits.accept));
  const lim: string[] = [];
  if (over.length) {
    lim.push(
      '파일은 한 분석에 최대 ' + maxF + '개까지 올릴 수 있습니다 — ' + over.slice(0, 3).join(', ') + (over.length > 3 ? ' 외 ' + (over.length - 3) + '개' : '') + ' 제외',
    );
  }
  tooBig.forEach((t) => lim.push(t));
  if (lim.length) alerts.push(alertLimit(lim, over.length + tooBig.length, maxF, maxMB));
  const enter = { ...state.enter };
  added.forEach((id, i) => {
    enter[id] = i;
  });
  return { next: { ...state, files, alerts, drag: false, enter }, added };
}

/** 올리는 중이던 파일을 준비됨으로(addFiles 의 later) */
export function markReady(state: UploadState, ids: readonly string[]): UploadState {
  if (!state.files.some((f) => ids.includes(f.id) && f.state === 'uploading')) return state;
  return { ...state, files: state.files.map((f) => (ids.includes(f.id) && f.state === 'uploading' ? { ...f, state: 'ready' } : f)) };
}

/** 목록에서 제거(원본 removeFile) */
export function removeFile(state: UploadState, id: string): UploadState {
  return { ...state, files: state.files.filter((f) => f.id !== id) };
}

/** '다시 올리기' — 올리는 중으로(원본 retryUpload 앞부분) */
export function retryFile(state: UploadState, id: string): UploadState {
  return { ...state, files: state.files.map((f) => (f.id === id ? { ...f, state: 'uploading', error: '' } : f)) };
}

/** '다시 올리기' CONFIG.sim.uploadRetryMs(900ms) 뒤 — 준비됨으로(원본 retryUpload 뒷부분) */
export function finishRetry(state: UploadState, id: string): UploadState {
  if (!state.files.some((f) => f.id === id)) return state;
  return { ...state, files: state.files.map((f) => (f.id === id ? { ...f, state: 'ready' } : f)) };
}

/** 경고 닫기 */
export function dismissAlert(state: UploadState, id: UploadAlertId): UploadState {
  return { ...state, alerts: state.alerts.filter((x) => x.id !== id) };
}

/** '샘플 문서 불러오기'(원본 loadSampleFiles) — 파일 목록을 샘플로 바꾸고, 분석명이 비었으면 샘플 이름 */
export function applySampleFiles(state: UploadState, samples: UploadFile[]): UploadState {
  const enter: Record<string, number> = {};
  samples.forEach((f, i) => {
    enter[f.id] = i;
  });
  return { ...state, files: samples, alerts: [], name: state.name.trim() ? state.name : SAMPLE_ANALYSIS_NAME, enter };
}

/** 직접 올린 파일이 있는지(샘플 토스트 문구 · 데모 환경 안내) */
export function hasUserFiles(state: Pick<UploadState, 'files'>): boolean {
  return state.files.some((f) => f.kind === 'user');
}

/** '분석 시작' 검사(원본 startAnalysis) */
export type StartCheck = { ok: false; reason: 'busy' | 'invalid' } | { ok: true; name: string; files: UploadFile[] };

export function checkStart(state: UploadState): StartCheck {
  if (state.requesting) return { ok: false, reason: 'busy' };
  const ready = state.files.filter((f) => f.state === 'ready');
  if (!state.name.trim() || !ready.length || state.files.some((f) => f.state !== 'ready')) return { ok: false, reason: 'invalid' };
  return { ok: true, name: state.name.trim(), files: ready };
}

/* ---------- 화면 모델(원본 uploadVM) ---------- */

export interface UploadFileRow {
  file: UploadFile;
  /** 형식 · 크기 */
  meta: string;
  /** 위 행과 사이에 선을 긋는다(원본 sep) — 실패한 행과 그 아래 행은 선 없음 */
  separated: boolean;
  sample: boolean;
  failed: boolean;
  uploading: boolean;
  ready: boolean;
  /** 제거 버튼 aria-label */
  removeLabel: string;
  /** 차례 등장 순번 */
  enterIndex: number;
}

export interface UploadView {
  /** 요청 중 — 입력·버튼 잠금 */
  busy: boolean;
  /** 올리는 중인 파일이 있음 */
  uploading: boolean;
  /** '분석 시작' 사용할 수 없음(aria-disabled) — 요청 중이거나 올리는 중 */
  cantStart: boolean;
  /** '분석 시작' disabled — 올리는 중이고 요청 중은 아님 */
  startDisabled: boolean;
  nameInvalid: boolean;
  /** 분석명 아래 글 — 오류면 오류 문구 */
  nameHelp: string;
  /** 파일이 없는데 시작을 눌렀다 — 파일 상자 붉게 */
  fileError: boolean;
  limitsText: string;
  /** 지원 형식 안내(파일 상자 안) */
  hintText: string;
  /** 파일이 있으면 상자를 한 줄로 줄인다 */
  compact: boolean;
  dropTitle: string;
  hasFiles: boolean;
  count: number;
  total: string;
  rows: UploadFileRow[];
  /** 데모 환경 안내 */
  userNotice: boolean;
  footText: string;
  footError: boolean;
}

export function uploadView(u: UploadState, limits: UploadLimits = UPLOAD_LIMITS): UploadView {
  const maxF = limits.maxFiles;
  const maxMB = limits.maxFileMB;
  const ready = u.files.filter((f) => f.state === 'ready');
  const nameOk = u.name.trim().length > 0;
  const hasFailed = u.files.some((f) => f.state === 'failed');
  const uploading = u.files.some((f) => f.state === 'uploading');
  const busy = !!u.requesting;
  const showNameErr = u.touched && !nameOk;
  const showFileErr = u.touched && !u.files.length;
  let foot = '';
  let footError = false;
  if (busy) foot = '분석을 요청하고 있습니다. 잠시만 기다려 주세요.';
  else if (!nameOk && !u.files.length) {
    foot = '분석명을 입력하고 파일을 1개 이상 선택하세요.';
    footError = u.touched;
  } else if (!nameOk) {
    foot = '분석명을 입력하세요.';
    footError = u.touched;
  } else if (!u.files.length) {
    foot = '분석할 파일을 1개 이상 선택하세요.';
    footError = u.touched;
  } else if (uploading) foot = '파일을 올리고 있습니다.';
  else if (hasFailed) {
    foot = '업로드에 실패한 파일을 다시 올리거나 목록에서 빼 주세요.';
    footError = true;
  } else foot = '문서 ' + ready.length + '개를 하나의 분석 건으로 요청합니다.';
  const total = u.files.reduce((n, f) => n + (f.size || 0), 0);
  const formats = formatLabels(limits.accept);
  return {
    busy,
    uploading,
    cantStart: busy || uploading,
    startDisabled: uploading && !busy,
    nameInvalid: showNameErr,
    nameHelp: showNameErr ? '분석명을 입력해 주세요.' : '목록에서 이 이름으로 찾을 수 있습니다. 예: 고객명 + 업무명',
    fileError: showFileErr,
    limitsText: formats.join(' · ') + ' · 파일당 최대 ' + maxMB + 'MB · 최대 ' + maxF + '개',
    hintText: '지원 형식 ' + formats.join(', '),
    compact: u.files.length > 0,
    dropTitle: u.drag ? '여기에 놓으면 파일이 추가됩니다' : u.files.length ? '파일을 더 추가하려면 여기로 끌어다 놓거나' : '파일을 여기로 끌어다 놓거나',
    hasFiles: u.files.length > 0,
    count: u.files.length,
    total: fmtSize(total),
    rows: u.files.map((f, i) => ({
      file: f,
      meta: f.ext + ' · ' + fmtSize(f.size),
      separated: i > 0 && f.state !== 'failed' && u.files[i - 1].state !== 'failed',
      sample: f.kind === 'sample',
      failed: f.state === 'failed',
      uploading: f.state === 'uploading',
      ready: f.state === 'ready',
      removeLabel: f.name + ' 목록에서 제거',
      enterIndex: u.enter[f.id] ?? 0,
    })),
    userNotice: hasUserFiles(u),
    footText: foot,
    footError,
  };
}
