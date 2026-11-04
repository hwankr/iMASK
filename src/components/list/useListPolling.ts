'use client';

/* ==========================================================================
   목록 화면의 진행 중 행 조회(실제 분석 모드만 — 데모는 서비스가 진행을 알린다).
   목록 데이터에 대기 · 분석 중 행이 있는 동안 POLL_MS(3초)마다 그 분석들을 service.get(id) 로 조회한다 —
   한 번에 최대 3개, 돌아가며(listPolling.pickPollBatch), 앞 차례가 끝난 뒤 다음, 탭이 숨겨지면 쉬고 다시 보이면 바로 한 번
   (상세 화면과 같은 usePolling). 조회 결과가 null(지워짐)이거나 목록 행과 상태가 다르면 목록을 다시 불러온다.
   ========================================================================== */

import { useCallback, useLayoutEffect, useRef } from 'react';
import { usePolling } from '@/components/live/liveHooks';
import { useService } from '@/services/react';
import type { Analysis } from '@/services/types';
import { activeIds, batchNeedsReload, pickPollBatch } from './listPolling';

/**
 * enabled 이고 list 에 진행 중 행이 있는 동안 돈다. list 는 화면이 보이는 목록(그린 그대로 — 지운 행 · 다시 분석을 시작한 행 반영),
 * refresh 는 목록 다시 불러오기(useAnalyses().refresh).
 */
export function useListPolling(enabled: boolean, list: readonly Analysis[] | undefined, refresh: () => Promise<void>): void {
  const service = useService();
  const listRef = useRef(list);
  useLayoutEffect(() => {
    listRef.current = list;
  });
  const cursor = useRef(0);
  const active = enabled && !!service && !!list && activeIds(list).length > 0;

  const tick = useCallback(async () => {
    const current = listRef.current ?? [];
    if (!service) return;
    const { batch, next } = pickPollBatch(activeIds(current), cursor.current);
    cursor.current = next;
    if (!batch.length) return;
    // 조회 실패는 undefined — 그 행은 다음 차례에 다시 본다
    const results = await Promise.all(batch.map((id) => service.get(id).then((a) => a, () => undefined)));
    if (batchNeedsReload(current, batch, results)) await refresh();
  }, [service, refresh]);

  usePolling(active, tick);
}
