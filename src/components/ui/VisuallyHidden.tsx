import type { ReactNode } from 'react';
import styles from './VisuallyHidden.module.css';

/** 화면에는 안 보이고 화면 낭독기만 읽는 글자(프로토타입의 1px·clip 숨김). */
export function VisuallyHidden({ children, id }: { children: ReactNode; id?: string }) {
  return (
    <span className={styles.hidden} id={id}>
      {children}
    </span>
  );
}
