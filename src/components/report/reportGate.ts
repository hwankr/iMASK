/* ==========================================================================
   보고서를 그릴지 — 순수 함수. 불러온 분석 하나로 보고서 화면이 무엇을 그릴지 정한다.
   - 데모 분석(raw 없음) → 'report'(지금 그대로 — 어떤 상태든 보고서를 그린다).
   - 실제 분석(raw 있음):
     대기 · 분석 중 → 'waiting'(안내 '분석이 끝나면 보고서를 볼 수 있습니다' + 상세로 가기, 주기 조회 없음),
     실패 · 일부 실패 · 완료지만 공통 계약 결과가 아님(옛 형식) → 'unavailable'(안내 '보고서를 만들 수 없는 분석입니다'),
     공통 계약 결과인데 검토 기록을 읽지 못함(reviewable false) → 'loadFailed'(불러오기 실패 블록 + 다시 불러오기 —
     검토 상태가 빠진 보고서를 내보내지 않게),
     보고서 대상(detailReady && reviewable) → 'report'.
   ========================================================================== */

import type { Analysis } from '@/services/types';

export type ReportGate = 'report' | 'waiting' | 'unavailable' | 'loadFailed';

export function reportGate(a: Analysis): ReportGate {
  const raw = a.raw;
  if (!raw) return 'report';
  if (a.status === 'queued' || a.status === 'running') return 'waiting';
  if (a.status !== 'done' || !raw.detailReady) return 'unavailable';
  if (!raw.reviewable) return 'loadFailed';
  return 'report';
}
