'use client';

/* ==========================================================================
   실제 분석 화면 훅 — 접근 코드 읽기 · 상태 확인 폴링 · 1초 시계 · 상태 변화 알림
   ========================================================================== */

import { useCallback, useEffect, useRef, useSyncExternalStore } from 'react';
import { useAnnounce } from '@/components/ui';
import type { AnalysisStatus } from '@/display/rules';
import { readAccessCode, subscribeAccessCode } from '@/services';
import { POLL_MS, statusAnnouncement } from './liveModel';

/** 이 탭에 저장한 접근 코드(입력한 그대로). 서버 렌더·하이드레이션 첫 렌더에서는 '' */
export function useAccessCode(): string {
  return useSyncExternalStore(subscribeAccessCode, () => readAccessCode(), () => '');
}

/**
 * active 인 동안 intervalMs 마다 refresh() 를 부른다.
 * - 앞 요청이 끝난 뒤에 다음을 잡는다(겹치지 않는다).
 * - 탭이 숨겨져 있으면 쉬고, 다시 보이면 바로 한 번 조회한 뒤 이어 간다.
 * - active 가 false 가 되거나 화면을 떠나면 멈춘다(늦게 끝난 요청 뒤에도 다시 잡지 않는다).
 */
export function usePolling(active: boolean, refresh: () => Promise<void>, intervalMs: number = POLL_MS): void {
  useEffect(() => {
    if (!active) return;
    let stopped = false;
    let resting = false;
    let timer: ReturnType<typeof setTimeout> | null = null;

    const hidden = () => typeof document !== 'undefined' && document.visibilityState === 'hidden';
    const schedule = () => {
      if (!stopped) timer = setTimeout(tick, intervalMs);
    };
    const tick = async () => {
      timer = null;
      if (stopped) return;
      if (hidden()) {
        resting = true; // 다시 보일 때까지 쉰다
        return;
      }
      try {
        await refresh();
      } catch {
        /* 오류는 데이터 훅의 error 로 보인다 — 다음 차례에 다시 확인 */
      }
      schedule();
    };
    const onVisibility = () => {
      if (stopped || hidden() || !resting) return;
      resting = false;
      void tick();
    };

    document.addEventListener('visibilitychange', onVisibility);
    schedule();
    return () => {
      stopped = true;
      if (timer) clearTimeout(timer);
      document.removeEventListener('visibilitychange', onVisibility);
    };
  }, [active, refresh, intervalMs]);
}

const noSubscribe = () => () => {};

/** active 인 동안 1초마다 바뀌는 지금 시각(밀리초, 초 단위로 내림). 서버 렌더에서는 0 */
export function useClock(active: boolean): number {
  const subscribe = useCallback(
    (onChange: () => void) => {
      if (!active) return () => {};
      const t = setInterval(onChange, 1000);
      return () => clearInterval(t);
    },
    [active],
  );
  return useSyncExternalStore(active ? subscribe : noSubscribe, () => Math.floor(Date.now() / 1000) * 1000, () => 0);
}

/** 분석 상태가 바뀌면(처음 불러올 때는 빼고) 화면 낭독기에 알린다 */
export function useStatusAnnounce(status: AnalysisStatus | undefined): void {
  const announce = useAnnounce();
  const prev = useRef<AnalysisStatus | null>(null);
  useEffect(() => {
    if (!status) return;
    const text = statusAnnouncement(prev.current, status);
    prev.current = status;
    if (text) announce(text);
  }, [status, announce]);
}
