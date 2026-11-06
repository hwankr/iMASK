/* 실제 분석 검토사항 매핑 — result.items(서버가 계산) → ReviewItem(toLiveItems) · 해결 기록 덧씌우기(overlayItemReviews) ·
   toAnalysis 의 detailReady · reviewable 갈래. 바깥 값이 어떤 모양이어도 예외 없이 · 선형으로 읽는지(경계 강건성)를 본다.
   고정 자료 fixtures/items-result.json(합성) — 원문 값은 테스트 출력에 옮기지 않는다. */
import { describe, expect, it } from 'vitest';
import { RTYPE } from '@/display/rules';
import type { Finding, ReviewItem } from '../types';
import { overlayItemReviews, readDocSources, toLiveFindings, toLiveItems } from './contract';
import { seoulDateTime, toAnalysis, toListAnalysis } from './mapping';
import { analysisOut, contractResult, itemsResult, listItemOut } from './testing';

type Obj = Record<string, unknown>;

const NEW_REVIEW = { status: 'needed', memo: '', memo_at: null, reviewer: '', reviewed_at: null, completion_note: '', findings: {}, items: {}, history: [], version: 0 };

/** 고정 자료(items-result)의 서류 · 탐지 항목 */
function base() {
  const r = itemsResult();
  const sources = readDocSources(r.documents);
  const findings = toLiveFindings(r.findings, sources, '');
  return { r, sources, findings, items: r.items as Obj[] };
}

/** 서류 0 의 올바른 검토사항 하나(필드를 바꿔 쓴다) */
function item(patch: Obj = {}): Obj {
  return {
    id: 'lowconf:0',
    number: 'R-01',
    type: 'lowconf',
    document_index: 0,
    page: 1,
    finding_id: null,
    title: '제목',
    desc: '설명',
    next: '할 일',
    evidence: [],
    ...patch,
  };
}

/** 받은 항목들을 고정 자료의 서류 · 탐지 항목으로 읽는다 */
function read(items: unknown): ReviewItem[] {
  const { sources, findings } = base();
  return toLiveItems(items, sources, findings);
}

const fid = (findings: readonly Finding[], number: string) => {
  const f = findings.find((x) => x.id === number);
  if (!f) throw new Error('탐지 항목 없음: ' + number);
  return f;
};

/* ---------- 고정 자료 그대로 ---------- */

describe('고정 자료(items-result) → 검토사항 8개', () => {
  const { r, findings } = base();
  const items = toLiveItems(r.items, readDocSources(r.documents), findings);

  it('화면 id = 표시 번호, 계약 id 는 live.id, 서버 순서 · 종류 · 서류 · 서류 안 쪽', () => {
    expect(items.map((i) => [i.id, i.live?.id, i.type, i.docId, i.page])).toEqual([
      ['R-01', 'lowconf:0', 'lowconf', 'doc-0', 1],
      ['R-02', 'missing:1:applicant_name_detected', 'missing', 'doc-1', 1],
      ['R-03', 'nolocation:2:income_info', 'nolocation', 'doc-2', 1],
      ['R-04', 'lowconf:2', 'lowconf', 'doc-2', 1],
      ['R-05', 'lowconf:3', 'lowconf', 'doc-3', 1],
      ['R-06', 'nolocation:4:credit_negative_info', 'nolocation', 'doc-4', 1],
      ['R-07', 'lowconf:4', 'lowconf', 'doc-4', 1],
      ['R-08', 'other:5', 'other', 'doc-5', 1],
    ]);
  });

  it('글은 서버 글 그대로, 해결 기본값(미해결 · 빈 글), 데모 필드(linkId · retryDoc) 없음', () => {
    const raw = r.items as Obj[];
    items.forEach((it, i) => {
      expect(it.title).toBe(raw[i].title);
      expect(it.desc).toBe(raw[i].desc);
      expect(it.next).toBe(raw[i].next);
      expect([it.resolved, it.note, it.resolvedAt, it.resolvedBy]).toEqual([false, '', '', '']);
      expect(it.linkId).toBeUndefined();
      expect(it.retryDoc).toBeUndefined();
    });
  });

  it('항목 단위 finding_id → 그 탐지 항목의 화면 번호(nolocation 만)', () => {
    expect(items.map((i) => i.findingId ?? null)).toEqual([null, null, 'D3-02', null, null, 'D5-03', null, null]);
  });

  it('근거 — 이름 · 서류 · 서류 안 쪽 · 위치 id(finding_ids 의 탐지 항목 상자) · findingId', () => {
    const ev = (n: string) => items.find((i) => i.id === n)?.evidence ?? [];
    const anchorsOf = (...numbers: string[]) => numbers.flatMap((n) => fid(findings, n).anchors);
    expect(ev('R-01')).toEqual([{ label: '1쪽 값 보기', docId: 'doc-0', page: 1, anchors: anchorsOf('D1-06', 'D1-08', 'D1-09') }]);
    expect(ev('R-01')[0].anchors).toEqual(['D1-06#1', 'D1-08#1', 'D1-09#1']);
    expect(ev('R-02')).toEqual([{ label: '1쪽 열기', docId: 'doc-1', page: 1, anchors: [] }]);
    // 위치 없는 항목 — 위치 id 는 없고 findingId 로 그 탐지 항목을 고른다
    expect(ev('R-03')).toEqual([{ label: '1쪽 열기', docId: 'doc-2', page: 1, anchors: [], findingId: 'D3-02' }]);
    expect(ev('R-04')).toEqual([]);
    expect(ev('R-05')[0].anchors).toEqual(anchorsOf('D4-03'));
    expect(ev('R-05')[0].anchors).toHaveLength(5);
    expect(ev('R-06')).toEqual([{ label: '1쪽 열기', docId: 'doc-4', page: 1, anchors: [], findingId: 'D5-03' }]);
    expect(ev('R-07')[0].anchors).toEqual(['D5-02#1', 'D5-02#2']);
    expect(ev('R-08')).toEqual([{ label: '1쪽 열기', docId: 'doc-5', page: 1, anchors: [] }]);
  });
});

/* ---------- result.items · 항목 모양 ---------- */

describe('result.items 와 항목 모양 — 틀리면 예외 없이 건너뛴다', () => {
  it('items 가 배열이 아니면(없음 · null · 객체 · 문자열 · 숫자 · true) []', () => {
    for (const bad of [undefined, null, {}, { 0: item() }, 'R-01', 1, true]) expect(read(bad)).toEqual([]);
  });

  it('항목이 객체가 아니면(null · 숫자 · 배열 · 문자열 · true) 그 항목만 건너뛴다', () => {
    const out = read([null, 7, [item()], 'R-01', true, item({ id: 'ok', number: 'R-09' })]);
    expect(out.map((i) => i.id)).toEqual(['R-09']);
  });

  it('id — 빈 문자열 · 숫자 · null · 없음은 버리고, 공백 id 는 그대로(비지 않은 문자열)', () => {
    const noId = item();
    delete noId.id;
    const out = read([item({ id: '' }), item({ id: 5, number: 'R-02' }), item({ id: null, number: 'R-03' }), { ...noId, number: 'R-04' }, item({ id: ' ', number: 'R-05' })]);
    expect(out.map((i) => [i.id, i.live?.id])).toEqual([['R-05', ' ']]);
  });

  it('number 형식 — R-1 · R-0a · r-01 · " R-01" · "R-01 " · "R-01\\n" · R- · 빈 글 · 숫자 · 전각 · 아랍 숫자는 버림, R-100 은 받음', () => {
    const bad = ['R-1', 'R-0a', 'r-01', ' R-01', 'R-01 ', 'R-01\n', 'R-', '', 'R_01', 'Ｒ-01', 'R-０１', 'R-١٢', 1, null];
    const out = read([...bad.map((n, i) => item({ id: 'b' + i, number: n })), item({ id: 'ok100', number: 'R-100' }), item({ id: 'ok01', number: 'R-01' })]);
    expect(out.map((i) => i.id)).toEqual(['R-100', 'R-01']);
  });

  it('같은 number 두 번 · 같은 id 두 번 → 처음 받아들인 것만(틀린 앞 항목은 자리를 차지하지 않는다)', () => {
    const out = read([
      item({ id: 'a', number: 'R-01', title: '처음' }),
      item({ id: 'b', number: 'R-01', title: '번호 겹침' }),
      item({ id: 'a', number: 'R-02', title: 'id 겹침' }),
      item({ id: 'c', number: 'R-03', type: 'nope' }), // 버림 — c · R-03 을 차지하지 않는다
      item({ id: 'c', number: 'R-03', title: '뒤의 올바른 c' }),
    ]);
    expect(out.map((i) => [i.id, i.live?.id, i.title])).toEqual([
      ['R-01', 'a', '처음'],
      ['R-03', 'c', '뒤의 올바른 c'],
    ]);
  });

  it('type — RTYPE 밖 · 자기 키가 아닌 이름(__proto__ · constructor · toString · hasOwnProperty) · 빈 글 · 숫자는 버림', () => {
    const bad = ['unknown', '__proto__', 'constructor', 'toString', 'hasOwnProperty', 'valueOf', '', 'LOWCONF', 5, null];
    const out = read(bad.map((t, i) => item({ id: 't' + i, number: `R-${10 + i}`, type: t })));
    expect(out).toEqual([]);
  });

  it('type — RTYPE 11개 키는 모두 받는다', () => {
    const keys = Object.keys(RTYPE);
    expect(keys).toEqual(['unreadable', 'cutoff', 'mismatch', 'weaklink', 'nolocation', 'failed', 'format', 'duplicate', 'missing', 'lowconf', 'other']);
    const out = read(keys.map((t, i) => item({ id: 't' + i, number: `R-${10 + i}`, type: t })));
    expect(out.map((i) => i.type)).toEqual(keys);
  });

  it('document_index — 문자열 · 실수 · 음수 · 보이지 않는 서류 · 큰 정수 · true · null · 없음은 버림', () => {
    const noIndex = item({ id: 'x8', number: 'R-18' });
    delete noIndex.document_index;
    const bad = ['0', 0.5, -1, 99, 2 ** 53, Number.MAX_SAFE_INTEGER, true, null, NaN, Infinity];
    const out = read([...bad.map((d, i) => item({ id: 'x' + i, number: `R-${30 + i}`, document_index: d })), noIndex]);
    expect(out).toEqual([]);
  });

  it('document_index — 보이지 않는 서류(쪽 범위가 틀린 행)의 항목은 버리고, 큰 정수 index 서류는 받는다', () => {
    const r = itemsResult();
    const docs = r.documents as Obj[];
    docs[1].page_start = 0; // 보이지 않는 서류
    docs.push({ ...docs[0], index: 2 ** 40, page_start: 7, page_end: 7 });
    const sources = readDocSources(r.documents);
    const out = toLiveItems([item({ id: 'a', number: 'R-01', document_index: 1, page: 2 }), item({ id: 'b', number: 'R-02', document_index: 2 ** 40, page: 7 })], sources, []);
    expect(out.map((i) => [i.id, i.docId, i.page])).toEqual([['R-02', `doc-${2 ** 40}`, 1]]);
  });

  it('page — 범위 밖 · 실수 · 문자열 · null · true 는 1쪽, 범위 안은 서류 안 쪽(여러 쪽 서류)', () => {
    const r = itemsResult();
    (r.documents as Obj[])[3].page_end = 5; // 서류 3 = 파일 4~5쪽
    const sources = readDocSources(r.documents);
    const pages = [0, 3, 6, 99, -4, 4.5, '5', null, true, 4, 5];
    const out = toLiveItems(
      pages.map((p, i) => item({ id: 'p' + i, number: `R-${10 + i}`, document_index: 3, page: p, evidence: [{ label: 'e', page: p, finding_ids: [], finding_id: null }] })),
      sources,
      [],
    );
    expect(out.map((i) => i.page)).toEqual([1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 2]);
    expect(out.map((i) => i.evidence[0].page)).toEqual([1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 2]);
  });

  it('글(title · desc · next)이 문자열이 아니면 빈 글', () => {
    const out = read([item({ title: 5, desc: null, next: { a: 1 } }), item({ id: 'b', number: 'R-02', title: ['x'], desc: true })]);
    expect(out.map((i) => [i.title, i.desc, i.next])).toEqual([
      ['', '', ''],
      ['', '', '할 일'],
    ]);
  });

  it('항목 단위 finding_id — 다른 서류의 항목 · 없는 id · 숫자 · 빈 글은 findingId 없음, 같은 서류면 화면 번호', () => {
    const out = read([
      item({ id: 'a', number: 'R-01', finding_id: '1:applicant_name' }), // 서류 1 의 항목
      item({ id: 'b', number: 'R-02', finding_id: '0:nope' }),
      item({ id: 'c', number: 'R-03', finding_id: 7 }),
      item({ id: 'd', number: 'R-04', finding_id: '' }),
      item({ id: 'e', number: 'R-05', finding_id: '0:employer_info' }),
    ]);
    expect(out.map((i) => i.findingId ?? null)).toEqual([null, null, null, null, 'D1-06']);
  });
});

/* ---------- 근거 ---------- */

describe('근거(evidence) — 틀린 근거만 건너뛴다', () => {
  const ev = (evidence: unknown) => read([item({ evidence })])[0].evidence;

  it('배열이 아니면(null · 객체 · 문자열 · 숫자) []', () => {
    for (const bad of [null, undefined, { label: 'x' }, 'x', 3]) expect(ev(bad)).toEqual([]);
  });

  it('항목이 객체가 아니거나 label 이 빈 글 · 숫자 · 없음이면 건너뛴다(공백 label 은 그대로)', () => {
    const out = ev([null, 5, 'x', [], { label: '' }, { label: 3 }, { page: 1 }, { label: ' ', page: 1 }, { label: '1쪽 열기', page: 1 }]);
    expect(out.map((e) => e.label)).toEqual([' ', '1쪽 열기']);
    expect(out.every((e) => e.docId === 'doc-0' && e.page === 1 && e.anchors.length === 0 && e.findingId === undefined)).toBe(true);
  });

  it('finding_ids — 배열 아님 · 문자열 아닌 원소 · 없는 id · 다른 서류의 id 는 건너뛰고, 같은 id 두 번이어도 위치 id 는 한 번', () => {
    expect(ev([{ label: 'a', page: 1, finding_ids: '0:employer_info' }])[0].anchors).toEqual([]);
    expect(ev([{ label: 'a', page: 1, finding_ids: { 0: '0:employer_info' } }])[0].anchors).toEqual([]);
    const out = ev([
      {
        label: 'a',
        page: 1,
        finding_ids: [5, null, {}, ['0:employer_info'], '0:nope', '1:applicant_name', '0:employer_info', '0:employer_info', '0:income_info'],
      },
    ]);
    expect(out[0].anchors).toEqual(['D1-06#1', 'D1-08#1']);
  });

  it('여러 상자 항목 — 상자 위치 id 를 차례로(겹치지 않게)', () => {
    const out = ev([{ label: 'a', page: 1, finding_ids: ['0:applicant_address', '0:applicant_address'] }]);
    expect(out[0].anchors).toEqual(['D1-05#1', 'D1-05#2', 'D1-05#3', 'D1-05#4', 'D1-05#5', 'D1-05#6']);
  });

  it('근거 쪽과 다른 쪽의 탐지 항목은 위치 id 에 넣지 않는다', () => {
    const r = itemsResult();
    (r.documents as Obj[])[0].page_end = 2; // 서류 0 = 파일 1~2쪽(탐지 항목은 모두 1쪽)
    const sources = readDocSources(r.documents);
    const findings = toLiveFindings(r.findings, sources, '');
    const out = toLiveItems(
      [item({ evidence: [{ label: '2쪽', page: 2, finding_ids: ['0:employer_info'] }, { label: '1쪽', page: 1, finding_ids: ['0:employer_info'] }] })],
      sources,
      findings,
    );
    expect(out[0].evidence.map((e) => [e.label, e.page, e.anchors])).toEqual([
      ['2쪽', 2, []],
      ['1쪽', 1, ['D1-06#1']],
    ]);
  });

  it('근거의 finding_id — 위치 있는 항목 · 위치 없는 항목 모두 findingId, 다른 서류 · 없는 id · 숫자는 없음', () => {
    const one = (finding_id: unknown, document_index = 0) => read([item({ document_index, evidence: [{ label: 'a', page: null, finding_ids: [], finding_id }] })])[0].evidence[0].findingId;
    expect(one('0:employer_info')).toBe('D1-06'); // 위치 있음
    expect(one('4:credit_negative_info', 4)).toBe('D5-03'); // 위치 없음(상자 0)
    expect(one('2:income_info', 2)).toBe('D3-02'); // 위치 없음(쪽 null)
    expect(one('2:income_info', 0)).toBeUndefined(); // 다른 서류
    expect(one('0:nope')).toBeUndefined();
    expect(one(0)).toBeUndefined();
    expect(one(null)).toBeUndefined();
  });

  it('탐지 항목의 계약 id 가 겹치면 처음 항목으로 찾는다', () => {
    const r = itemsResult();
    const fs = r.findings as Obj[];
    fs[6].id = fs[5].id; // D1-07 의 계약 id = D1-06 의 계약 id
    const sources = readDocSources(r.documents);
    const findings = toLiveFindings(r.findings, sources, '');
    const out = toLiveItems([item({ finding_id: fs[5].id, evidence: [{ label: 'a', page: 1, finding_ids: [fs[5].id], finding_id: fs[5].id }] })], sources, findings);
    expect(out[0].findingId).toBe('D1-06');
    expect(out[0].evidence[0]).toMatchObject({ anchors: ['D1-06#1'], findingId: 'D1-06' });
  });
});

/* ---------- 덧씌우기 ---------- */

describe('해결 기록 덧씌우기(overlayItemReviews)', () => {
  const items = () => read(itemsResult().items);
  const at = '2026-11-04T01:02:03.123456+00:00';

  it('review.items 가 객체가 아니면(null · 배열 · 문자열 · 숫자 · 없음) 모두 기본값', () => {
    for (const bad of [null, undefined, [], [{ resolved: true }], 'x', 1, true]) {
      const out = overlayItemReviews(items(), bad, seoulDateTime);
      expect(out.every((i) => !i.resolved && i.note === '' && i.resolvedAt === '' && i.resolvedBy === '')).toBe(true);
    }
  });

  it('계약 id 로 덧씌운다 — 해결 · 처리 내용 · 서울 시각 · 처리자, 다른 항목은 그대로, 모르는 키는 무시', () => {
    const out = overlayItemReviews(
      items(),
      { 'lowconf:0': { resolved: true, note: '원본 확인', resolved_at: at, resolved_by: '이지은' }, 'gone:9': { resolved: true }, 'R-02': { resolved: true } },
      seoulDateTime,
    );
    expect(out[0]).toMatchObject({ id: 'R-01', resolved: true, note: '원본 확인', resolvedAt: '2026-11-04 10:02', resolvedBy: '이지은' });
    expect(out.slice(1).every((i) => !i.resolved)).toBe(true);
    // 위치 · 근거 · 글 · 계약 id 는 그대로
    expect(out[0].evidence).toEqual(items()[0].evidence);
    expect(out[0].live).toEqual({ id: 'lowconf:0' });
  });

  it('상속 키(__proto__ · constructor · toString)는 없는 것 — 자기 속성일 때만', () => {
    const odd = read([item({ id: '__proto__', number: 'R-01' }), item({ id: 'constructor', number: 'R-02' }), item({ id: 'toString', number: 'R-03' })]);
    expect(odd).toHaveLength(3);
    const plain = overlayItemReviews(odd, {}, seoulDateTime);
    expect(plain.every((i) => !i.resolved && i.note === '')).toBe(true);
    // JSON 으로 받은 자기 속성 __proto__ 는 읽는다
    const own = JSON.parse('{"__proto__": {"resolved": true, "note": "자기 속성"}, "constructor": {"resolved": true}}') as unknown;
    const out = overlayItemReviews(odd, own, seoulDateTime);
    expect(out.map((i) => [i.live?.id, i.resolved, i.note])).toEqual([
      ['__proto__', true, '자기 속성'],
      ['constructor', true, ''],
      ['toString', false, ''],
    ]);
  });

  it('값이 객체가 아니면(true · 글 · 숫자 · null · 배열) 기본값', () => {
    for (const v of [true, 'resolved', 1, null, [true]]) {
      const out = overlayItemReviews(items(), { 'lowconf:0': v }, seoulDateTime);
      expect(out[0]).toMatchObject({ resolved: false, note: '', resolvedAt: '', resolvedBy: '' });
    }
  });

  it("resolved 는 정확히 true 일 때만 — 'true' · 1 · 'yes' · {} 는 false", () => {
    for (const v of ['true', 1, 'yes', {}, null]) {
      expect(overlayItemReviews(items(), { 'lowconf:0': { resolved: v } }, seoulDateTime)[0].resolved).toBe(false);
    }
  });

  it('note · resolved_by 가 문자열이 아니면 빈 글, resolved_at 을 읽을 수 없으면 빈 글', () => {
    const out = overlayItemReviews(items(), { 'lowconf:0': { resolved: true, note: 12, resolved_by: ['a'], resolved_at: 'not-a-date' } }, seoulDateTime);
    expect(out[0]).toMatchObject({ resolved: true, note: '', resolvedBy: '', resolvedAt: '' });
    for (const bad of [null, 5, {}, '', '2026-13-45T99:99']) {
      expect(overlayItemReviews(items(), { 'lowconf:0': { resolved_at: bad } }, seoulDateTime)[0].resolvedAt).toBe('');
    }
  });

  it('다시 연 항목(resolved false) — 처리 내용 · 시각 · 처리자는 남은 값 그대로 보인다', () => {
    const out = overlayItemReviews(items(), { 'other:5': { resolved: false, note: '앞서 처리', resolved_at: at, resolved_by: '이지은' } }, seoulDateTime);
    expect(out[7]).toMatchObject({ id: 'R-08', resolved: false, note: '앞서 처리', resolvedAt: '2026-11-04 10:02', resolvedBy: '이지은' });
  });
});

/* ---------- toAnalysis ---------- */

describe('toAnalysis — detailReady · reviewable 에 따른 검토사항', () => {
  const done = (result: Obj, review: unknown = NEW_REVIEW) => toAnalysis(analysisOut({ status: 'done', result, review: structuredClone(review) }));

  it('옛 결과(items 없음 — done-result) → 검토사항 0개', () => {
    const a = done(contractResult());
    expect(a.raw?.detailReady).toBe(true);
    expect(a.items).toEqual([]);
  });

  it('items 가 든 결과 + 검토 기록 → 8개, review.items 를 덧씌운다', () => {
    const a = done(itemsResult(), { ...NEW_REVIEW, items: { 'missing:1:applicant_name_detected': { resolved: true, note: '확인', resolved_at: '2026-11-04T00:00:00Z', resolved_by: '이지은' } } });
    expect(a.raw?.reviewable).toBe(true);
    expect(a.items).toHaveLength(8);
    expect(a.items.filter((i) => i.resolved).map((i) => [i.id, i.note, i.resolvedAt, i.resolvedBy])).toEqual([['R-02', '확인', '2026-11-04 09:00', '이지은']]);
  });

  it('검토 기록을 읽지 못함(review null · 키 없음) → 검토사항은 보이고 덧씌우지 않는다', () => {
    const a = done(itemsResult(), null);
    expect(a.raw?.reviewable).toBe(false);
    expect(a.items).toHaveLength(8);
    expect(a.items.every((i) => !i.resolved)).toBe(true);
    const noKey = toAnalysis(analysisOut({ status: 'done', result: itemsResult() }));
    expect(noKey.items).toHaveLength(8);
  });

  it('review 에 items 키가 없는 옛 검토 기록 → 모두 미해결', () => {
    const old = { ...NEW_REVIEW } as Obj;
    delete old.items;
    const a = done(itemsResult(), old);
    expect(a.raw?.reviewable).toBe(true);
    expect(a.items.every((i) => !i.resolved)).toBe(true);
  });

  it('detailReady 가 아니면(대기 · 분석 중 · 실패 · 일부 실패 · 서류 0개) items 가 있어도 []', () => {
    for (const status of ['queued', 'running', 'failed', 'partial']) {
      expect(toAnalysis(analysisOut({ status, result: itemsResult(), review: NEW_REVIEW })).items).toEqual([]);
    }
    const noDocs = itemsResult();
    noDocs.documents = [];
    expect(done(noDocs).items).toEqual([]);
  });

  it('목록 항목(toListAnalysis)은 그대로 items []', () => {
    expect(toListAnalysis(listItemOut({ status: 'done', review: 'needed' }))?.items).toEqual([]);
  });

  it('result.items 의 모양이 틀려도 예외 없이 나머지 값은 그대로', () => {
    for (const bad of [null, 'x', { a: 1 }, [null, 1, 'x', []]]) {
      const r = itemsResult();
      r.items = bad;
      const a = done(r);
      expect(a.items).toEqual([]);
      expect(a.findings).toHaveLength(19);
      expect(a.docs).toHaveLength(6);
    }
  });
});

/* ---------- 큰 입력 ---------- */

describe('큰 입력 — 선형(탐지 항목 찾기는 Map)', () => {
  it('검토사항 10,000 · 탐지 10,000 · 근거마다 finding_ids 100 · 해결 기록 10,000 → 1초 안', () => {
    const N = 10_000;
    const box = [
      { x: 0.1, y: 0.1 },
      { x: 0.2, y: 0.1 },
      { x: 0.2, y: 0.2 },
      { x: 0.1, y: 0.2 },
    ];
    const result = {
      documents: [{ index: 0, type: 'loan_application', page_start: 1, page_end: 1, kind: 'extracted', other_guide: '', validation: 'green' }],
      findings: Array.from({ length: N }, (_, k) => ({ id: `0:f${k}`, document_index: 0, field: `f${k}`, label: `항목${k}`, value: '', masked: '', page: 1, boxes: [box], confidence: 'low' })),
    };
    const sources = readDocSources(result.documents);
    const findings = toLiveFindings(result.findings, sources, '');
    expect(findings).toHaveLength(N);
    const items = Array.from({ length: N }, (_, i) => ({
      id: `lowconf:x${i}`,
      number: 'R-' + String(i + 1).padStart(2, '0'),
      type: 'lowconf',
      document_index: 0,
      page: 1,
      finding_id: null,
      title: 't',
      desc: 'd',
      next: 'n',
      evidence: [{ label: '1쪽 값 보기', page: 1, finding_ids: Array.from({ length: 100 }, (_, j) => `0:f${(i * 37 + j * 101) % N}`), finding_id: `0:f${i}` }],
    }));
    const saved = Object.fromEntries(items.map((it, i) => [it.id, { resolved: i % 2 === 0, note: 'n', resolved_at: '2026-11-04T00:00:00Z', resolved_by: 'a' }]));
    const t0 = performance.now();
    const out = overlayItemReviews(toLiveItems(items, sources, findings), saved, seoulDateTime);
    const ms = performance.now() - t0;
    expect(out).toHaveLength(N);
    expect(out[0].evidence[0].anchors).toHaveLength(100);
    expect(out.filter((i) => i.resolved)).toHaveLength(N / 2);
    expect(ms).toBeLessThan(1000);
  });
});
