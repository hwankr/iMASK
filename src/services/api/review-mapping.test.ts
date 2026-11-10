/* 검토 기록(AnalysisOut.review) 덧씌우기 — 고정 자료(fixtures/done-result.json) + review 블록 → toAnalysis */
import { describe, expect, it } from 'vitest';
import type { Analysis, Finding } from '../types';
import { overlayFindingReviews } from './contract';
import { readHistory, readReviewInfo, seoulDateTime, toAnalysis } from './mapping';
import { analysisOut, contractResult, doneResult } from './testing';

/** 백엔드 기본 review 블록(검토 기록 행이 없는 분석) */
function baseReview(patch: Record<string, unknown> = {}): Record<string, unknown> {
  return { status: 'needed', memo: '', memo_at: null, reviewer: '', reviewed_at: null, completion_note: '', findings: {}, history: [], version: 0, ...patch };
}

/** 저장된 항목 값 하나(AI 값으로 시작) */
function saved(patch: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    status: 'open',
    category: '이름',
    subject: '신청인',
    exposure: '전체 노출',
    fp_type: '',
    fp_note: '',
    reclass_note: '',
    memo: '',
    updated_at: null,
    ...patch,
  };
}

/** 완료 + 공통 계약 결과 + review 블록 */
function reviewed(review: unknown, edit?: (result: Record<string, unknown>) => void): Analysis {
  const result = contractResult();
  edit?.(result);
  return toAnalysis(analysisOut({ status: 'done', result, review }));
}

/** 검토 기록 없이(옛 응답) — 덧씌우기 전 값 */
const plain = (edit?: (result: Record<string, unknown>) => void): Analysis => {
  const result = contractResult();
  edit?.(result);
  return toAnalysis(analysisOut({ status: 'done', result }));
};

const byId = (a: Analysis, id: string): Finding => {
  const f = a.findings.find((x) => x.id === id);
  if (!f) throw new Error('항목 없음: ' + id);
  return f;
};

/** 분석 시각(updated_at 서울) — 덧씌우지 않은 항목의 updatedAt */
const ANALYZED = '2026-11-02 14:10';

describe('올바른 검토 기록 — 항목 · 분석에 덧씌운다', () => {
  const review = baseReview({
    status: 'needed',
    memo: '검토 메모',
    memo_at: '2026-11-03T01:10:00.123456+00:00',
    reviewer: '김민지',
    reviewed_at: '2026-11-03T15:30:00Z',
    completion_note: '완료 메모',
    version: 7,
    findings: {
      '0:applicant_name': saved({ status: 'confirmed', memo: '원본 교체 필요', updated_at: '2026-11-03T01:02:03.456789+00:00' }),
      '0:applicant_rrn': saved({
        status: 'false_positive',
        category: '고유식별정보',
        fp_type: '이미 가려진 값',
        fp_note: '원본에서 가려져 있음',
        updated_at: '2026-11-03T15:30:00Z',
      }),
      '0:applicant_phone': saved({
        status: 'reclassified',
        category: '기타 개인정보',
        subject: '보증인',
        exposure: '마스킹됨',
        reclass_note: '직장 대표번호',
        fp_type: '기타',
        fp_note: '분류 수정 전에 남은 값',
        updated_at: '2026-11-03T02:00:00+09:00',
      }),
      '1:applicant_name': saved({ status: 'open', memo: '' }),
    },
    history: [
      { id: 'S1', at: '2026-11-02T05:10:00.123456+00:00', actor: '시스템', kind: 'request', target: '분석 건', change: '문서 1개 분석 요청', reason: '' },
      { id: 'S2', at: '2026-11-02T05:10:34.900000+00:00', actor: '시스템', kind: 'ai', target: '분석 건', change: '분석 완료 · 탐지 19건 · 위험등급 상 · 검토사항 0건', reason: '' },
      { id: 'H1', at: '2026-11-03T01:02:03+00:00', actor: '김민지', kind: 'confirm', target: 'D1-01 이름', change: '미확인 → 확인함', reason: '' },
      { id: 'H2', at: '2026-11-03T15:30:00Z', actor: '김민지', kind: 'fp', target: 'D1-02 주민등록번호', change: '고유식별정보 → 오탐 (이미 가려진 값)', reason: '원본에서 가려져 있음' },
      { id: 'H3', at: '2026-11-03T01:10:00+00:00', actor: '김민지', kind: 'memo', target: '분석 건', change: '검토 메모 저장', reason: '검토 메모' },
    ],
  });
  const a = reviewed(review);
  const before = plain();

  it('분석 — 검토 필요 · 메모 · 메모 시각 · 검토자 · 검토 완료 시각 · 완료 메모(서울 시각) · raw.reviewable', () => {
    expect(a.raw?.detailReady).toBe(true);
    expect(a.raw?.reviewable).toBe(true);
    expect(a.review).toBe('needed');
    expect(a.memo).toBe('검토 메모');
    expect(a.memoAt).toBe('2026-11-03 10:10');
    expect(a.reviewer).toBe('김민지');
    expect(a.reviewedAt).toBe('2026-11-04 00:30');
    expect(a.completionNote).toBe('완료 메모');
    // 분석 시각 · 위험도 · 항목 수는 그대로
    expect(a.analyzedAt).toBe(before.analyzedAt);
    expect(a.risk).toBe(before.risk);
    expect(a.findings).toHaveLength(19);
  });

  it("검토 완료 — status 'done' 이면 done", () => {
    expect(reviewed(baseReview({ status: 'done' })).review).toBe('done');
  });

  it('이력 — 줄 수 · 순서 · 서울 시각 · 글 그대로', () => {
    expect(a.history.map((h) => [h.id, h.at, h.kind])).toEqual([
      ['S1', '2026-11-02 14:10', 'request'],
      ['S2', '2026-11-02 14:10', 'ai'],
      ['H1', '2026-11-03 10:02', 'confirm'],
      ['H2', '2026-11-04 00:30', 'fp'],
      ['H3', '2026-11-03 10:10', 'memo'],
    ]);
    expect(a.history[3]).toEqual({
      id: 'H2',
      at: '2026-11-04 00:30',
      actor: '김민지',
      kind: 'fp',
      target: 'D1-02 주민등록번호',
      change: '고유식별정보 → 오탐 (이미 가려진 값)',
      reason: '원본에서 가려져 있음',
    });
  });

  it('항목 — 확인함 · 메모 · 수정 시각(서울)', () => {
    const f = byId(a, 'D1-01');
    expect(f.status).toBe('confirmed');
    expect(f.memo).toBe('원본 교체 필요');
    expect(f.updatedAt).toBe('2026-11-03 10:02');
    expect([f.cat, f.subject, f.exposure, f.fpType, f.fpNote, f.reclassNote]).toEqual(['이름', '신청인', '전체 노출', '', '', '']);
  });

  it('항목 — 오탐(사유 · 메모, 날짜가 넘어가는 서울 시각)', () => {
    const f = byId(a, 'D1-02');
    expect(f.status).toBe('false_positive');
    expect(f.fpType).toBe('이미 가려진 값');
    expect(f.fpNote).toBe('원본에서 가려져 있음');
    expect(f.updatedAt).toBe('2026-11-04 00:30');
  });

  it('항목 — 분류 수정(정보 종류 · 주체 · 노출 · 수정 사유, 남은 오탐 사유도 그대로)', () => {
    const f = byId(a, 'D1-03');
    expect(f.status).toBe('reclassified');
    expect([f.cat, f.subject, f.exposure]).toEqual(['기타 개인정보', '보증인', '마스킹됨']);
    expect(f.reclassNote).toBe('직장 대표번호');
    expect([f.fpType, f.fpNote]).toEqual(['기타', '분류 수정 전에 남은 값']);
    expect(f.updatedAt).toBe('2026-11-03 02:00');
    expect(f.ai).toEqual({ cat: '연락처·이메일', subject: '신청인', exposure: '전체 노출' });
  });

  it('항목 — 미확인 저장 값 · updated_at null 이면 분석 시각, 기록 없는 항목은 기본값', () => {
    const f = byId(a, 'D2-01');
    expect(f.status).toBe('open');
    expect(f.updatedAt).toBe(ANALYZED);
    const untouched = byId(a, 'D5-02');
    expect(untouched).toEqual(byId(before, 'D5-02'));
    expect(untouched.status).toBe('open');
    expect(untouched.updatedAt).toBe(ANALYZED);
  });

  it('ai · risk · reason · live · 위치는 덧씌운 뒤에도 최초 값', () => {
    a.findings.forEach((f, i) => {
      const g = before.findings[i];
      expect(f.id).toBe(g.id);
      expect(f.ai).toEqual(g.ai);
      expect(f.risk).toBe(g.risk);
      expect(f.reason).toBe(g.reason);
      expect(f.live).toEqual(g.live);
      expect(f.anchors).toEqual(g.anchors);
      expect(f.boxes).toEqual(g.boxes);
      expect([f.label, f.masked, f.evidence, f.page, f.docId]).toEqual([g.label, g.masked, g.evidence, g.page, g.docId]);
    });
  });
});

describe('잘못된 값은 버리고 AI 값 · 기본값', () => {
  it('항목 값 — 목록 밖 status · 분류 · 오탐 사유, 숫자 · null · 배열 글, 못 읽는 시각', () => {
    const a = reviewed(
      baseReview({
        findings: {
          '0:applicant_name': {
            status: 'bogus',
            category: '없는 분류',
            subject: 7,
            exposure: null,
            fp_type: '아무 사유',
            fp_note: 5,
            reclass_note: null,
            memo: ['메모'],
            updated_at: '어제',
          },
          '0:applicant_rrn': { status: 'CONFIRMED', category: ['이름'], subject: { v: '보증인' }, exposure: '전체노출', fp_type: 0, updated_at: 1730000000000 },
          '0:applicant_phone': { status: 'toString', fp_type: 'constructor', category: '__proto__', updated_at: '' },
        },
      }),
    );
    const f1 = byId(a, 'D1-01');
    expect([f1.status, f1.cat, f1.subject, f1.exposure, f1.fpType, f1.fpNote, f1.reclassNote, f1.memo, f1.updatedAt]).toEqual([
      'open',
      '이름',
      '신청인',
      '전체 노출',
      '',
      '',
      '',
      '',
      ANALYZED,
    ]);
    const f2 = byId(a, 'D1-02');
    expect([f2.status, f2.cat, f2.subject, f2.exposure, f2.fpType, f2.updatedAt]).toEqual(['open', '고유식별정보', '신청인', '전체 노출', '', ANALYZED]);
    const f3 = byId(a, 'D1-03');
    expect([f3.status, f3.cat, f3.fpType, f3.updatedAt]).toEqual(['open', '연락처·이메일', '', ANALYZED]);
  });

  it('객체가 아닌 항목 값 · 지금 없는 id 는 무시', () => {
    const before = plain();
    const a = reviewed(
      baseReview({
        findings: {
          '0:applicant_name': 'confirmed',
          '0:applicant_rrn': 3,
          '0:applicant_phone': null,
          '0:applicant_email': [saved({ status: 'confirmed' })],
          '9:없는 항목': saved({ status: 'confirmed', memo: '사라진 항목' }),
          'D1-05': saved({ status: 'confirmed' }), // 화면 번호는 키가 아니다
        },
      }),
    );
    expect(a.findings).toEqual(before.findings);
  });

  it('__proto__ · constructor · toString 키 — 자기 속성이 아니면 없는 것, 자기 속성이면 그 id 의 항목에만', () => {
    // 1) 저장소에 그런 키가 있어도(JSON 의 자기 속성) 지금 항목 id 가 아니면 무시
    const table = JSON.parse('{"__proto__": {"status": "confirmed"}, "constructor": {"status": "confirmed"}, "toString": {"status": "confirmed"}}');
    expect(reviewed(baseReview({ findings: table })).findings).toEqual(plain().findings);

    // 2) 항목 id 가 그 이름이어도 저장 값이 없으면(상속 속성만) 덧씌우지 않는다
    const rename = (r: Record<string, unknown>) => {
      const fs = r.findings as { id: string }[];
      fs[0].id = '__proto__';
      fs[1].id = 'constructor';
      fs[2].id = 'toString';
    };
    const none = reviewed(baseReview({ findings: {} }), rename);
    expect(none.findings).toEqual(plain(rename).findings);
    expect(['D1-01', 'D1-02', 'D1-03'].map((id) => byId(none, id).status)).toEqual(['open', 'open', 'open']);

    // 3) 자기 속성으로 저장돼 있으면 그 항목에만 덧씌운다
    const own = reviewed(baseReview({ findings: JSON.parse('{"__proto__": {"status": "confirmed", "memo": "proto"}}') }), rename);
    expect(byId(own, 'D1-01')).toMatchObject({ status: 'confirmed', memo: 'proto' });
    expect(byId(own, 'D1-02').status).toBe('open');
    expect(byId(own, 'D1-03').status).toBe('open');
  });

  it('findings 가 객체가 아니면(배열 · 문자열 · null) 항목은 그대로, 분석 기록은 읽는다', () => {
    for (const findings of [[saved({ status: 'confirmed' })], 'x', null, 3]) {
      const a = reviewed(baseReview({ findings, memo: 'm' }));
      expect(a.raw?.reviewable).toBe(true);
      expect(a.memo).toBe('m');
      expect(a.findings).toEqual(plain().findings);
    }
  });

  it('분석 값 — 목록 밖 status 는 needed, 글이 아니면 빈 값, 못 읽는 시각은 빈 값', () => {
    const a = reviewed(baseReview({ status: 'bogus', memo: 5, memo_at: '어제', reviewer: null, reviewed_at: 17, completion_note: ['x'] }));
    expect(a.review).toBe('needed');
    expect([a.memo, a.memoAt, a.reviewer, a.reviewedAt, a.completionNote]).toEqual(['', '', '', '', '']);
    expect(reviewed(baseReview({ status: 'DONE' })).review).toBe('needed');
  });

  it('이력 — 모르는 kind · 상속 키 kind · 객체 아닌 줄은 빼고, 글 아님 → 빈 값, id 없으면 H<순번>, 시각 못 읽으면 빈 값', () => {
    const history = readHistory([
      { id: 'S1', at: '2026-11-02T05:10:00Z', actor: '시스템', kind: 'request', target: '분석 건', change: '문서 1개 분석 요청', reason: '' },
      { id: 'X', at: '2026-11-02T05:10:00Z', actor: '김민지', kind: 'bogus', target: '', change: '', reason: '' },
      { id: 'Y', kind: 'toString' },
      { id: 'Z', kind: '__proto__' },
      'confirm',
      null,
      ['confirm'],
      { at: '어제', actor: 3, kind: 'confirm', target: null, change: ['x'], reason: { r: 1 } },
      { id: '', at: '2026-11-03T00:00:00Z', actor: '김민지', kind: 'reopen', target: '분석 건', change: '검토 완료 → 검토 필요', reason: '다시 확인' },
      { id: 'H9', at: '2026-11-03T00:00:00Z', actor: '김민지', kind: 'complete', target: '분석 건', change: '검토 필요 → 검토 완료', reason: '' },
    ]);
    expect(history).toEqual([
      { id: 'S1', at: '2026-11-02 14:10', actor: '시스템', kind: 'request', target: '분석 건', change: '문서 1개 분석 요청', reason: '' },
      { id: 'H8', at: '', actor: '', kind: 'confirm', target: '', change: '', reason: '' },
      { id: 'H9', at: '2026-11-03 09:00', actor: '김민지', kind: 'reopen', target: '분석 건', change: '검토 완료 → 검토 필요', reason: '다시 확인' },
      { id: 'H9', at: '2026-11-03 09:00', actor: '김민지', kind: 'complete', target: '분석 건', change: '검토 필요 → 검토 완료', reason: '' },
    ]);
    for (const v of [null, 'x', {}, 3]) expect(readHistory(v)).toEqual([]);
  });

  it('review 가 배열 · 문자열 · 숫자 — 검토 기록을 읽지 못한 것과 같다', () => {
    for (const review of [[baseReview()], 'needed', 3, true]) {
      const a = reviewed(review);
      expect(a.raw?.reviewable).toBe(false);
      expect(a.review).toBe('none');
      expect(a.history).toEqual([]);
      expect(a.findings).toEqual(plain().findings);
    }
    expect(readReviewInfo([])).toBeNull();
    expect(readReviewInfo(null)).toBeNull();
  });
});

describe('검토할 수 없을 때', () => {
  it("review null + detailReady — 'none' · reviewable false · 빈 값(상세 화면은 검토 버튼만 막는다)", () => {
    const a = reviewed(null);
    expect(a.raw?.detailReady).toBe(true);
    expect(a.raw?.reviewable).toBe(false);
    expect(a.review).toBe('none');
    expect(a.history).toEqual([]);
    expect([a.memo, a.memoAt, a.reviewer, a.reviewedAt, a.completionNote]).toEqual(['', '', '', '', '']);
    expect(a.findings).toEqual(plain().findings);
  });

  it("detailReady 아님(대기 · 분석 중 · 실패 · 일부 실패 · 옛 형식) — review 가 와도 'none' · 빈 이력 · reviewable false", () => {
    const review = baseReview({ status: 'done', memo: 'm', reviewer: '김민지', history: [{ id: 'S1', at: '2026-11-02T05:10:00Z', actor: '시스템', kind: 'request', target: '', change: '', reason: '' }] });
    const outs = [
      analysisOut({ status: 'queued', review }),
      analysisOut({ status: 'running', result: contractResult(), review }),
      analysisOut({ status: 'failed', result: contractResult(), error: '실패', review }),
      analysisOut({ status: 'partial', result: contractResult(), review }),
      analysisOut({ status: 'done', result: doneResult(), review }),
    ];
    for (const out of outs) {
      const a = toAnalysis(out);
      expect(a.raw?.detailReady).toBe(false);
      expect(a.raw?.reviewable).toBe(false);
      expect(a.review).toBe('none');
      expect(a.history).toEqual([]);
      expect([a.memo, a.reviewer]).toEqual(['', '']);
      expect(a.findings).toEqual([]);
    }
  });
});

describe('계약 id 에 어떤 문자든 — 그 항목에 정확히 덧씌운다', () => {
  it('짝 없는 서로게이트 · \\u0000 · 따옴표 · 역슬래시(JSON 왕복 뒤에도)', () => {
    const odd = ['0:전화"\ud800', '0:\u0000이메일', '0:주소\\"\udc00\u0000'];
    const rename = (r: Record<string, unknown>) => {
      const fs = r.findings as { id: string }[];
      fs[2].id = odd[0];
      fs[3].id = odd[1];
      fs[4].id = odd[2];
    };
    // 서버 응답처럼 JSON 문자열을 거친 값(서로게이트는 \ud800 escape 로 온다)
    const wire = JSON.parse(
      JSON.stringify(
        baseReview({
          findings: {
            [odd[0]]: saved({ status: 'confirmed', memo: 'a' }),
            [odd[1]]: saved({ status: 'false_positive', fp_type: '기타', memo: 'b' }),
            [odd[2]]: saved({ status: 'reclassified', category: '이름', memo: 'c' }),
            '0:전화"': saved({ status: 'confirmed', memo: '비슷한 키' }), // 서로게이트 없는 비슷한 키는 다른 항목
          },
        }),
      ),
    );
    const a = reviewed(wire, rename);
    expect(byId(a, 'D1-03')).toMatchObject({ status: 'confirmed', memo: 'a' });
    expect(byId(a, 'D1-04')).toMatchObject({ status: 'false_positive', fpType: '기타', memo: 'b' });
    expect(byId(a, 'D1-05')).toMatchObject({ status: 'reclassified', cat: '이름', memo: 'c' });
    expect(byId(a, 'D1-05').live?.id).toBe(odd[2]);
    const rest = a.findings.filter((f) => !['D1-03', 'D1-04', 'D1-05'].includes(f.id));
    expect(rest.every((f) => f.status === 'open' && f.memo === '')).toBe(true);
  });
});

describe('overlayFindingReviews — 순수 함수', () => {
  it('saved 가 객체가 아니면 같은 항목들, 고친 항목은 새 객체(원래 목록은 그대로)', () => {
    const findings = plain().findings;
    const copy = structuredClone(findings);
    expect(overlayFindingReviews(findings, null, seoulDateTime)).toEqual(findings);
    const out = overlayFindingReviews(findings, { '0:applicant_name': saved({ status: 'confirmed' }) }, seoulDateTime);
    expect(out[0].status).toBe('confirmed');
    expect(out[0]).not.toBe(findings[0]);
    expect(out[1]).toBe(findings[1]);
    expect(findings).toEqual(copy);
  });
});
