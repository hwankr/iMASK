/* 문서 간 연결 매핑(최종 흐름 워크플로우) — result.links(서버가 계산) → DocLink(toLiveLinks) · 검토사항 link_id → linkId ·
   위험도 판정 키(readDecision) · 묶음 검증(readBundleCheck) · 주요 위험 사유(riskReasonLines) · toAnalysis 갈래.
   바깥 값이 어떤 모양이어도 예외 없이 · 선형으로 읽는지(경계 강건성)를 본다. 옛 결과(done-result · items-result)는 연결 0개 · 판정 키 없음.
   고정 자료 fixtures/final-flow-result.json(손으로 만든 모양 — 지어낸 값). 원문 값은 테스트 출력에 옮기지 않는다. */
import { describe, expect, it } from 'vitest';
import type { DocLink, Finding } from '../types';
import {
  MAX_BUNDLE_CHECKS,
  MAX_DECISION_ITEMS,
  MAX_ID,
  MAX_LINK_BASIS,
  MAX_LINK_DOCS,
  MAX_LINK_FINDING_IDS,
  MAX_LINKS,
  MAX_TEXT,
  MAX_TEXT_SOURCE,
  finalText,
  identifier,
  markdownLines,
  readBundleCheck,
  readDecision,
  readDocSources,
  riskReasonLines,
  safeText,
  toLiveFindings,
  toLiveItems,
  toLiveLinks,
} from './contract';
import { toAnalysis } from './mapping';
import { analysisOut, contractResult, finalFlowResult, itemsResult } from './testing';

type Obj = Record<string, unknown>;

const NEW_REVIEW = { status: 'needed', memo: '', memo_at: null, reviewer: '', reviewed_at: null, completion_note: '', findings: {}, items: {}, history: [], version: 0 };
const done = (result: Obj, review: unknown = NEW_REVIEW) =>
  toAnalysis(analysisOut({ status: 'done', result, upstage_job_id: 'job_test', upstage_status: 'completed', review: structuredClone(review) }));

/** 고정 자료(final-flow-result)의 서류 · 탐지 항목 */
function base() {
  const r = finalFlowResult();
  const sources = readDocSources(r.documents);
  const findings = toLiveFindings(r.findings, sources, '');
  return { r, sources, findings, links: r.links as Obj[] };
}

/** 서류 0 · 2 를 잇는 올바른 연결 하나(필드를 바꿔 쓴다) */
function link(patch: Obj = {}): Obj {
  return {
    id: 'link:0:2',
    number: 'L-01',
    status: 'confirmed',
    state: 'linked',
    title: '제목',
    field: 'applicant_name',
    label: '신청인 성명',
    docs: [
      { document_index: 0, page: 1, fields: '왼쪽', finding_ids: ['0:applicant_name'] },
      { document_index: 2, page: 4, fields: '오른쪽', finding_ids: ['2:applicant_name'] },
    ],
    basis: ['근거'],
    missing: '',
    check: '할 일',
    ...patch,
  };
}

/** 받은 연결들을 고정 자료의 서류 · 탐지 항목으로 읽는다 */
function read(links: unknown): DocLink[] {
  const { sources, findings } = base();
  return toLiveLinks(links, sources, findings);
}

const byNumber = (findings: readonly Finding[], number: string) => {
  const f = findings.find((x) => x.id === number);
  if (!f) throw new Error('탐지 항목 없음: ' + number);
  return f;
};

/* ---------- 고정 자료 그대로 ---------- */

describe('고정 자료(final-flow-result) → 연결 3개', () => {
  const { r, sources, findings } = base();
  const links = toLiveLinks(r.links, sources, findings);

  it('화면 id = 표시 번호, 계약 id 는 live.id, 서버 순서 · 상태 · 글 그대로, 판단 값은 비어 있다', () => {
    expect(links.map((l) => [l.id, l.live?.id, l.status])).toEqual([
      ['L-01', 'link:0:1', 'check'],
      ['L-02', 'link:0:2', 'confirmed'],
      ['L-03', 'link:0:3', 'check'],
    ]);
    const raw = r.links as Obj[];
    links.forEach((l, i) => {
      expect(l.title).toBe(raw[i].title);
      expect(l.basis).toEqual(raw[i].basis);
      expect(l.missing).toBe(raw[i].missing);
      expect(l.check).toBe(raw[i].check);
      expect([l.decision, l.decisionNote, l.decidedAt, l.decidedBy]).toEqual([null, '', '', '']);
    });
  });

  it('서류 — 화면 서류 id · 서류 안 쪽 · fields 그대로 · anchors = finding_ids 의 위치 ID(위치 없는 쪽은 [])', () => {
    const anchorsOf = (n: string) => byNumber(findings, n).anchors;
    expect(links.map((l) => l.docs.map((d) => [d.docId, d.page]))).toEqual([
      [['doc-0', 1], ['doc-1', 1]],
      [['doc-0', 1], ['doc-2', 2]],
      [['doc-0', 1], ['doc-3', 1]],
    ]);
    expect(links[1].docs.map((d) => d.anchors)).toEqual([anchorsOf('D1-01'), anchorsOf('D3-01')]);
    expect(links[1].docs[1].anchors.length).toBe(1);
    expect(links[2].docs[1].anchors).toEqual([]);
    const raw = r.links as { docs: { fields: string }[] }[];
    links.forEach((l, i) => expect(l.docs.map((d) => d.fields)).toEqual(raw[i].docs.map((d) => d.fields)));
  });
});

/* ---------- 경계 ---------- */

describe('toLiveLinks — 경계(예외 없이 건너뛴다)', () => {
  it('배열이 아니면 []', () => {
    for (const v of [undefined, null, {}, 'links', 3, true, { 0: link() }]) expect(read(v)).toEqual([]);
  });

  it('객체가 아닌 연결 · 키가 틀린 연결은 버린다', () => {
    const bad: unknown[] = [
      null,
      'L-01',
      [link()],
      link({ id: '' }),
      link({ id: 3 }),
      link({ id: undefined }),
      link({ number: 'L-1' }),
      link({ number: 'R-01' }),
      link({ number: ' L-01' }),
      link({ number: 'L-０１' }),
      link({ number: 1 }),
      link({ status: 'linked' }),
      link({ status: 'CONFIRMED' }),
      link({ status: null }),
      link({ docs: [] }),
      link({ docs: 'doc-0' }),
      link({ docs: null }),
    ];
    expect(read(bad)).toEqual([]);
  });

  it('보이지 않는 서류 · 서류 객체가 아님 · 번호가 정수가 아님이 하나라도 있으면 그 연결을 버린다', () => {
    const doc0 = { document_index: 0, page: 1, fields: '', finding_ids: [] };
    for (const other of [
      { document_index: 9, page: 1 },
      { document_index: -1, page: 1 },
      { document_index: 1.5, page: 1 },
      { document_index: '1', page: 1 },
      { document_index: true, page: 1 },
      { page: 1 },
      null,
      'doc-1',
    ]) {
      expect(read([link({ docs: [doc0, other] })])).toEqual([]);
    }
    // 서류 하나만이어도 보이는 서류면 받는다
    expect(read([link({ docs: [doc0] })]).map((l) => l.docs.length)).toEqual([1]);
  });

  it('같은 id · 같은 번호는 처음 받아들인 것만(버린 연결은 자리를 차지하지 않는다)', () => {
    const out = read([
      link({ id: 'a', number: 'L-01', status: 'nope' }),
      link({ id: 'a', number: 'L-01' }),
      link({ id: 'a', number: 'L-02' }),
      link({ id: 'b', number: 'L-01' }),
      link({ id: 'c', number: 'L-03', status: 'check' }),
    ]);
    expect(out.map((l) => [l.id, l.live?.id, l.status])).toEqual([
      ['L-01', 'a', 'confirmed'],
      ['L-03', 'c', 'check'],
    ]);
  });

  it('글 · 쪽 — 문자열이 아니면 빈 글, basis 는 문자열만, 쪽이 범위 밖 · 정수 아님이면 1쪽', () => {
    const [l] = read([
      link({
        title: 5,
        basis: ['하나', 2, null, '둘', { x: 1 }],
        missing: null,
        check: ['x'],
        docs: [
          { document_index: 2, page: 99, fields: 7, finding_ids: [] },
          { document_index: 2, page: 3.5, fields: null },
          { document_index: 2, page: '4', fields: '셋' },
          { document_index: 2, page: 4, fields: '넷' },
        ],
      }),
    ]);
    expect([l.title, l.basis, l.missing, l.check]).toEqual(['', ['하나', '둘'], '', '']);
    expect(l.docs.map((d) => [d.docId, d.page, d.fields])).toEqual([
      ['doc-2', 1, ''],
      ['doc-2', 1, ''],
      ['doc-2', 1, '셋'],
      ['doc-2', 2, '넷'],
    ]);
    expect(read([link({ basis: 'x' })])[0].basis).toEqual([]);
  });

  it('finding_ids 이상 — 배열 아님 · 문자열 아님 · 없는 id · 다른 서류 · 다른 쪽은 건너뛰고, 겹치는 위치 ID 는 한 번', () => {
    const { findings } = base();
    const d1 = byNumber(findings, 'D1-01').anchors;
    const d2 = byNumber(findings, 'D1-02').anchors;
    const docs = (ids: unknown) => [{ document_index: 0, page: 1, fields: '', finding_ids: ids }];
    for (const v of [undefined, null, '0:applicant_name', { 0: '0:applicant_name' }, 3]) expect(read([link({ docs: docs(v) })])[0].docs[0].anchors).toEqual([]);
    const [l] = read([link({ docs: docs([1, null, '없는:id', '1:applicant_name', '2:applicant_name', '0:applicant_name', '0:applicant_phone', '0:applicant_name', '0:account_number']) })]);
    expect(l.docs[0].anchors).toEqual([...d1, ...d2]);
    // 다른 쪽(서류 안 2쪽)을 가리키는 연결 서류는 1쪽 탐지 항목의 위치를 담지 않는다
    expect(read([link({ docs: [{ document_index: 2, page: 3, fields: '', finding_ids: ['2:applicant_name'] }] })])[0].docs[0].anchors).toEqual([]);
  });

});

/* ---------- 한도 · 서로게이트(V-T4-1 M1) ---------- */

const cps = (s: string) => Array.from(s).length;
const numbered = (n: number, patch: Obj = {}) => Array.from({ length: n }, (_, i) => link({ id: 'link:' + i, number: 'L-' + String(i + 1).padStart(2, '0'), ...patch }));
const doc0 = (patch: Obj = {}) => ({ document_index: 0, page: 1, fields: '', finding_ids: [], ...patch });

describe('toLiveLinks — 한도(앞 N개만 · 넘는 연결은 버림)', () => {
  it(`연결은 앞 ${MAX_LINKS}개만 본다 — 한도 안은 모두 받고, 아주 많아도 시간이 한도에 묶인다`, () => {
    expect(read(numbered(MAX_LINKS)).length).toBe(MAX_LINKS);
    expect(read(numbered(MAX_LINKS + 1)).length).toBe(MAX_LINKS);
    const huge = numbered(50000);
    const t0 = performance.now();
    expect(read(huge).length).toBe(MAX_LINKS);
    expect(performance.now() - t0).toBeLessThan(500);
    // 앞 N개만 본다 — 앞이 모두 틀린 연결이면 뒤의 올바른 연결은 읽지 않는다
    expect(read([...Array(MAX_LINKS).fill(null), link()])).toEqual([]);
    expect(read([...Array(MAX_LINKS - 1).fill(null), link()]).length).toBe(1);
  });

  it(`연결 하나의 서류는 ${MAX_LINK_DOCS}개까지 — 넘으면 그 연결을 버린다`, () => {
    expect(read([link({ docs: Array.from({ length: MAX_LINK_DOCS }, () => doc0()) })])[0].docs.length).toBe(MAX_LINK_DOCS);
    expect(read([link({ docs: Array.from({ length: MAX_LINK_DOCS + 1 }, () => doc0()) })])).toEqual([]);
  });

  it(`서류 하나의 finding_ids 는 앞 ${MAX_LINK_FINDING_IDS}개만 본다`, () => {
    const { findings } = base();
    const d101 = byNumber(findings, 'D1-01').anchors;
    const ids = (at: number) => [...Array(at).fill('없는:id'), '0:applicant_name'];
    expect(read([link({ docs: [doc0({ finding_ids: ids(MAX_LINK_FINDING_IDS - 1) })] })])[0].docs[0].anchors).toEqual(d101);
    expect(read([link({ docs: [doc0({ finding_ids: ids(MAX_LINK_FINDING_IDS) })] })])[0].docs[0].anchors).toEqual([]);
  });

  it(`근거는 앞 ${MAX_LINK_BASIS}줄만 본다(그 안의 문자열만)`, () => {
    const lines = Array.from({ length: MAX_LINK_BASIS + 5 }, (_, i) => '줄 ' + i);
    expect(read([link({ basis: lines })])[0].basis).toEqual(lines.slice(0, MAX_LINK_BASIS));
    expect(read([link({ basis: [1, ...lines] })])[0].basis).toEqual(lines.slice(0, MAX_LINK_BASIS - 1));
  });
});

describe('finalText · safeText · identifier — 화면 글과 식별자(자르지 않는다)', () => {
  it(`최종 규칙 — ${MAX_TEXT} 코드 포인트까지 그대로, 넘으면 통째로 버림(''), 서로게이트 쌍은 한 글자`, () => {
    const at = 'a'.repeat(MAX_TEXT);
    expect(finalText(at)).toBe(at);
    expect(finalText('a'.repeat(MAX_TEXT + 1))).toBe('');
    const astral = '😀'.repeat(MAX_TEXT);
    expect(finalText(astral)).toBe(astral);
    expect(finalText('😀'.repeat(MAX_TEXT + 1))).toBe('');
    // '…' 로 자르는 길이 없다
    expect(finalText('b'.repeat(MAX_TEXT + 5)).includes('…')).toBe(false);
  });

  it('최종 규칙 — 짝 없는 서로게이트는 U+FFFD(길이 그대로), 짝이 맞는 쌍 · 빈 글은 그대로, 아주 긴 글은 넘는 순간 멈춘다', () => {
    expect(finalText('a\uD800b')).toBe('a�b');
    expect(finalText('\uDC00')).toBe('�');
    expect(finalText('x\uD83D')).toBe('x�');
    expect(finalText('\uDE00\uD83D')).toBe('��');
    expect(finalText('😀 정상')).toBe('😀 정상');
    expect(finalText('')).toBe('');
    const atLone = '\uD800' + 'y'.repeat(MAX_TEXT - 1);
    expect([cps(finalText(atLone)), finalText(atLone).startsWith('�')]).toEqual([MAX_TEXT, true]);
    expect(finalText('\uD800' + 'y'.repeat(MAX_TEXT))).toBe('');
    const huge = 'x'.repeat(1_000_000) + '\uD800';
    const t0 = performance.now();
    expect(finalText(huge)).toBe('');
    expect(performance.now() - t0).toBeLessThan(100);
  });

  it(`한 길(safeText) — 문자열 아님 · ${MAX_TEXT_SOURCE} 코드 단위를 넘는 원래 글은 가리기 전에 버림, 그 밖은 원래 글 전체를 가린 뒤 최종 규칙`, () => {
    for (const v of [null, undefined, 3, ['a'], { a: 1 }]) expect(safeText(v, (s) => s)).toBe('');
    let calls = 0;
    const counting = (s: string) => {
      calls++;
      return s;
    };
    expect(safeText('q'.repeat(MAX_TEXT_SOURCE + 1), counting)).toBe('');
    expect(calls).toBe(0);
    // 가린 결과로 길이를 본다 — 원래 글이 한도를 넘어도 가린 결과가 한도 안이면 보인다(그 반대는 버린다)
    const long = 'RAWVALUE'.repeat(300); // 2,400 코드 포인트
    expect(safeText(long, (s) => s.split('RAWVALUE').join('*'))).toBe('*'.repeat(300));
    expect(safeText('짧은 글', () => 'M'.repeat(MAX_TEXT + 1))).toBe('');
    expect(safeText('짧은 글', () => 'M\uD800')).toBe('M�');
    // 다듬기는 가린 뒤
    expect(safeText('  가  ', (s) => s.replace('가', '나'), true)).toBe('나');
  });

  it(`식별자 — 1~${MAX_ID} 코드 포인트 · 짝 없는 서로게이트 없음만(아니면 null — 바꾸지 않는다)`, () => {
    expect(identifier('i'.repeat(MAX_ID))).toBe('i'.repeat(MAX_ID));
    expect(identifier('i'.repeat(MAX_ID + 1))).toBeNull();
    expect(identifier('😀'.repeat(MAX_ID))).toBe('😀'.repeat(MAX_ID));
    expect(identifier('😀'.repeat(MAX_ID + 1))).toBeNull();
    for (const v of ['', 'a\uD800', '\uDC00b', '\uD800', 3, null, undefined, ['a']]) expect(identifier(v)).toBeNull();
  });

  it('연결 — 화면 글 다섯 자리는 한 길(넘으면 비움 · 넘는 근거 줄은 뺌), id · 번호는 식별자(넘거나 서로게이트면 그 연결을 버린다)', () => {
    const long = 'z'.repeat(MAX_TEXT + 10);
    const [l] = read([
      link({ title: long, basis: ['b\uD800', long, '근거'], missing: '\uDC00m', check: long, docs: [doc0({ fields: 'f\uD800' }), doc0({ fields: long })] }),
    ]);
    expect([l.title, l.check, l.docs[1].fields]).toEqual(['', '', '']);
    expect([l.basis, l.missing, l.docs[0].fields]).toEqual([['b�', '근거'], '�m', 'f�']);
    expect(read([link({ id: 'link\uD800' })])).toEqual([]);
    expect(read([link({ id: 'k'.repeat(MAX_ID + 1) })])).toEqual([]);
    expect(read([link({ id: 'k'.repeat(MAX_ID) })]).map((x) => x.live?.id.length)).toEqual([MAX_ID]);
    expect(read([link({ number: 'L-' + '1'.repeat(MAX_ID - 2) })]).length).toBe(1);
    expect(read([link({ number: 'L-' + '1'.repeat(MAX_ID - 1) })])).toEqual([]);
  });
});

describe('readDecision · readBundleCheck — 한도 · 서로게이트', () => {
  it(`판정 목록은 앞 ${MAX_DECISION_ITEMS}개만, 글은 한 길(넘으면 버림 — 목록 항목은 뺌), 서류 종류 코드는 식별자(아니면 그 항목만 버림)`, () => {
    const items = (n: number) => Array.from({ length: n }, (_, i) => 'c' + i);
    const d = readDecision({
      decision: {
        risk_level: '상\uD800',
        document_types: [...items(MAX_DECISION_ITEMS - 3), 'bad\uD800', 'x'.repeat(MAX_ID + 1), ' income_proof ', 'late'],
        sensitive_categories: items(MAX_DECISION_ITEMS + 1),
        review_reasons: ['r\uDC00', 'y'.repeat(MAX_TEXT + 1), ' 다듬음 '],
        reason: 'w'.repeat(1_000_000) + '\uD800',
      },
    })!;
    expect(d.riskLevel).toBe('상�');
    expect(d.documentTypes).toEqual([...items(MAX_DECISION_ITEMS - 3), 'income_proof']);
    expect(d.sensitiveCategories).toEqual(items(MAX_DECISION_ITEMS));
    expect(d.reviewReasons).toEqual(['r�', '다듬음']);
    expect(d.reason).toBeNull();
    expect(readDecision({ decision: { reason: 'v'.repeat(MAX_TEXT) } })?.reason?.length).toBe(MAX_TEXT);
    expect(readDecision({ decision: { reason: 'v'.repeat(MAX_TEXT + 1) } })?.reason).toBeNull();
    const t0 = performance.now();
    expect(readDecision({ decision: { document_types: Array(50000).fill('x'), review_reasons: Array(50000).fill('y') } })?.documentTypes?.length).toBe(MAX_DECISION_ITEMS);
    expect(performance.now() - t0).toBeLessThan(100);
  });

  it(`묶음 검증 규칙은 앞 ${MAX_BUNDLE_CHECKS}개만 센다`, () => {
    const fails = (n: number) => Array.from({ length: n }, () => ({ status: 'fail' }));
    expect(readBundleCheck({ bundle_check: { checks: fails(MAX_BUNDLE_CHECKS) } })?.failed).toBe(MAX_BUNDLE_CHECKS);
    expect(readBundleCheck({ bundle_check: { checks: fails(MAX_BUNDLE_CHECKS + 1) } })?.failed).toBe(MAX_BUNDLE_CHECKS);
    expect(readBundleCheck({ bundle_check: { checks: [...Array(MAX_BUNDLE_CHECKS).fill({ status: 'pass' }), { status: 'fail' }] } })?.failed).toBe(0);
    expect(readBundleCheck({ bundle_check: { checks: fails(50000) } })?.failed).toBe(MAX_BUNDLE_CHECKS);
  });
});

/* ---------- 같은 탐지 id 반복(V-T4-1 M2) ---------- */

describe('같은 탐지 id 반복 — 그 항목의 위치 목록은 한 번만 돈다', () => {
  /** 서류 0 · 1쪽 성명 항목에 서로 다른 위치 n개 */
  const wide = (n: number): Finding[] => {
    const { findings } = base();
    const one = findings.find((f) => f.live?.id === '0:applicant_name')!;
    return [{ ...one, anchors: Array.from({ length: n }, (_, i) => 'a' + i) }, ...findings.filter((f) => f !== one)];
  };
  const evidenceItem = (ids: unknown[]) => ({ id: 'x', number: 'R-01', type: 'lowconf', document_index: 0, page: 1, finding_id: null, title: '', desc: '', next: '', evidence: [{ label: 'l', page: 1, finding_ids: ids, finding_id: null }] });

  it('검토사항 근거 — 다른 위치 N개 + 같은 id N번: 위치 N개(차례 그대로) · 시간 선형', () => {
    const { sources } = base();
    const run = (n: number) => {
      const fs = wide(n);
      const t0 = performance.now();
      const out = toLiveItems([evidenceItem(Array(n).fill('0:applicant_name'))], sources, fs);
      const ms = performance.now() - t0;
      expect(out[0].evidence[0].anchors).toEqual(fs[0].anchors);
      return ms;
    };
    run(1000);
    // 고치기 전(N²)에는 12,000 에서 약 1.8초 — 선형이면 수 ms
    expect(run(20000)).toBeLessThan(300);
  });

  it('연결 서류 — 같은 id 반복 · 섞임: 위치는 처음 나온 순서로 한 번씩', () => {
    const { sources } = base();
    const fs = wide(5000);
    const d102 = fs.find((f) => f.live?.id === '0:applicant_phone')!.anchors;
    const ids = ['0:applicant_name', '0:applicant_phone', '0:applicant_name', '0:applicant_phone', ...Array(40).fill('0:applicant_name')];
    const t0 = performance.now();
    const [l] = toLiveLinks([link({ docs: [doc0({ finding_ids: ids })] })], sources, fs);
    expect(performance.now() - t0).toBeLessThan(200);
    expect(l.docs[0].anchors).toEqual([...fs[0].anchors, ...d102]);
  });
});

/* ---------- 연결 글 원문 값 바꾸기(V-T4-1 M3) ---------- */

describe('연결 글 — 원문 값은 masked 로(상세 연결 카드 · 보고서 · 내보내기 모두)', () => {
  it('다섯 글 자리(title · fields · basis · missing · check)에 원문 값을 넣어도 masked 로, id · 위치 · 탐지 항목 값은 그대로', () => {
    const { sources, findings } = base();
    const raws = [...new Set(findings.map((f) => f.live?.value ?? '').filter((v, i) => v && cps(v) >= 2 && v !== findings[i].masked))];
    expect(raws.length).toBeGreaterThanOrEqual(4);
    const masked = (v: string) => findings.find((f) => f.live?.value === v)!.masked;
    const before = JSON.stringify(findings);
    const [l] = toLiveLinks(
      [
        link({
          title: '제목 ' + raws[0],
          basis: [raws[1] + ' 같음', '근거'],
          missing: raws[2],
          check: '확인 ' + raws[3],
          docs: [doc0({ fields: '성명 ' + raws[0], finding_ids: ['0:applicant_name'] }), { document_index: 2, page: 4, fields: raws[1], finding_ids: ['2:applicant_name'] }],
        }),
      ],
      sources,
      findings,
    );
    const text = JSON.stringify([l.title, l.basis, l.missing, l.check, l.docs.map((d) => d.fields)]);
    expect(raws.filter((v) => text.includes(v)).length).toBe(0);
    expect(l.title === '제목 ' + masked(raws[0])).toBe(true);
    expect(l.basis[0] === masked(raws[1]) + ' 같음' && l.basis[1] === '근거').toBe(true);
    expect(l.missing === masked(raws[2]) && l.check === '확인 ' + masked(raws[3])).toBe(true);
    expect(l.docs[0].fields === '성명 ' + masked(raws[0]) && l.docs[1].fields === masked(raws[1])).toBe(true);
    // 위치 · id · 탐지 항목(원문 보기에 쓰는 value 포함)은 그대로
    expect(l.docs.map((d) => d.anchors)).toEqual([byNumber(findings, 'D1-01').anchors, byNumber(findings, 'D3-01').anchors]);
    expect([l.id, l.live?.id]).toEqual(['L-01', 'link:0:2']);
    expect(JSON.stringify(findings) === before).toBe(true);
  });

  it('toAnalysis — 정상 고정 자료의 연결 글은 바뀌지 않는다(마스킹 값만 담는 계약)', () => {
    const r = finalFlowResult();
    const a = done(r);
    const raw = r.links as { title: string; basis: string[]; missing: string; check: string; docs: { fields: string }[] }[];
    expect(a.links.map((l) => [l.title, l.basis, l.missing, l.check, l.docs.map((d) => d.fields)])).toEqual(raw.map((l) => [l.title, l.basis, l.missing, l.check, l.docs.map((d) => d.fields)]));
  });
});

/* ---------- 검토사항 link_id → linkId ---------- */

describe('검토사항 link_id → linkId(연결 보기)', () => {
  it('고정 자료 — mismatch · weaklink 는 그 연결의 화면 번호, 그 밖은 없음', () => {
    const { r, sources, findings } = base();
    const links = toLiveLinks(r.links, sources, findings);
    const items = toLiveItems(r.items, sources, findings, links);
    expect(items.map((i) => [i.id, i.type, i.linkId ?? null])).toEqual([
      ['R-01', 'missing', null],
      ['R-02', 'nolocation', null],
      ['R-03', 'lowconf', null],
      ['R-04', 'mismatch', 'L-01'],
      ['R-05', 'nolocation', null],
      ['R-06', 'lowconf', null],
      ['R-07', 'weaklink', 'L-03'],
      ['R-08', 'other', null],
    ]);
  });

  it('link_id 가 문자열이 아니거나 · 없는 연결 · 버린 연결이면 linkId 없음, 연결 목록을 주지 않으면 없음', () => {
    const { r, sources, findings } = base();
    const items = r.items as Obj[];
    const links = toLiveLinks(r.links, sources, findings);
    for (const v of [null, undefined, 3, ['link:0:1'], { id: 'link:0:1' }, 'link:9:9', 'L-01', '']) {
      const one = [{ ...items[3], link_id: v }];
      expect(toLiveItems(one, sources, findings, links)[0].linkId).toBeUndefined();
    }
    expect(toLiveItems(r.items, sources, findings).every((i) => i.linkId === undefined)).toBe(true);
    // 버린 연결(키가 틀림)을 가리키면 없음
    const broken = structuredClone(r.links as Obj[]);
    broken[0].status = 'linked';
    const kept = toLiveLinks(broken, sources, findings);
    expect(toLiveItems(r.items, sources, findings, kept).find((i) => i.id === 'R-04')?.linkId).toBeUndefined();
  });

  it('옛 결과(link_id 키 없음 · items-result 의 link_id null)도 그대로 읽힌다', () => {
    const a = done(itemsResult());
    expect(a.items.length).toBe(8);
    expect(a.items.every((i) => i.linkId === undefined)).toBe(true);
    const noKey = itemsResult();
    for (const it of noKey.items as Obj[]) delete it.link_id;
    expect(done(noKey).items).toEqual(a.items);
  });
});

/* ---------- 판정 키 · 묶음 검증 · 주요 위험 사유 ---------- */

describe('readDecision · readBundleCheck · riskReasonLines', () => {
  it('판정 키 — 객체가 아니면 null, 값은 문자열 · 문자열 목록만(못 읽은 값 null, 빈 목록은 [])', () => {
    for (const v of [undefined, null, [], 'x', 3]) expect(readDecision({ decision: v })).toBeNull();
    expect(readDecision(null)).toBeNull();
    expect(readDecision(['decision'])).toBeNull();
    expect(readDecision({ decision: {} })).toEqual({ riskLevel: null, documentTypes: null, sensitiveCategories: null, reviewReasons: null, reason: null });
    expect(
      readDecision({ decision: { risk_level: ' 상 ', document_types: ['loan_application', 3, '', ' x '], sensitive_categories: [], review_reasons: 'a, b', reason: '  ' } }),
    ).toEqual({ riskLevel: '상', documentTypes: ['loan_application', 'x'], sensitiveCategories: [], reviewReasons: null, reason: null });
    expect(readDecision(finalFlowResult())?.documentTypes?.length).toBe(5);
  });

  it('묶음 검증 — 객체가 아니면 null, 모르는 판정은 "", 실패 규칙 = status fail 인 객체 수', () => {
    for (const v of [undefined, null, [], 'red']) expect(readBundleCheck({ bundle_check: v })).toBeNull();
    expect(readBundleCheck({ bundle_check: {} })).toEqual({ verdict: '', failed: 0 });
    expect(readBundleCheck({ bundle_check: { verdict: 'RED', checks: 'x' } })).toEqual({ verdict: '', failed: 0 });
    expect(readBundleCheck({ bundle_check: { verdict: 'yellow', checks: [{ status: 'fail' }, { status: 'FAIL' }, 'fail', null, { status: 'fail' }, { status: 'absent' }] } })).toEqual({
      verdict: 'yellow',
      failed: 2,
    });
    expect(readBundleCheck(finalFlowResult())).toEqual({ verdict: 'red', failed: 1 });
  });

  it('주요 위험 사유 — 판정 키가 있으면 읽을 수 있는 판단 근거 + 검토 사유만(비면 빈 목록), 판정 키가 없을 때만 overall 줄', () => {
    const overall = { level: '상', text: '## 판정\n- 하나\n- 둘', nextStage: '', nextText: '' };
    const d = { riskLevel: '상', documentTypes: null, sensitiveCategories: null, reviewReasons: ['사유 1', '사유 2'], reason: '근거' };
    expect(riskReasonLines(d, overall)).toEqual(['근거', '사유 1', '사유 2']);
    expect(riskReasonLines({ ...d, reviewReasons: null }, overall)).toEqual(['근거']);
    expect(riskReasonLines({ ...d, reason: null }, overall)).toEqual(['사유 1', '사유 2']);
    // 판정 키는 있는데 사유를 못 읽음 — overall 본문으로 돌아가지 않는다(보고서는 '-')
    expect(riskReasonLines({ ...d, reason: null, reviewReasons: [] }, overall)).toEqual([]);
    expect(riskReasonLines({ ...d, reason: null, reviewReasons: null }, overall)).toEqual([]);
    expect(riskReasonLines(null, overall)).toEqual(['하나', '둘']);
    expect(riskReasonLines(null, null)).toEqual([]);
  });

  it('toAnalysis — 판정 키 객체에 사유가 없으면 주요 위험 사유는 빈 목록', () => {
    const r = finalFlowResult();
    r.decision = { risk_level: '상', document_types: [], sensitive_categories: [], review_reasons: [], reason: null };
    expect(done(r).riskReasons).toEqual([]);
    r.decision = {};
    expect(done(r).riskReasons).toEqual([]);
  });
});

/* ---------- toAnalysis ---------- */

describe('toAnalysis — 최종 흐름 결과 · 옛 결과', () => {
  it('최종 흐름 — 연결 3개 · 검토사항 linkId · raw.decision · raw.bundleCheck · 주요 위험 사유 = 판단 근거 + 검토 사유', () => {
    const a = done(finalFlowResult());
    expect(a.links.map((l) => [l.id, l.status, l.live?.id])).toEqual([
      ['L-01', 'check', 'link:0:1'],
      ['L-02', 'confirmed', 'link:0:2'],
      ['L-03', 'check', 'link:0:3'],
    ]);
    expect(a.items.filter((i) => i.linkId).map((i) => [i.id, i.linkId])).toEqual([
      ['R-04', 'L-01'],
      ['R-07', 'L-03'],
    ]);
    const d = (finalFlowResult().decision as Obj) ?? {};
    expect(a.raw?.decision?.reason).toBe(d.reason);
    expect(a.raw?.bundleCheck).toEqual({ verdict: 'red', failed: 1 });
    expect(a.riskReasons).toEqual([d.reason, ...(d.review_reasons as string[])]);
    expect(a.docs.map((x) => x.title)).toEqual(['자동이체 신청서', 'FATCA/CRS 본인확인서', '소득 증빙', '위임장', '기타']);
  });

  it('완료가 아니거나 공통 계약 결과가 아니면 연결 없음', () => {
    expect(toAnalysis(analysisOut({ status: 'running', result: finalFlowResult() })).links).toEqual([]);
    const noDocs = finalFlowResult();
    noDocs.documents = [];
    expect(done(noDocs).links).toEqual([]);
  });

  it('옛 결과(done-result · items-result) — 연결 0개 · 판정 키 · 묶음 검증 null · 주요 위험 사유는 overall 줄', () => {
    for (const r of [contractResult(), itemsResult()]) {
      const a = done(r);
      expect(a.links).toEqual([]);
      expect(a.raw?.decision).toBeNull();
      expect(a.raw?.bundleCheck).toBeNull();
      expect(a.riskReasons.length).toBeGreaterThan(0);
      expect(a.riskReasons).toEqual(markdownLines((r.overall as Obj).text));
    }
  });
});
