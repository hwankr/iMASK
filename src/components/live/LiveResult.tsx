'use client';

/* ==========================================================================
   실제 분석 결과 — 요약 줄(result.summary) + 단계별 결과(result.stages, output 순서)
   - 단계마다 <details>(단계 이름 · 같은 이름이 여러 개면 (2/5) · 상태). 펼칠 때만 JsonTree 를 그린다.
   - 단계 목록(StageList)은 상세 검토 화면의 '분석 요약' 탭(LiveSummaryTab)도 같이 쓴다.
   ========================================================================== */

import { useState } from 'react';
import { cx } from '@/components/ui';
import { JsonTree } from './JsonTree';
import { stageRows, summaryRows, type StageRow } from './liveModel';
import styles from './LiveDetailScreen.module.css';

export interface LiveResultProps {
  result: unknown;
  createdAt: string;
  updatedAt: string;
  jobId: string;
}

export function LiveResult({ result, createdAt, updatedAt, jobId }: LiveResultProps) {
  const rows = summaryRows(result, { createdAt, updatedAt, jobId });
  const stages = stageRows(result);
  return (
    <>
      <section className={styles.card} aria-labelledby="live-summary-title">
        <h2 id="live-summary-title" className={styles.cardTitle}>
          결과 요약
        </h2>
        <dl className={styles.summary}>
          {rows.map((r) => (
            <div key={r.key} className={cx(styles.summaryRow, r.key === 'docs' && styles.summaryWide)} data-row={r.key}>
              <dt className={styles.summaryLabel}>{r.label}</dt>
              <dd className={cx(styles.summaryValue, r.key === 'job' && styles.mono)}>{r.value}</dd>
            </div>
          ))}
        </dl>
      </section>

      <section className={styles.card} aria-labelledby="live-stages-title">
        <h2 id="live-stages-title" className={styles.cardTitle}>
          단계별 결과 <span className={styles.cardCount}>{stages.length}개</span>
        </h2>
        <p className={styles.cardLead}>워크플로우가 돌려준 순서대로입니다. 단계를 펼치면 결과 JSON(data · additional_values)을 볼 수 있습니다.</p>
        <StageList stages={stages} />
      </section>
    </>
  );
}

/** 단계별 결과 목록 — 없으면 '단계 결과가 없습니다.' */
export function StageList({ stages }: { stages: StageRow[] }) {
  if (!stages.length) return <p className={styles.empty}>단계 결과가 없습니다.</p>;
  return (
    <ol className={styles.stages}>
      {stages.map((s) => (
        <StageItem key={s.index} stage={s} />
      ))}
    </ol>
  );
}

function StageItem({ stage: s }: { stage: StageRow }) {
  const [open, setOpen] = useState(false);
  return (
    <li className={styles.stage}>
      <details className={styles.stageDetails} open={open} onToggle={(e) => setOpen(e.currentTarget.open)}>
        <summary className={styles.stageSummary}>
          <span className={styles.stageNo}>{s.index + 1}</span>
          <span className={styles.stageName}>
            {s.label}
            {s.counter ? <span className={styles.stageCounter}> {s.counter}</span> : null}
          </span>
          {s.status ? <span className={cx(styles.stageStatus, s.failed && styles.stageFailed)}>{s.status}</span> : null}
        </summary>
        {open ? (
          <div className={styles.stageBody}>
            <JsonTree name="data" value={s.data} />
            <JsonTree name="additional_values" value={s.additionalValues} />
            {s.contents ? <JsonTree name="contents" value={s.contents} defaultOpen={false} /> : null}
          </div>
        ) : null}
      </details>
    </li>
  );
}
