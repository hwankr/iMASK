import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { PDF_CANCELLED, PDF_OPEN_FAILED, PDF_OPEN_TIMEOUT, PDF_WORKER_FAILED } from './liveViewerModel';
import { PDF_CLOSE_GRACE_MS, PDF_OPEN_TIMEOUT_MS, guardOpen, type GuardPort } from './pdfOpenGuard';

/** 오류 이벤트를 흉내 내는 워커 — 등록된 리스너 수와 terminate 횟수를 센다 */
class FakePort implements GuardPort {
  listeners = new Map<string, Set<() => void>>();
  terminated = 0;
  addEventListener(type: string, fn: () => void) {
    if (!this.listeners.has(type)) this.listeners.set(type, new Set());
    this.listeners.get(type)!.add(fn);
  }
  removeEventListener(type: string, fn: () => void) {
    this.listeners.get(type)?.delete(fn);
  }
  emit(type: string) {
    [...(this.listeners.get(type) ?? [])].forEach((fn) => fn());
  }
  count() {
    return [...this.listeners.values()].reduce((n, s) => n + s.size, 0);
  }
  terminate() {
    this.terminated++;
  }
}

function deferred<T>() {
  let resolve!: (v: T) => void;
  let reject!: (e: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

function setup() {
  const port = new FakePort();
  const opened = deferred<string>();
  const destroyed = deferred<void>();
  const calls = { destroyTask: 0, destroyWorker: 0 };
  const g = guardOpen<string>({
    port,
    opened: opened.promise,
    destroyTask: () => {
      calls.destroyTask++;
      return destroyed.promise;
    },
    destroyWorker: () => {
      calls.destroyWorker++;
    },
    // 원래 오류 내용은 버리고 고정 문구만
    mapError: () => new Error(PDF_OPEN_FAILED),
  });
  return { port, opened, destroyed, calls, g };
}

/** microtask(promise 후속)만 처리한다 — 가짜 타이머는 진행하지 않는다 */
async function flushMicrotasks(rounds = 10): Promise<void> {
  for (let i = 0; i < rounds; i++) await Promise.resolve();
}

/** 결과를 기다린다(성공 값 또는 오류 문구) */
async function outcome(p: Promise<string>): Promise<{ ok: string } | { err: string }> {
  return p.then(
    (ok) => ({ ok }),
    (e: unknown) => ({ err: e instanceof Error ? e.message : String(e) }),
  );
}

beforeEach(() => {
  vi.useFakeTimers();
});
afterEach(() => {
  vi.useRealTimers();
});

describe('guardOpen — PDF 열기 지킴이(열기 전 실패 · 시간 초과 · 취소)', () => {
  it('열기 시작 즉시 정리 손잡이를 돌려주고, 워커 error · messageerror 를 듣는다', () => {
    const { port, g } = setup();
    expect(typeof g.close).toBe('function');
    expect(port.listeners.get('error')?.size).toBe(1);
    expect(port.listeners.get('messageerror')?.size).toBe(1);
  });

  it('열리면 문서를 돌려주고 리스너 · 타이머를 해제한다(이후 워커 오류 · 시간 초과는 무시)', async () => {
    const { port, opened, calls, g } = setup();
    opened.resolve('doc');
    expect(await outcome(g.promise)).toEqual({ ok: 'doc' });
    expect(port.count()).toBe(0);
    expect(vi.getTimerCount()).toBe(0);
    port.emit('error');
    vi.advanceTimersByTime(PDF_OPEN_TIMEOUT_MS * 2);
    expect(calls).toEqual({ destroyTask: 0, destroyWorker: 0 });
    expect(port.terminated).toBe(0);
  });

  it('워커 error(스크립트 404 등) → 고정 문구로 실패 · 바로 정리(task destroy · PDFWorker destroy · terminate) · 리스너 해제', async () => {
    const { port, calls, g } = setup();
    port.emit('error');
    expect(await outcome(g.promise)).toEqual({ err: PDF_WORKER_FAILED });
    expect(calls).toEqual({ destroyTask: 1, destroyWorker: 1 });
    expect(port.terminated).toBe(1);
    expect(port.count()).toBe(0);
    expect(vi.getTimerCount()).toBe(0);
  });

  it('워커 messageerror 도 같은 고정 문구로 실패', async () => {
    const { port, g } = setup();
    port.emit('messageerror');
    expect(await outcome(g.promise)).toEqual({ err: PDF_WORKER_FAILED });
    expect(port.terminated).toBe(1);
  });

  it(`제한 시간(${PDF_OPEN_TIMEOUT_MS}ms)을 넘으면 고정 문구로 실패 · 정리, 그 전에는 기다린다`, async () => {
    const { port, calls, g } = setup();
    vi.advanceTimersByTime(PDF_OPEN_TIMEOUT_MS - 1);
    expect(port.terminated).toBe(0);
    vi.advanceTimersByTime(1);
    expect(await outcome(g.promise)).toEqual({ err: PDF_OPEN_TIMEOUT });
    expect(calls).toEqual({ destroyTask: 1, destroyWorker: 1 });
    expect(port.terminated).toBe(1);
    expect(port.count()).toBe(0);
  });

  it('열기 실패(손상 PDF 등) → mapError 의 고정 문구 · 정리, 원래 오류 내용은 보이지 않는다', async () => {
    const { port, opened, g } = setup();
    opened.reject(new Error('Invalid PDF structure at https://storage.example.test/x'));
    const r = await outcome(g.promise);
    expect(r).toEqual({ err: PDF_OPEN_FAILED });
    expect(port.terminated).toBe(1);
    expect(port.count()).toBe(0);
    expect(vi.getTimerCount()).toBe(0);
  });

  it('여는 중 close(언마운트 · 다시 시도) → 바로 정리하고 PDF_CANCELLED, 늦게 도착한 문서는 버린다', async () => {
    const { port, opened, calls, g } = setup();
    g.close();
    expect(calls).toEqual({ destroyTask: 1, destroyWorker: 1 });
    expect(port.terminated).toBe(1);
    expect(port.count()).toBe(0);
    expect(vi.getTimerCount()).toBe(0);
    opened.resolve('late');
    expect(await outcome(g.promise)).toEqual({ err: PDF_CANCELLED });
    port.emit('error');
    g.close();
    expect(port.terminated).toBe(1);
  });

  it('연 뒤 close → 문서 정리를 기다렸다가 끝내고, 정리가 끝난 자리에서 대기 타이머를 해제한다(타이머를 소진하지 않고 확인)', async () => {
    const a = setup();
    a.opened.resolve('doc');
    await a.g.promise;
    a.g.close();
    expect(a.calls.destroyTask).toBe(1);
    expect(a.port.terminated).toBe(0); // 아직 정리 중
    expect(vi.getTimerCount()).toBe(1); // graceMs 대기 타이머
    a.destroyed.resolve();
    await flushMicrotasks(); // 타이머는 진행하지 않는다
    expect(a.calls.destroyWorker).toBe(1);
    expect(a.port.terminated).toBe(1);
    expect(vi.getTimerCount()).toBe(0);
    a.g.close();
    await flushMicrotasks();
    expect(a.calls).toEqual({ destroyTask: 1, destroyWorker: 1 });
    expect(a.port.terminated).toBe(1);
    expect(vi.getTimerCount()).toBe(0);
  });

  it('정상 정리가 바로 끝나는 경우 — close 를 두 번 불러도 정리 · 종료 각 1회, microtask 만 처리한 상태에서 남은 타이머 0', async () => {
    const { port, opened, destroyed, calls, g } = setup();
    destroyed.resolve(); // destroyTask 가 곧바로 풀리는 promise 를 돌려준다
    opened.resolve('doc');
    await g.promise;
    g.close();
    g.close();
    await flushMicrotasks();
    expect(calls).toEqual({ destroyTask: 1, destroyWorker: 1 });
    expect(port.terminated).toBe(1);
    expect(port.count()).toBe(0);
    expect(vi.getTimerCount()).toBe(0);
  });

  it(`문서 정리가 멈추면 ${PDF_CLOSE_GRACE_MS}ms 뒤 강제로 끝낸다 — 늦게 끝난 정리 · 다시 close 는 종료를 더하지 않는다`, async () => {
    const b = setup();
    b.opened.resolve('doc');
    await b.g.promise;
    b.g.close();
    await vi.advanceTimersByTimeAsync(PDF_CLOSE_GRACE_MS - 1);
    expect(b.port.terminated).toBe(0);
    await vi.advanceTimersByTimeAsync(1);
    expect(b.port.terminated).toBe(1); // 정리 promise 가 끝나지 않아도
    expect(b.calls.destroyWorker).toBe(1);
    expect(vi.getTimerCount()).toBe(0);
    b.destroyed.resolve();
    await flushMicrotasks();
    b.g.close();
    expect(b.port.terminated).toBe(1); // 여러 번 불러도 한 번
    expect(b.calls.destroyWorker).toBe(1);
  });

  it('정리 함수가 던지거나 거절해도 워커는 끝낸다', async () => {
    const port = new FakePort();
    const g = guardOpen<string>({
      port,
      opened: new Promise(() => {}),
      destroyTask: () => {
        throw new Error('boom');
      },
      destroyWorker: () => {
        throw new Error('boom');
      },
      mapError: () => new Error(PDF_OPEN_FAILED),
    });
    g.close();
    expect(await outcome(g.promise)).toEqual({ err: PDF_CANCELLED });
    expect(port.terminated).toBe(1);
  });
});
