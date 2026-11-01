import type { CSSProperties } from 'react';
import { cx } from '@/components/ui';
import type { ReportView } from './reportModel';
import { ReportSection } from './ReportSection';
import { CHANGE_TABLE_TITLE, ReportChangeTable } from './ReportTables';
import styles from './ReportHistory.module.css';

/**
 * 08 수정 이력과 검토 기록 — Main 676–700.
 * 최초 AI 결과와 담당자 수정(표 또는 없음 안내), 검토 기록(세로 선 + 구분별 색 점 타임라인).
 */
export function ReportHistory({ v }: { v: ReportView }) {
  return (
    <ReportSection n={8} title="수정 이력과 검토 기록" look="history">
      <h3 className={styles.h3}>{CHANGE_TABLE_TITLE}</h3>
      {v.changes.length > 0 ? (
        <ReportChangeTable v={v} />
      ) : (
        <p className={styles.empty}>담당자가 수정한 탐지 항목이 없습니다. 모든 항목이 최초 AI 결과와 같습니다.</p>
      )}
      <h3 className={cx(styles.h3, styles.h3Log)}>검토 기록</h3>
      <ol className={styles.timeline}>
        {v.history.map((h) => (
          <li key={h.id} className={styles.entry} style={{ '--dot': h.dot, '--kind-fg': h.kindFg } as CSSProperties}>
            <span aria-hidden="true" className={styles.dot} />
            <span className={styles.at}>{h.at}</span>
            <div className={styles.body}>
              <div className={styles.line1}>
                <strong className={styles.kind}>{h.kind}</strong>
                <span className={styles.actor}>{h.actor}</span>
                <span className={styles.target}>{h.target}</span>
              </div>
              <span className={styles.change}>{h.change}</span>
              <span className={styles.reason}>사유·메모 · {h.reason}</span>
            </div>
          </li>
        ))}
      </ol>
    </ReportSection>
  );
}
