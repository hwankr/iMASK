'use client';

import { use } from 'react';
import styles from '../../placeholder.module.css';

/** /analyses/[id] 상세 검토 — 자리(T6·T7이 채운다). Next 16: params 는 Promise → React.use */
export default function DetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  return (
    <main className={styles.page} data-analysis-id={id}>
      <h1 className={styles.title}>상세 검토</h1>
    </main>
  );
}
