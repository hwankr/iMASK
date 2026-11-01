'use client';

import { use } from 'react';
import styles from '../../../placeholder.module.css';

/** /analyses/[id]/report 보고서 — 자리(T8이 채운다). Next 16: params 는 Promise → React.use */
export default function ReportPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  return (
    <main className={styles.page} data-analysis-id={id}>
      <h1 className={styles.title}>보고서</h1>
    </main>
  );
}
