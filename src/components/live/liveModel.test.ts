import { describe, expect, it } from 'vitest';
import { doneResult } from '@/services/api/testing';
import {
  LIVE_MAX_FILES,
  LIVE_MAX_FILE_BYTES,
  MSG_BAD_TYPE,
  MSG_EMPTY_FILE,
  MSG_TOO_LARGE,
  MSG_TOO_MANY,
  MSG_TYPE_MISMATCH,
  addLiveFiles,
  analysisNameFor,
  docTypeName,
  durationText,
  elapsedText,
  fileLine,
  isPolling,
  judgeLevelText,
  liveFileProblem,
  nextStageTitle,
  pickErrorLines,
  progressSteps,
  riskText,
  stageLabel,
  stageRows,
  stageStatusText,
  statusAnnouncement,
  summaryRows,
  upstageStatusText,
} from './liveModel';

const pdf = (name = '묶음.pdf', size = 1000, type = 'application/pdf', lastModified = 1) => ({ name, size, type, lastModified });
const none = { type: 0, mismatch: 0, empty: 0, size: 0, limit: 0 };

describe('파일 검사', () => {
  it('PDF·PNG·JPEG, 20MB 이하면 통과', () => {
    expect(liveFileProblem(pdf())).toBeNull();
    expect(liveFileProblem(pdf('스캔.PNG', 10, 'image/png'))).toBeNull();
    expect(liveFileProblem(pdf('사진.jpeg', 10, 'image/jpeg'))).toBeNull();
    expect(liveFileProblem(pdf('사진.jpg', 10, ''))).toBeNull(); // 브라우저가 형식을 비워 둔 경우
    expect(liveFileProblem(pdf('a.pdf', LIVE_MAX_FILE_BYTES))).toBeNull();
  });

  it('확장자 · 형식 · 빈 파일 · 크기 위반은 이유', () => {
    expect(liveFileProblem(pdf('메모.txt', 10, 'text/plain'))).toBe('type');
    expect(liveFileProblem(pdf('확장자없음', 10, 'application/pdf'))).toBe('type');
    expect(liveFileProblem(pdf('가짜.pdf', 10, 'image/png'))).toBe('mismatch');
    expect(liveFileProblem(pdf('빈.pdf', 0))).toBe('empty');
    expect(liveFileProblem(pdf('큰.pdf', LIVE_MAX_FILE_BYTES + 1))).toBe('size');
    expect(MSG_TOO_LARGE).toBe('파일은 20MB 이하여야 합니다.');
  });

  it('파일 줄', () => {
    expect(fileLine({ name: '묶음.pdf', size: 322053 })).toBe('묶음.pdf · 315KB');
  });
});

describe('파일 담기 — 누적 · 건너뜀 · 한도', () => {
  it('한도는 설정의 maxFiles(10), 한도 문구', () => {
    expect(LIVE_MAX_FILES).toBe(10);
    expect(MSG_TOO_MANY).toBe('파일은 한 번에 10개까지 올릴 수 있습니다.');
  });

  it('고른 순서대로 지금 목록 뒤에 더한다', () => {
    const a = pdf('a.pdf');
    const b = pdf('b.pdf');
    const c = pdf('c.pdf');
    const first = addLiveFiles([], [a, b]);
    expect(first).toEqual({ files: [a, b], added: [a, b], rejected: none, picked: 2 });
    const second = addLiveFiles(first.files, [c]);
    expect(second.files).toEqual([a, b, c]);
    expect(second.added).toEqual([c]);
  });

  it('이름 · 크기 · lastModified 가 모두 같으면 조용히 건너뛴다(같은 고르기 안 포함) — 하나라도 다르면 담는다', () => {
    const a = pdf('a.pdf', 100, 'application/pdf', 5);
    const r = addLiveFiles([a], [pdf('a.pdf', 100, 'application/pdf', 5), pdf('b.pdf'), pdf('b.pdf')]);
    expect(r.files.map((f) => f.name)).toEqual(['a.pdf', 'b.pdf']);
    expect(r.rejected).toEqual(none);
    expect(pickErrorLines(r)).toEqual([]);
    const differ = addLiveFiles([a], [pdf('a.pdf', 101, 'application/pdf', 5), pdf('a.pdf', 100, 'application/pdf', 6), pdf('A.pdf', 100, 'application/pdf', 5)]);
    expect(differ.added).toHaveLength(3);
  });

  it('한도에 닿으면 담지 않고 한도로 센다 — 검사 실패 · 겹침이 먼저', () => {
    const nine = Array.from({ length: 9 }, (_, i) => pdf(`f${i}.pdf`));
    const r = addLiveFiles(nine, [pdf('x.pdf'), pdf('y.pdf'), pdf('메모.txt', 1, 'text/plain'), pdf('f0.pdf'), pdf('z.pdf')]);
    expect(r.files).toHaveLength(10);
    expect(r.added.map((f) => f.name)).toEqual(['x.pdf']);
    expect(r.rejected).toEqual({ ...none, type: 1, limit: 2 });
    expect(addLiveFiles([], Array.from({ length: 11 }, (_, i) => pdf(`g${i}.pdf`))).rejected.limit).toBe(1);
    expect(addLiveFiles([pdf('a.pdf')], [pdf('b.pdf')], 1).rejected.limit).toBe(1);
  });

  it('오류 줄 — 이유마다 한 줄, 고정 순서. 1개를 골랐으면 이유 문구만, 2개 이상이면 개수와 함께', () => {
    expect(pickErrorLines(addLiveFiles([], [pdf('메모.txt', 1, 'text/plain')]))).toEqual([MSG_BAD_TYPE]);
    expect(pickErrorLines(addLiveFiles([], [pdf('빈.pdf', 0)]))).toEqual([MSG_EMPTY_FILE]);
    const mixed = addLiveFiles(
      Array.from({ length: 8 }, (_, i) => pdf(`f${i}.pdf`)),
      [
        pdf('큰.pdf', LIVE_MAX_FILE_BYTES + 1),
        pdf('a.pdf'),
        pdf('메모.txt', 1, 'text/plain'),
        pdf('가짜.pdf', 1, 'image/png'),
        pdf('b.pdf'),
        pdf('빈.pdf', 0),
        pdf('c.pdf'),
        pdf('d.hwp', 1, ''),
        pdf('e.pdf'),
      ],
    );
    expect(mixed.added.map((f) => f.name)).toEqual(['a.pdf', 'b.pdf']);
    expect(pickErrorLines(mixed)).toEqual([
      `2개를 담지 못했습니다. ${MSG_BAD_TYPE}`,
      `1개를 담지 못했습니다. ${MSG_TYPE_MISMATCH}`,
      `1개를 담지 못했습니다. ${MSG_EMPTY_FILE}`,
      `1개를 담지 못했습니다. ${MSG_TOO_LARGE}`,
      `2개를 담지 못했습니다. ${MSG_TOO_MANY}`,
    ]);
    expect(pickErrorLines(addLiveFiles([pdf('a.pdf')], [pdf('b.pdf')], 1))).toEqual([MSG_TOO_MANY]);
  });
});

describe('분석명 — 파일마다 분석 1건', () => {
  it('비면 파일 이름, 하나면 입력한 이름, 여러 개면 "입력 · 파일 이름"', () => {
    expect(analysisNameFor('  합성 묶음 ', 'a.pdf', false)).toBe('합성 묶음');
    expect(analysisNameFor('   ', ' iMASK_smoke_bundle.pdf ', false)).toBe('iMASK_smoke_bundle.pdf');
    expect(analysisNameFor('', 'a.pdf', true)).toBe('a.pdf');
    expect(analysisNameFor(' 합성 묶음 ', ' a.pdf ', true)).toBe('합성 묶음 · a.pdf');
  });

  it('60자(UTF-16 단위)까지 — 자른 끝이 짝 없는 high surrogate 면 하나 더 뺀다', () => {
    expect(analysisNameFor('', 'ㄱ'.repeat(70) + '.pdf', false)).toHaveLength(60);
    expect(analysisNameFor('ㄴ'.repeat(60), 'a.pdf', false)).toBe('ㄴ'.repeat(60));
    expect(analysisNameFor('ㄴ'.repeat(55), 'abcdef.pdf', true)).toBe('ㄴ'.repeat(55) + ' · ab');
    // 59자 + 이모지(서로게이트 쌍) — 60자에서 자르면 high 만 남으므로 59자
    const emoji = '\u{1F600}';
    expect(analysisNameFor('', 'ㄷ'.repeat(59) + emoji + '.pdf', false)).toBe('ㄷ'.repeat(59));
    expect(analysisNameFor('ㄹ'.repeat(57), emoji + '.pdf', true)).toBe('ㄹ'.repeat(57) + ' · ');
    expect(analysisNameFor('', 'ㄷ'.repeat(58) + emoji + '.pdf', false)).toBe('ㄷ'.repeat(58) + emoji);
    // 자르지 않을 때는 그대로(60자 이하)
    expect(analysisNameFor('', 'ㄷ'.repeat(58) + emoji, false)).toBe('ㄷ'.repeat(58) + emoji);
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
    // 분석 요약 머리의 등급 글 — 옆 배지가 같은 등급을 보이면 숨김
    expect(judgeLevelText('검토 필요', '검토 필요')).toBe('');
    expect(judgeLevelText(' 검토 필요 ', '검토 필요')).toBe('');
    expect(judgeLevelText('상', '상')).toBe('');
    expect(judgeLevelText('중', '중')).toBe('');
    expect(judgeLevelText('하', '하')).toBe('');
    expect(judgeLevelText('상', '미평가')).toBe('상');
    expect(judgeLevelText(null, '미평가')).toBe('판정 없음');
    expect(judgeLevelText('검토 필요', '미평가')).toBe('검토 필요');
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
    expect(byKey.final).toBe('권장 조치');
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
