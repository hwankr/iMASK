'use client';

import type { StateId } from '@/services/analysis-service';
import { DevStateBar } from './DevStateBar';
import { findState } from './states';
import styles from './StatePreview.module.css';

/**
 * /dev/states/[state] 미리보기.
 * 지금은 상태 제목과 안내만 보여 준다. 뒤 작업(T4·T5·T7·T8)이 DemoControls.prepare(state)로
 * 데모 서비스를 그 상태로 맞추고 실제 화면을 여기에 연결한다.
 */
export function StatePreview({ stateId }: { stateId: StateId }) {
  const state = findState(stateId);
  return (
    <div className={styles.wrap}>
      <DevStateBar stateId={stateId} />
      <section className={styles.body} aria-labelledby="dev-state-title">
        <p className={styles.id}>{stateId}</p>
        <h1 id="dev-state-title" className={styles.title}>
          {state?.title}
        </h1>
        <p className={styles.note}>화면 연결 전 — 이 상태의 화면은 뒤 작업에서 연결합니다.</p>
      </section>
    </div>
  );
}
