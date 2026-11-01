import type { Metadata } from 'next';
import Link from 'next/link';
import { LISTED_STATES, STATE_GROUPS } from '@/dev/states';
import styles from './states.module.css';

export const metadata: Metadata = {
  title: '개발용 · 상태 목록',
  robots: { index: false, follow: false },
};

/** /dev/states — 상태 23개(휴대폰 전용 제외)를 그룹별로 보여 준다. */
export default function DevStatesPage() {
  return (
    <main className={styles.page}>
      <header className={styles.head}>
        <span className={styles.badge}>개발용</span>
        <h1 className={styles.title}>화면 상태 목록</h1>
        <p className={styles.lead}>
          상태를 고르면 데모 서비스를 그 상태로 맞추고 해당 화면을 엽니다. 상태 {LISTED_STATES.length}개 · 휴대폰 전용 상태는 목록에서 뺐습니다.
        </p>
      </header>
      {STATE_GROUPS.map((group) => {
        const states = LISTED_STATES.filter((s) => s.group === group.id);
        return (
          <section key={group.id} className={styles.group} aria-labelledby={`group-${group.id}`}>
            <h2 id={`group-${group.id}`} className={styles.groupTitle}>
              {group.title}
              <span className={styles.groupCount}>{states.length}</span>
            </h2>
            <ul className={styles.list}>
              {states.map((s) => (
                <li key={s.id}>
                  <Link className={styles.link} href={`/dev/states/${s.id}`} data-state-link={s.id}>
                    <span className={styles.num}>{LISTED_STATES.indexOf(s) + 1}</span>
                    <span className={styles.name}>{s.title}</span>
                    <span className={styles.id}>{s.id}</span>
                  </Link>
                </li>
              ))}
            </ul>
          </section>
        );
      })}
    </main>
  );
}
