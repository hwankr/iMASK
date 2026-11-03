'use client';

/* ==========================================================================
   실제 분석 화면 훅 — 접근 코드 읽기 · 상태 확인 폴링 · 1초 시계 · 상태 변화 알림 · 단계별 JSON 불러오기
   ========================================================================== */

import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from 'react';
import { useAnnounce } from '@/components/ui';
import type { AnalysisStatus } from '@/display/rules';
import { apiErrorCode, readAccessCode, subscribeAccessCode, type LiveExtras } from '@/services';
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

/** 단계별 JSON 상태 — 처음 펼칠 때 불러온다 */
export type LiveStagesState =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'error'; message: string }
  /** stages: 받은 단계 목록(없으면 null) */
  | { status: 'ready'; stages: unknown[] | null };

/** 단계별 JSON 을 불러오지 못했을 때 — 서비스 오류(ApiError, 한국어)가 아니면 이 문구 */
export const STAGES_FAILED = '단계별 결과를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.';

/**
 * 원본 단계별 JSON(result.stages) — load() 를 처음 부를 때 loadStages(id)(?include=stages)로 받아 둔다.
 * 받는 중 · 받은 뒤에는 다시 부르지 않는다(접었다 펴거나 탭을 바꿔도 그대로). 실패하면 load() 로 다시 시도한다.
 * 응답에 이미 stages 가 있으면(옛 백엔드) 그것을 쓰고 부르지 않는다. id · extras 가 없으면(데모) 아무것도 하지 않는다.
 */
export function useLiveStages(id: string | null, extras: LiveExtras | null, result: unknown): { state: LiveStagesState; load: () => void } {
  const preset = result && typeof result === 'object' && Array.isArray((result as { stages?: unknown }).stages) ? ((result as { stages: unknown[] }).stages) : null;
  const [state, setState] = useState<LiveStagesState>(() => (preset ? { status: 'ready', stages: preset } : { status: 'idle' }));
  const busy = useRef(false);
  const alive = useRef(true);
  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);

  const load = useCallback(() => {
    if (!id || !extras || busy.current) return;
    if (state.status === 'loading' || state.status === 'ready') return;
    busy.current = true;
    setState({ status: 'loading' });
    extras.loadStages(id).then(
      (stages) => {
        busy.current = false;
        if (alive.current) setState({ status: 'ready', stages });
      },
      (err: unknown) => {
        busy.current = false;
        const message = err instanceof Error && err.message && apiErrorCode(err) !== null ? err.message : STAGES_FAILED;
        if (alive.current) setState({ status: 'error', message });
      },
    );
  }, [id, extras, state.status]);

  return { state, load };
}
