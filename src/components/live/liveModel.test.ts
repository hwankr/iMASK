import { describe, expect, it } from 'vitest';
import { doneResult } from '@/services/api/testing';
import {
  LIVE_MAX_FILE_BYTES,
  MSG_BAD_TYPE,
  MSG_EMPTY_FILE,
  MSG_ONE_FILE_ONLY,
  MSG_PICK_FILE,
  MSG_TOO_LARGE,
  MSG_TYPE_MISMATCH,
  analysisNameFor,
  checkLiveFiles,
  docTypeName,
  durationText,
  elapsedText,
  fileLine,
  isPolling,
  nextStageTitle,
  progressSteps,
  riskText,
  stageLabel,
  stageRows,
  stageStatusText,
  statusAnnouncement,
  summaryRows,
  upstageStatusText,
} from './liveModel';

const pdf = (name = '묶음.pdf', size = 1000, type = 'application/pdf') => ({ name, size, type });

describe('파일 검사', () => {
  it('PDF·PNG·JPEG 하나, 20MB 이하면 통과', () => {
    expect(checkLiveFiles([pdf()])).toEqual({ ok: true });
    expect(checkLiveFiles([pdf('스캔.PNG', 10, 'image/png')])).toEqual({ ok: true });
    expect(checkLiveFiles([pdf('사진.jpeg', 10, 'image/jpeg')])).toEqual({ ok: true });
    expect(checkLiveFiles([pdf('사진.jpg', 10, '')])).toEqual({ ok: true }); // 브라우저가 형식을 비워 둔 경우
    expect(checkLiveFiles([pdf('a.pdf', LIVE_MAX_FILE_BYTES)])).toEqual({ ok: true });
  });

  it('개수 · 확장자 · 형식 · 크기 위반은 한국어 오류', () => {
    expect(checkLiveFiles([])).toEqual({ ok: false, error: MSG_PICK_FILE });
    expect(checkLiveFiles([pdf(), pdf('b.pdf')])).toEqual({ ok: false, error: MSG_ONE_FILE_ONLY });
    expect(checkLiveFiles([pdf('메모.txt', 10, 'text/plain')])).toEqual({ ok: false, error: MSG_BAD_TYPE });
    expect(checkLiveFiles([pdf('확장자없음', 10, 'application/pdf')])).toEqual({ ok: false, error: MSG_BAD_TYPE });
    expect(checkLiveFiles([pdf('가짜.pdf', 10, 'image/png')])).toEqual({ ok: false, error: MSG_TYPE_MISMATCH });
    expect(checkLiveFiles([pdf('빈.pdf', 0)])).toEqual({ ok: false, error: MSG_EMPTY_FILE });
    expect(checkLiveFiles([pdf('큰.pdf', LIVE_MAX_FILE_BYTES + 1)])).toEqual({ ok: false, error: MSG_TOO_LARGE });
    expect(MSG_TOO_LARGE).toBe('파일은 20MB 이하여야 합니다.');
  });

  it('파일 줄 · 분석명(비면 파일 이름, 60자)', () => {
    expect(fileLine({ name: '묶음.pdf', size: 322053 })).toBe('묶음.pdf · 315KB');
    expect(analysisNameFor('  합성 묶음 ', 'a.pdf')).toBe('합성 묶음');
    expect(analysisNameFor('   ', 'iMASK_smoke_bundle.pdf')).toBe('iMASK_smoke_bundle.pdf');
    expect(analysisNameFor('', 'ㄱ'.repeat(70) + '.pdf')).toHaveLength(60);
  });
});

describe('진행 단계 · 폴링 · 시간', () => {
  it('진행 단계 — 지금 단계 앞은 끝남', () => {
    expect(progressSteps(null).map((s) => s.state)).toEqual(['todo', 'todo', 'todo']);
    expect(progressSteps('upload').map((s) => [s.step, s.state])).toEqual([
      ['create', 'done'],
      ['upload', 'current'],
      ['start', 'todo'],
    ]);
    expect(progressSteps('start').map((s) => s.label)).toEqual(['분석 건 만드는 중', '파일 올리는 중', '분석 시작 중']);
  });

  it('대기 · 분석 중에만 폴링', () => {
    expect(isPolling('queued')).toBe(true);
    expect(isPolling('running')).toBe(true);
    for (const s of ['done', 'failed', 'partial', undefined, null, '']) expect(isPolling(s)).toBe(false);
  });

  it('경과 m:ss · 걸린 시간', () => {
    const from = '2026-11-02T05:10:00.123456+00:00';
    const base = Date.UTC(2026, 10, 2, 5, 10, 0, 123);
    expect(elapsedText(from, base + 65_000)).toBe('1:05');
    expect(elapsedText(from, base + 600)).toBe('0:00');
    expect(elapsedText(from, base - 5000)).toBe('0:00');
    expect(elapsedText('', base)).toBe('');
    expect(durationText(from, '2026-11-02T05:10:34.900000+00:00')).toBe('35초');
    expect(durationText(from, '2026-11-02T05:12:05.123+00:00')).toBe('2분 5초');
    expect(durationText(from, '2026-11-02T05:13:00.123+00:00')).toBe('3분');
    expect(durationText(from, '')).toBe('');
    expect(durationText('2026-11-02T06:00:00Z', from)).toBe('');
  });

  it('상태 변화 알림 — 처음 · 같으면 없음', () => {
    expect(statusAnnouncement(null, 'running')).toBe('');
    expect(statusAnnouncement('running', 'running')).toBe('');
    expect(statusAnnouncement('queued', 'running')).toBe('분석을 시작했습니다.');
    expect(statusAnnouncement('running', 'done')).toContain('끝났습니다');
    expect(statusAnnouncement('running', 'failed')).toBe('분석에 실패했습니다.');
  });
});

describe('라벨', () => {
  it('서류 종류 코드 → 한국어 이름, 모르는 코드는 그대로', () => {
    expect(['loan_application', 'consent_form', 'income_proof', 'power_of_attorney', 'debt_transaction', 'Other', 'other'].map(docTypeName)).toEqual([
      '대출신청서',
      '동의서',
      '소득 증빙',
      '위임장',
      '채무내역',
      '기타',
      '기타',
    ]);
    expect(docTypeName('bank_statement')).toBe('bank_statement');
    expect(docTypeName('constructor')).toBe('constructor');
  });

  it('위험도 · Upstage 상태 · 단계 상태 문구', () => {
    expect(riskText('상')).toBe('상');
    expect(riskText('검토 필요')).toBe('검토 필요');
    expect(riskText('')).toBe('판정 없음');
    expect(riskText(null)).toBe('판정 없음');
    expect(upstageStatusText('in_progress')).toBe('진행 중(in_progress)');
    expect(upstageStatusText('')).toBe('아직 확인 전');
    expect(upstageStatusText('cancelled')).toBe('cancelled');
    expect(stageStatusText('completed')).toBe('완료');
    expect(stageStatusText('failed')).toBe('실패');
    expect(stageStatusText(undefined)).toBe('');
  });

  it('단계 이름 — key, 없으면 name', () => {
    expect(stageLabel({ key: '민감정보_추출', name: 'Information Extract - 민감정보_추출' })).toBe('민감정보_추출');
    expect(stageLabel({ key: null, name: 'Instruct - 권장_조치' })).toBe('Instruct - 권장_조치');
    expect(stageLabel({})).toBe('이름 없는 단계');
    expect(stageLabel('x')).toBe('이름 없는 단계');
  });
});

describe('결과', () => {
  it('요약 줄 — 서류 6(종류 이름) · 추출 5 · 위험도 상 · 마지막 단계 · 기타 · 걸린 시간 · 작업 번호', () => {
    const rows = summaryRows(doneResult(), { createdAt: '2026-11-02T05:10:00Z', updatedAt: '2026-11-02T05:10:34Z', jobId: 'job_abc' });
    const byKey = Object.fromEntries(rows.map((r) => [r.key, r.value]));
    expect(byKey.docs).toBe('6개 — 대출신청서 · 동의서 · 소득 증빙 · 위임장 · 채무내역 · 기타');
    expect(byKey.extracted).toBe('5개');
    expect(byKey.risk).toBe('상');
    expect(byKey.final).toBe('권장_조치');
    expect(byKey.other).toBe('1개');
    expect(byKey.took).toBe('34초');
    expect(byKey.job).toBe('job_abc');
    expect(rows.map((r) => r.label)).toEqual(['분류한 서류', '정보를 추출한 서류', '위험도', '마지막 단계', '기타 서류', '걸린 시간', 'Upstage 작업 번호']);
  });

  it('요약이 없거나 모양이 다르면 예외 없이 빈 값', () => {
    const rows = summaryRows(null, { createdAt: '', updatedAt: '', jobId: '' });
    expect(rows.find((r) => r.key === 'risk')?.value).toBe('판정 없음');
    expect(rows.find((r) => r.key === 'docs')?.value).toBe('읽지 못함');
    expect(rows.find((r) => r.key === 'took')?.value).toBe('-');
    const partial = summaryRows({ summary: { document_count: null, document_types: null, risk_level: null } }, { createdAt: '', updatedAt: '', jobId: '' });
    expect(partial.find((r) => r.key === 'docs')?.value).toBe('읽지 못함');
    expect(partial.find((r) => r.key === 'other')?.value).toBe('없음');
  });

  it('단계 목록 — output 순서, 같은 이름은 (n/전체), contents 는 둘 이상일 때만', () => {
    const rows = stageRows(doneResult());
    expect(rows.map((r) => [r.index, r.label, r.counter, r.status])).toEqual([
      [0, '서류-인식', '', '완료'],
      [1, '민감정보_추출', '(1/2)', '완료'],
      [2, '민감정보_추출', '(2/2)', '완료'],
      [3, 'Instruct - 권장_조치', '', '실패'],
    ]);
    expect(rows[3].failed).toBe(true);
    expect(rows[1].contents).toHaveLength(2);
    expect(rows[0].contents).toBeNull();
    expect(rows[1].data).toEqual({ 성명: '홍길동' });
    expect(rows[0].additionalValues).toBeNull();
    expect(stageRows(null)).toEqual([]);
    expect(stageRows({ stages: 'x' })).toEqual([]);
  });
});

describe('nextStageTitle — 실제 분석 상세 분석 요약의 다음 단계 제목', () => {
  it('권장_조치 · 검토_안내 · 그 밖', () => {
    expect(nextStageTitle('권장_조치')).toBe('권장 조치');
    expect(nextStageTitle(' 검토_안내 ')).toBe('검토 안내');
    expect(nextStageTitle('')).toBe('다음 단계');
    expect(nextStageTitle(null)).toBe('다음 단계');
  });
});
