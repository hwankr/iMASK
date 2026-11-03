import { describe, expect, it } from 'vitest';
import { UNRATED_REASON } from './contract';
import { analysisCode, extLabel, parseIsoMs, riskFromLevel, seoulDateTime, toAnalysis, toStatus } from './mapping';
import { analysisOut, contractResult, documentOut, doneResult } from './testing';

describe('시각 · 분석 번호', () => {
  it('Postgres 6자리 소수 초와 시간대를 읽는다', () => {
    expect(parseIsoMs('2026-11-02T05:10:00.123456+00:00')).toBe(Date.UTC(2026, 10, 2, 5, 10, 0, 123));
    expect(parseIsoMs('2026-11-02 05:10:00Z')).toBe(Date.UTC(2026, 10, 2, 5, 10, 0));
    expect(Number.isNaN(parseIsoMs(''))).toBe(true);
    expect(Number.isNaN(parseIsoMs(null))).toBe(true);
    expect(Number.isNaN(parseIsoMs('어제'))).toBe(true);
  });

  it('서울 시각 YYYY-MM-DD HH:mm (UTC+9, 날짜가 넘어가는 경우 포함)', () => {
    expect(seoulDateTime('2026-11-02T05:10:59.999+00:00')).toBe('2026-11-02 14:10');
    expect(seoulDateTime('2026-11-02T15:30:00Z')).toBe('2026-11-03 00:30');
    expect(seoulDateTime('2026-12-31T20:05:00+09:00')).toBe('2026-12-31 20:05');
    expect(seoulDateTime('잘못된 값')).toBe('');
  });

  it("분석 번호 = 'DG-' + 서울 날짜 + id 앞 4자 대문자", () => {
    expect(analysisCode('ab12cd34-0000', '2026-11-02T15:30:00Z')).toBe('DG-20261103-AB12');
    expect(analysisCode('ab12cd34-0000', '')).toBe('DG-AB12');
  });
});

describe('상태 · 위험도 · 형식', () => {
  it('알려진 상태는 그대로, 모르는 값은 queued', () => {
    for (const s of ['queued', 'running', 'done', 'partial', 'failed']) expect(toStatus(s)).toBe(s);
    expect(toStatus('cancelled')).toBe('queued');
    expect(toStatus(undefined)).toBe('queued');
    expect(toStatus('toString')).toBe('queued');
  });

  it('위험도 상·중·하 → high·medium·low, 그 밖 → unrated', () => {
    expect(riskFromLevel('상')).toBe('high');
    expect(riskFromLevel('중')).toBe('medium');
    expect(riskFromLevel(' 하 ')).toBe('low');
    expect(riskFromLevel('검토 필요')).toBe('unrated');
    expect(riskFromLevel(null)).toBe('unrated');
  });

  it('형식 표기 — MIME 우선, 없으면 확장자(jpeg → JPG)', () => {
    expect(extLabel('application/pdf', 'x.bin')).toBe('PDF');
    expect(extLabel('image/jpeg', 'a.png')).toBe('JPG');
    expect(extLabel('', '사진.JPEG')).toBe('JPG');
    expect(extLabel('', '스캔.png')).toBe('PNG');
    expect(extLabel('', '이름없음')).toBe('');
  });
});

describe('toAnalysis', () => {
  it('대기 — 기본값, 분석 시각 없음, raw 빈 값', () => {
    const a = toAnalysis(analysisOut());
    expect(a.id).toBe('ab12cd34-0000-4000-8000-000000000000');
    expect(a.code).toBe('DG-20261102-AB12');
    expect(a.name).toBe('합성 묶음');
    expect(a.submittedAt).toBe('2026-11-02 14:10');
    expect(a.analyzedAt).toBe('');
    expect(a.status).toBe('queued');
    expect(a.risk).toBe('unrated');
    expect(a.review).toBe('none');
    expect(a.findings).toEqual([]);
    expect(a.items).toEqual([]);
    expect(a.links).toEqual([]);
    expect(a.history).toEqual([]);
    expect(a.riskReasons).toEqual([]);
    expect(a.recs).toEqual([]);
    expect([a.memo, a.memoAt, a.limits, a.reviewer, a.reviewedAt, a.completionNote]).toEqual(['', '', '', '', '', '']);
    expect(a.demoQueued).toBe(false);
    expect(a.retrying).toBe(false);
    expect(a.raw).toEqual({
      result: null,
      file: { id: 'd0c00000-0000-4000-8000-000000000001', name: 'iMASK_smoke_bundle.pdf', mime: 'application/pdf', size: 322053 },
      detailReady: false,
      reviewable: false,
      overall: null,
      error: '',
      jobId: '',
      upstageStatus: '',
      pollError: '',
      createdAt: '2026-11-02T05:10:00.123456+00:00',
      updatedAt: '2026-11-02T05:10:34.900000+00:00',
    });
  });

  it('문서 — 파일 이름 · 형식 · 크기 · 상태(분석 상태와 같음), 쪽은 없음', () => {
    const a = toAnalysis(analysisOut({ status: 'running', upstage_job_id: 'job_1', upstage_status: 'in_progress', poll_error: '연결 실패' }));
    expect(a.docs).toEqual([
      { id: 'd0c00000-0000-4000-8000-000000000001', title: 'iMASK_smoke_bundle.pdf', name: 'iMASK_smoke_bundle.pdf', ext: 'PDF', size: 322053, status: 'running', error: '', pages: null },
    ]);
    expect(a.raw?.jobId).toBe('job_1');
    expect(a.raw?.upstageStatus).toBe('in_progress');
    expect(a.raw?.pollError).toBe('연결 실패');
    expect(a.analyzedAt).toBe('');
  });

  it('완료 — 위험도는 summary.risk_level, 분석 시각은 updated_at, result 를 raw 에 둔다', () => {
    const result = doneResult();
    const a = toAnalysis(analysisOut({ status: 'done', result, upstage_job_id: 'job_test' }));
    expect(a.status).toBe('done');
    expect(a.risk).toBe('high');
    expect(a.analyzedAt).toBe('2026-11-02 14:10');
    expect(a.raw?.result).toBe(result);
    expect(a.docs[0].status).toBe('done');
  });

  it('실패 — 문서도 실패, 오류 문구를 문서와 raw 에 그대로', () => {
    const a = toAnalysis(analysisOut({ status: 'failed', error: '파일 내용이 PDF·PNG·JPEG 형식이 아닙니다.' }));
    expect(a.status).toBe('failed');
    expect(a.analyzedAt).toBe('2026-11-02 14:10');
    expect(a.docs[0]).toMatchObject({ status: 'failed', error: '파일 내용이 PDF·PNG·JPEG 형식이 아닙니다.' });
    expect(a.raw?.error).toBe('파일 내용이 PDF·PNG·JPEG 형식이 아닙니다.');
  });

  it('일부 실패 — 문서는 failed', () => {
    const a = toAnalysis(analysisOut({ status: 'partial', error: '일부 실패' }));
    expect(a.status).toBe('partial');
    expect(a.docs[0].status).toBe('failed');
  });

  it('모르는 상태 → queued, 모양이 깨진 값도 예외 없이', () => {
    const a = toAnalysis(
      analysisOut({ status: 'weird', result: 'not-an-object' as unknown, documents: [documentOut({ size_bytes: Number.NaN, mime_type: 'image/png', filename: '스캔.png' })] }),
    );
    expect(a.status).toBe('queued');
    expect(a.raw?.result).toBeNull();
    expect(a.risk).toBe('unrated');
    expect(a.docs[0]).toMatchObject({ ext: 'PNG', size: 0, name: '스캔.png' });
    const b = toAnalysis({ ...analysisOut(), documents: undefined as unknown as [] });
    expect(b.docs).toEqual([]);
  });
});

/* ---------- 공통 계약(result.documents · findings · overall) ---------- */

const FILE_ROW = { id: 'd0c00000-0000-4000-8000-000000000001', title: 'iMASK_smoke_bundle.pdf', name: 'iMASK_smoke_bundle.pdf', ext: 'PDF', size: 322053, error: '', pages: null };

/** 완료 + 계약 결과 */
const doneWith = (result: unknown) => toAnalysis(analysisOut({ status: 'done', result, upstage_job_id: 'job_fixture_smoke_bundle' }));

describe('공통 계약 — 고정 자료(fixtures/done-result.json)', () => {
  it('서류 6개 — 제목 · 쪽 수 · source · 파일 이름 · 형식 · 크기', () => {
    const a = doneWith(contractResult());
    expect(a.raw?.detailReady).toBe(true);
    expect(a.docs.map((d) => d.id)).toEqual(['doc-0', 'doc-1', 'doc-2', 'doc-3', 'doc-4', 'doc-5']);
    expect(a.docs.map((d) => d.title)).toEqual(['대출신청서', '동의서', '소득 증빙', '위임장', '채무내역', '기타']);
    for (const d of a.docs) {
      expect(d).toMatchObject({ name: 'iMASK_smoke_bundle.pdf', ext: 'PDF', size: 322053, status: 'done', error: '', pages: null, pageCount: 1 });
    }
    expect(a.docs[0].source).toEqual({ index: 0, type: 'loan_application', pageStart: 1, pageEnd: 1, kind: 'extracted', otherGuide: '', validation: 'green' });
    expect(a.docs[5].source).toMatchObject({ index: 5, type: 'Other', pageStart: 6, pageEnd: 6, kind: 'other', validation: '' });
    expect(a.docs[5].source?.otherGuide).toContain('## 기타 서류 안내');
  });

  it('항목 — 미평가(판정 2개 제외) · 번호 · 위치 없는 항목은 anchors [] · 분석 위험도 high', () => {
    const a = doneWith(contractResult());
    expect(a.risk).toBe('high');
    expect(a.findings).toHaveLength(19);
    expect(a.findings.map((f) => f.id)).toEqual([
      'D1-01', 'D1-02', 'D1-03', 'D1-04', 'D1-05', 'D1-06', 'D1-07', 'D1-08', 'D1-09',
      'D2-01', 'D2-02',
      'D3-01', 'D3-02',
      'D4-01', 'D4-02', 'D4-03',
      'D5-01', 'D5-02', 'D5-03',
    ]);
    const judged = a.findings.filter((f) => f.risk !== 'unrated');
    expect(judged.map((f) => [f.id, f.risk, f.live?.riskSource])).toEqual([
      ['D1-02', 'high', 'workflow'],
      ['D4-02', 'high', 'workflow'],
    ]);
    expect(judged[0].reason).toBe('주민등록번호 13자리가 가림 없이 그대로 적혀 있습니다.');
    for (const f of a.findings.filter((x) => x.risk === 'unrated')) {
      expect(f.reason).toBe(UNRATED_REASON);
      expect(f.live?.riskSource).toBeNull();
    }
    const noLoc = a.findings.filter((f) => f.anchors.length === 0);
    expect(noLoc.map((f) => f.id)).toEqual(['D3-02', 'D5-03']); // page null · boxes []
    expect(noLoc.map((f) => f.evidence)).toEqual(['소득금액: 48,000,000원; 결정세액: 2,150,000원', '데모카드 카드론 연체 32일']);
    expect(a.findings.every((f) => f.page === 1)).toBe(true); // 서류마다 1쪽
  });

  it('항목 하나의 모든 값(D1-01) — 분류 · 마스킹 · 상자 · live · 검토 기본값', () => {
    const a = doneWith(contractResult());
    expect(a.findings[0]).toEqual({
      id: 'D1-01',
      cat: '이름',
      label: '성명',
      masked: '윤*아',
      subject: '신청인',
      exposure: '전체 노출',
      risk: 'unrated',
      reason: UNRATED_REASON,
      rule: '',
      docId: 'doc-0',
      page: 1,
      anchors: ['D1-01#1'],
      evidence: '윤서아',
      status: 'open',
      memo: '',
      fpType: '',
      fpNote: '',
      reclassNote: '',
      updatedAt: '2026-11-02 14:10',
      ai: { cat: '이름', subject: '신청인', exposure: '전체 노출' },
      boxes: [{ a: 'D1-01#1', points: [{ x: 0.237, y: 0.225 }, { x: 0.286, y: 0.225 }, { x: 0.286, y: 0.238 }, { x: 0.237, y: 0.238 }] }],
      live: { id: '0:applicant_name', field: 'applicant_name', value: '윤서아', mappingStatus: 'ok', confidence: 'high', riskSource: null },
    });
  });

  it('상자 여러 개(단어별) · 위치 ID 가 분석 안에서 겹치지 않는다 · live 의 상태 값', () => {
    const a = doneWith(contractResult());
    const address = a.findings.find((f) => f.live?.field === 'applicant_address');
    expect(address?.anchors).toEqual(['D1-05#1', 'D1-05#2', 'D1-05#3', 'D1-05#4', 'D1-05#5', 'D1-05#6']);
    expect(address?.boxes?.map((b) => b.a)).toEqual(address?.anchors);
    const all = a.findings.flatMap((f) => f.anchors);
    expect(new Set(all).size).toBe(all.length);
    expect(new Set(a.findings.map((f) => f.id)).size).toBe(a.findings.length);
    const byField = (docIndex: number, field: string) => a.findings.find((f) => f.live?.id === `${docIndex}:${field}`)?.live;
    expect(byField(0, 'employer_info')).toMatchObject({ mappingStatus: 'needs_review', confidence: 'low' });
    expect(byField(0, 'staff_contact')).toMatchObject({ mappingStatus: 'unknown', confidence: 'low' });
    expect(byField(4, 'credit_negative_info')).toMatchObject({ mappingStatus: 'unknown', confidence: null });
  });

  it('riskReasons · recs = overall Markdown 줄, raw 에 file · detailReady · overall', () => {
    const a = doneWith(contractResult());
    expect(a.riskReasons).toEqual([
      '상으로 판단됩니다.',
      '고유식별정보가 포함되어 있습니다: 대출신청서에 신청인의 주민등록번호가 있습니다.',
      '위임장에 대리인의 주민등록번호가 있습니다.',
      '신용도판단정보가 포함되어 있습니다: 채무내역에 연체 정보가 있습니다.',
      '고유식별정보 또는 신용도판단정보가 하나라도 있으면 위험도는 상입니다.',
    ]);
    expect(a.recs).toEqual([
      '고유식별정보 | 대상 서류: 대출신청서, 위임장, 소득 증빙 | 처리 방법: 가림 | 이유: 주민등록번호가 실제 값으로 들어 있습니다.',
      '신용도판단정보 | 대상 서류: 채무내역 | 처리 방법: 접근 제한 | 이유: 연체 정보가 실제 값으로 들어 있습니다.',
      '보관·전달 전 마스킹본을 만들어 공유합니다.',
      '※ 담당자 최종 확인 필요',
    ]);
    expect(a.raw?.file).toEqual({ id: 'd0c00000-0000-4000-8000-000000000001', name: 'iMASK_smoke_bundle.pdf', mime: 'application/pdf', size: 322053 });
    expect(a.raw?.overall).toMatchObject({ level: '상', nextStage: '권장_조치' });
    expect(a.raw?.overall?.text).toContain('## 위험도 판정');
    expect(a.raw?.overall?.nextText).toContain('## 여신 담당자 사전 조치 정리');
    expect(a.raw?.result).toMatchObject({ format: 'imask-upstage-v1' });
    expect(a.items).toEqual([]);
    expect(a.links).toEqual([]);
    expect(a.history).toEqual([]);
    expect(a.review).toBe('none');
  });

  it('같은 응답이면 늘 같은 값(번호 · 위치 ID 가 안정적)', () => {
    const r = contractResult();
    expect(doneWith(r)).toEqual(doneWith(structuredClone(r)));
  });
});

describe('공통 계약 — 분석 위험도', () => {
  it('overall.level 이 summary.risk_level 보다 우선', () => {
    const r = contractResult();
    const overall = r.overall as Record<string, unknown>;
    overall.level = '하';
    expect(doneWith(r).risk).toBe('low'); // summary 는 '상'
    overall.level = '중';
    expect(doneWith(r).risk).toBe('medium');
    overall.level = '검토 필요';
    expect(doneWith(r).risk).toBe('unrated');
  });

  it('overall.level 이 없으면 summary.risk_level', () => {
    const r = contractResult();
    (r.overall as Record<string, unknown>).level = null;
    expect(doneWith(r).risk).toBe('high');
    const r2 = contractResult();
    delete r2.overall;
    const a = doneWith(r2);
    expect(a.risk).toBe('high');
    expect(a.raw?.overall).toBeNull();
    expect(a.riskReasons).toEqual([]);
    expect(a.recs).toEqual([]);
    expect(a.raw?.detailReady).toBe(true); // overall 은 판단 조건이 아니다
  });

  it('검토_안내 단계도 recs 로, 단계 이름은 raw.overall.nextStage 로 구분', () => {
    const r = contractResult();
    r.overall = { level: '검토 필요', text: '판정할 수 없습니다.', next_stage: '검토_안내', next_text: '- 원본을 다시 확인하세요.' };
    const a = doneWith(r);
    expect(a.recs).toEqual(['원본을 다시 확인하세요.']);
    expect(a.raw?.overall).toEqual({ level: '검토 필요', text: '판정할 수 없습니다.', nextStage: '검토_안내', nextText: '- 원본을 다시 확인하세요.' });
  });
});

describe('공통 계약 — 서류', () => {
  it('index 순 · 같은 index 는 처음 것만 · 끝 쪽 < 시작 쪽이면 끝 = 시작 · 유효하지 않은 행은 뺀다', () => {
    const a = doneWith({
      documents: [
        { index: 2, type: 'income_proof', page_start: 4, page_end: 2, kind: 'extracted' },
        { index: 0, type: 'loan_application', page_start: 1, page_end: 3, kind: 'extracted', validation: 'green' },
        { index: 0, type: 'consent_form', page_start: 9, page_end: 9 },
        { index: -1, type: 'x', page_start: 1, page_end: 1 },
        { index: 1.5, type: 'x', page_start: 1, page_end: 1 },
        { index: '1', type: 'x', page_start: 1, page_end: 1 },
        { index: 1, type: 'x', page_start: 0, page_end: 1 },
        { index: 1, type: 'x', page_start: 1 },
        { index: 1, type: 'x', page_start: '1', page_end: 2 },
        null,
        'doc',
        [1, 2],
      ],
      findings: [],
    });
    expect(a.raw?.detailReady).toBe(true);
    expect(a.docs.map((d) => [d.id, d.title, d.pageCount, d.source?.pageStart, d.source?.pageEnd])).toEqual([
      ['doc-0', '대출신청서', 3, 1, 3],
      ['doc-2', '소득 증빙', 1, 4, 4],
    ]);
  });

  it('같은 이름은 두 번째부터 " 2" · " 3", kind other 도 분류 코드의 이름(Other → 기타), 모르는 코드는 그대로', () => {
    const a = doneWith({
      documents: [
        { index: 0, type: 'consent_form', page_start: 1, page_end: 1, kind: 'extracted' },
        { index: 1, type: 'consent_form', page_start: 2, page_end: 2, kind: 'extracted' },
        { index: 2, type: 'consent_form', page_start: 3, page_end: 3 },
        { index: 3, type: 'Other', page_start: 4, page_end: 4, kind: 'other', other_guide: '안내' },
        { index: 4, type: 'other', page_start: 5, page_end: 5, kind: 'other' },
        { index: 5, type: 'bank_statement', page_start: 6, page_end: 6, kind: 'other' },
        { index: 6, type: '', page_start: 7, page_end: 7, kind: 'other' },
        { index: 7, type: null, page_start: 8, page_end: 8, kind: 'weird' },
      ],
      findings: [],
    });
    expect(a.docs.map((d) => d.title)).toEqual(['동의서', '동의서 2', '동의서 3', '기타', '기타 2', 'bank_statement', '기타 3', '분류 없는 서류']);
    expect(a.docs.map((d) => d.source?.kind)).toEqual(['extracted', 'extracted', 'extracted', 'other', 'other', 'other', 'other', 'extracted']);
    expect(a.docs[3].source?.otherGuide).toBe('안내');
    expect(a.docs[7].source).toMatchObject({ type: '', otherGuide: '', validation: '' });
  });

  it('올린 파일이 없으면 이름 · 형식 · 크기는 빈 값', () => {
    const a = toAnalysis(analysisOut({ status: 'done', documents: [], result: { documents: [{ index: 0, type: 'consent_form', page_start: 1, page_end: 1 }], findings: [] } }));
    expect(a.raw?.file).toBeNull();
    expect(a.docs).toEqual([
      {
        id: 'doc-0',
        title: '동의서',
        name: '',
        ext: '',
        size: 0,
        status: 'done',
        error: '',
        pages: null,
        pageCount: 1,
        source: { index: 0, type: 'consent_form', pageStart: 1, pageEnd: 1, kind: 'extracted', otherGuide: '', validation: '' },
      },
    ]);
  });
});

describe('공통 계약 — 탐지 항목', () => {
  /** 서류 둘(0: 3~5쪽, 3: 6쪽)과 항목 목록 */
  const withFindings = (findings: unknown[]) =>
    doneWith({
      documents: [
        { index: 0, type: 'loan_application', page_start: 3, page_end: 5, kind: 'extracted' },
        { index: 3, type: 'power_of_attorney', page_start: 6, page_end: 6, kind: 'extracted' },
      ],
      findings,
    });
  const box = (x: number, y: number) => [{ x, y }, { x: x + 0.1, y }, { x: x + 0.1, y: y + 0.02 }, { x, y: y + 0.02 }];

  it('짝이 되는 서류가 없는 항목은 버리고, 번호는 서류마다 이어진다(D<서류 목록 순번>-<두 자리>)', () => {
    const a = withFindings([
      { id: '0:a', document_index: 0, field: 'a', page: 3 },
      { id: '1:b', document_index: 1, field: 'b', page: 3 }, // 서류 1 없음
      { id: '0:c', document_index: '0', field: 'c', page: 3 }, // 숫자가 아님
      { id: '3:d', document_index: 3, field: 'd', page: 6 },
      { id: '9:e', document_index: 9, field: 'e' },
      { id: 'x', field: 'x' },
      null,
      'finding',
      { id: '0:f', document_index: 0, field: 'f', page: 4 },
    ]);
    // 서류 index 3 은 서류 목록의 두 번째 → D2(계약 index 는 서류 id doc-3 에 남는다)
    expect(a.findings.map((f) => [f.id, f.docId, f.live?.id])).toEqual([
      ['D1-01', 'doc-0', '0:a'],
      ['D2-01', 'doc-3', '3:d'],
      ['D1-02', 'doc-0', '0:f'],
    ]);
  });

  it('index 에 빈 번호가 있어도(0 · 2 · 5) 번호는 서류 목록 순번 D1 · D2 · D3 — 계약 index 는 source.index · 서류 id 에', () => {
    const a = doneWith({
      documents: [
        { index: 5, type: 'debt_transaction', page_start: 3, page_end: 3 },
        { index: 0, type: 'loan_application', page_start: 1, page_end: 1 },
        { index: 2, type: 'consent_form', page_start: 2, page_end: 2 },
      ],
      findings: [
        { id: '5:a', document_index: 5, field: 'a', page: 3, boxes: [box(0.1, 0.1)] },
        { id: '0:b', document_index: 0, field: 'b', page: 1, boxes: [box(0.1, 0.1)] },
        { id: '2:c', document_index: 2, field: 'c', page: 2, boxes: [box(0.1, 0.1)] },
        { id: '5:d', document_index: 5, field: 'd', page: 3 },
      ],
    });
    expect(a.docs.map((d) => [d.id, d.source?.index])).toEqual([
      ['doc-0', 0],
      ['doc-2', 2],
      ['doc-5', 5],
    ]);
    expect(a.findings.map((f) => [f.id, f.docId, f.anchors])).toEqual([
      ['D3-01', 'doc-5', ['D3-01#1']],
      ['D1-01', 'doc-0', ['D1-01#1']],
      ['D2-01', 'doc-2', ['D2-01#1']],
      ['D3-02', 'doc-5', []],
    ]);
  });

  it('큰 정수 index(9007199254740991 · 9007199254740992)에서도 항목 번호 · 위치 ID 가 서로 다르다', () => {
    const indices = [Number.MAX_SAFE_INTEGER, Number.MAX_SAFE_INTEGER + 1];
    expect(indices).toEqual([9007199254740991, 9007199254740992]);
    // 검증 보고서 V-T1-1 의 재현과 같은 입력
    const a = doneWith({
      documents: indices.map((index, i) => ({ index, type: 'loan_application', page_start: i + 1, page_end: i + 1 })),
      findings: indices.map((document_index, i) => ({ document_index, field: `field_${i}`, page: i + 1, boxes: [[{ x: 0.1, y: 0.1 }, { x: 0.2, y: 0.2 }]] })),
    });
    expect(a.docs.map((d) => d.id)).toEqual(['doc-9007199254740991', 'doc-9007199254740992']);
    expect(a.docs.map((d) => d.title)).toEqual(['대출신청서', '대출신청서 2']);
    expect(a.findings.map((f) => [f.id, f.docId, f.anchors])).toEqual([
      ['D1-01', 'doc-9007199254740991', ['D1-01#1']],
      ['D2-01', 'doc-9007199254740992', ['D2-01#1']],
    ]);
    const anchors = a.findings.flatMap((f) => f.anchors);
    expect(new Set(a.findings.map((f) => f.id)).size).toBe(2);
    expect(new Set(anchors).size).toBe(2);
  });

  it('계약 id 가 겹치고 서류마다 항목이 여럿이어도 항목 번호 · 위치 ID 는 모두 다르다', () => {
    const findings = [0, 3].flatMap((docIndex) =>
      Array.from({ length: 4 }, (_, k) => ({
        id: `${docIndex}:applicant_name`, // 같은 계약 id 반복
        document_index: docIndex,
        field: 'applicant_name',
        page: docIndex === 0 ? 3 + (k % 3) : 6,
        boxes: [box(0.1, 0.1), box(0.3, 0.1), box(0.5, 0.1)],
      })),
    );
    const a = withFindings(findings);
    const ids = a.findings.map((f) => f.id);
    expect(ids).toEqual(['D1-01', 'D1-02', 'D1-03', 'D1-04', 'D2-01', 'D2-02', 'D2-03', 'D2-04']);
    expect(new Set(a.findings.map((f) => f.live?.id))).toEqual(new Set(['0:applicant_name', '3:applicant_name']));
    const anchors = a.findings.flatMap((f) => f.anchors);
    expect(anchors).toHaveLength(24);
    expect(new Set(anchors).size).toBe(24);
    for (const f of a.findings) expect(f.boxes?.map((b) => b.a)).toEqual(f.anchors);
  });

  it('순번은 두 자리(D1-10), 100번째부터는 세 자리 — 모두 겹치지 않는다', () => {
    const many = Array.from({ length: 100 }, (_, i) => ({ id: `0:f${i}`, document_index: 0, field: `f${i}`, page: 3 }));
    const ids = withFindings(many).findings.map((f) => f.id);
    expect(ids.slice(0, 2)).toEqual(['D1-01', 'D1-02']);
    expect(ids[9]).toBe('D1-10');
    expect(ids[99]).toBe('D1-100');
    expect(new Set(ids).size).toBe(100);
  });

  it('쪽 — 파일 기준 → 서류 안 쪽, 범위 밖 · null · 소수 · 문자열이면 1쪽 · 위치 없음(상자를 쓰지 않음)', () => {
    const cases: [unknown, number, number][] = [
      [3, 1, 1],
      [4, 2, 1],
      [5, 3, 1],
      [2, 1, 0],
      [6, 1, 0],
      [null, 1, 0],
      [undefined, 1, 0],
      [4.5, 1, 0],
      ['4', 1, 0],
    ];
    const a = withFindings(cases.map(([page], i) => ({ id: `0:p${i}`, document_index: 0, field: `p${i}`, page, boxes: [box(0.1, 0.1)] })));
    expect(a.findings.map((f) => [f.page, f.anchors.length, f.boxes?.length])).toEqual(cases.map(([, page, n]) => [page, n, n]));
  });

  it('상자 검사 — 꼭짓점 2개 이상 · 모든 x·y 가 유한한 수, 값은 자르지 않음, 위치 ID 는 유효한 상자만 차례로', () => {
    const a = withFindings([
      {
        id: '0:b',
        document_index: 0,
        field: 'b',
        page: 3,
        boxes: [
          box(0.1, 0.1),
          [{ x: 0.1, y: 0.2 }], // 꼭짓점 1개
          [{ x: '0.1', y: 0.2 }, { x: 0.3, y: 0.2 }], // 문자열
          [{ x: Number.NaN, y: 0.2 }, { x: 0.3, y: 0.2 }],
          [{ x: Number.POSITIVE_INFINITY, y: 0.2 }, { x: 0.3, y: 0.2 }],
          [{ x: 0.1, y: 0.2 }, null],
          { x: 0.1, y: 0.2 },
          'box',
          null,
          [{ x: -0.05, y: 0.9 }, { x: 1.2, y: 1.01 }], // 꼭짓점 2개 · 범위 밖 값 그대로
        ],
      },
      { id: '0:c', document_index: 0, field: 'c', page: 3, boxes: 'not-array' },
      { id: '0:d', document_index: 0, field: 'd', page: 3, boxes: [[{ x: 0.1 }, { x: 0.2, y: 0.3 }]] },
    ]);
    const [b, c, d] = a.findings;
    expect(b.anchors).toEqual(['D1-01#1', 'D1-01#2']);
    expect(b.boxes).toEqual([
      { a: 'D1-01#1', points: box(0.1, 0.1) },
      { a: 'D1-01#2', points: [{ x: -0.05, y: 0.9 }, { x: 1.2, y: 1.01 }] },
    ]);
    expect(c.anchors).toEqual([]);
    expect(c.boxes).toEqual([]);
    expect(d.anchors).toEqual([]);
  });

  it('상자 검사 — 쪽(0~1)과 전혀 겹치지 않는 상자는 버리고, 위치 ID 는 남은 상자만 차례로(그린 상자와 같다)', () => {
    const a = withFindings([
      {
        id: '0:e',
        document_index: 0,
        field: 'e',
        page: 3,
        boxes: [
          [{ x: 2, y: 2 }, { x: 3, y: 3 }], // 쪽 밖(오른쪽 아래)
          box(0.1, 0.1),
          [{ x: -0.5, y: 0.2 }, { x: -0.1, y: 0.3 }], // 쪽 밖(왼쪽)
          [{ x: 0.9, y: 0.95 }, { x: 1.4, y: 1.2 }], // 일부만 걸침 — 남긴다
        ],
      },
      { id: '0:f', document_index: 0, field: 'f', page: 3, boxes: [[{ x: 1.1, y: 0.1 }, { x: 1.3, y: 0.2 }]] },
    ]);
    const [e, f] = a.findings;
    expect(e.anchors).toEqual(['D1-01#1', 'D1-01#2']);
    expect(e.boxes!.map((b) => b.points)).toEqual([box(0.1, 0.1), [{ x: 0.9, y: 0.95 }, { x: 1.4, y: 1.2 }]]);
    expect(f.anchors).toEqual([]);
    expect(f.boxes).toEqual([]);
  });

  it('분류 대체값 — 목록 밖 정보 종류 → 기타 개인정보, 주체 → 기타, 노출 → 전체 노출(ai 도 같은 값)', () => {
    const a = withFindings([
      { id: '0:x', document_index: 0, field: 'x', category: '건강정보', subject: '배우자', exposure: '일부 노출', page: 3 },
      { id: '0:y', document_index: 0, field: 'y', category: '계좌번호', subject: '보증인', exposure: '마스킹됨', page: 3 },
      { id: '0:z', document_index: 0, field: 'z', category: 7, subject: null, page: 3 },
    ]);
    expect(a.findings.map((f) => [f.cat, f.subject, f.exposure])).toEqual([
      ['기타 개인정보', '기타', '전체 노출'],
      ['계좌번호', '보증인', '마스킹됨'],
      ['기타 개인정보', '기타', '전체 노출'],
    ]);
    for (const f of a.findings) expect(f.ai).toEqual({ cat: f.cat, subject: f.subject, exposure: f.exposure });
  });

  it('이름 · 마스킹 · 원문 — label 이 비면 field, 둘 다 비면 이름 없는 항목, 문자열이 아니면 빈 값', () => {
    const a = withFindings([
      { id: '0:a', document_index: 0, field: 'applicant_name', label: '  ', masked: 3, value: null, page: 3 },
      { id: '0:b', document_index: 0, label: null, page: 3 },
      { document_index: 0, field: 'f', label: '성명', masked: '홍*동', value: '홍길동', page: 3 },
    ]);
    expect(a.findings.map((f) => [f.label, f.masked, f.evidence, f.live?.value, f.live?.id, f.live?.field])).toEqual([
      ['applicant_name', '', '', '', '0:a', 'applicant_name'],
      ['이름 없는 항목', '', '', '', '0:b', ''],
      ['성명', '홍*동', '홍길동', '홍길동', '', 'f'],
    ]);
  });

  it('항목 위험등급 — risk_source 가 workflow 일 때만 받은 값, 그 밖은 미평가(사유 없으면 고정 문구)', () => {
    const a = withFindings([
      { document_index: 0, risk: 'high', risk_source: null, page: 3 },
      { document_index: 0, risk: 'high', page: 3 },
      { document_index: 0, risk: 'high', risk_source: 'model', page: 3 },
      { document_index: 0, risk: 'medium', risk_source: 'workflow', page: 3 },
      { document_index: 0, risk: 'low', risk_source: 'workflow', risk_reason: ' 일부만 보입니다. ', page: 3 },
      { document_index: 0, risk: 'critical', risk_source: 'workflow', page: 3 },
      { document_index: 0, risk: 'toString', risk_source: 'workflow', page: 3 },
      { document_index: 0, risk: 'unrated', risk_source: null, risk_reason: '판정 근거 부족', page: 3 },
    ]);
    expect(a.findings.map((f) => [f.risk, f.reason, f.live?.riskSource])).toEqual([
      ['unrated', UNRATED_REASON, null],
      ['unrated', UNRATED_REASON, null],
      ['unrated', UNRATED_REASON, null],
      ['medium', '', 'workflow'],
      ['low', '일부만 보입니다.', 'workflow'],
      ['unrated', UNRATED_REASON, 'workflow'],
      ['unrated', UNRATED_REASON, 'workflow'],
      ['unrated', '판정 근거 부족', null],
    ]);
  });

  it('live — 목록 밖 mapping_status → unknown, confidence → null', () => {
    const a = withFindings([
      { document_index: 0, mapping_status: 'needs_review', confidence: 'low', page: 3 },
      { document_index: 0, mapping_status: 'OK', confidence: 0.9, page: 3 },
      { document_index: 0, page: 3 },
    ]);
    expect(a.findings.map((f) => [f.live?.mappingStatus, f.live?.confidence])).toEqual([
      ['needs_review', 'low'],
      ['unknown', null],
      ['unknown', null],
    ]);
  });
});

describe('공통 계약이 아니면 전과 같다(파일 행 docs · 빈 findings · detailReady false)', () => {
  const fileRow = (status: string, error = '') => [{ ...FILE_ROW, status, error }];

  it('옛 형식(summary · stages 만) — 위험도는 summary, 줄 목록 없음', () => {
    const a = doneWith(doneResult());
    expect(a.docs).toEqual(fileRow('done'));
    expect(a.findings).toEqual([]);
    expect(a.raw?.detailReady).toBe(false);
    expect(a.raw?.overall).toBeNull();
    expect(a.risk).toBe('high');
    expect([a.riskReasons, a.recs]).toEqual([[], []]);
  });

  it('대기 · 분석 중 · 실패 · 일부 실패 — 계약 결과가 있어도 파일 행', () => {
    for (const [status, docStatus] of [
      ['queued', 'queued'],
      ['running', 'running'],
      ['failed', 'failed'],
      ['partial', 'failed'],
    ] as const) {
      const a = toAnalysis(analysisOut({ status, error: docStatus === 'failed' ? '실패' : null, result: contractResult() }));
      expect(a.raw?.detailReady).toBe(false);
      expect(a.docs).toEqual(fileRow(docStatus, docStatus === 'failed' ? '실패' : ''));
      expect(a.findings).toEqual([]);
    }
  });

  it('서류 0개 · 유효한 서류 없음 · documents 배열 아님 · findings 배열 아님', () => {
    const withoutFindings = contractResult();
    delete withoutFindings.findings;
    const variants: Record<string, unknown>[] = [
      { ...contractResult(), documents: [] },
      { ...contractResult(), documents: [{ index: '0', page_start: 1, page_end: 1 }, null] },
      { ...contractResult(), documents: 'documents' },
      { ...contractResult(), documents: { 0: {} } },
      { ...contractResult(), findings: null },
      { ...contractResult(), findings: { 0: {} } },
      withoutFindings,
    ];
    for (const result of variants) {
      const a = doneWith(result);
      expect(a.raw?.detailReady).toBe(false);
      expect(a.docs).toEqual(fileRow('done'));
      expect(a.findings).toEqual([]);
    }
  });

  it('모양이 깨진 값에도 예외 없이', () => {
    const broken: unknown[] = [
      null,
      'result',
      42,
      [],
      [contractResult()],
      { documents: null, findings: null, overall: null },
      { documents: [{}], findings: [{}], overall: 'overall' },
      { documents: [{ index: 0, page_start: 1, page_end: 1 }], findings: [{ document_index: 0, boxes: [[null, null]], page: {} }], overall: [] },
      {
        documents: [{ index: 0, page_start: 1, page_end: 1, type: 5, kind: [], other_guide: 3, validation: {} }],
        findings: [7, [], { document_index: 0, label: {}, category: [], risk: {}, risk_source: [], risk_reason: 9 }],
        overall: { level: 3, text: [], next_stage: {}, next_text: null },
      },
    ];
    for (const result of broken) {
      expect(() => doneWith(result)).not.toThrow();
    }
    const a = doneWith(broken[8]);
    expect(a.raw?.detailReady).toBe(true);
    expect(a.docs[0]).toMatchObject({ title: '분류 없는 서류', source: { type: '', kind: 'extracted', otherGuide: '', validation: '' } });
    expect(a.findings).toHaveLength(1);
    expect(a.findings[0]).toMatchObject({ id: 'D1-01', label: '이름 없는 항목', cat: '기타 개인정보', risk: 'unrated', reason: UNRATED_REASON, anchors: [] });
    expect(a.raw?.overall).toEqual({ level: '', text: '', nextStage: '', nextText: '' });
    expect(a.risk).toBe('unrated'); // overall.level 이 문자열이 아니고 summary 도 없다
    expect([a.riskReasons, a.recs]).toEqual([[], []]);
  });
});
