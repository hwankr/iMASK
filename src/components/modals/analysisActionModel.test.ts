/* 삭제 · 다시 분석 문구(BRIEF §5.8 그대로)와 결과 토스트 고르기. */
import { describe, expect, it } from 'vitest';
import { ApiError } from '@/services/api/client';
import {
  DELETE_BODY,
  DELETE_CANCEL,
  DELETE_FAILED_TEXT,
  DELETE_LABEL,
  DELETE_TITLE,
  DELETED_TEXT,
  GONE_TEXT,
  RETRY_LABEL,
  RETRY_STARTED_TEXT,
  deleteFailedText,
  isGoneError,
  retryNotStartedText,
  retryToast,
} from './analysisActionModel';
import { retryFailedText } from './reviewModalModel';

describe('문구 — 정해진 것 그대로', () => {
  it('삭제 · 확인 창 · 토스트 · 다시 분석', () => {
    expect([DELETE_LABEL, DELETE_TITLE, DELETE_BODY, DELETE_CANCEL]).toEqual(['삭제', '이 분석을 지울까요?', '원본 파일과 검토 기록이 함께 지워지며 되돌릴 수 없습니다.', '취소']);
    expect([DELETED_TEXT, DELETE_FAILED_TEXT, GONE_TEXT]).toEqual(['분석을 지웠습니다.', '분석을 지우지 못했습니다. 잠시 후 다시 시도해 주세요.', '이미 지워진 분석입니다.']);
    expect([RETRY_STARTED_TEXT, RETRY_LABEL, retryNotStartedText('이미 분석하고 있습니다.')]).toEqual([
      '다시 분석을 시작했습니다.',
      '다시 분석',
      '다시 분석을 시작하지 못했습니다 · 이미 분석하고 있습니다.',
    ]);
    expect(retryFailedText('손상된 파일')).toBe('다시 분석했지만 실패했습니다 · 손상된 파일'); // 데모 — 그대로
  });
});

describe('retryToast — 다시 분석 결과 → 토스트', () => {
  it('started true → 시작 토스트(성공)', () => {
    expect(retryToast({ ok: true, started: true, message: '' })).toEqual({ text: '다시 분석을 시작했습니다.', kind: 'ok' });
  });

  it('started false + 404(gone) → 이미 지워진 분석(오류)', () => {
    expect(retryToast({ ok: false, started: false, gone: true, message: '분석 건을 찾을 수 없습니다.' })).toEqual({ text: '이미 지워진 분석입니다.', kind: 'error' });
  });

  it('started false + 그 밖 → 시작하지 못함 · 이유(오류)', () => {
    expect(retryToast({ ok: false, started: false, message: '이미 분석하고 있습니다.' })).toEqual({ text: '다시 분석을 시작하지 못했습니다 · 이미 분석하고 있습니다.', kind: 'error' });
    expect(retryToast({ ok: false, started: false, message: '업로드된 파일을 찾을 수 없습니다. 파일을 다시 올려 주세요.' })?.text).toBe(
      '다시 분석을 시작하지 못했습니다 · 업로드된 파일을 찾을 수 없습니다. 파일을 다시 올려 주세요.',
    );
  });

  it('데모(started 없음) → 지금 그대로: 이유가 있으면 \'다시 분석했지만 실패했습니다 · 이유\', 없으면 토스트 없음', () => {
    expect(retryToast({ ok: false, message: '파일이 손상되었습니다.' })).toEqual({ text: '다시 분석했지만 실패했습니다 · 파일이 손상되었습니다.', kind: 'error' });
    expect(retryToast({ ok: false, message: '' })).toBeNull();
    expect(retryToast(null)).toBeNull();
    expect(retryToast(undefined)).toBeNull();
  });
});

describe('삭제 실패 문구', () => {
  it('404(not_found) → 이미 지워진 분석, 그 밖 → 지우지 못함', () => {
    const gone = new ApiError(404, 'not_found', '분석 건을 찾을 수 없습니다.');
    expect(isGoneError(gone)).toBe(true);
    expect(deleteFailedText(gone)).toBe('이미 지워진 분석입니다.');
    expect(deleteFailedText(new ApiError(502, 'server', '원본 파일을 지우지 못했습니다. 잠시 후 다시 시도해 주세요.'))).toBe('분석을 지우지 못했습니다. 잠시 후 다시 시도해 주세요.');
    expect(deleteFailedText(new ApiError(0, 'network', '연결 실패'))).toBe('분석을 지우지 못했습니다. 잠시 후 다시 시도해 주세요.');
    expect(deleteFailedText(new Error('분석 건을 찾을 수 없습니다.'))).toBe('분석을 지우지 못했습니다. 잠시 후 다시 시도해 주세요.');
    expect(isGoneError(null)).toBe(false);
  });
});
