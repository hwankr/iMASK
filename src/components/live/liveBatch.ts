/* ==========================================================================
   새 분석 · 실제 분석 — 여러 파일 묶음 보내기 모델. 순수 함수만(React·서비스 없음). 테스트 대상.
   - 행 하나 = 담은 파일 하나 = 분석 1건. 행 상태: ready(담김) → sending(보내는 중 · 단계 create·upload·start) →
     started(분석 id) | failed(문구) | unknown(시작 결과 모름 — 문구 + 이미 만든 분석 id).
   - 보낼 행 = ready · failed 행, 목록 순서대로 한 번에 하나씩(앞 행의 보내기가 끝난 뒤 다음). 하나가 실패해도 다음 행으로
     간다. started · unknown 행은 다시 보내지 않는다. 묶음을 시작하면 다시 보낼 failed 행은 먼저 ready(대기)로 돌린다.
   - 오류 문구: 던진 값이 Error 이고 message 가 있으면 그 문구, 아니면 MSG_REQUEST_FAILED. 그 값에 이미 만든 분석 id 가 있으면
     (analysisIdOf — 화면은 apiErrorAnalysisId) unknown, 없으면 failed.
   - 계속할지(alive)는 다음 행을 보내기 전과 상태를 알리기 전마다 묻는다 — 화면을 떠나면 아직 시작하지 않은 행은 보내지 않고,
     진행 중이던 한 행의 보내기는 끝까지 가되 그 뒤 상태를 알리지 않는다.
   - 단계 알림(보내는 함수에 넘긴 onStep)은 그 행의 보내기가 끝나기 전까지만 받는다 — 끝난 뒤 늦게 온 알림은 버린다.
   - 행 키는 한 묶음 안에서 서로 달라야 한다(화면이 순번으로 만든다). 같은 키가 둘이면 둘 다 보내고 상태는 마지막 것만 남는다.
   - 끝난 뒤 갈 곳(batchOutcome): 목록의 모든 행이 started 면 행 1개 → 상세, 2개 이상 → 목록. 그 밖이면 남기 — 행 1개면 그 행의
     문구(시작 결과를 모르면 분석 id 도), 2개 이상이면 '{n}개 중 {k}개를 시작하지 못했습니다.'(목록 전체로 센다 — n = 행 수,
     k = started 가 아닌 수)와 started 행이 있으면 '시작한 분석 보기'.
   ========================================================================== */

import type { RequestStep } from '@/services/analysis-service';

export const MSG_REQUEST_FAILED = '분석을 시작하지 못했습니다. 잠시 후 다시 시도해 주세요.';
export const MSG_CREATED_UNKNOWN = '분석 건은 만들어졌지만 시작됐는지 확인하지 못했습니다. 상세 화면에서 실제 상태를 확인하세요.';
/** 행 상태 글 — 시작 결과를 모르는 행 */
export const MSG_ROW_UNKNOWN = '시작됐는지 확인하지 못했습니다.';
export const LABEL_CHECK_CREATED = '분석 건 확인하기';
export const LABEL_STARTED_LIST = '시작한 분석 보기';
export const LABEL_WAITING = '대기';
export const LABEL_STARTED = '시작함';
export const TOAST_STARTED_ONE = '분석을 시작했습니다.';

/** 분석 n건을 시작했을 때의 토스트 */
export function startedToast(count: number): string {
  return count === 1 ? TOAST_STARTED_ONE : `분석 ${count}건을 시작했습니다.`;
}

export type LiveRowState =
  | { kind: 'ready' }
  | { kind: 'sending'; step: RequestStep }
  | { kind: 'started'; id: string }
  | { kind: 'failed'; message: string }
  | { kind: 'unknown'; message: string; id: string };

/** 행 — 화면은 파일 등을 더 붙여 쓴다 */
export interface LiveBatchRow {
  /** 한 묶음 안에서 서로 달라야 한다(화면이 순번으로 만든다) — 같은 키가 둘이면 둘 다 보내고 상태는 마지막 것만 남는다 */
  key: string;
  state: LiveRowState;
}

export const READY: LiveRowState = { kind: 'ready' };

/** 보낼 행인지 — ready · failed */
export function isSendable(state: LiveRowState): boolean {
  return state.kind === 'ready' || state.kind === 'failed';
}

/** 보낼 행들(목록 순서) */
export function sendableRows<R extends LiveBatchRow>(rows: readonly R[]): R[] {
  return rows.filter((r) => isSendable(r.state));
}

/** 빼기 버튼이 있는 행인지 — started · unknown 행은 없다(보내는 중인 행은 요청 중이라 버튼이 막힌다) */
export function canRemove(state: LiveRowState): boolean {
  return state.kind !== 'started' && state.kind !== 'unknown';
}

/** 던진 값 → 실패 상태(문구 + 이미 만든 분석 id 가 있으면 unknown) */
export function errorState(err: unknown, analysisIdOf: (err: unknown) => string | null): LiveRowState {
  const message = err instanceof Error && err.message ? err.message : MSG_REQUEST_FAILED;
  const id = analysisIdOf(err);
  return id ? { kind: 'unknown', message, id } : { kind: 'failed', message };
}

/** 이번 묶음에서의 자리 — index 는 1부터 */
export interface BatchPos {
  index: number;
  total: number;
}

export interface LiveBatchDeps<R extends LiveBatchRow> {
  /** 한 행을 보낸다 — 분석 id 를 돌려주거나 던진다. onStep 은 단계가 바뀔 때마다 */
  send: (row: R, onStep: (step: RequestStep) => void) => Promise<string>;
  /** 계속할지 — 화면을 떠나면 false */
  alive: () => boolean;
  /** 행 상태가 바뀔 때(alive 일 때만) */
  onState: (key: string, state: LiveRowState, pos: BatchPos) => void;
  /** 던진 값 → 이미 만든 분석 id(시작 결과를 모를 때), 없으면 null */
  analysisIdOf: (err: unknown) => string | null;
}

export interface LiveBatchResult {
  /** 이번 묶음에서 보낼 행(목록 순서) */
  queued: string[];
  /** 끝난 행의 마지막 상태 */
  states: Map<string, LiveRowState>;
  /** 떠나서 멈췄는지(그러면 끝난 뒤의 일 — 토스트 · 이동 · 오류 상자 — 을 하지 않는다) */
  stopped: boolean;
}

/** 묶음 보내기 — 보낼 행(ready · failed)을 목록 순서대로 하나씩 보낸다 */
export async function runLiveBatch<R extends LiveBatchRow>(rows: readonly R[], deps: LiveBatchDeps<R>): Promise<LiveBatchResult> {
  const queue = sendableRows(rows);
  const total = queue.length;
  const states = new Map<string, LiveRowState>();
  const tell = (key: string, state: LiveRowState, index: number): boolean => {
    if (!deps.alive()) return false;
    deps.onState(key, state, { index, total });
    return true;
  };
  queue.forEach((row, i) => {
    if (row.state.kind === 'failed') tell(row.key, READY, i + 1);
  });
  for (let i = 0; i < total; i += 1) {
    const row = queue[i];
    const index = i + 1;
    if (!tell(row.key, { kind: 'sending', step: 'create' }, index)) return { queued: queue.map((r) => r.key), states, stopped: true };
    let state: LiveRowState;
    // 이 행의 진행 알림을 받는 중 — 보내기가 끝나는 즉시(성공 · 거절, 끝 상태를 알리기 전에) 닫는다.
    // 닫힌 뒤 늦게 온 단계 알림은 버린다(끝난 행이 다시 '보내는 중'이 되거나 띠의 순번이 앞 행으로 돌아가지 않게)
    let open = true;
    try {
      const id = await deps.send(row, (step) => {
        if (open) tell(row.key, { kind: 'sending', step }, index);
      });
      open = false;
      state = { kind: 'started', id };
    } catch (err) {
      open = false;
      state = errorState(err, deps.analysisIdOf);
    }
    states.set(row.key, state);
    if (!tell(row.key, state, index)) return { queued: queue.map((r) => r.key), states, stopped: true };
  }
  return { queued: queue.map((r) => r.key), states, stopped: false };
}

/** 끝난 뒤 갈 곳 */
export type LiveBatchOutcome =
  | { kind: 'detail'; id: string; toast: string }
  | { kind: 'list'; count: number; toast: string }
  | {
      kind: 'stay';
      /** 오류 상자 글 */
      message: string;
      /** 행 1개 · 시작 결과 모름 — MSG_CREATED_UNKNOWN 과 '분석 건 확인하기'(상세) */
      createdId: string | null;
      /** 행 2개 이상 · started 행이 있음 — '시작한 분석 보기'(목록) */
      startedLink: boolean;
      /** 행 1개 때 — 상자가 말하는 행(그 행의 상태 글은 숨긴다) */
      rowKey: string | null;
    };

/** 끝난 뒤 갈 곳 — 묶음이 끝난 때의 목록 전체로 정한다 */
export function batchOutcome(rows: readonly LiveBatchRow[]): LiveBatchOutcome {
  const started = rows.filter((r) => r.state.kind === 'started');
  if (rows.length && started.length === rows.length) {
    const first = rows[0].state;
    if (rows.length === 1 && first.kind === 'started') return { kind: 'detail', id: first.id, toast: startedToast(1) };
    return { kind: 'list', count: rows.length, toast: startedToast(rows.length) };
  }
  if (rows.length === 1) {
    const { key, state } = rows[0];
    const message = (state.kind === 'failed' || state.kind === 'unknown') && state.message ? state.message : MSG_REQUEST_FAILED;
    return { kind: 'stay', message, createdId: state.kind === 'unknown' ? state.id : null, startedLink: false, rowKey: key };
  }
  return {
    kind: 'stay',
    message: `${rows.length}개 중 ${rows.length - started.length}개를 시작하지 못했습니다.`,
    createdId: null,
    startedLink: started.length > 0,
    rowKey: null,
  };
}

/** 아래 띠의 진행 글 — 이번에 보내는 행이 1개면 '{단계}…', 2개 이상이면 '{i}/{n} · {단계}…' */
export function batchBarText(stepLabel: string, pos: BatchPos): string {
  return pos.total >= 2 ? `${pos.index}/${pos.total} · ${stepLabel}…` : `${stepLabel}…`;
}

/** 행 상태 글 */
export type LiveRowStatus =
  | { kind: 'none' }
  | { kind: 'waiting' }
  | { kind: 'sending' }
  | { kind: 'started' }
  | { kind: 'failed'; message: string }
  | { kind: 'unknown'; id: string };

/**
 * 행 상태 글 — ready 는 요청 중일 때만 '대기', sending 은 돌림 표시, started 는 '시작함', failed 는 그 문구,
 * unknown 은 '시작됐는지 확인하지 못했습니다.' + '분석 건 확인하기'. hidden(오류 상자가 이 행 하나를 말하는 동안)이면 없음.
 */
export function rowStatus(state: LiveRowState, opts: { busy: boolean; hidden: boolean }): LiveRowStatus {
  if (opts.hidden) return { kind: 'none' };
  switch (state.kind) {
    case 'ready':
      return opts.busy ? { kind: 'waiting' } : { kind: 'none' };
    case 'sending':
      return { kind: 'sending' };
    case 'started':
      return { kind: 'started' };
    case 'failed':
      return { kind: 'failed', message: state.message };
    case 'unknown':
      return { kind: 'unknown', id: state.id };
  }
}

/**
 * 행을 뺀 뒤 포커스를 옮길 행 — 뺀 뒤 목록(rows)에서 같은 자리(removedIndex)부터 뒤로 빼기 버튼이 있는 가장 가까운 행,
 * 없으면 앞으로 가장 가까운 행. 그것도 없으면 null(파일 입력으로).
 */
export function focusAfterRemove(rows: readonly LiveBatchRow[], removedIndex: number): string | null {
  for (let i = Math.max(0, removedIndex); i < rows.length; i += 1) if (canRemove(rows[i].state)) return rows[i].key;
  for (let i = Math.min(removedIndex, rows.length) - 1; i >= 0; i -= 1) if (canRemove(rows[i].state)) return rows[i].key;
  return null;
}
