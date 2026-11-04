'use client';

/* ==========================================================================
   실제 분석 상세 — 결과 패널 '분석 요약' 탭(데모에는 없다)
   - 위험도 판정(overall.text)과 다음 단계 문구(권장 조치 · 검토 안내 — next_text)를 글자 그대로 보인다
     (줄바꿈 유지, 인용 표시 【…】만 지움 — HTML 로 그리지 않는다).
   - 결과 요약 줄(분류한 서류 · 추출한 서류 · 위험도 · 마지막 단계 · 기타 서류 · 걸린 시간 · Upstage 작업 번호).
   - 원본 단계별 JSON 은 접은 칸(<details>). 처음 펼칠 때 불러오고(useLiveStages — 상세 화면이 들고 있어 다시 부르지 않음),
     불러오는 중 · 실패(다시 시도) · 단계 없음을 보인다. 단계 목록은 기존 결과 JSON 보기와 같은 StageList.
   ========================================================================== */

import { useState } from 'react';
import { Button, Icon, RiskBadge, Spinner, cx } from '@/components/ui';
import type { Analysis } from '@/services/types';
import { guideText } from '@/components/detail/liveViewerModel';
import { StageList } from './LiveResult';
import type { LiveStagesState } from './liveHooks';
import { nextStageTitle, riskText, stageRows, summaryRows } from './liveModel';
import liveStyles from './LiveDetailScreen.module.css';
import styles from './LiveSummaryTab.module.css';

export interface LiveSummaryTabProps {
  analysis: Analysis;
  stages: LiveStagesState;
  /** 단계별 JSON 을 불러온다(처음 펼칠 때 · 다시 시도) */
  onLoadStages: () => void;
}

export function LiveSummaryTab({ analysis: a, stages, onLoadStages }: LiveSummaryTabProps) {
  const raw = a.raw;
  const overall = raw?.overall ?? null;
  const judge = guideText(overall?.text);
  const next = guideText(overall?.nextText);
  const rows = summaryRows(raw?.result ?? null, { createdAt: raw?.createdAt ?? '', startedAt: raw?.startedAt ?? '', updatedAt: raw?.updatedAt ?? '', jobId: raw?.jobId ?? '' });
  const [open, setOpen] = useState(false);

  return (
    <div className={styles.wrap}>
      <section className={styles.block} aria-labelledby="live-judge-title">
        <h3 id="live-judge-title" className={styles.title}>
          위험도 판정
          <RiskBadge level={a.risk} size="xs" />
          <span className={styles.level}>{riskText(overall?.level)}</span>
        </h3>
        {judge ? <p className={styles.text}>{judge}</p> : <p className={styles.none}>위험도 판정 문구가 없습니다.</p>}
      </section>

      <section className={styles.block} aria-labelledby="live-next-title">
        <h3 id="live-next-title" className={styles.title}>
          {nextStageTitle(overall?.nextStage)}
        </h3>
        {next ? <p className={styles.text}>{next}</p> : <p className={styles.none}>다음 단계 안내가 없습니다.</p>}
      </section>

      <section className={styles.block} aria-labelledby="live-rows-title">
        <h3 id="live-rows-title" className={styles.title}>
          결과 요약
        </h3>
        <dl className={styles.rows}>
          {rows.map((r) => (
            <div key={r.key} className={styles.row} data-row={r.key}>
              <dt className={styles.label}>{r.label}</dt>
              <dd className={cx(styles.value, r.key === 'job' && liveStyles.mono)}>{r.value}</dd>
            </div>
          ))}
        </dl>
      </section>

      <details
        className={styles.raw}
        open={open}
        onToggle={(e) => {
          const isOpen = e.currentTarget.open;
          setOpen(isOpen);
          if (isOpen && stages.status === 'idle') onLoadStages();
        }}
      >
        <summary className={styles.rawSummary}>
          <Icon name="dg-i-chev-down" size={16} strokeWidth={2.2} className={styles.rawChev} />
          원본 단계별 JSON
          {stages.status === 'ready' && stages.stages ? <span className={styles.rawCount}>{stages.stages.length}개</span> : null}
        </summary>
        {open ? (
          <div className={styles.rawBody} aria-live="polite">
            {stages.status === 'idle' || stages.status === 'loading' ? (
              <p className={styles.state}>
                <Spinner size={16} /> 단계별 결과를 불러오는 중입니다.
              </p>
            ) : null}
            {stages.status === 'error' ? (
              <div role="alert" className={styles.error}>
                <span>{stages.message}</span>
                <Button size="sm" variant="secondary" icon="dg-i-refresh" onClick={onLoadStages}>
                  다시 시도
                </Button>
              </div>
            ) : null}
            {stages.status === 'ready' ? (
              <>
                <p className={styles.lead}>워크플로우가 돌려준 순서대로입니다. 단계를 펼치면 결과 JSON(data · additional_values)을 볼 수 있습니다.</p>
                <StageList stages={stageRows({ stages: stages.stages ?? [] })} />
              </>
            ) : null}
          </div>
        ) : null}
      </details>
    </div>
  );
}
