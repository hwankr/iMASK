/* 실제 분석 서비스의 검토 동작 — 가짜 백엔드(GET 분석 · POST review-actions)로 본문 · id 변환 · 알림 · 오류를 확인한다. */
import { describe, expect, it, vi } from 'vitest';
import { CONFIG } from '@/config/app';
import type { AnalysisService } from '../analysis-service';
import type { Analysis } from '../types';
import { ApiError, createApiClient } from './client';
import { MSG_NO_ANALYSIS, MSG_NO_FINDING, MSG_UNSUPPORTED, createApiService } from './service';
import { analysisOut, contractResult, fakeFetch, json, memoryStorage, type SeenRequest } from './testing';

const ID = 'ab12cd34-0000-4000-8000-000000000000';
const ACTION_URL = `/api/py/analyses/${ID}/review-actions`;
const GET_URL = `/api/py/analyses/${ID}`;

function review(findings: Record<string, unknown> = {}): Record<string, unknown> {
  return { status: 'needed', memo: '', memo_at: null, reviewer: '', reviewed_at: null, completion_note: '', findings, history: [], version: 0 };
}

/** 완료 + 계약 결과 + 검토 기록 */
function doneOut(opts: { findings?: Record<string, unknown>; edit?: (r: Record<string, unknown>) => void } = {}) {
  const result = contractResult();
  opts.edit?.(result);
  return analysisOut({ status: 'done', result, review: review(opts.findings) });
}

interface SetupOptions {
  /** GET 응답(기본 doneOut()) */
  get?: () => Response;
  /** POST 응답(기본 200 + changed true) */
  post?: (req: SeenRequest) => Response;
}

/** 서비스 + 가짜 백엔드 + 알림 기록 */
function setup(opts: SetupOptions = {}) {
  const { fetch, seen } = fakeFetch((req) => {
    if (req.method === 'POST' && req.url === ACTION_URL) return opts.post ? opts.post(req) : json(200, { analysis: doneOut(), changed: true });
    if (req.method === 'GET' && req.url === GET_URL) return opts.get ? opts.get() : json(200, doneOut());
    return json(404, { detail: '분석 건을 찾을 수 없습니다.' });
  });
  const service: AnalysisService = createApiService({ client: createApiClient({ fetch }), upload: async () => {}, storage: memoryStorage() });
  const notified = vi.fn();
  service.subscribe(notified);
  const posts = () => seen.filter((r) => r.method === 'POST');
  const gets = () => seen.filter((r) => r.method === 'GET');
  return { service, seen, notified, posts, gets };
}

const ACTOR = CONFIG.user.name;

describe('검토 동작 9개 — 본문(type · 계약 id · 필드 · actor) · 알림 한 번', () => {
  const cases: { name: string; call: (s: AnalysisService) => Promise<unknown>; body: Record<string, unknown> }[] = [
    {
      name: 'setStatus 확인(사유 없음 → "")',
      call: (s) => s.setStatus(ID, 'D1-02', 'confirmed'),
      body: { type: 'set_status', actor: ACTOR, finding_id: '0:applicant_rrn', status: 'confirmed', reason: '' },
    },
    {
      name: 'setStatus 확인 취소(사유 그대로)',
      call: (s) => s.setStatus(ID, 'D2-02', 'open', '  다시 볼 것 '),
      body: { type: 'set_status', actor: ACTOR, finding_id: '1:applicant_birth_date', status: 'open', reason: '  다시 볼 것 ' },
    },
    {
      name: 'confirmMany(순서대로 · 중복 없이)',
      call: (s) => s.confirmMany(ID, ['D1-03', 'D1-01', 'D1-03', 'D5-02']),
      body: { type: 'confirm_many', actor: ACTOR, finding_ids: ['0:applicant_phone', '0:applicant_name', '4:card_number'] },
    },
    {
      name: 'markFalsePositive',
      call: (s) => s.markFalsePositive(ID, 'D2-01', '이미 가려진 값', '원본에서 가려짐'),
      body: { type: 'mark_false_positive', actor: ACTOR, finding_id: '1:applicant_name', reason_type: '이미 가려진 값', note: '원본에서 가려짐' },
    },
    {
      name: 'restore(메모 없음 → "")',
      call: (s) => s.restore(ID, 'D2-01'),
      body: { type: 'restore', actor: ACTOR, finding_id: '1:applicant_name', note: '' },
    },
    {
      name: 'restore(메모)',
      call: (s) => s.restore(ID, 'D2-01', '다시 보니 개인정보'),
      body: { type: 'restore', actor: ACTOR, finding_id: '1:applicant_name', note: '다시 보니 개인정보' },
    },
    {
      name: 'reclassify(셋 모두)',
      call: (s) => s.reclassify(ID, 'D1-03', { cat: '이름', subject: '보증인', exposure: '마스킹됨' }, '직장 번호'),
      body: { type: 'reclassify', actor: ACTOR, finding_id: '0:applicant_phone', category: '이름', subject: '보증인', exposure: '마스킹됨', reason: '직장 번호' },
    },
    {
      name: 'reclassify(바꿀 값만)',
      call: (s) => s.reclassify(ID, 'D1-03', { subject: '보증인' }, '사유'),
      body: { type: 'reclassify', actor: ACTOR, finding_id: '0:applicant_phone', subject: '보증인', reason: '사유' },
    },
    {
      name: 'saveFindingMemo(빈 값 = 삭제)',
      call: (s) => s.saveFindingMemo(ID, 'D5-02', ''),
      body: { type: 'save_finding_memo', actor: ACTOR, finding_id: '4:card_number', text: '' },
    },
    {
      name: 'saveMemo',
      call: (s) => s.saveMemo(ID, '검토 메모\n둘째 줄'),
      body: { type: 'save_memo', actor: ACTOR, text: '검토 메모\n둘째 줄' },
    },
    {
      name: 'completeReview',
      call: (s) => s.completeReview(ID, ''),
      body: { type: 'complete_review', actor: ACTOR, note: '' },
    },
    {
      name: 'reopenReview',
      call: (s) => s.reopenReview(ID, '다시 확인 필요'),
      body: { type: 'reopen_review', actor: ACTOR, reason: '다시 확인 필요' },
    },
  ];
  for (const c of cases) {
    it(c.name, async () => {
      const { service, seen, notified, posts } = setup();
      await c.call(service);
      expect(seen.map((r) => [r.method, r.url])).toEqual([
        ['GET', GET_URL],
        ['POST', ACTION_URL],
      ]);
      expect(posts()[0].body).toEqual(c.body);
      expect(posts()[0].headers['content-type']).toBe('application/json');
      expect(notified).toHaveBeenCalledTimes(1);
      expect(notified).toHaveBeenCalledWith();
    });
  }

  it('actor 는 CONFIG.user.name', () => {
    expect(ACTOR).toBe(CONFIG.user.name);
    expect(ACTOR.length).toBeGreaterThan(0);
  });
});

describe('id 변환 — 화면 번호 → 지금 분석의 계약 id', () => {
  it('검토 기록이 덧씌워진 뒤에도 같은 번호 → 같은 계약 id', async () => {
    const { service, posts } = setup({ get: () => json(200, doneOut({ findings: { '0:applicant_rrn': { status: 'confirmed' } } })) });
    await service.setStatus(ID, 'D1-02', 'open');
    expect(posts()[0].body).toMatchObject({ finding_id: '0:applicant_rrn' });
  });

  it('계약 id 에 짝 없는 서로게이트 · \\u0000 · 따옴표 · / · ? 가 있어도 그대로 본문에(주소는 분석 id 만)', async () => {
    const odd = '0:a/b"c\ud800\u0000?#';
    const { service, posts } = setup({
      get: () =>
        json(
          200,
          doneOut({
            edit: (r) => {
              (r.findings as { id: string }[])[0].id = odd;
            },
          }),
        ),
    });
    await service.saveFindingMemo(ID, 'D1-01', '메모');
    expect(posts()[0].url).toBe(ACTION_URL);
    expect(posts()[0].body).toEqual({ type: 'save_finding_memo', actor: ACTOR, finding_id: odd, text: '메모' });
  });

  it('없는 번호 → 요청 없이 거절(짧은 한국어) · 알림 없음', async () => {
    const { service, notified, posts } = setup();
    const calls = [
      service.setStatus(ID, 'D9-01', 'confirmed'),
      service.markFalsePositive(ID, 'F-01', '기타', ''),
      service.restore(ID, 'D1-99'),
      service.reclassify(ID, '0:applicant_name', { cat: '이름' }, ''), // 계약 id 는 화면 번호가 아니다
      service.saveFindingMemo(ID, '', ''),
      service.confirmMany(ID, ['D1-01', 'D9-09']),
    ];
    const results = await Promise.allSettled(calls);
    for (const r of results) {
      expect(r.status).toBe('rejected');
      expect((r as PromiseRejectedResult).reason.message).toBe(MSG_NO_FINDING);
    }
    expect(MSG_NO_FINDING).toBe('탐지 항목을 찾을 수 없습니다.');
    expect(posts()).toHaveLength(0);
    expect(notified).not.toHaveBeenCalled();
  });

  it('없는 분석(GET 404) → 요청 없이 거절 · 알림 없음(모든 동작)', async () => {
    const { service, notified, posts } = setup({ get: () => json(404, { detail: '분석 건을 찾을 수 없습니다.' }) });
    const calls = [
      service.setStatus(ID, 'D1-01', 'confirmed'),
      service.confirmMany(ID, ['D1-01']),
      service.markFalsePositive(ID, 'D1-01', '기타', ''),
      service.restore(ID, 'D1-01'),
      service.reclassify(ID, 'D1-01', { cat: '주소' }, ''),
      service.saveFindingMemo(ID, 'D1-01', ''),
      service.saveMemo(ID, ''),
      service.completeReview(ID, ''),
      service.reopenReview(ID, ''),
    ];
    const results = await Promise.allSettled(calls);
    expect(results).toHaveLength(9);
    for (const r of results) {
      expect(r.status).toBe('rejected');
      expect((r as PromiseRejectedResult).reason.message).toBe(MSG_NO_ANALYSIS);
    }
    expect(posts()).toHaveLength(0);
    expect(notified).not.toHaveBeenCalled();
  });

  it('분석 조회가 502 · 네트워크면 그 오류(ApiError)로 거절 · 요청 없음', async () => {
    const { service, posts, notified } = setup({ get: () => json(502, { detail: '저장소 오류' }) });
    const err = await service.saveMemo(ID, 'x').catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err).toMatchObject({ code: 'server', message: '저장소 오류' });
    expect(posts()).toHaveLength(0);
    expect(notified).not.toHaveBeenCalled();
  });

  it('confirmMany 빈 목록 → 조회 · 요청 · 알림 없이 끝', async () => {
    const { service, seen, notified } = setup();
    await expect(service.confirmMany(ID, [])).resolves.toBeUndefined();
    expect(seen).toHaveLength(0);
    expect(notified).not.toHaveBeenCalled();
  });

  it('같은 분석을 동시에 고치면 조회 하나를 나눠 쓴다(요청은 동작마다)', async () => {
    const { service, gets, posts, notified } = setup();
    await Promise.all([service.setStatus(ID, 'D1-01', 'confirmed'), service.setStatus(ID, 'D1-02', 'confirmed'), service.saveMemo(ID, 'm')]);
    expect(gets()).toHaveLength(1);
    expect(posts().map((p) => (p.body as { type: string }).type).sort()).toEqual(['save_memo', 'set_status', 'set_status']);
    expect(notified).toHaveBeenCalledTimes(3);
  });
});

describe('응답 · 오류', () => {
  it('changed false 여도 알림 한 번(데모 write 와 같다), reclassify 는 changed 를 돌려준다', async () => {
    const off = setup({ post: () => json(200, { analysis: doneOut(), changed: false }) });
    await expect(off.service.reclassify(ID, 'D1-01', { cat: '이름' }, '사유')).resolves.toBe(false);
    expect(off.notified).toHaveBeenCalledTimes(1);
    await off.service.confirmMany(ID, ['D1-01']);
    expect(off.notified).toHaveBeenCalledTimes(2);

    const on = setup({ post: () => json(200, { analysis: doneOut(), changed: true }) });
    await expect(on.service.reclassify(ID, 'D1-01', { cat: '주소' }, '사유')).resolves.toBe(true);
    expect(on.notified).toHaveBeenCalledTimes(1);

    // changed 가 true 가 아니면(빠짐 · 글) false
    const odd = setup({ post: () => json(200, { analysis: doneOut(), changed: 'true' }) });
    await expect(odd.service.reclassify(ID, 'D1-01', { cat: '주소' }, '사유')).resolves.toBe(false);
  });

  const failures: [number, string, string][] = [
    [409, 'conflict', '검토를 완료한 분석은 바꿀 수 없습니다.'],
    [409, 'conflict', '다른 요청과 겹쳐 저장하지 못했습니다. 잠시 후 다시 시도해 주세요.'],
    [404, 'not_found', '탐지 항목을 찾을 수 없습니다.'],
    [400, 'bad_request', '메모·사유는 500자 이하로 적어 주세요.'],
    [413, 'bad_request', '요청 본문이 너무 큽니다.'],
    [502, 'server', '서버 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.'],
  ];
  for (const [status, code, detail] of failures) {
    it(`요청 ${status} → 알림 없이 ApiError(${code}) 그대로`, async () => {
      const { service, notified } = setup({ post: () => json(status, { detail }) });
      const err = await service.setStatus(ID, 'D1-01', 'confirmed').catch((e: unknown) => e);
      expect(err).toBeInstanceOf(ApiError);
      expect(err).toMatchObject({ status, code, message: detail });
      expect(notified).not.toHaveBeenCalled();
    });
  }

  it('요청 네트워크 오류 → 알림 없이 network', async () => {
    const { service, notified } = setup({
      post: () => {
        throw new TypeError('Failed to fetch');
      },
    });
    await expect(service.completeReview(ID, '')).rejects.toMatchObject({ code: 'network', status: 0 });
    expect(notified).not.toHaveBeenCalled();
  });
});

describe('pending — 조회한 분석의 미확인 항목', () => {
  it('open 만(검토 기록 반영) · 검토사항 · 연결은 빈 목록', async () => {
    const findings: Record<string, unknown> = {};
    const all = contractResult().findings as { id: string }[];
    // 2개만 남기고 모두 확인함 · 오탐 · 분류 수정
    all.forEach((f, i) => {
      if (i === 1 || i === 4) return;
      findings[f.id] = { status: ['confirmed', 'false_positive', 'reclassified'][i % 3] };
    });
    const { service, seen, posts } = setup({ get: () => json(200, doneOut({ findings })) });
    const p = await service.pending(ID);
    expect(p.openF.map((f) => f.id)).toEqual(['D1-02', 'D1-05']);
    expect(p.openF.map((f) => f.live?.id)).toEqual(['0:applicant_rrn', '0:applicant_address']);
    expect(p.openI).toEqual([]);
    expect(p.openL).toEqual([]);
    expect(p.any).toBe(true);
    expect(seen.map((r) => r.method)).toEqual(['GET']);
    expect(posts()).toHaveLength(0);
  });

  it('미확인이 없으면 any false, 검토 기록이 없으면 모두 미확인', async () => {
    const findings = Object.fromEntries((contractResult().findings as { id: string }[]).map((f) => [f.id, { status: 'confirmed' }]));
    const none = setup({ get: () => json(200, doneOut({ findings })) });
    expect(await none.service.pending(ID)).toEqual({ openF: [], openI: [], openL: [], any: false });
    const fresh = setup();
    const p = await fresh.service.pending(ID);
    expect(p.openF).toHaveLength(19);
    expect(p.any).toBe(true);
  });

  it('없는 분석 → 빈 값, 대기 중인 분석 → 빈 값', async () => {
    const missing = setup({ get: () => json(404, { detail: '분석 건을 찾을 수 없습니다.' }) });
    expect(await missing.service.pending(ID)).toEqual({ openF: [], openI: [], openL: [], any: false });
    const queued = setup({ get: () => json(200, analysisOut()) });
    expect(await queued.service.pending(ID)).toEqual({ openF: [], openI: [], openL: [], any: false });
  });
});

describe('남은 미지원 기능은 그대로', () => {
  it('검토사항 · 연결 판단 · 내보내기는 요청 없이 거절, 다시 분석은 실패 결과', async () => {
    const { service, seen, notified } = setup();
    const results = await Promise.allSettled([
      service.resolveItem(ID, 'R-01', '처리'),
      service.reopenItem(ID, 'R-01'),
      service.decideLink(ID, 'L-01', 'linked', '근거'),
      service.buildExport(ID, 'json'),
      service.logExport(ID, { format: 'json', name: '', mime: '', text: '', size: 0, preview: '' }, 'handed'),
    ]);
    for (const r of results) {
      expect(r.status).toBe('rejected');
      expect((r as PromiseRejectedResult).reason.message).toBe(MSG_UNSUPPORTED);
    }
    await expect(service.retry(ID)).resolves.toEqual({ ok: false, message: MSG_UNSUPPORTED });
    expect(seen).toHaveLength(0);
    expect(notified).not.toHaveBeenCalled();
  });
});

/* ---------- 저장 뒤 알림의 최신성(V-T2-1 M1 회귀) ---------- */

/** 밖에서 푸는 약속 */
function deferred(): { promise: Promise<void>; resolve: () => void } {
  let resolve: () => void = () => {};
  const promise = new Promise<void>((r) => {
    resolve = r;
  });
  return { promise, resolve };
}

/** 저장 값을 가진 가짜 서버 — GET 은 시작할 때의 값을 찍어 두고, 붙잡힌 차례(n 번째)면 풀릴 때까지 기다린다 */
function liveServer() {
  const findings: Record<string, Record<string, unknown>> = {};
  let memo = '';
  let gets = 0;
  let posts = 0;
  const getGates = new Map<number, Promise<void>>();
  const getStarted = new Map<number, () => void>();
  const postGates = new Map<string, Promise<void>>();
  let postFailure: Response | null = null;
  const snapshot = () => {
    const out = doneOut({ findings: structuredClone(findings) });
    (out.review as Record<string, unknown>).memo = memo;
    return out;
  };
  const { fetch } = fakeFetch(async (req) => {
    if (req.method === 'POST') {
      posts++;
      const body = req.body as { type: string; finding_id?: string; text?: string };
      const gate = postGates.get(body.finding_id ?? body.type);
      if (gate) await gate;
      if (postFailure) return postFailure;
      if (body.type === 'set_status') findings[body.finding_id as string] = { status: 'confirmed' };
      if (body.type === 'save_memo') memo = body.text ?? '';
      return json(200, { analysis: snapshot(), changed: true });
    }
    const n = ++gets;
    const value = snapshot(); // 시작할 때의 서버 값
    getStarted.get(n)?.();
    const gate = getGates.get(n);
    if (gate) await gate;
    return json(200, value);
  });
  const service = createApiService({ client: createApiClient({ fetch }), upload: async () => {}, storage: memoryStorage() });
  return {
    service,
    counts: () => ({ gets, posts }),
    /** n 번째 GET 을 풀 때까지 붙잡는다(started = 그 GET 이 시작됨) */
    holdGet(n: number) {
      const gate = deferred();
      const started = deferred();
      getGates.set(n, gate.promise);
      getStarted.set(n, started.resolve);
      return { release: gate.resolve, started: started.promise };
    },
    /** 이 항목 id(또는 type)의 POST 를 풀 때까지 붙잡는다 */
    holdPost(key: string) {
      const gate = deferred();
      postGates.set(key, gate.promise);
      return gate.resolve;
    },
    failPosts(status: number, detail: string) {
      postFailure = json(status, { detail });
    },
  };
}

/**
 * 화면 훅(useServiceQuery)처럼 구독한다 — 알림마다 get 을 다시 부르고, 마지막 요청의 응답만 반영한다.
 * byNotice[i] = i 번째 알림의 조회가 받은 값(반영 여부와 무관), state.shown = 반영된 값.
 */
function hookLike<T>(service: AnalysisService, pick: (a: Analysis) => T) {
  let ticket = 0;
  const byNotice: T[] = [];
  const runs: Promise<void>[] = [];
  const state: { shown: T | undefined } = { shown: undefined };
  service.subscribe(() => {
    const mine = ++ticket;
    runs.push(
      service.get(ID).then((a) => {
        if (!a) throw new Error('분석 없음');
        byNotice[mine - 1] = pick(a);
        if (mine === ticket) state.shown = pick(a);
      }),
    );
  });
  return { byNotice, state, settle: () => Promise.all(runs), notices: () => ticket };
}

describe('저장 성공 알림 — 저장 전에 시작한 조회를 나눠 쓰지 않는다(V-T2-1 M1)', () => {
  it('두 항목을 연이어 확인 — 두 번째 알림의 조회는 두 번째 저장 뒤 값(첫 알림의 조회를 재사용하지 않음)', async () => {
    const srv = liveServer();
    const view = hookLike(srv.service, (a) => a.findings.slice(0, 2).map((f) => f.status));
    const firstRefresh = srv.holdGet(2); // 첫 알림이 시작한 조회(첫 항목만 확인된 값)를 붙잡는다
    const releaseSecondPost = srv.holdPost('0:applicant_rrn');
    const first = srv.service.setStatus(ID, 'D1-01', 'confirmed');
    const second = srv.service.setStatus(ID, 'D1-02', 'confirmed');
    await firstRefresh.started;
    releaseSecondPost();
    await Promise.all([first, second]);
    firstRefresh.release();
    await view.settle();

    expect(view.notices()).toBe(2);
    expect(srv.counts()).toEqual({ gets: 3, posts: 2 }); // 처음 조회 1(두 동작이 나눠 씀) + 알림마다 새 조회 1
    expect(view.byNotice).toEqual([
      ['confirmed', 'open'], // 첫 알림 = 첫 저장 뒤 값
      ['confirmed', 'confirmed'], // 두 번째 알림 = 두 번째 저장 뒤 값
    ]);
    expect(view.state.shown).toEqual(['confirmed', 'confirmed']); // 마지막 요청만 반영 — 늦게 끝난 첫 조회는 버려진다
  });

  it('메모 저장 중 다른 구독자가 시작한 조회 — 알림 뒤 조회는 저장 뒤 값, 옛 조회는 그 호출자에게만', async () => {
    const srv = liveServer();
    const view = hookLike(srv.service, (a) => a.memo);
    const releasePost = srv.holdPost('save_memo');
    const oldGet = srv.holdGet(2);
    const saving = srv.service.saveMemo(ID, '저장 후');
    await vi.waitFor(() => expect(srv.counts().posts).toBe(1)); // 저장 전 조회(1)가 끝나고 POST 가 붙잡힘
    const background = srv.service.get(ID); // 다른 구독자의 조회(2)
    await oldGet.started;
    releasePost();
    await saving;
    oldGet.release();
    const bg = await background;
    await view.settle();

    expect(view.byNotice).toEqual(['저장 후']);
    expect(view.state.shown).toBe('저장 후');
    expect(bg?.memo).toBe(''); // 저장 전에 시작한 조회는 저장 전 값 — 알림 쪽과 나눠 쓰지 않았다
    expect(srv.counts()).toEqual({ gets: 3, posts: 1 });
  });

  it('알림을 받은 구독자 여럿은 저장 뒤 새 조회 하나를 나눠 쓰고, 늦게 끝난 옛 조회가 그 공유를 지우지 않는다', async () => {
    const srv = liveServer();
    const views = [0, 1, 2].map(() => hookLike(srv.service, (x) => x.memo));
    const releasePost = srv.holdPost('save_memo');
    const oldGet = srv.holdGet(2);
    const newGet = srv.holdGet(3);
    const saving = srv.service.saveMemo(ID, '새 메모');
    await vi.waitFor(() => expect(srv.counts().posts).toBe(1));
    const background = srv.service.get(ID); // 저장 전 조회(2)
    await oldGet.started;
    releasePost();
    await saving;
    await newGet.started; // 알림 뒤 조회(3) — 세 구독자가 나눠 씀
    oldGet.release();
    await background; // 옛 조회가 끝나도(finally) 새 조회의 공유 자리는 남는다
    const late = srv.service.get(ID); // 진행 중인 새 조회(3)를 나눠 쓴다
    newGet.release();
    await Promise.all([...views.map((v) => v.settle()), late]);

    expect(srv.counts()).toEqual({ gets: 3, posts: 1 });
    for (const v of views) {
      expect(v.notices()).toBe(1);
      expect(v.state.shown).toBe('새 메모');
    }
    expect((await late)?.memo).toBe('새 메모');
  });

  it('실패하면 떼지도 알리지도 않는다 — 진행 중 조회는 계속 나눠 쓴다', async () => {
    const srv = liveServer();
    const view = hookLike(srv.service, (a) => a.memo);
    srv.failPosts(409, '다른 요청과 겹쳐 저장하지 못했습니다. 잠시 후 다시 시도해 주세요.');
    const releasePost = srv.holdPost('save_memo');
    const oldGet = srv.holdGet(2);
    const saving = srv.service.saveMemo(ID, '실패할 메모').catch((e: unknown) => e);
    await vi.waitFor(() => expect(srv.counts().posts).toBe(1));
    const background = srv.service.get(ID);
    await oldGet.started;
    releasePost();
    const err = await saving;
    const after = srv.service.get(ID); // 실패 뒤 — 진행 중 조회(2)를 그대로 나눠 쓴다
    oldGet.release();
    await Promise.all([background, after]);

    expect(err).toBeInstanceOf(ApiError);
    expect(err).toMatchObject({ code: 'conflict' });
    expect(view.notices()).toBe(0);
    expect(srv.counts()).toEqual({ gets: 2, posts: 1 });
  });
});
