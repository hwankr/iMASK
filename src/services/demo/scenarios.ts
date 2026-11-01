/* ==========================================================================
   ④ 데모 서비스 — /dev/states 상태별 데이터 준비.
   원본: Main.dc.html 1536–1580줄 initScenario 의 '데이터' 부분만 옮겼다
   (원본도 상태를 바꿀 때마다 svc.reset() 뒤에 initScenario 를 부른다).
   탭·선택 항목·모달·업로드 파일 목록 같은 화면 쪽 시작 조건은 각 화면 작업이 src/dev/ 에서 맡는다.
   ========================================================================== */

import type { StateId } from '../analysis-service';
import type { DemoCore, QueuedFileInput } from './core';
import { demoProgressA1 } from './seed';

/** 원본 userFile(name, ext, size) 중 createQueued 가 쓰는 값만 — 업로드 화면용 도우미는 화면 쪽에 둔다 */
const queuedFile = (name: string, ext: string, size: number): QueuedFileInput => ({ name, ext, size });

/**
 * reset() 이 끝난 코어에 상태 데이터를 적용하고, 그 상태가 열어야 할 분석 ID를 돌려준다.
 * 목록·업로드 상태는 분석 ID가 없다.
 */
export function applyScenario(core: DemoCore, state: StateId): { analysisId?: string } {
  switch (state) {
    case 'list':
    case 'list-noresults':
    case 'upload':
    case 'upload-selected':
    case 'upload-unsupported':
    case 'upload-limit':
    case 'upload-failed':
    case 'upload-requesting':
      return {};
    case 'list-empty':
      core.clearAll();
      return {};
    case 'detail':
    case 'detail-results':
    case 'detail-docs':
    case 'detail-nolocation':
    case 'detail-review':
    case 'detail-links':
    case 'detail-edit':
    case 'detail-complete':
      return { analysisId: 'A1' };
    case 'detail-queued':
      return {
        analysisId: core.createQueued('김○○ 대출 서류 (직접 올린 파일)', [
          queuedFile('대출서류_스캔.pdf', 'PDF', 3145728),
          queuedFile('통장사본_촬영.jpg', 'JPG', 912384),
        ]),
      };
    case 'detail-running':
      return { analysisId: 'A3' };
    case 'detail-partial':
      return { analysisId: 'A4' };
    case 'detail-failed':
      return { analysisId: 'A6' };
    case 'detail-completed':
      return { analysisId: 'A5' };
    case 'report':
    case 'report-saved':
    case 'report-failed':
      demoProgressA1(core);
      return { analysisId: 'A1' };
    default: {
      const unknownState: never = state;
      throw new Error('알 수 없는 상태: ' + String(unknownState));
    }
  }
}
