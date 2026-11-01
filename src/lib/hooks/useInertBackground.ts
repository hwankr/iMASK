import { useEffect } from 'react';
import { APP_ROOT_ATTR } from './dom-attrs';

let inertCount = 0;

/**
 * 모달이 열려 있는 동안 뒤 화면(AppShell 루트)을 inert 로 막는다 — 마우스·키보드·화면 낭독기 모두 닿지 않는다.
 * 토스트와 알림 영역(LiveRegion)은 루트 밖에 있어 막히지 않는다.
 */
export function useInertBackground(active: boolean): void {
  useEffect(() => {
    if (!active) return;
    const root = document.querySelector<HTMLElement>(`[${APP_ROOT_ATTR}]`);
    if (!root) return;
    inertCount += 1;
    root.inert = true;
    return () => {
      inertCount = Math.max(0, inertCount - 1);
      if (inertCount === 0) root.inert = false;
    };
  }, [active]);
}
