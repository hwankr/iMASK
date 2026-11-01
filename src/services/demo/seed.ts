/* ==========================================================================
   ④ 데모 서비스 — 샘플에 미리 해 둔 검토 동작. 원본: Main.dc.html 1188–1204줄.
   - seedReviewActions: reset() 때마다 적용(A1 일부 검토, A5 검토 완료).
   - demoProgressA1: 보고서 상태(report*)용 — A1 검토를 거의 끝내고 완료한다.
   - 고정 시각 at() 으로 실행하므로 이력 시각이 언제나 같다.
   - 서비스를 조작하므로 ③ 샘플(순수 데이터)이 아니라 여기에 둔다.
   ========================================================================== */

import { FP_REASONS } from '@/display/rules';
import type { DemoCore } from './core';

export function seedReviewActions(svc: DemoCore): void {
  svc.at('2026-10-30 16:05', () => { svc.setStatus('A1', 'F-01', 'confirmed'); svc.saveFindingMemo('A1', 'F-01', '원본 보관 전 마스킹 사본으로 교체 필요'); });
  svc.at('2026-10-30 16:10', () => svc.markFalsePositive('A1', 'F-10', FP_REASONS[0], '은행 양식 관리번호로 개인 계좌번호가 아님'));
  svc.at('2026-10-30 16:14', () => svc.reclassify('A1', 'F-12', { subject: '기타 · 은행 직원' }, '상담 직원 서명란에 적힌 직원 성명'));
  svc.at('2026-10-29 09:10', () => svc.confirmMany('A5', ['P-01', 'P-02', 'P-03', 'P-04']));
  svc.at('2026-10-29 09:11', () => svc.saveMemo('A5', '모든 개인정보가 원본에서 가려져 있어 추가 조치가 필요하지 않습니다.'));
  svc.at('2026-10-29 09:12', () => svc.completeReview('A5', ''));
}

export function demoProgressA1(svc: DemoCore): void {
  svc.at('2026-10-30 16:22', () => svc.confirmMany('A1', ['F-02', 'F-03', 'F-04', 'F-05', 'F-06', 'F-07', 'F-08', 'F-09', 'F-11', 'F-13', 'F-14', 'F-15', 'F-16', 'F-17', 'F-18', 'F-19', 'F-21', 'F-22']));
  svc.at('2026-10-30 16:27', () => { svc.setStatus('A1', 'F-20', 'confirmed'); svc.resolveItem('A1', 'R-03', '고객과 통화해 최신 연락처(…7719)를 확인함. 거래내역서의 번호는 예전 번호임.'); });
  svc.at('2026-10-30 16:31', () => svc.decideLink('A1', 'L-02', 'linked', '고객 통화로 본인 급여계좌임을 확인함.'));
  svc.at('2026-10-30 16:32', () => svc.decideLink('A1', 'L-03', 'unlinked', '보증인과의 거래 여부는 이번 심사와 관계없어 연결하지 않음.'));
  svc.at('2026-10-30 16:34', () => { svc.setStatus('A1', 'F-23', 'confirmed'); svc.resolveItem('A1', 'R-05', '2쪽 9월 27일 거래 적요에서 확인함. 주민등록번호 전체가 적혀 있음.'); });
  svc.at('2026-10-30 16:37', () => svc.saveMemo('A1', '주민등록번호 · 계좌번호가 전체 노출된 서류는 마스킹 사본으로 교체를 요청함.\n거래내역서 2쪽은 원본 재스캔 후 다시 확인 예정.'));
  svc.at('2026-10-30 16:40', () => svc.completeReview('A1', '판독 불가 영역(R-01)과 잘린 페이지(R-02)는 원본 확인 후 보완 예정.'));
}
