import { useCallback, useSyncExternalStore } from 'react';

/** 휴대폰 폭(< 768px) — tokens.css 의 휴대폰 중단점과 같다 */
export const MOBILE_QUERY = '(max-width: 767.98px)';

/**
 * 미디어 쿼리 일치 여부를 구독한다. 서버 렌더와 첫 하이드레이션에서는 `serverValue`.
 * 화면 모양은 되도록 CSS @media 로 바꾸고, 이 훅은 동작(정렬 방향 등)이 달라질 때만 쓴다.
 */
export function useMediaQuery(query: string, serverValue = false): boolean {
  const subscribe = useCallback(
    (onChange: () => void) => {
      const mq = window.matchMedia(query);
      mq.addEventListener('change', onChange);
      return () => mq.removeEventListener('change', onChange);
    },
    [query],
  );
  return useSyncExternalStore(
    subscribe,
    () => window.matchMedia(query).matches,
    () => serverValue,
  );
}

/** 휴대폰 폭인지(< 768px) */
export function useIsMobile(): boolean {
  return useMediaQuery(MOBILE_QUERY);
}
