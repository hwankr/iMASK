import { AnalysisStatusLabel, Icon, ReviewStatusPill, RiskBadge } from '@/components/ui';
import type { ReportView } from './reportModel';
import styles from './ReportHead.module.css';

/**
 * 보고서 머리 — Main 612–625. 보고서 표시·분석 ID·생성 시각, 제목(h1#rp-title),
 * 최종 위험등급·분석 상태·검토 상태·검토자/완료 시각, 검토 미완료 안내.
 * 상태 표기는 서비스 값을 공통 컴포넌트에 그대로 넘긴다(② 규칙으로 그림).
 */
export function ReportHead({ v, generatedAt }: { v: ReportView; generatedAt: string }) {
  return (
    <header className={styles.head}>
      <div className={styles.titleBlock}>
        <div className={styles.kicker}>
          <span className={styles.kind}>검토 결과 보고서</span>
          <span className={styles.code}>{v.code}</span>
          <span>보고서 생성 {generatedAt}</span>
        </div>
        <h1 id="rp-title" className={styles.title}>
          {v.name}
        </h1>
      </div>
      <dl className={styles.meta}>
        <div className={styles.cell}>
          <dt className={styles.dt}>최종 위험등급</dt>
          <dd className={styles.dd}>
            <RiskBadge level={v.risk} size="lg" />
          </dd>
        </div>
        <div className={styles.cell}>
          <dt className={styles.dt}>분석 상태</dt>
          <dd className={styles.dd}>
            <AnalysisStatusLabel status={v.status} size="xl" />
          </dd>
        </div>
        <div className={styles.cell}>
          <dt className={styles.dt}>검토 상태</dt>
          <dd className={styles.dd}>
            <ReviewStatusPill status={v.review} size="lg" />
          </dd>
        </div>
        <div className={styles.cell}>
          <dt className={styles.dt}>검토자 · 검토 완료 시각</dt>
          <dd className={styles.completed}>{v.completedText}</dd>
        </div>
      </dl>
      {v.notDone ? (
        <div role="note" className={styles.note}>
          <span className={styles.noteIcon}>
            <Icon name="dg-i-info" size={17} />
          </span>
          <span>
            <strong className={styles.noteStrong}>검토가 아직 완료되지 않았습니다.</strong>
          </span>
        </div>
      ) : null}
    </header>
  );
}
