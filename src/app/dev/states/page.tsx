import type { Metadata } from 'next';
import Link from 'next/link';
import { notFound } from 'next/navigation';
import { DemoBadge } from '@/components/layout/DemoBadge';
import { devPagesEnabled } from '@/dev/devPages';
import { LISTED_STATES, STATE_GROUPS } from '@/dev/states';
import styles from './states.module.css';

// 운영 빌드(개발용 경로가 닫힘)에서는 개발용 제목을 내보내지 않는다 — 404 화면과 같은 제목
export const metadata: Metadata = devPagesEnabled()
  ? { title: '개발용 · 상태 목록', robots: { index: false, follow: false } }
  : { title: '페이지를 찾을 수 없습니다' };

/**
 * /dev/states — 상태 23개(휴대폰 전용 제외)를 그룹별로 보여 준다. 항목마다 상태 제목과 그 상태가 여는 화면 경로.
 * `<main>` 은 AppShell 이 그리므로 최상위는 `<div>` 다.
 */
export default function DevStatesPage() {
  if (!devPagesEnabled()) notFound();
  return (
    <div className={styles.page}>
      <header className={styles.head}>
        <div className={styles.badges}>
          <span className={styles.badge}>개발용</span>
          <DemoBadge />
        </div>
        <h1 className={styles.title}>화면 상태 목록</h1>
        <p className={styles.lead}>상태를 고르면 데모 데이터를 그 상태로 맞추고 화면을 엽니다. 실제 저장은 없습니다.</p>
        <p className={styles.note}>
          상태 {LISTED_STATES.length}개 · 미리보기 위 막대에서 이전·다음으로 넘기거나 키보드 <kbd className={styles.kbd}>[</kbd> <kbd className={styles.kbd}>]</kbd> 를 누릅니다. 휴대폰 전용 상태 2개는 목록에 없고 주소(
          <code className={styles.code}>/dev/states/detail-docs</code> · <code className={styles.code}>/dev/states/detail-results</code>)로 엽니다.
        </p>
      </header>
      {STATE_GROUPS.map((group) => {
        const states = LISTED_STATES.filter((s) => s.group === group.id);
        return (
          <section key={group.id} className={styles.group} aria-labelledby={`group-${group.id}`}>
            <h2 id={`group-${group.id}`} className={styles.groupTitle}>
              {group.title}
              <span className={styles.groupCount}>{states.length}</span>
              <code className={styles.groupPath}>{group.path}</code>
            </h2>
            <ul className={styles.list}>
              {states.map((s) => (
                <li key={s.id}>
                  <Link className={styles.link} href={`/dev/states/${s.id}`} data-state-link={s.id}>
                    <span className={styles.num}>{LISTED_STATES.indexOf(s) + 1}</span>
                    <span className={styles.name}>{s.title}</span>
                    <span className={styles.meta}>
                      <span className={styles.id}>{s.id}</span>
                      <span className={styles.path}>
                        <span className={styles.pathLabel}>화면</span> {group.path}
                      </span>
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          </section>
        );
      })}
    </div>
  );
}
