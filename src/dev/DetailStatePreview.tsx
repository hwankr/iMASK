'use client';

import { useEffect, useState } from 'react';
import { DetailScreen } from '@/components/detail/DetailScreen';
import type { DetailUiState } from '@/components/detail/detailState';
import { VisuallyHidden } from '@/components/ui';
import { useService } from '@/services/react';
import { detailScenario, type DetailStateId } from './detailScenarios';
import styles from './StatePreview.module.css';

/**
 * 상세 상태 미리보기 — 시작 조건(detail-edit 의 분류는 서비스 값에서)을 만든 뒤 상세 화면을 그 상태로 연다.
 * PreparedState 가 데모 서비스를 먼저 그 상태로 맞추고, 열 분석 ID 를 넘겨준다.
 */
export function DetailStatePreview({ stateId, analysisId }: { stateId: DetailStateId; analysisId: string | undefined }) {
  const service = useService();
  const [ready, setReady] = useState<{ stateId: DetailStateId; initial: Partial<DetailUiState> } | null>(null);

  useEffect(() => {
    if (!service || !analysisId) return;
    let alive = true;
    void detailScenario(stateId, service, analysisId).then((initial) => {
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
  return (
    <div className={styles.fillBody}>
      <DetailScreen key={`${stateId}:${analysisId}`} id={analysisId} initial={ready.initial} />
    </div>
  );
}
