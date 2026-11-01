import type { ReactNode } from 'react';
import { cx } from '@/components/ui';
import styles from './Tip.module.css';

export interface TipProps {
  /** 툴팁 글자 — 버튼의 aria-label 과 같게 둔다(툴팁 자체는 aria-hidden) */
  label: string;
  /** right: 오른쪽(접힌 레일) · top: 위(원문 뷰어 도구 줄) */
  side: 'right' | 'top';
  /** 툴팁을 숨긴다(버튼에 글자가 보일 때) */
  hidden?: boolean;
  className?: string;
  children: ReactNode;
}

/** 버튼을 감싸 툴팁을 붙인다 — 마우스 올림 · 키보드 포커스 때 보인다 */
export function Tip({ label, side, hidden = false, className, children }: TipProps) {
  return (
    <span className={cx(styles.host, className)}>
      {children}
      {hidden ? null : (
        <span className={cx(styles.tip, styles[side])} aria-hidden="true">
          {label}
        </span>
      )}
    </span>
  );
}
