/* 목록 덧씌움 — 지운 행 빼기 · 다시 분석 요청 중 '재시도 중' · 시작한 행 '분석 중'(새 목록이 오기 전까지). */
import { describe, expect, it } from 'vitest';
import { toListAnalysis } from '@/services/api/mapping';
import { listItemOut } from '@/services/api/testing';
import type { Analysis } from '@/services/types';
import { NO_OVERLAY, applyListOverlay } from './listOverlay';
import { toRow } from './listModel';

const a = (id: string, status: string): Analysis => toListAnalysis(listItemOut({ id, status, error: status === 'failed' ? '실패 이유' : null }))!;

describe('applyListOverlay', () => {
  const list = [a('a1', 'done'), a('a2', 'failed'), a('a3', 'running')];

  it('덧씌움이 없으면 같은 객체 그대로', () => {
    const out = applyListOverlay(list, NO_OVERLAY);
    expect(out).toHaveLength(3);
    out.forEach((x, i) => expect(x).toBe(list[i]));
  });

  it('지운 행은 빠지고 순서는 그대로', () => {
    expect(applyListOverlay(list, { ...NO_OVERLAY, hidden: new Set(['a2']) }).map((x) => x.id)).toEqual(['a1', 'a3']);
  });

  it('다시 분석 요청 중 — 그 행만 retrying(목록 행 \'재시도 중…\' · \'다시 분석하는 중\')', () => {
    const out = applyListOverlay(list, { ...NO_OVERLAY, retrying: new Set(['a2']) });
    expect(out[1]).not.toBe(list[1]);
    expect(out[1].retrying).toBe(true);
    expect(toRow(out[1])).toMatchObject({ failed: true, retrying: true, sub: '다시 분석하는 중' });
    expect(list[1].retrying).toBe(false); // 원본은 그대로
  });

  it('시작한 행 — 분석 중(문서도 분석 중, 오류 · 분석 시각 비움) → 오류 확인 · 재시도 버튼이 사라진다', () => {
    const out = applyListOverlay(list, { ...NO_OVERLAY, started: new Set(['a2']), retrying: new Set(['a2']) });
    expect(out[1]).toMatchObject({ status: 'running', retrying: false, analyzedAt: '' });
    expect(out[1].docs.every((d) => d.status === 'running' && d.error === '')).toBe(true);
    expect(toRow(out[1])).toMatchObject({ failed: false, retrying: false, status: 'running', sub: '문서 0/1개 완료' });
  });
});
