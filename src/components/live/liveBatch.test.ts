import { describe, expect, it } from 'vitest';
import type { RequestStep } from '@/services/analysis-service';
import {
  MSG_REQUEST_FAILED,
  READY,
  batchBarText,
  batchOutcome,
  canRemove,
  errorState,
  focusAfterRemove,
  rowStatus,
  runLiveBatch,
  sendableRows,
  startedToast,
  type LiveBatchRow,
  type LiveRowState,
} from './liveBatch';

/** 시작 결과를 모를 때 서비스가 던지는 값처럼 — 분석 id 를 담은 오류 */
class FakeApiError extends Error {
  constructor(
    message: string,
    readonly analysisId: string | null,
  ) {
    super(message);
  }
}
const idOf = (err: unknown) => (err instanceof FakeApiError ? err.analysisId : null);
const row = (key: string, state: LiveRowState = READY): LiveBatchRow => ({ key, state });
const STEPS: RequestStep[] = ['create', 'upload', 'start'];

/** 가짜 보내기 — 행마다 정해 둔 결과, 기록(시작 · 끝 · 동시에 몇 개)을 남긴다 */
function fakeSend(plan: Record<string, { fail?: unknown; id?: string; at?: RequestStep }>) {
  const log: string[] = [];
  let inFlight = 0;
  let maxInFlight = 0;
  const send = async (r: LiveBatchRow, onStep: (s: RequestStep) => void) => {
    inFlight += 1;
    maxInFlight = Math.max(maxInFlight, inFlight);
    log.push('begin ' + r.key);
    const p = plan[r.key] ?? {};
    try {
      for (const s of STEPS) {
        onStep(s);
        await Promise.resolve();
        if (p.fail !== undefined && p.at === s) throw p.fail;
      }
      if (p.fail !== undefined && !p.at) throw p.fail;
      return p.id ?? 'id-' + r.key;
    } finally {
      log.push('end ' + r.key);
      inFlight -= 1;
    }
  };
  return { send, log, max: () => maxInFlight };
}

describe('묶음 보내기 — 차례로 · 겹치지 않음 · 실패 뒤 계속', () => {
  it('보낼 행(ready · failed)만, 목록 순서대로, 앞 행이 끝난 뒤 다음', async () => {
    const rows = [row('a'), row('b', { kind: 'started', id: 'old' }), row('c', { kind: 'failed', message: 'x' }), row('d', { kind: 'unknown', message: 'y', id: 'u' }), row('e')];
    expect(sendableRows(rows).map((r) => r.key)).toEqual(['a', 'c', 'e']);
    const f = fakeSend({});
    const events: string[] = [];
    const res = await runLiveBatch(rows, {
      send: f.send,
      alive: () => true,
      onState: (key, state, pos) => events.push(`${key}:${state.kind}${state.kind === 'sending' ? '/' + state.step : ''}@${pos.index}/${pos.total}`),
      analysisIdOf: idOf,
    });
    expect(f.log).toEqual(['begin a', 'end a', 'begin c', 'end c', 'begin e', 'end e']);
    expect(f.max()).toBe(1);
    expect(res.stopped).toBe(false);
    expect(res.queued).toEqual(['a', 'c', 'e']);
    expect([...res.states]).toEqual([
      ['a', { kind: 'started', id: 'id-a' }],
      ['c', { kind: 'started', id: 'id-c' }],
      ['e', { kind: 'started', id: 'id-e' }],
    ]);
    // 다시 보낼 failed 행은 먼저 대기(ready)로, 그다음 차례대로 sending → started
    expect(events[0]).toBe('c:ready@2/3');
    expect(events.filter((e) => e.startsWith('a:'))).toEqual(['a:sending/create@1/3', 'a:sending/create@1/3', 'a:sending/upload@1/3', 'a:sending/start@1/3', 'a:started@1/3']);
    expect(events.filter((e) => e.startsWith('e:')).at(-1)).toBe('e:started@3/3');
  });

  it('하나가 실패해도 다음 행으로 — Error 문구 · 그 밖은 기본 문구, 분석 id 가 있으면 unknown', async () => {
    const rows = [row('a'), row('b'), row('c'), row('d')];
    const f = fakeSend({
      b: { fail: new Error('파일을 올리지 못했습니다. 잠시 후 새 분석으로 다시 시도해 주세요.'), at: 'upload' },
      c: { fail: new FakeApiError('분석 시작 결과를 확인하지 못했습니다.', 'made-c'), at: 'start' },
      d: { fail: 'boom' },
    });
    const res = await runLiveBatch(rows, { send: f.send, alive: () => true, onState: () => {}, analysisIdOf: idOf });
    expect(f.log).toEqual(['begin a', 'end a', 'begin b', 'end b', 'begin c', 'end c', 'begin d', 'end d']);
    expect(res.states.get('a')).toEqual({ kind: 'started', id: 'id-a' });
    expect(res.states.get('b')).toEqual({ kind: 'failed', message: '파일을 올리지 못했습니다. 잠시 후 새 분석으로 다시 시도해 주세요.' });
    expect(res.states.get('c')).toEqual({ kind: 'unknown', message: '분석 시작 결과를 확인하지 못했습니다.', id: 'made-c' });
    expect(res.states.get('d')).toEqual({ kind: 'failed', message: MSG_REQUEST_FAILED });
  });

  it('오류 분류 — 빈 문구 Error 는 기본 문구', () => {
    expect(errorState(new Error(''), idOf)).toEqual({ kind: 'failed', message: MSG_REQUEST_FAILED });
    expect(errorState(new FakeApiError('', 'x'), idOf)).toEqual({ kind: 'unknown', message: MSG_REQUEST_FAILED, id: 'x' });
    expect(errorState(new FakeApiError('m', null), idOf)).toEqual({ kind: 'failed', message: 'm' });
  });

  it('떠나면 — 진행 중이던 행은 끝까지 가되 상태를 알리지 않고, 아직 시작하지 않은 행은 보내지 않는다', async () => {
    let alive = true;
    const rows = [row('a'), row('b'), row('c')];
    const events: string[] = [];
    const f = fakeSend({});
    const send = async (r: LiveBatchRow, onStep: (s: RequestStep) => void) => {
      if (r.key === 'b') alive = false; // b 를 보내는 중에 떠남
      return f.send(r, onStep);
    };
    const res = await runLiveBatch(rows, { send, alive: () => alive, onState: (k, s) => events.push(`${k}:${s.kind}`), analysisIdOf: idOf });
    expect(res.stopped).toBe(true);
    expect(f.log).toEqual(['begin a', 'end a', 'begin b', 'end b']);
    expect(events.filter((e) => e.startsWith('b:'))).toEqual(['b:sending']);
    expect(events.some((e) => e.startsWith('c:'))).toBe(false);
  });

  it('끝난 행의 늦은 단계 알림은 버린다 — 성공 · 실패 · 시작 결과 모름 각각(알림 수 · 마지막 알림 · 반환 상태 그대로, 예외 없음)', async () => {
    const cases: [unknown, LiveRowState][] = [
      [undefined, { kind: 'started', id: 'id-a' }],
      [new Error('파일을 올리지 못했습니다.'), { kind: 'failed', message: '파일을 올리지 못했습니다.' }],
      [new FakeApiError('분석 시작 결과를 확인하지 못했습니다.', 'made-a'), { kind: 'unknown', message: '분석 시작 결과를 확인하지 못했습니다.', id: 'made-a' }],
    ];
    for (const [fail, expected] of cases) {
      const hold: { step?: (s: RequestStep) => void } = {};
      const events: string[] = [];
      const res = await runLiveBatch([row('a')], {
        send: async (_r, onStep) => {
          hold.step = onStep;
          onStep('upload');
          if (fail !== undefined) throw fail;
          return 'id-a';
        },
        alive: () => true,
        onState: (k, s) => events.push(`${k}:${s.kind}`),
        analysisIdOf: idOf,
      });
      const n = events.length;
      expect(() => hold.step?.('start')).not.toThrow();
      hold.step?.('upload');
      expect(events).toHaveLength(n);
      expect(events.at(-1)).toBe(`a:${expected.kind}`);
      expect(res.states.get('a')).toEqual(expected);
      expect(res.stopped).toBe(false);
    }
  });

  it('앞 행의 늦은 단계 알림을 다음 행을 보내는 중에 불러도 버린다 — 다음 행의 순번 · 단계 알림은 그대로', async () => {
    const hold: { a?: (s: RequestStep) => void } = {};
    const events: string[] = [];
    const res = await runLiveBatch([row('a'), row('b')], {
      send: async (r, onStep) => {
        if (r.key === 'a') {
          hold.a = onStep;
          onStep('upload');
          return 'id-a';
        }
        onStep('upload');
        hold.a?.('start'); // 앞 행(a)의 늦은 알림
        onStep('start');
        return 'id-b';
      },
      alive: () => true,
      onState: (k, s, pos) => events.push(`${k}:${s.kind}${s.kind === 'sending' ? '/' + s.step : ''}@${pos.index}/${pos.total}`),
      analysisIdOf: idOf,
    });
    expect(events).toEqual([
      'a:sending/create@1/2',
      'a:sending/upload@1/2',
      'a:started@1/2',
      'b:sending/create@2/2',
      'b:sending/upload@2/2',
      'b:sending/start@2/2',
      'b:started@2/2',
    ]);
    expect([...res.states]).toEqual([
      ['a', { kind: 'started', id: 'id-a' }],
      ['b', { kind: 'started', id: 'id-b' }],
    ]);
  });

  it('처음부터 떠나 있으면 아무것도 보내지 않는다', async () => {
    const f = fakeSend({});
    const res = await runLiveBatch([row('a'), row('b', { kind: 'failed', message: 'x' })], { send: f.send, alive: () => false, onState: () => { throw new Error('알리면 안 됨'); }, analysisIdOf: idOf });
    expect(res.stopped).toBe(true);
    expect(f.log).toEqual([]);
  });

  it('보낼 행이 없으면 바로 끝', async () => {
    const f = fakeSend({});
    const res = await runLiveBatch([row('a', { kind: 'started', id: '1' }), row('b', { kind: 'unknown', message: 'm', id: '2' })], { send: f.send, alive: () => true, onState: () => {}, analysisIdOf: idOf });
    expect(res).toEqual({ queued: [], states: new Map(), stopped: false });
    expect(f.log).toEqual([]);
  });
});

describe('끝난 뒤 갈 곳', () => {
  const started = (id: string): LiveRowState => ({ kind: 'started', id });

  it('모두 시작 — 1개면 상세, 여러 개면 목록(행 수)', () => {
    expect(batchOutcome([row('a', started('x'))])).toEqual({ kind: 'detail', id: 'x', toast: '분석을 시작했습니다.' });
    expect(batchOutcome([row('a', started('x')), row('b', started('y')), row('c', started('z'))])).toEqual({ kind: 'list', count: 3, toast: '분석 3건을 시작했습니다.' });
    expect(startedToast(2)).toBe('분석 2건을 시작했습니다.');
  });

  it('행 1개 실패 · 시작 결과 모름 — 그 문구(없으면 기본), 모름이면 분석 id, 상자가 그 행을 말한다', () => {
    expect(batchOutcome([row('a', { kind: 'failed', message: '파일을 올리지 못했습니다.' })])).toEqual({
      kind: 'stay',
      message: '파일을 올리지 못했습니다.',
      createdId: null,
      startedLink: false,
      rowKey: 'a',
    });
    expect(batchOutcome([row('a', { kind: 'unknown', message: '분석 시작 결과를 확인하지 못했습니다.', id: 'made' })])).toEqual({
      kind: 'stay',
      message: '분석 시작 결과를 확인하지 못했습니다.',
      createdId: 'made',
      startedLink: false,
      rowKey: 'a',
    });
    expect(batchOutcome([row('a', { kind: 'failed', message: '' })])).toMatchObject({ message: MSG_REQUEST_FAILED });
  });

  it('여러 개 일부 실패 — 목록 전체로 센다(n = 행 수, k = started 아닌 수), started 가 있으면 목록 링크', () => {
    expect(batchOutcome([row('a', started('x')), row('b', { kind: 'failed', message: 'm' }), row('c', started('z'))])).toEqual({
      kind: 'stay',
      message: '3개 중 1개를 시작하지 못했습니다.',
      createdId: null,
      startedLink: true,
      rowKey: null,
    });
    expect(batchOutcome([row('a', { kind: 'failed', message: 'm' }), row('b', { kind: 'unknown', message: 'm', id: 'u' })])).toEqual({
      kind: 'stay',
      message: '2개 중 2개를 시작하지 못했습니다.',
      createdId: null,
      startedLink: false,
      rowKey: null,
    });
    // 앞 묶음의 unknown 이 남고 이번에 보낸 행은 모두 시작 — 같은 규칙
    expect(batchOutcome([row('a', started('x')), row('b', { kind: 'unknown', message: 'm', id: 'u' }), row('c', started('z'))])).toMatchObject({
      message: '3개 중 1개를 시작하지 못했습니다.',
      startedLink: true,
    });
  });
});

describe('표시', () => {
  it('띠 글 — 1개면 단계만, 여러 개면 i/n', () => {
    expect(batchBarText('파일 올리는 중', { index: 1, total: 1 })).toBe('파일 올리는 중…');
    expect(batchBarText('파일 올리는 중', { index: 2, total: 3 })).toBe('2/3 · 파일 올리는 중…');
  });

  it('행 상태 글 — ready 는 요청 중에만 대기, 상자가 그 행을 말하면 숨김', () => {
    expect(rowStatus(READY, { busy: false, hidden: false })).toEqual({ kind: 'none' });
    expect(rowStatus(READY, { busy: true, hidden: false })).toEqual({ kind: 'waiting' });
    expect(rowStatus({ kind: 'sending', step: 'upload' }, { busy: true, hidden: false })).toEqual({ kind: 'sending' });
    expect(rowStatus({ kind: 'started', id: 'x' }, { busy: false, hidden: false })).toEqual({ kind: 'started' });
    expect(rowStatus({ kind: 'failed', message: 'm' }, { busy: false, hidden: false })).toEqual({ kind: 'failed', message: 'm' });
    expect(rowStatus({ kind: 'unknown', message: 'm', id: 'u' }, { busy: false, hidden: false })).toEqual({ kind: 'unknown', id: 'u' });
    expect(rowStatus({ kind: 'failed', message: 'm' }, { busy: false, hidden: true })).toEqual({ kind: 'none' });
  });

  it('빼기 버튼 — started · unknown 행에는 없다', () => {
    expect(canRemove(READY)).toBe(true);
    expect(canRemove({ kind: 'failed', message: 'm' })).toBe(true);
    expect(canRemove({ kind: 'started', id: 'x' })).toBe(false);
    expect(canRemove({ kind: 'unknown', message: 'm', id: 'u' })).toBe(false);
  });

  it('뺀 뒤 포커스 — 같은 자리부터 뒤로, 없으면 앞으로, 없으면 파일 입력(null)', () => {
    const s: LiveRowState = { kind: 'started', id: 'x' };
    // [a, (뺀 자리) b, c] → 같은 자리(1) = c
    expect(focusAfterRemove([row('a'), row('c')], 1)).toBe('c');
    // 마지막을 뺐으면 앞 행
    expect(focusAfterRemove([row('a'), row('b')], 2)).toBe('b');
    // 같은 자리 · 뒤가 started 면 그 뒤에서 버튼이 있는 행
    expect(focusAfterRemove([row('a', s), row('b', s), row('c')], 1)).toBe('c');
    // 뒤에 없으면 앞으로 가장 가까운 행
    expect(focusAfterRemove([row('a'), row('b', s), row('c', s)], 1)).toBe('a');
    // 버튼이 있는 행이 없으면 파일 입력
    expect(focusAfterRemove([row('a', s)], 0)).toBeNull();
    expect(focusAfterRemove([], 0)).toBeNull();
  });
});
