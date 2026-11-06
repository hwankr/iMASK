/* ==========================================================================
   원문 값 바꾸기(rawValueMasker) — 순수 함수. 탐지 항목의 원문 값(live.value)이 글에 그대로 들어 있으면 그 자리를
   그 항목의 masked 로 바꾼다. 보고서용 안전한 사본(report-safe.ts)과 실제 분석 연결 글 읽기(api/contract.ts toLiveLinks)가 같이 쓴다.
   - 대상 원문 값 = live.value 가 비지 않았고 2 코드 포인트 이상이며 그 항목의 masked 와 다른 것(같은 값이 여러 항목이면 처음 항목의 masked).
     예외는 값 하나다: 설정 60 의 정해진 관계 칸(risk_source workflow · 칸 키 RELATION_KEYS — 표 칸 포함)의 값이 **정확히 '본인'** 일 때만 대상에서 뺀다.
     '본인' 은 사람을 가리키지 않고, 그대로 두면 고정 글 '본인 성명' 과 토큰 '…본인_성명' 이 망가진다. 관계 칸이어도 그 밖의 값은 모두 대상이다
     (형식 제한이 없는 칸이라 사람 이름이 올 수 있고, live.value 를 지워도 판단 근거 · 권장 조치에 복사된 값은 지워지지 않는다).
     같은 '본인' 이 다른 칸에 있으면 그 항목 때문에 대상이 된다. 옛 결과(risk_source null)는 그대로다.
   - 정규식 · 엔진 검색 없이 KMP 로 맞추는 한 번의 훑기다 — 커서 뒤 가장 이른 일치, 같은 위치면 긴 값(바꾼 글을 다시 훑지 않는다 ·
     값 길이와 개수에 한도가 없고 시간은 글 길이 × 값 수에 선형 · 예외가 원문 값을 담지 않는다). masked 가 비면 같은 코드 포인트 수의 '*'.
   - 타입만 import 한다(서비스 · 매핑을 import 하지 않는다 — 순환 import 없음).
   ========================================================================== */

import type { Finding } from './types';

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

/** 대상에서 빼는 값 하나 — 관계 칸의 이 값은 사람을 가리키지 않고 고정 글 '본인 성명' 과 겹친다 */
const SELF_VALUE = '본인';

/** 설정 60 의 관계 칸 키 — imask_backend/fields.py 의 관계 칸 전부(tests/test_v2_fixture_sync.py 가 같은지 지킨다) */
const RELATION_KEYS: ReadonlySet<string> = new Set(['중_관계', '중_대리인_관계', '중_법정대리인_관계', '중_가족관계']);

/** 칸 이름의 전체 꼴 — '<표>[<행>].'(표 칸만) + 칸 키 + '#<번호>'(같은 이름 구별 표시). 처음부터 끝까지 맞추므로 접미어 · 부분 일치가 없다 */
const FIELD_SHAPE = /^(?:[^[\]]+\[\d+\]\.)?([^[\]#]+)(?:#\d+)?$/;

/** 대상에서 뺄 항목인지 — 설정 60(risk_source workflow)의 정해진 관계 칸이고 값이 정확히 '본인'. 그 밖은 늘 거짓(옛 결과 포함) */
function isSelfRelation(f: Finding): boolean {
  if (f.live?.value !== SELF_VALUE || f.live.riskSource !== 'workflow') return false;
  const key = FIELD_SHAPE.exec(f.live.field)?.[1];
  return key !== undefined && RELATION_KEYS.has(key);
}

/**
 * 탐지 항목들의 원문 값 → masked 로 바꾸는 함수. 대상 값이 없으면 받은 글을 그대로 돌려준다.
 * 대상 = live.value 가 비지 않았고 2 코드 포인트 이상이며 그 항목의 masked 와 다른 값(같은 값이 여러 항목이면 처음 항목의 masked) —
 * 설정 60 의 정해진 관계 칸에서 값이 정확히 '본인' 인 항목만 뺀다(isSelfRelation).
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
    if (!value || seen.has(value) || value === f.masked || isSelfRelation(f)) continue;
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
