/* ==========================================================================
   보고서용 안전한 사본 — 순수 함수. 실제 분석의 보고서 화면과 실제 서비스의 내보내기 파일은 원래 분석이 아니라
   이 사본으로만 만든다(원문 값이 보고서 DOM · 내려받은 파일에 들어가지 않게).
   - 실제 분석인지는 Analysis.raw 가 있는지로 가른다(실제 분석 서비스만 채운다). 데모 분석은 받은 값을 그대로 돌려준다.
   - 실제 분석이면 새 사본: 모든 탐지 항목의 evidence = '' · live.value = ''(다른 live 필드는 그대로), raw.result = null.
   - 워크플로우가 만든 글(주요 위험 사유 riskReasons 줄 · 권장 조치 recs 줄 · 탐지 항목 판단 근거 reason, 그리고 그 원문인
     raw.overall 의 text · nextText 와 raw.decision 의 판단 근거 · 검토 사유 · 정보 종류, 설정 60 의 등급별 항목 토큰 · 권장 조치)와 검토사항 글(서버가 만든 title · desc · next ·
     근거 label) · 문서 간 연결 글(서버가 만든 title · 서류별 fields · basis · missing · check)에 어떤 탐지 항목의 원문 값이
     그대로 들어 있으면 그 자리를 그 항목의 masked 로 바꾼다(검토사항 · 연결 글은 원래 고정 문구 · 이름 · 번호 · 마스킹 값으로만
     만들지만 한 겹 더 막는다 — 연결 글은 읽을 때(api/contract.ts toLiveLinks)도 이미 한 번 거친다).
     바꾸는 함수 rawValueMasker 는 raw-mask.ts 에 있다(여기서 다시 내보낸다). 대상 원문 값 = 원래 live.value 가 비지 않았고 2 코드 포인트 이상이며 그 항목의 masked 와 다른 것(같은 값이 여러 항목이면
     처음 항목의 masked — 설정 60 의 정해진 관계 칸에서 값이 정확히 '본인' 인 항목만 뺀다, raw-mask.ts). 정규식 · 엔진 검색 없이 KMP 로 맞추는 한 번의 훑기다 — 커서 뒤 가장 이른 일치, 같은 위치면 긴 값
     (바꾼 글을 다시 훑지 않는다 · 값 길이와 개수에 한도가 없고 시간은 글 길이 × 값 수에 선형 · 예외가 원문 값을 담지 않는다).
     masked 가 비면 같은 코드 포인트 수의 '*' 로 바꾼다.
   - 최종 흐름 워크플로우 글(연결 글 · 판정 키 · 판정 키가 있는 결과의 주요 위험 사유)은 api/contract.ts 의 한 길 safeText 를 지난다:
     자르지 않은 원래 글 전체에 원문 값 바꾸기 → 최종 규칙(짝 없는 서로게이트 → U+FFFD, 2,000 코드 포인트를 넘으면 통째로 버림).
     판정 키 · 주요 위험 사유는 상세용 raw.decision(원래 글)을 다시 쓰지 않고 raw.result(자르지 않은 응답 값)에서 새로 만든다.
   - 담당자가 쓴 글(메모 · 사유 · 완료 메모 · 검토사항 처리 내용 note) · 처리자 · 분석 이름 · 파일 이름 · 이력 줄은 바꾸지 않는다.
   - 원래 객체는 바꾸지 않는다(새 객체 · 새 배열).
   - 보고서 대상(isReportTarget) = 실제 분석 중 raw.detailReady && raw.reviewable(완료 + 공통 계약 결과 + 검토 기록을 읽음).
   ========================================================================== */

import { nowStr } from '@/lib/format';
import { readDecision, riskReasonLines, safeText } from './api/contract';
import { seoulNow } from './api/mapping';
import { rawValueMasker } from './raw-mask';
import type { Analysis } from './types';

export { rawValueMasker };

/** 실제 분석인지(raw 가 있음) */
export function isLiveAnalysis(a: Analysis): boolean {
  return a.raw !== undefined && a.raw !== null;
}

/** 실제 분석 중 보고서 · 내보내기를 만들 수 있는 분석인지 */
export function isReportTarget(a: Analysis): boolean {
  return !!a.raw && a.raw.detailReady === true && a.raw.reviewable === true;
}

/** 보고서 생성 시각 'YYYY-MM-DD HH:mm' — 실제 분석은 서울 시각, 데모는 지금처럼 브라우저 시각 */
export function reportClock(a: Analysis, date: Date = new Date()): string {
  return isLiveAnalysis(a) ? seoulNow(date) : nowStr(date);
}

/** 보고서 · 내보내기용 안전한 사본 — 데모 분석은 그대로, 실제 분석은 원문 값을 지운 새 사본 */
export function reportSafeAnalysis(a: Analysis): Analysis {
  if (!isLiveAnalysis(a) || !a.raw) return a;
  const mask = rawValueMasker(a.findings);
  const overall = a.raw.overall;
  // 판정 키 · 주요 위험 사유 — 자르지 않은 응답 값(raw.result)에서 연결 글과 같은 한 길(safeText: 가리기 → 최종 규칙)로 다시 만든다
  const decision = readDecision(a.raw.result, mask);
  const safeLine = (s: string): string => safeText(s, mask);
  return {
    ...a,
    docs: a.docs.slice(),
    findings: a.findings.map((f) => ({
      ...f,
      reason: mask(f.reason),
      evidence: '',
      ...(f.live ? { live: { ...f.live, value: '' } } : {}),
    })),
    items: a.items.map((i) => ({
      ...i,
      title: mask(i.title),
      desc: mask(i.desc),
      next: mask(i.next),
      evidence: i.evidence.map((ev) => ({ ...ev, label: mask(ev.label) })),
    })),
    links: a.links.map((l) => ({
      ...l,
      title: safeLine(l.title),
      docs: l.docs.map((d) => ({ ...d, fields: safeLine(d.fields) })),
      basis: l.basis.map(safeLine).filter((b) => b !== ''),
      missing: safeLine(l.missing),
      check: safeLine(l.check),
    })),
    history: a.history.slice(),
    // 판정 키가 있는 결과는 위의 decision 에서(원문 가림 · 최종 규칙), 옛 결과(overall 줄)는 지금처럼 가리기만
    riskReasons: decision ? riskReasonLines(decision, null) : a.riskReasons.map(mask),
    recs: a.recs.map(mask),
    raw: {
      ...a.raw,
      result: null,
      overall: overall ? { ...overall, text: mask(overall.text), nextText: mask(overall.nextText) } : null,
      decision,
    },
  };
}
