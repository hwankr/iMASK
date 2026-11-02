import { describe, expect, it } from 'vitest';
import { analysisCode, extLabel, parseIsoMs, riskFromLevel, seoulDateTime, toAnalysis, toStatus } from './mapping';
import { analysisOut, documentOut, doneResult } from './testing';

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
