/* 목록(GET /analyses) 항목 → Analysis — 상세 매핑(toAnalysis)과 따로 읽는 가벼운 항목. */
import { describe, expect, it } from 'vitest';
import { readAnalysisList, toListAnalysis } from './mapping';
import { listItemOut } from './testing';

const must = (item: unknown) => {
  const a = toListAnalysis(item);
  if (!a) throw new Error('항목을 읽지 못함');
  return a;
};

describe('목록 항목 → Analysis — 키 하나하나', () => {
  it('완료 항목 — 번호 · 이름 · 시각 · 상태 · 위험 · 검토 · 문서 · 빈 값 · raw', () => {
    const a = must(
      listItemOut({
        id: 'cd34ab12-0000-4000-8000-000000000000',
        name: '실제 확인',
        status: 'done',
        error: null,
        created_at: '2026-11-02T05:10:00.123456+00:00',
        updated_at: '2026-11-02T05:12:34.900000+00:00',
        started_at: '2026-11-02T05:10:01.5+00:00',
        risk_level: '상',
        review: 'needed',
      }),
    );
    expect(a).toEqual({
      id: 'cd34ab12-0000-4000-8000-000000000000',
      code: 'DG-20261102-CD34',
      name: '실제 확인',
      submittedAt: '2026-11-02 14:10',
      analyzedAt: '2026-11-02 14:12',
      status: 'done',
      risk: 'high',
      review: 'needed',
      docs: [{ id: 'f1', title: 'iMASK_smoke_bundle.pdf', name: 'iMASK_smoke_bundle.pdf', ext: 'PDF', size: 322053, status: 'done', error: '', pages: null }],
      findings: [],
      items: [],
      links: [],
      history: [],
      memo: '',
      memoAt: '',
      riskReasons: [],
      recs: [],
      limits: '',
      reviewer: '',
      reviewedAt: '',
      completionNote: '',
      demoQueued: false,
      retrying: false,
      raw: {
        result: null,
        file: { id: '', name: 'iMASK_smoke_bundle.pdf', mime: 'application/pdf', size: 322053 },
        detailReady: false,
        reviewable: false,
        overall: null,
        decision: null,
        bundleCheck: null,
        error: '',
        jobId: '',
        upstageStatus: '',
        pollError: '',
        createdAt: '2026-11-02T05:10:00.123456+00:00',
        updatedAt: '2026-11-02T05:12:34.900000+00:00',
        startedAt: '2026-11-02T05:10:01.5+00:00',
      },
    });
  });

  it('실패 항목 — 오류는 raw.error 와 문서 오류, 분석 시각은 updated_at', () => {
    const a = must(listItemOut({ status: 'failed', error: '업로드된 파일을 찾을 수 없습니다.' }));
    expect(a.status).toBe('failed');
    expect(a.raw?.error).toBe('업로드된 파일을 찾을 수 없습니다.');
    expect(a.docs[0]).toMatchObject({ status: 'failed', error: '업로드된 파일을 찾을 수 없습니다.' });
    expect(a.analyzedAt).toBe('2026-11-02 14:10');
    expect(a.review).toBe('none');
  });

  it('대기 · 분석 중 — 분석 시각 없음, 모르는 상태는 queued', () => {
    expect(must(listItemOut({ status: 'running' }))).toMatchObject({ status: 'running', analyzedAt: '' });
    expect(must(listItemOut({ status: 'queued' }))).toMatchObject({ status: 'queued', analyzedAt: '' });
    expect(must(listItemOut({ status: '이상한 값' })).status).toBe('queued');
  });

  it('검토 상태 — done · needed 는 그대로, none · 모르는 값 · 빠짐은 none', () => {
    expect(must(listItemOut({ status: 'done', review: 'done' })).review).toBe('done');
    expect(must(listItemOut({ status: 'done', review: 'needed' })).review).toBe('needed');
    expect(must(listItemOut({ status: 'done', review: 'none' })).review).toBe('none');
    expect(must(listItemOut({ status: 'done', review: 'DONE' })).review).toBe('none');
    expect(must({ ...listItemOut({ status: 'done' }), review: undefined }).review).toBe('none');
    expect(must({ ...listItemOut({ status: 'done' }), review: 1 }).review).toBe('none');
  });

  it('위험등급 — 상 · 중 · 하 · 검토 필요 → high · medium · low · review, 그 밖 · null → unrated', () => {
    expect(must(listItemOut({ risk_level: '상' })).risk).toBe('high');
    expect(must(listItemOut({ risk_level: '중' })).risk).toBe('medium');
    expect(must(listItemOut({ risk_level: '하' })).risk).toBe('low');
    expect(must(listItemOut({ risk_level: '검토 필요' })).risk).toBe('review');
    expect(must(listItemOut({ risk_level: '미평가' })).risk).toBe('unrated');
    expect(must(listItemOut({ risk_level: null })).risk).toBe('unrated');
    expect(must({ ...listItemOut(), risk_level: 3 }).risk).toBe('unrated');
  });

  it('문서 — 분석 안에서 겹치지 않는 id(f1 · f2 …), 객체가 아닌 행은 뺀다, 목록이 아니면 []', () => {
    const a = must({
      ...listItemOut(),
      documents: [
        { filename: '묶음.pdf', size_bytes: 100, mime_type: 'application/pdf' },
        null,
        '글',
        { filename: '사진.JPEG', size_bytes: 'x', mime_type: '' },
      ],
    });
    expect(a.docs.map((d) => [d.id, d.name, d.ext, d.size])).toEqual([
      ['f1', '묶음.pdf', 'PDF', 100],
      ['f2', '사진.JPEG', 'JPG', 0],
    ]);
    expect(new Set(a.docs.map((d) => d.id)).size).toBe(a.docs.length);
    expect(must({ ...listItemOut(), documents: '없음' }).docs).toEqual([]);
    expect(must({ ...listItemOut(), documents: [] }).raw?.file).toBeNull();
  });

  it('시작 시각 — started_at 원문, null · 빠짐 · 글이 아님 → \'\'', () => {
    expect(must(listItemOut({ started_at: '2026-11-04T01:00:00Z' })).raw?.startedAt).toBe('2026-11-04T01:00:00Z');
    expect(must(listItemOut({ started_at: null })).raw?.startedAt).toBe('');
    expect(must({ ...listItemOut(), started_at: undefined }).raw?.startedAt).toBe('');
    expect(must({ ...listItemOut(), started_at: 7 }).raw?.startedAt).toBe('');
  });

  it('객체가 아니거나 id 가 비면 null', () => {
    expect(toListAnalysis(null)).toBeNull();
    expect(toListAnalysis('a')).toBeNull();
    expect(toListAnalysis([listItemOut()])).toBeNull();
    expect(toListAnalysis({ ...listItemOut(), id: '' })).toBeNull();
    expect(toListAnalysis({ ...listItemOut(), id: 5 })).toBeNull();
  });
});

describe('목록 응답 → 목록', () => {
  it('서버 순서 그대로 — 다시 정렬하지 않는다', () => {
    const ids = ['bbbb0000-0000-4000-8000-000000000000', 'aaaa0000-0000-4000-8000-000000000000', 'cccc0000-0000-4000-8000-000000000000'];
    const list = readAnalysisList({
      analyses: [
        listItemOut({ id: ids[0], created_at: '2026-11-01T00:00:00Z' }),
        listItemOut({ id: ids[1], created_at: '2026-11-03T00:00:00Z' }),
        listItemOut({ id: ids[2], created_at: '2026-11-02T00:00:00Z' }),
      ],
    });
    expect(list?.map((a) => a.id)).toEqual(ids);
  });

  it('항목 하나가 깨지면 그 항목만 빠진다', () => {
    const list = readAnalysisList({ analyses: [listItemOut({ id: 'a1' }), null, { name: 'id 없음' }, 3, listItemOut({ id: 'a2' })] });
    expect(list?.map((a) => a.id)).toEqual(['a1', 'a2']);
  });

  it('응답 모양이 틀리면 null(객체 아님 · analyses 가 배열 아님)', () => {
    expect(readAnalysisList(null)).toBeNull();
    expect(readAnalysisList(undefined)).toBeNull();
    expect(readAnalysisList([])).toBeNull();
    expect(readAnalysisList('[]')).toBeNull();
    expect(readAnalysisList({})).toBeNull();
    expect(readAnalysisList({ analyses: {} })).toBeNull();
    expect(readAnalysisList({ analyses: null })).toBeNull();
    expect(readAnalysisList({ analyses: [] })).toEqual([]);
  });
});
