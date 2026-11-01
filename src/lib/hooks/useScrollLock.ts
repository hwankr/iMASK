import { useEffect } from 'react';
import { SCROLL_LOCK_ATTR } from './dom-attrs';

let lockCount = 0;

/**
 * 뒤 화면 스크롤 잠금(모달). 여러 개가 겹쳐도 마지막 것이 풀릴 때 풀린다.
 * 문서(body)와 AppShell 의 <main>(내부 스크롤 영역)을 함께 잠근다.
 */
export function useScrollLock(active: boolean): void {
  useEffect(() => {
    if (!active) return;
    const root = document.documentElement;
    lockCount += 1;
    root.setAttribute(SCROLL_LOCK_ATTR, '');
    return () => {
      lockCount = Math.max(0, lockCount - 1);
      if (lockCount === 0) root.removeAttribute(SCROLL_LOCK_ATTR);
    };
  }, [active]);
}
