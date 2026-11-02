import { Button } from '@/components/ui';
import styles from './LiveDetailScreen.module.css';

/** /analyses/[id]/report — 실제 분석 모드에는 보고서가 아직 없다. 상세로 가는 길만 둔다. */
export function LiveReportNotice({ id }: { id: string }) {
  return (
    <div className={styles.screen}>
      <div className={`${styles.page} ${styles.narrow}`}>
        <h1 className={styles.title}>실제 분석 보고서는 아직 없습니다</h1>
        <p className={styles.lead}>실제 분석에서는 검토 결과 보고서와 내보내기를 아직 지원하지 않습니다. 분석 결과는 상세 화면에서 확인하세요.</p>
        <div className={styles.actions}>
          <Button href={`/analyses/${encodeURIComponent(id)}`} variant="primary">
            상세로 가기
          </Button>
        </div>
      </div>
    </div>
  );
}
