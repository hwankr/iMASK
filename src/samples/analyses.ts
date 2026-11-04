/**
 * ③ 샘플 데이터 — 분석 건 6개(A1~A6)와 첫 이력.
 * 이름·주민등록번호·전화번호·계좌번호·주소·금액은 모두 가상의 데모 데이터다(실제 인물·거래와 관계없음).
 * 원본: Main.dc.html 1164–1187줄 mkA · summaryText · rawSamples — 값은 한 글자도 바꾸지 않았다.
 * (Object.assign(리터럴, 묶음) 은 같은 순서의 펼치기 { …리터럴, ...묶음 } 으로 썼다. 리터럴 타입을 지키기 위해서다.)
 * 부를 때마다 새 객체를 돌려준다. 이 폴더는 src/services/demo/** 만 import한다.
 */

import { CONFIG } from '@/config/app';
import { analysisRiskView } from '@/display/rules';
import type { Analysis } from '@/services/types';
import { incomeSet, loanResults, maskedSet, newSet, scanSet, brokenSet } from './sets';
import { loanDocs } from './documents';

/** mkA 입력 — 필수 7개 + 나머지(기본값이 있음) */
export type MkAInput = Pick<Analysis, 'id' | 'code' | 'name' | 'submittedAt' | 'status' | 'risk' | 'review'> & Partial<Analysis>;

export function mkA(o: MkAInput): Analysis {
  return { docs: [], findings: [], items: [], links: [], history: [], memo: '', memoAt: '', riskReasons: [], recs: [], limits: '', reviewer: '', reviewedAt: '', completionNote: '', demoQueued: false, retrying: false, analyzedAt: '', ...o };
}
export function summaryText(a: Analysis): string {
  if (a.status === 'failed') return '분석 실패 · 파일을 열 수 없음 · 위험등급 미평가';
  const head = a.status === 'partial' ? '분석 일부 실패 · 문서 ' + a.docs.filter((d) => d.status === 'failed').length + '개 실패' : '분석 완료';
  return head + ' · 탐지 ' + a.findings.length + '건 · 위험등급 ' + analysisRiskView(a.risk).label + ' · 검토사항 ' + a.items.length + '건';
}
export function rawSamples(): Analysis[] {
  const list = [
    mkA({ id: 'A1', code: 'DG-20261030-0007', name: '대출상담 서류 묶음', submittedAt: '2026-10-30 14:22', analyzedAt: '2026-10-30 14:31', status: 'done', risk: 'high', review: 'needed', docs: loanDocs(), ...loanResults() }),
    mkA({ id: 'A2', code: 'DG-20261029-0003', name: '소득증빙 확인', submittedAt: '2026-10-29 10:48', analyzedAt: '2026-10-29 10:52', status: 'done', risk: 'medium', review: 'none', ...incomeSet() }),
    mkA({ id: 'A3', code: 'DG-20261031-0002', name: '신규 접수 서류', submittedAt: '2026-10-31 14:56', analyzedAt: '', status: 'running', risk: 'unrated', review: 'none', ...newSet() }),
    mkA({ id: 'A4', code: 'DG-20261030-0002', name: '거래내역 스캔본', submittedAt: '2026-10-30 09:15', analyzedAt: '2026-10-30 09:24', status: 'partial', risk: 'high', review: 'needed', ...scanSet() }),
    mkA({ id: 'A5', code: 'DG-20261028-0011', name: '마스킹된 상담 서류', submittedAt: '2026-10-28 16:40', analyzedAt: '2026-10-28 16:44', status: 'done', risk: 'low', review: 'none', ...maskedSet() }),
    mkA({ id: 'A6', code: 'DG-20261030-0011', name: '손상된 문서 파일', submittedAt: '2026-10-30 18:02', analyzedAt: '2026-10-30 18:03', status: 'failed', risk: 'unrated', review: 'needed', ...brokenSet() }),
  ];
  let n = 0;
  list.forEach((a) => {
    a.history.push({ id: 'S' + (++n), at: a.submittedAt, actor: CONFIG.user.name, kind: 'request', target: '분석 건', change: '문서 ' + a.docs.length + '개 분석 요청', reason: '' });
    if (a.analyzedAt) a.history.push({ id: 'S' + (++n), at: a.analyzedAt, actor: '시스템', kind: 'ai', target: '분석 건', change: summaryText(a), reason: '' });
  });
  return list;
}
