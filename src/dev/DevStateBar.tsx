import Link from 'next/link';
import type { StateId } from '@/services/analysis-service';
import { statePosition } from './states';
import styles from './DevStateBar.module.css';

/** /dev/states/[state] 미리보기 위에 붙는 막대 — ← 상태 목록 · n / 23 · 제목 · 이전 · 다음 */
export function DevStateBar({ stateId }: { stateId: StateId }) {
  const pos = statePosition(stateId);
  if (!pos) return null;
  const { state, number, total, prev, next } = pos;
  return (
    <nav className={styles.bar} aria-label="개발용 상태 이동">
      <Link className={styles.back} href="/dev/states">
        ← 상태 목록
      </Link>
      <span className={styles.sep} aria-hidden="true">·</span>
      {number === null ? (
        <span className={styles.phone}>휴대폰 전용</span>
      ) : (
        <span className={styles.count}>{`${number} / ${total}`}</span>
      )}
      <span className={styles.sep} aria-hidden="true">·</span>
      <span className={styles.title} aria-current="page">
        {state.title}
      </span>
      <span className={styles.moves}>
        {prev ? (
          <Link className={styles.move} href={`/dev/states/${prev.id}`} title={prev.title}>
            이전
          </Link>
        ) : (
          <span className={styles.move} aria-disabled="true">이전</span>
        )}
        {next ? (
          <Link className={styles.move} href={`/dev/states/${next.id}`} title={next.title}>
            다음
          </Link>
        ) : (
          <span className={styles.move} aria-disabled="true">다음</span>
        )}
      </span>
    </nav>
  );
}
