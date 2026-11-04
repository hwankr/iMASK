/* 경과 · 걸린 시간의 시작 시각 — started_at(마지막으로 시작한 시각), 없거나 못 읽으면 created_at. */
import { describe, expect, it } from 'vitest';
import { doneResult } from '@/services/api/testing';
import { elapsedText, summaryRows, timingStart } from './liveModel';

const CREATED = '2026-11-02T05:10:00.000000+00:00';
const STARTED = '2026-11-02T06:00:00.123456+00:00';
const UPDATED = '2026-11-02T06:01:05.000000+00:00';

describe('timingStart — 경과 · 걸린 시간을 잴 시작 시각', () => {
  it('startedAt 이 있으면 그 값', () => {
    expect(timingStart({ startedAt: STARTED, createdAt: CREATED })).toBe(STARTED);
  });

  it('startedAt 이 없으면(빈 값 · null · 빠짐) createdAt', () => {
    expect(timingStart({ startedAt: '', createdAt: CREATED })).toBe(CREATED);
    expect(timingStart({ startedAt: null, createdAt: CREATED })).toBe(CREATED);
    expect(timingStart({ createdAt: CREATED })).toBe(CREATED);
  });

  it('startedAt 을 읽을 수 없으면 createdAt', () => {
    expect(timingStart({ startedAt: '어제', createdAt: CREATED })).toBe(CREATED);
    expect(timingStart({ startedAt: '   ', createdAt: CREATED })).toBe(CREATED);
  });
});

describe('진행 화면 경과 — startedAt 부터', () => {
  const now = Date.parse('2026-11-02T06:02:30Z');

  it('다시 분석한 분석 — 요청 시각이 아니라 다시 시작한 시각부터 2:29', () => {
    expect(elapsedText(timingStart({ startedAt: STARTED, createdAt: CREATED }), now)).toBe('2:29');
  });

  it('시작 시각이 없거나 못 읽으면 요청 시각부터 52:30', () => {
    expect(elapsedText(timingStart({ startedAt: '', createdAt: CREATED }), now)).toBe('52:30');
    expect(elapsedText(timingStart({ startedAt: 'x', createdAt: CREATED }), now)).toBe('52:30');
  });
});

describe('요약의 걸린 시간 — startedAt(없으면 createdAt)부터 updatedAt 까지', () => {
  const took = (startedAt: string | undefined) =>
    summaryRows(doneResult(), { createdAt: CREATED, startedAt, updatedAt: UPDATED, jobId: 'job_1' }).find((r) => r.key === 'took')?.value;

  it('startedAt 있음 → 1분 5초', () => {
    expect(took(STARTED)).toBe('1분 5초');
  });

  it('startedAt 없음 · 못 읽음 → createdAt 부터 51분 5초', () => {
    expect(took('')).toBe('51분 5초');
    expect(took(undefined)).toBe('51분 5초');
    expect(took('어제')).toBe('51분 5초');
  });
});
