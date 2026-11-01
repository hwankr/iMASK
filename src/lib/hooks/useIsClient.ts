import { useSyncExternalStore } from 'react';

const noopSubscribe = () => () => {};

/** 브라우저에서 하이드레이션이 끝났는지 — 서버 렌더와 첫 하이드레이션에서는 false (포털 등) */
export function useIsClient(): boolean {
  return useSyncExternalStore(noopSubscribe, () => true, () => false);
}
