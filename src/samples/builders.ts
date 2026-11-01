/**
 * ③ 샘플 데이터 — 만드는 함수(H · F · I · Lk)와 거래내역 표 머리.
 * 이름·주민등록번호·전화번호·계좌번호·주소·금액은 모두 가상의 데모 데이터다(실제 인물·거래와 관계없음).
 * 원본: Main.dc.html 853줄 H, 855–867줄 F · I · Lk · TX_HEAD · TX_ALIGN — 기본값·키 순서를 그대로 옮겼다.
 * 부를 때마다 새 객체를 돌려준다. 이 폴더는 src/services/demo/** 만 import한다.
 */

import type { Exposure, InfoCategory, InfoSubject, RiskLevel, RuleId } from '@/display/rules';
import type { CellAlign, DocLink, EvidenceRef, Finding, Highlight, LinkDocRef, ReviewItem } from '@/services/types';

/** 원문 위치 조각 — H(위치 ID, 원문 값, 마스킹 값) */
export function H(a: string, x: string, m?: string): Highlight {
  return { a: a, x: x, m: m || '' };
}

/** F() 의 마지막 인자 — 기본값을 덮어쓸 값(예: 위치가 없을 때의 evidence) */
export type FindingExtra = Partial<Omit<Finding, 'ai'>>;

/** 탐지 항목. 최초 AI 분류(ai)는 만들 때의 cat · subject · exposure 를 복사해 둔다. */
export function F(
  id: string,
  cat: InfoCategory,
  label: string,
  masked: string,
  subject: InfoSubject,
  exposure: Exposure,
  risk: RiskLevel,
  reason: string,
  rule: RuleId,
  docId: string,
  page: number,
  anchors: string[],
  extra?: FindingExtra,
): Finding {
  const f: Omit<Finding, 'ai'> = { id, cat, label, masked, subject, exposure, risk, reason, rule, docId, page, anchors, evidence: '', status: 'open', memo: '', fpType: '', fpNote: '', reclassNote: '', updatedAt: '', ...(extra || {}) };
  return { ...f, ai: { cat: f.cat, subject: f.subject, exposure: f.exposure } };
}

/** I() 의 마지막 인자 — 연결 · 탐지 항목 · 다시 분석 문서 */
export type ReviewItemExtra = Partial<Pick<ReviewItem, 'linkId' | 'findingId' | 'retryDoc'>>;

/** 검토사항 */
export function I(
  id: string,
  type: ReviewItem['type'],
  title: string,
  desc: string,
  next: string,
  docId: string,
  page: number,
  evidence?: EvidenceRef[],
  extra?: ReviewItemExtra,
): ReviewItem {
  return { id, type, title, desc, next, docId, page, evidence: evidence || [], resolved: false, note: '', resolvedAt: '', resolvedBy: '', ...(extra || {}) };
}

/** 문서 간 연결 */
export function Lk(
  id: string,
  status: DocLink['status'],
  title: string,
  docs: LinkDocRef[],
  basis: string[],
  missing: string,
  check: string,
): DocLink {
  return { id, status, title, docs, basis, missing, check, decision: null, decisionNote: '', decidedAt: '', decidedBy: '' };
}

/** 거래내역 표 머리와 열 정렬 — 쓰는 곳에서 복사해 새 배열로 넣는다 */
export const TX_HEAD = ['거래일시', '적요', '출금', '입금', '잔액', '거래점'] as const;
export const TX_ALIGN = ['l', 'l', 'r', 'r', 'r', 'c'] as const satisfies readonly CellAlign[];
