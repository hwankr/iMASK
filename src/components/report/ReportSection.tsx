import type { ReactNode } from 'react';
import { cx } from '@/components/ui';
import styles from './ReportSection.module.css';

export interface ReportSectionProps {
  /** 구역 번호 1~8 — 제목 앞 '01' 처럼 두 자리 고정폭 */
  n: number;
  title: string;
  children: ReactNode;
  /**
   * 간격 — summary: 첫 구역(22, 위 선 없음, Main 627) · history: 08 구역(18, Main 676) · 그 밖 16(Main 640 …)
   */
  look?: 'summary' | 'default' | 'history';
}

/** 보고서 구역 — `<section aria-labelledby="rp-sN">` + 번호 붙은 h2 (Main 627–700) */
export function ReportSection({ n, title, children, look = 'default' }: ReportSectionProps) {
  const id = 'rp-s' + n;
  return (
    <section aria-labelledby={id} className={cx(styles.section, styles[look])}>
      <h2 id={id} className={styles.title}>
        <span className={styles.num}>{String(n).padStart(2, '0')}</span>
        {title}
      </h2>
      {children}
    </section>
  );
}
