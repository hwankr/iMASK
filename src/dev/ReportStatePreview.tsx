'use client';

import { useEffect, useState } from 'react';
import { ReportScreen, type ReportInitial } from '@/components/report/ReportScreen';
import { VisuallyHidden } from '@/components/ui';
import { useService } from '@/services/react';
import { reportScenario, type ReportStateId } from './reportScenarios';
import styles from './StatePreview.module.css';

/**
 * 보고서 상태 미리보기 — 시작 조건(report-saved 의 파일은 서비스에서)을 만든 뒤 보고서 화면을 그 상태로 연다.
 * PreparedState 가 데모 서비스를 먼저 그 상태로 맞추고, 열 분석 ID 를 넘겨준다.
 */
export function ReportStatePreview({ stateId, analysisId }: { stateId: ReportStateId; analysisId: string | undefined }) {
  const service = useService();
  const [ready, setReady] = useState<{ stateId: ReportStateId; initial: ReportInitial } | null>(null);

  useEffect(() => {
    if (!service || !analysisId) return;
    let alive = true;
    void reportScenario(stateId, service, analysisId).then((initial) => {
      if (alive) setReady({ stateId, initial });
    });
    return () => {
      alive = false;
    };
  }, [service, stateId, analysisId]);

  if (!analysisId) {
    return (
      <p role="alert" className={styles.note}>
        이 상태의 분석 건을 준비하지 못했습니다(prepare 가 분석 ID 를 돌려주지 않음).
      </p>
    );
  }
  if (!ready || ready.stateId !== stateId) {
    return (
      <VisuallyHidden>
        <span role="status">상태를 준비하는 중입니다.</span>
      </VisuallyHidden>
    );
  }
  return <ReportScreen id={analysisId} initial={ready.initial} />;
}
