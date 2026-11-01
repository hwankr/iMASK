import { describe, expect, it } from 'vitest';
import type { StateId } from '@/services/analysis-service';
import { DEV_STATES, LISTED_STATES, STATE_GROUPS, findGroup, findState, isStateId, statePosition } from './states';

/** Tweaks '시작 상태' 순서(Main.dc.html 761줄) */
const PROTOTYPE_ORDER: StateId[] = [
  'list', 'list-empty', 'list-noresults', 'upload', 'upload-selected', 'upload-unsupported', 'upload-limit',
  'upload-failed', 'upload-requesting', 'detail', 'detail-queued', 'detail-running', 'detail-partial',
  'detail-failed', 'detail-completed', 'detail-nolocation', 'detail-review', 'detail-links', 'detail-edit',
  'detail-complete', 'detail-docs', 'detail-results', 'report', 'report-saved', 'report-failed',
];

describe('DEV_STATES', () => {
  it('25개, 프로토타입 순서 그대로, 중복 없음', () => {
    expect(DEV_STATES.map((s) => s.id)).toEqual(PROTOTYPE_ORDER);
    expect(new Set(DEV_STATES.map((s) => s.id)).size).toBe(25);
  });

  it('목록에는 휴대폰 전용 2개를 뺀 23개', () => {
    expect(LISTED_STATES).toHaveLength(23);
    expect(DEV_STATES.filter((s) => s.phoneOnly).map((s) => s.id)).toEqual(['detail-docs', 'detail-results']);
  });

  it('모든 그룹이 정의되어 있다', () => {
    const groups = new Set(STATE_GROUPS.map((g) => g.id));
    for (const s of DEV_STATES) expect(groups.has(s.group)).toBe(true);
  });

  it('그룹마다 여는 화면 경로(목록 23개 = 3 · 6 · 11 · 3)', () => {
    expect(STATE_GROUPS.map((g) => g.path)).toEqual(['/', '/analyses/new', '/analyses/[id]', '/analyses/[id]/report']);
    expect(STATE_GROUPS.map((g) => LISTED_STATES.filter((s) => s.group === g.id).length)).toEqual([3, 6, 11, 3]);
    expect(findGroup('detail').title).toBe('상세 검토');
  });

  it('findState · isStateId', () => {
    expect(findState('list-empty')?.title).toBe('분석 이력 없음');
    expect(isStateId('nope')).toBe(false);
    expect(isStateId('toString')).toBe(false);
  });
});

describe('statePosition', () => {
  it('첫 상태는 이전이 없다', () => {
    const p = statePosition('list');
    expect(p?.number).toBe(1);
    expect(p?.total).toBe(23);
    expect(p?.prev).toBeNull();
    expect(p?.next?.id).toBe('list-empty');
  });

  it('휴대폰 전용 상태는 번호가 없고, 앞뒤 목록 상태로 이어진다', () => {
    const p = statePosition('detail-docs');
    expect(p?.number).toBeNull();
    expect(p?.prev?.id).toBe('detail-complete');
    expect(p?.next?.id).toBe('report');
  });

  it('휴대폰 전용 상태를 건너뛰어 번호를 센다', () => {
    expect(statePosition('detail-complete')?.next?.id).toBe('report');
    expect(statePosition('report')?.number).toBe(21);
    expect(statePosition('report-failed')?.number).toBe(23);
    expect(statePosition('report-failed')?.next).toBeNull();
  });
});
