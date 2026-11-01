import { Skeleton, SkeletonCard, VisuallyHidden, cx } from '@/components/ui';
import styles from './DetailScreen.module.css';

/** 불러오는 중 뼈대 — 머리글 · 문서 목록 · 원문 · 결과 자리(휴대폰은 머리글과 원문만) */
export function DetailSkeleton({ label = '분석 건을 불러오는 중입니다.' }: { label?: string }) {
  return (
    <div className={styles.screen} aria-busy="true">
      <VisuallyHidden>
        <span role="status">{label}</span>
      </VisuallyHidden>
      <div className={styles.skHead} aria-hidden="true">
        <Skeleton size="title" className={styles.skTitle} />
        <Skeleton className={styles.skMeta} />
      </div>
      <div className={cx(styles.panes, styles.skPanes)} aria-hidden="true">
        <div className={cx(styles.skPane, styles.skLeft)}>
          <Skeleton size="title" width={60} />
          <Skeleton width={90} />
          <Skeleton width={70} />
          <Skeleton width={80} />
        </div>
        <div className={styles.skViewer}>
          <SkeletonCard look="viewer" lines={[46, 92, 78, 86, 58]} />
        </div>
        <div className={cx(styles.skPane, styles.skRight)}>
          <Skeleton size="title" width={50} />
          <Skeleton width={92} />
          <Skeleton width={84} />
          <Skeleton width={66} />
        </div>
      </div>
    </div>
  );
}
