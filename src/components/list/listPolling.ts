/* ==========================================================================
   목록 화면의 진행 중 행 조회(실제 분석 모드만) — 고르는 규칙만(순수 함수). 훅은 ListScreen 의 useListPolling.
   - 목록 데이터에 대기 · 분석 중 행이 있는 동안 POLL_MS(3초)마다 그 분석들을 service.get(id) 로 조회한다
     (조회할 때마다 백엔드가 Upstage 상태를 한 번 확인한다 — 끝났으면 서비스가 완료 알림을 보내 목록 · 헤더가 다시 불러온다).
   - 한 번에 최대 LIST_POLL_MAX(3)개, 돌아가며 고른다(진행 중 행이 많아도 모든 행이 차례로 조회되게).
   - 조회 결과가 null(지워짐)이거나 목록 행과 상태가 다르면 목록을 다시 불러온다(완료 알림을 놓쳐도 멈춘 행이 남지 않게).
     조회가 실패하면(오류) 그 행은 다음 차례에 다시 본다.
   ========================================================================== */

import type { Analysis } from '@/services/types';

/** 한 차례에 조회하는 진행 중 행 수 */
export const LIST_POLL_MAX = 3;

/** 진행 중(대기 · 분석 중)인지 */
export function isActiveStatus(status: string): boolean {
  return status === 'queued' || status === 'running';
}

/** 진행 중 행 id — 목록 순서 그대로 */
export function activeIds(list: readonly Pick<Analysis, 'id' | 'status'>[]): string[] {
  return list.filter((a) => isActiveStatus(a.status)).map((a) => a.id);
}

/** 한 차례 고른 결과 — batch = 이번에 조회할 id, next = 다음 차례의 시작 자리 */
export interface PollPick {
  batch: string[];
  next: number;
}

/**
 * 이번 차례에 조회할 id — cursor 자리부터 최대 max 개, 끝에 닿으면 앞으로 돌아간다(같은 id 는 한 번만).
 * 진행 중 행이 없으면 빈 batch(조회를 멈춘다). cursor 는 지난 차례의 next(목록이 바뀌어도 길이로 나눈 나머지에서 이어 간다).
 */
export function pickPollBatch(ids: readonly string[], cursor: number, max: number = LIST_POLL_MAX): PollPick {
  const n = ids.length;
  if (n === 0 || max <= 0) return { batch: [], next: 0 };
  const start = (((Math.trunc(cursor) || 0) % n) + n) % n;
  const size = Math.min(max, n);
  const batch: string[] = [];
  for (let i = 0; i < size; i++) batch.push(ids[(start + i) % n]);
  return { batch, next: (start + size) % n };
}

/**
 * 조회 결과로 목록을 다시 불러와야 하는지 — 지워졌거나(null) 목록 행과 상태가 다르면 true.
 * fetched 가 undefined(조회 실패)면 false(다음 차례에 다시 본다).
 */
export function needsListReload(rowStatus: string, fetched: Pick<Analysis, 'status'> | null | undefined): boolean {
  if (fetched === undefined) return false;
  if (fetched === null) return true;
  return fetched.status !== rowStatus;
}

/** 한 차례의 조회 결과 전체로 — 하나라도 다시 불러와야 하면 true */
export function batchNeedsReload(
  list: readonly Pick<Analysis, 'id' | 'status'>[],
  batch: readonly string[],
  results: readonly (Pick<Analysis, 'status'> | null | undefined)[],
): boolean {
  return batch.some((id, i) => {
    const row = list.find((a) => a.id === id);
    // 목록에서 이미 빠진 행은 다시 불러올 이유가 없다
    return row !== undefined && needsListReload(row.status, results[i]);
  });
}
