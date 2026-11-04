/* 목록 화면의 진행 중 행 조회 — 고르는 규칙(최대 3개 · 돌아가며 · 진행 중 행 없으면 멈춤 · 다시 불러오기 결정). */
import { describe, expect, it } from 'vitest';
import { LIST_POLL_MAX, activeIds, batchNeedsReload, isActiveStatus, needsListReload, pickPollBatch } from './listPolling';

const row = (id: string, status: string) => ({ id, status: status as 'queued' });

describe('진행 중 행', () => {
  it('대기 · 분석 중만, 목록 순서 그대로', () => {
    expect(['queued', 'running', 'done', 'partial', 'failed'].map(isActiveStatus)).toEqual([true, true, false, false, false]);
    expect(activeIds([row('a', 'done'), row('b', 'running'), row('c', 'failed'), row('d', 'queued')])).toEqual(['b', 'd']);
  });
});

describe('pickPollBatch — 한 번에 최대 3개, 돌아가며', () => {
  it('최대 3개', () => {
    expect(LIST_POLL_MAX).toBe(3);
    expect(pickPollBatch(['a', 'b', 'c', 'd', 'e'], 0).batch).toEqual(['a', 'b', 'c']);
    expect(pickPollBatch(['a', 'b'], 0)).toEqual({ batch: ['a', 'b'], next: 0 });
  });

  it('돌아가며 모두 조회된다(5개 → 두 차례 안에 모두, 같은 차례에 같은 id 는 한 번)', () => {
    const ids = ['a', 'b', 'c', 'd', 'e'];
    let cursor = 0;
    const seen = new Set<string>();
    const rounds: string[][] = [];
    for (let i = 0; i < 4; i++) {
      const { batch, next } = pickPollBatch(ids, cursor);
      expect(batch.length).toBeLessThanOrEqual(3);
      expect(new Set(batch).size).toBe(batch.length);
      rounds.push(batch);
      batch.forEach((id) => seen.add(id));
      cursor = next;
    }
    expect(rounds).toEqual([
      ['a', 'b', 'c'],
      ['d', 'e', 'a'],
      ['b', 'c', 'd'],
      ['e', 'a', 'b'],
    ]);
    expect([...seen].sort()).toEqual(ids);
  });

  it('목록이 줄어도 이어 간다(지난 자리를 길이로 나눈 나머지)', () => {
    expect(pickPollBatch(['a', 'b'], 3)).toEqual({ batch: ['b', 'a'], next: 1 });
    expect(pickPollBatch(['a', 'b', 'c', 'd'], -1).batch).toEqual(['d', 'a', 'b']);
  });

  it('진행 중 행이 없으면 빈 차례(멈춤)', () => {
    expect(pickPollBatch([], 7)).toEqual({ batch: [], next: 0 });
    expect(pickPollBatch(activeIds([row('a', 'done'), row('b', 'failed')]), 0).batch).toEqual([]);
  });
});

describe('다시 불러오기 결정', () => {
  it('조회 결과 null(지워짐) → 다시 불러온다', () => {
    expect(needsListReload('running', null)).toBe(true);
  });

  it('상태가 다르면 다시 불러온다, 같으면 그대로', () => {
    expect(needsListReload('running', { status: 'done' })).toBe(true);
    expect(needsListReload('queued', { status: 'running' })).toBe(true);
    expect(needsListReload('running', { status: 'running' })).toBe(false);
  });

  it('조회 실패(undefined) → 다시 불러오지 않는다(다음 차례에 다시 본다)', () => {
    expect(needsListReload('running', undefined)).toBe(false);
  });

  it('한 차례 결과 — 하나라도 다르면 true, 목록에서 이미 빠진 행은 보지 않는다', () => {
    const list = [row('a', 'running'), row('b', 'queued'), row('c', 'running')];
    expect(batchNeedsReload(list, ['a', 'b', 'c'], [{ status: 'running' }, { status: 'queued' }, { status: 'running' }])).toBe(false);
    expect(batchNeedsReload(list, ['a', 'b', 'c'], [{ status: 'running' }, { status: 'queued' }, { status: 'done' }])).toBe(true);
    expect(batchNeedsReload(list, ['a', 'b'], [undefined, null])).toBe(true);
    expect(batchNeedsReload(list, ['a'], [undefined])).toBe(false);
    expect(batchNeedsReload([row('a', 'running')], ['z'], [null])).toBe(false);
  });
});
