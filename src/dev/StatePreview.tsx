'use client';

import type { ReactNode } from 'react';
import { ListScreen } from '@/components/list/ListScreen';
import { cx } from '@/components/ui';
import type { StateId } from '@/services/analysis-service';
import { DetailStatePreview } from './DetailStatePreview';
import { DevStateBar } from './DevStateBar';
import { PreparedState, type PreparedResult } from './PreparedState';
import { ReportStatePreview } from './ReportStatePreview';
import { findState } from './states';
import { UploadStatePreview } from './UploadStatePreview';
import styles from './StatePreview.module.css';

/**
 * 연결된 상태 — 데모 서비스를 prepare(state)로 맞춘 뒤 실제 화면을 그린다.
 * 목록 상태(T4): 필터는 URL 과 잇지 않는다(syncWithUrl=false) — 실제 화면 경로에 개발용 값을 넣지 않기 위해서다.
 * 업로드 상태(T5): 프로토타입 initScenario 의 시작 조건(uploadScenarios.ts)으로 새 분석 화면을 연다.
 * 상세 상태(T7): prepare 가 돌려준 분석 ID 로 상세 화면을 열고, 화면 시작 조건(detailScenarios.ts)을 준다.
 * 보고서 상태(T8): prepare 가 돌려준 분석 ID 로 보고서를 열고, 내보내기 모달 시작 조건(reportScenarios.ts)을 준다.
 */
const CONNECTED: Partial<Record<StateId, (prepared: PreparedResult) => ReactNode>> = {
  list: () => <ListScreen syncWithUrl={false} />,
  'list-empty': () => <ListScreen syncWithUrl={false} />,
  'list-noresults': () => <ListScreen syncWithUrl={false} initialFilters={{ q: '전세 계약서' }} />,
  upload: () => <UploadStatePreview stateId="upload" />,
  'upload-selected': () => <UploadStatePreview stateId="upload-selected" />,
  'upload-unsupported': () => <UploadStatePreview stateId="upload-unsupported" />,
  'upload-limit': () => <UploadStatePreview stateId="upload-limit" />,
  'upload-failed': () => <UploadStatePreview stateId="upload-failed" />,
  'upload-requesting': () => <UploadStatePreview stateId="upload-requesting" />,
  detail: (r) => <DetailStatePreview stateId="detail" analysisId={r.analysisId} />,
  'detail-queued': (r) => <DetailStatePreview stateId="detail-queued" analysisId={r.analysisId} />,
  'detail-running': (r) => <DetailStatePreview stateId="detail-running" analysisId={r.analysisId} />,
  'detail-partial': (r) => <DetailStatePreview stateId="detail-partial" analysisId={r.analysisId} />,
  'detail-failed': (r) => <DetailStatePreview stateId="detail-failed" analysisId={r.analysisId} />,
  'detail-completed': (r) => <DetailStatePreview stateId="detail-completed" analysisId={r.analysisId} />,
  'detail-nolocation': (r) => <DetailStatePreview stateId="detail-nolocation" analysisId={r.analysisId} />,
  'detail-review': (r) => <DetailStatePreview stateId="detail-review" analysisId={r.analysisId} />,
  'detail-links': (r) => <DetailStatePreview stateId="detail-links" analysisId={r.analysisId} />,
  'detail-edit': (r) => <DetailStatePreview stateId="detail-edit" analysisId={r.analysisId} />,
  'detail-complete': (r) => <DetailStatePreview stateId="detail-complete" analysisId={r.analysisId} />,
  /* 휴대폰 전용 — 목록에는 없고 주소로만 연다(데스크톱 폭에서는 휴대폰 탭이 화면에 영향 없음) */
  'detail-docs': (r) => <DetailStatePreview stateId="detail-docs" analysisId={r.analysisId} />,
  'detail-results': (r) => <DetailStatePreview stateId="detail-results" analysisId={r.analysisId} />,
  report: (r) => <ReportStatePreview stateId="report" analysisId={r.analysisId} />,
  'report-saved': (r) => <ReportStatePreview stateId="report-saved" analysisId={r.analysisId} />,
  'report-failed': (r) => <ReportStatePreview stateId="report-failed" analysisId={r.analysisId} />,
};

/**
 * /dev/states/[state] 미리보기.
 * 연결된 상태는 데모 서비스를 그 상태로 맞추고 실제 화면을 연다(25개 모두 연결).
 * 표에 없는 상태가 생기면 제목과 안내만 보여 준다.
 */
export function StatePreview({ stateId }: { stateId: StateId }) {
  const state = findState(stateId);
  const render = CONNECTED[stateId];
  return (
    <div className={cx(styles.wrap, state?.group === 'detail' && styles.fill)}>
      <DevStateBar stateId={stateId} />
      {render ? (
        <PreparedState key={stateId} stateId={stateId}>
          {(prepared) => render(prepared)}
        </PreparedState>
      ) : (
        <section className={styles.body} aria-labelledby="dev-state-title">
          <p className={styles.id}>{stateId}</p>
          <h1 id="dev-state-title" className={styles.title}>
            {state?.title}
          </h1>
          <p className={styles.note}>화면 연결 전 — 이 상태의 화면은 뒤 작업에서 연결합니다.</p>
        </section>
      )}
    </div>
  );
}
