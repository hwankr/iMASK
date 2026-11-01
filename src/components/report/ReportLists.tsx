import { Icon, cx } from '@/components/ui';
import type { ReportView } from './reportModel';
import { ReportSection } from './ReportSection';
import styles from './ReportLists.module.css';

/** 02 주요 위험 사유 — Main 640–643. 사유 목록(높음 점) · 없을 때 안내 · 분석 한계(주의 띠) */
export function ReportReasons({ v }: { v: ReportView }) {
  return (
    <ReportSection n={2} title="주요 위험 사유">
      {v.reasons.length > 0 ? (
        <ol className={styles.list}>
          {v.reasons.map((r, i) => (
            <li key={i} className={styles.reason}>
              <span aria-hidden="true" className={styles.dot} />
              <span>{r}</span>
            </li>
          ))}
        </ol>
      ) : (
        <p className={styles.empty}>{v.noReasonsText}</p>
      )}
      {v.limits ? (
        <div className={styles.limits}>
          <span className={styles.limitsIcon}>
            <Icon name="dg-i-alert" size={17} strokeWidth={2.1} />
          </span>
          <span>
            <strong className={styles.limitsTitle}>분석 한계</strong> · {v.limits}
          </span>
        </div>
      ) : null}
    </ReportSection>
  );
}

/** 05 남아 있는 검토사항 — Main 659–662 */
export function ReportRemaining({ v }: { v: ReportView }) {
  return (
    <ReportSection n={5} title="남아 있는 검토사항">
      {v.remaining.length > 0 ? (
        <ul className={styles.remaining}>
          {v.remaining.map((r) => (
            <li key={r.id} className={styles.remainingItem}>
              <span className={styles.remainingHead}>
                <span className={styles.type}>{r.type}</span>
                <span className={styles.itemId}>{r.id}</span>
                <strong className={styles.itemTitle}>{r.title}</strong>
              </span>
              <span className={styles.itemWhere}>
                {r.where} · 할 일: {r.next}
              </span>
            </li>
          ))}
        </ul>
      ) : (
        <p className={styles.none}>
          <Icon name="dg-i-check-circle" size={18} strokeWidth={2.1} />
          남아 있는 검토사항이 없습니다.
        </p>
      )}
    </ReportSection>
  );
}

/** 06 권장 조치 — Main 665–668 */
export function ReportRecs({ v }: { v: ReportView }) {
  return (
    <ReportSection n={6} title="권장 조치">
      {v.recs.length > 0 ? (
        <ol className={styles.list}>
          {v.recs.map((r, i) => (
            <li key={i} className={styles.rec}>
              <span className={styles.recIcon}>
                <Icon name="dg-i-check-circle" size={20} />
              </span>
              <span>{r}</span>
            </li>
          ))}
        </ol>
      ) : (
        <p className={styles.empty}>분석이 끝나면 권장 조치가 표시됩니다.</p>
      )}
    </ReportSection>
  );
}

/** 07 검토자 메모 — Main 671–674 */
export function ReportMemo({ v }: { v: ReportView }) {
  return (
    <ReportSection n={7} title="검토자 메모">
      <div className={cx(styles.memo, !v.hasMemo && styles.memoEmpty)}>{v.memo}</div>
      {v.completionNote ? (
        <div className={styles.completion}>
          <strong className={styles.completionTitle}>검토 완료 시 남긴 내용</strong> · {v.completionNote}
        </div>
      ) : null}
    </ReportSection>
  );
}
