/* ==========================================================================
   보고서용 안전한 사본 — 순수 함수. 실제 분석의 보고서 화면과 실제 서비스의 내보내기 파일은 원래 분석이 아니라
   이 사본으로만 만든다(원문 값이 보고서 DOM · 내려받은 파일에 들어가지 않게).
   - 실제 분석인지는 Analysis.raw 가 있는지로 가른다(실제 분석 서비스만 채운다). 데모 분석은 받은 값을 그대로 돌려준다.
   - 실제 분석이면 새 사본: 모든 탐지 항목의 evidence = '' · live.value = ''(다른 live 필드는 그대로), raw.result = null.
   - 워크플로우가 만든 글(주요 위험 사유 riskReasons 줄 · 권장 조치 recs 줄 · 탐지 항목 판단 근거 reason, 그리고 그 원문인
     raw.overall 의 text · nextText)와 검토사항 글(서버가 만든 title · desc · next · 근거 label)에 어떤 탐지 항목의 원문 값이
     그대로 들어 있으면 그 자리를 그 항목의 masked 로 바꾼다(검토사항 글은 원래 고정 문구 · 이름 · 번호로만 만들지만 한 겹 더 막는다).
     대상 원문 값 = 원래 live.value 가 비지 않았고 2 코드 포인트 이상이며 그 항목의 masked 와 다른 것(같은 값이 여러 항목이면
     처음 항목의 masked). 정규식 · 엔진 검색 없이 KMP 로 맞추는 한 번의 훑기다 — 커서 뒤 가장 이른 일치, 같은 위치면 긴 값
     (바꾼 글을 다시 훑지 않는다 · 값 길이와 개수에 한도가 없고 시간은 글 길이 × 값 수에 선형 · 예외가 원문 값을 담지 않는다).
     masked 가 비면 같은 코드 포인트 수의 '*' 로 바꾼다.
   - 담당자가 쓴 글(메모 · 사유 · 완료 메모 · 검토사항 처리 내용 note) · 처리자 · 분석 이름 · 파일 이름 · 이력 줄은 바꾸지 않는다.
   - 원래 객체는 바꾸지 않는다(새 객체 · 새 배열).
   - 보고서 대상(isReportTarget) = 실제 분석 중 raw.detailReady && raw.reviewable(완료 + 공통 계약 결과 + 검토 기록을 읽음).
   ========================================================================== */

import { nowStr } from '@/lib/format';
import { seoulNow } from './api/mapping';
import type { Analysis, Finding } from './types';

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

const isHigh = (c: number): boolean => c >= 0xd800 && c <= 0xdbff;
const isLow = (c: number): boolean => c >= 0xdc00 && c <= 0xdfff;

/** 코드 포인트 수(짝이 맞는 서로게이트 쌍 = 1, 짝 없는 서로게이트 = 1) */
function cpLen(s: string): number {
  let n = 0;
  for (let i = 0; i < s.length; i++) {
    if (isHigh(s.charCodeAt(i)) && i + 1 < s.length && isLow(s.charCodeAt(i + 1))) i++;
    n++;
  }
  return n;
}

/** 글 → UTF-16 코드 단위 배열 */
function codeUnits(s: string): Uint16Array {
  const u = new Uint16Array(s.length);
  for (let i = 0; i < s.length; i++) u[i] = s.charCodeAt(i);
  return u;
}

/** KMP 실패 표 — fail[i] = p[0..i] 의 진접두이자 접미인 것 중 가장 긴 길이 */
function failureTable(p: Uint16Array): Int32Array {
  const fail = new Int32Array(p.length);
  let k = 0;
  for (let i = 1; i < p.length; i++) {
    while (k > 0 && p[i] !== p[k]) k = fail[k - 1];
    if (p[i] === p[k]) k++;
    fail[i] = k;
  }
  return fail;
}

/** 일치 [start, end) 가 서로게이트 쌍을 가르는지 — 코드 포인트 경계에서만 맞춘다(u 플래그 정규식과 같은 뜻) */
function splitsPair(t: Uint16Array, start: number, end: number): boolean {
  return (start > 0 && isLow(t[start]) && isHigh(t[start - 1])) || (end < t.length && isLow(t[end]) && isHigh(t[end - 1]));
}

/** 바꿀 원문 값 하나 */
interface MaskTarget {
  /** 원문 값의 코드 단위 */
  units: Uint16Array;
  /** KMP 실패 표(masker 를 만들 때 한 번) */
  fail: Int32Array;
  /** 바꿀 글(masked, 비면 같은 코드 포인트 수의 '*') */
  replacement: string;
}

/**
 * 탐지 항목들의 원문 값 → masked 로 바꾸는 함수. 대상 값이 없으면 받은 글을 그대로 돌려준다.
 * 대상 = live.value 가 비지 않았고 2 코드 포인트 이상이며 그 항목의 masked 와 다른 값(같은 값이 여러 항목이면 처음 항목의 masked).
 * 정규식 · 엔진 검색(indexOf 등) 없이 KMP 로 맞춘다 — 값 길이 · 개수에 한도가 없고, 시간은 선형이며, 예외가 원문을 담지 않는다.
 *  1) 값마다 KMP 로 글 전체를 한 번 훑어 모든 일치 시작 위치(겹침 포함)를 찾고, 서로게이트 쌍을 가르는 일치는 버린다.
 *  2) 시작 위치마다 가장 긴(코드 단위) 값을 적는다 — 같은 위치에서 둘 다 유효하면 짧은 쪽이 긴 쪽의 접두이고 쌍을 가르지 않으므로
 *     코드 단위로 길면 코드 포인트로도 길다. 같은 위치 같은 길이는 같은 값이라 중복 제거로 생기지 않는다.
 *  3) 왼쪽부터 한 번: 커서 이상인 첫 위치에 적힌 값이 있으면 그 앞 글 + 바꿀 글을 출력에 붙이고 커서를 그 일치 끝으로 —
 *     가장 이른 일치 · 같은 위치 긴 값 · 한 번의 훑기(출력은 다시 훑지 않는다).
 * 시간: 실패 표 O(값 길이 합) 한 번, 글마다 O(글 길이 × 값 수). 같은 글은 결과를 다시 쓴다(판단 근거는 항목마다 같은 글이 많다).
 */
export function rawValueMasker(findings: readonly Finding[]): (text: string) => string {
  const targets: MaskTarget[] = [];
  const seen = new Set<string>();
  for (const f of findings) {
    const value = typeof f.live?.value === 'string' ? f.live.value : '';
    if (!value || seen.has(value) || value === f.masked) continue;
    const cp = cpLen(value);
    if (cp < 2) continue;
    seen.add(value);
    const units = codeUnits(value);
    targets.push({ units, fail: failureTable(units), replacement: f.masked || '*'.repeat(cp) });
  }
  if (targets.length === 0) return (text) => text;
  const done = new Map<string, string>();

  const maskText = (text: string): string => {
    const t = codeUnits(text);
    const n = t.length;
    /* 시작 위치마다 가장 긴 값의 번호 + 1(0 = 없음) — 일치가 하나도 없으면 만들지 않는다 */
    let best: Int32Array | null = null;
    for (let k = 0; k < targets.length; k++) {
      const { units: p, fail } = targets[k];
      const m = p.length;
      if (m > n) continue;
      let j = 0;
      for (let i = 0; i < n; i++) {
        const c = t[i];
        while (j > 0 && c !== p[j]) j = fail[j - 1];
        if (c === p[j]) j++;
        if (j === m) {
          const start = i - m + 1;
          if (!splitsPair(t, start, i + 1)) {
            if (best === null) best = new Int32Array(n);
            const had = best[start];
            if (had === 0 || targets[had - 1].units.length < m) best[start] = k + 1;
          }
          j = fail[j - 1];
        }
      }
    }
    if (best === null) return text;
    const out: string[] = [];
    let cursor = 0;
    for (let pos = 0; pos < n; pos++) {
      const hit = best[pos];
      if (hit === 0) continue;
      const target = targets[hit - 1];
      out.push(text.slice(cursor, pos), target.replacement);
      cursor = pos + target.units.length;
      pos = cursor - 1;
    }
    out.push(text.slice(cursor));
    return out.join('');
  };

  return (text) => {
    if (typeof text !== 'string' || !text) return text;
    const cached = done.get(text);
    if (cached !== undefined) return cached;
    const masked = maskText(text);
    done.set(text, masked);
    return masked;
  };
}

/** 보고서 · 내보내기용 안전한 사본 — 데모 분석은 그대로, 실제 분석은 원문 값을 지운 새 사본 */
export function reportSafeAnalysis(a: Analysis): Analysis {
  if (!isLiveAnalysis(a) || !a.raw) return a;
  const mask = rawValueMasker(a.findings);
  const overall = a.raw.overall;
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
    links: a.links.slice(),
    history: a.history.slice(),
    riskReasons: a.riskReasons.map(mask),
    recs: a.recs.map(mask),
    raw: {
      ...a.raw,
      result: null,
      overall: overall ? { ...overall, text: mask(overall.text), nextText: mask(overall.nextText) } : null,
    },
  };
}
