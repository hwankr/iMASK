/* ==========================================================================
   /dev/states 보고서 상태 3개의 화면 쪽 시작 조건 — 원본 initScenario(Main.dc.html 1571–1580)
   - 데모 서비스 상태(demoProgressA1)는 PreparedState 의 prepare(state) 가 먼저 맞춘다.
   - 여기서는 내보내기 모달 상태만 만든다. report-saved 의 파일은 서비스 buildExport 결과 그대로다.
   ========================================================================== */

import type { ReportInitial } from '@/components/report/ReportScreen';
import { nowStr } from '@/lib/format';
import type { AnalysisService, StateId } from '@/services/analysis-service';

export type ReportStateId = Extract<StateId, 'report' | 'report-saved' | 'report-failed'>;

/** report-failed 의 실패 문구(원본 그대로) */
export const REPORT_FAILED_MESSAGE = '저장 위치에 파일을 쓰지 못했습니다. 잠시 후 다시 시도하거나 다른 형식을 선택하세요.';

/** 상태별 보고서 화면 처음 값 */
export async function reportScenario(id: ReportStateId, service: AnalysisService, analysisId: string): Promise<ReportInitial> {
  switch (id) {
    case 'report':
      return {};
    case 'report-saved': {
      const file = await service.buildExport(analysisId, 'csv');
      return { exportModal: { format: 'csv', state: 'saved', file, msg: '', at: nowStr() } };
    }
    case 'report-failed':
      return { exportModal: { format: 'csv', state: 'failed', file: null, msg: REPORT_FAILED_MESSAGE, at: '' } };
    default: {
      const unknownState: never = id;
      throw new Error('알 수 없는 보고서 상태: ' + String(unknownState));
    }
  }
}
