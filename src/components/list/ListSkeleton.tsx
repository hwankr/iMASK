import { Skeleton, VisuallyHidden } from '@/components/ui';
import styles from './ListSkeleton.module.css';

const ROWS = [62, 48, 70, 54, 66];

/**
 * 불러오는 중 — 요약 카드 띠와 목록 행 자리에 뼈대 막대(dg-shimmer).
 * 프로토타입에는 없는 상태다(데이터가 동기). 실제 화면처럼 서비스가 Promise 로 답하므로 첫 응답 전에 보인다.
 * 크기는 실제 요약 카드(띠 · 카드 여백)와 표 행(72px)에 맞춰 화면이 덜 흔들리게 했다.
 */
export function ListSkeleton() {
  return (
    <div className={styles.wrap} aria-busy="true">
      <VisuallyHidden>
        <span role="status">분석 목록을 불러오는 중입니다.</span>
      </VisuallyHidden>
      <div className={styles.band} aria-hidden="true">
        {[0, 1, 2].map((i) => (
          <div key={i} className={styles.card}>
            <Skeleton size="text" width={44} />
            <Skeleton size="title" width={28} className={styles.num} />
            <Skeleton size="text" width={70} className={styles.hint} />
          </div>
        ))}
      </div>
      <div className={styles.rows} aria-hidden="true">
        <div className={styles.toolbar}>
          <span className={styles.search} />
        </div>
        {ROWS.map((w, i) => (
          <div key={i} className={styles.row}>
            <span className={styles.tile} />
            <div className={styles.lines}>
              <Skeleton size="title" width={w} />
              <Skeleton size="text" width={Math.round(w * 0.6)} />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
