'use client';

import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from 'react';
import styles from './VisuallyHidden.module.css';

type Announce = (text: string) => void;

const AnnounceContext = createContext<Announce>(() => {});

export interface LiveRegionProps {
  /** 지금 알릴 글자 */
  message: string;
}

/**
 * 화면에 보이지 않는 알림 영역 — `role="status"` `aria-live="polite"` (프로토타입 757줄).
 * 보통은 LiveRegionProvider 가 하나 그리고, 화면은 useAnnounce() 로 글자를 넘긴다.
 */
export function LiveRegion({ message }: LiveRegionProps) {
  return (
    <div role="status" aria-live="polite" aria-atomic="true" className={styles.hidden}>
      {message}
    </div>
  );
}

/**
 * 알림 영역 제공자 — 자식 뒤에 LiveRegion 하나를 그린다.
 * AppShell 이 화면 전체를 감싼다. 모달이 뒤 화면을 inert 로 막아도 이 영역은 막히지 않는 자리에 있다.
 */
export function LiveRegionProvider({ children }: { children: ReactNode }) {
  const [message, setMessage] = useState('');
  const frame = useRef(0);

  const announce = useCallback<Announce>((text) => {
    // 같은 글자를 다시 알려도 읽히도록 한 번 비웠다가 다음 프레임에 넣는다
    window.cancelAnimationFrame(frame.current);
    setMessage('');
    frame.current = window.requestAnimationFrame(() => setMessage(text));
  }, []);

  useEffect(() => () => window.cancelAnimationFrame(frame.current), []);

  return (
    <AnnounceContext.Provider value={announce}>
      {children}
      <LiveRegion message={message} />
    </AnnounceContext.Provider>
  );
}

/** 화면 낭독기에 상태 변화를 알린다 — `announce('검토를 완료했습니다')` */
export function useAnnounce(): Announce {
  return useContext(AnnounceContext);
}
