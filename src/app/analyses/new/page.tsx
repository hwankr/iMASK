import type { Metadata } from 'next';
import styles from '../../placeholder.module.css';

export const metadata: Metadata = { title: '새 분석' };

/** /analyses/new 새 분석 — 자리(T5가 채운다) */
export default function NewAnalysisPage() {
  return (
    <main className={styles.page}>
      <h1 className={styles.title}>새 분석</h1>
    </main>
  );
}
