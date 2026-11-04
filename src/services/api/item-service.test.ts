/* 실제 분석 서비스의 검토사항 동작(resolveItem · reopenItem) · pending — 가짜 백엔드(GET 분석 · POST review-actions)로
   본문(정확한 키) · 화면 번호 → 계약 id · 요청 횟수 · 알림 · 오류를 확인한다. 고정 자료 fixtures/items-result.json(합성). */
import { describe, expect, it, vi } from 'vitest';
import { CONFIG } from '@/config/app';
import type { AnalysisService } from '../analysis-service';
import { ApiError, createApiClient } from './client';
import { MSG_NO_ANALYSIS, MSG_NO_ITEM, MSG_UNSUPPORTED, createApiService } from './service';
import { analysisOut, contractResult, fakeFetch, itemsResult, json, type SeenRequest } from './testing';

const ID = 'ab12cd34-0000-4000-8000-000000000000';
const ACTION_URL = `/api/py/analyses/${ID}/review-actions`;
const GET_URL = `/api/py/analyses/${ID}`;
const ACTOR = CONFIG.user.name;

function review(items: Record<string, unknown> = {}, findings: Record<string, unknown> = {}): Record<string, unknown> {
  return { status: 'needed', memo: '', memo_at: null, reviewer: '', reviewed_at: null, completion_note: '', findings, items, history: [], version: 0 };
}

/** 완료 + 검토사항이 든 결과 + 검토 기록 */
function doneOut(opts: { items?: Record<string, unknown>; findings?: Record<string, unknown>; result?: Record<string, unknown> } = {}) {
  return analysisOut({ status: 'done', result: opts.result ?? itemsResult(), review: review(opts.items, opts.findings) });
}

interface SetupOptions {
  get?: () => Response;
  post?: (req: SeenRequest) => Response;
}

function setup(opts: SetupOptions = {}) {
  const { fetch, seen } = fakeFetch((req) => {
    if (req.method === 'POST' && req.url === ACTION_URL) return opts.post ? opts.post(req) : json(200, { analysis: doneOut(), changed: true });
    if (req.method === 'GET' && req.url === GET_URL) return opts.get ? opts.get() : json(200, doneOut());
    return json(404, { detail: '분석 건을 찾을 수 없습니다.' });
  });
  const service: AnalysisService = createApiService({ client: createApiClient({ fetch }), upload: async () => {} });
  const notified = vi.fn();
  service.subscribe(notified);
  const posts = () => seen.filter((r) => r.method === 'POST');
  const gets = () => seen.filter((r) => r.method === 'GET');
  return { service, seen, notified, posts, gets };
}

describe('resolveItem · reopenItem — 본문 · 계약 id · 알림 한 번', () => {
  it('resolveItem — GET 한 번 뒤 POST 본문이 정확히 { type, actor, item_id, note }', async () => {
    const { service, seen, posts, notified } = setup();
    await service.resolveItem(ID, 'R-03', '원본에서 확인함');
    expect(seen.map((r) => [r.method, r.url])).toEqual([
      ['GET', GET_URL],
      ['POST', ACTION_URL],
    ]);
    const body = posts()[0].body as Record<string, unknown>;
    expect(body).toEqual({ type: 'resolve_item', actor: ACTOR, item_id: 'nolocation:2:income_info', note: '원본에서 확인함' });
    expect(Object.keys(body).sort()).toEqual(['actor', 'item_id', 'note', 'type']);
    expect(posts()[0].headers['content-type']).toBe('application/json');
    expect(notified).toHaveBeenCalledTimes(1);
    expect(notified).toHaveBeenCalledWith();
  });

  it('reopenItem — POST 본문이 정확히 { type, actor, item_id }(note 없음)', async () => {
    const { service, posts, notified } = setup({ get: () => json(200, doneOut({ items: { 'lowconf:0': { resolved: true, note: 'n', resolved_at: null, resolved_by: 'a' } } })) });
    await service.reopenItem(ID, 'R-01');
    const body = posts()[0].body as Record<string, unknown>;
    expect(body).toEqual({ type: 'reopen_item', actor: ACTOR, item_id: 'lowconf:0' });
    expect(Object.keys(body).sort()).toEqual(['actor', 'item_id', 'type']);
    expect(notified).toHaveBeenCalledTimes(1);
  });

  it('처리 내용은 받은 그대로(빈 글 · 줄바꿈 · 앞뒤 공백 — 다듬기는 화면이 한다)', async () => {
    const { service, posts } = setup();
    await service.resolveItem(ID, 'R-08', '');
    await service.resolveItem(ID, 'R-08', '  둘째\n줄  ');
    expect(posts().map((p) => (p.body as { note: string }).note)).toEqual(['', '  둘째\n줄  ']);
    expect(posts().every((p) => (p.body as { item_id: string }).item_id === 'other:5')).toBe(true);
  });

  it('처리자는 CONFIG.user.name', async () => {
    const { service, posts } = setup();
    await service.resolveItem(ID, 'R-01', '확인');
    expect((posts()[0].body as { actor: string }).actor).toBe(CONFIG.user.name);
    expect(CONFIG.user.name.length).toBeGreaterThan(0);
  });

  it('계약 id 에 따옴표 · / · ? · # · 짝 없는 서로게이트 · \\u0000 이 있어도 본문에 그대로(주소는 분석 id 만)', async () => {
    const odd = 'missing:1:a/b"c\ud800\u0000?#';
    const r = itemsResult();
    (r.items as { id: string }[])[1].id = odd;
    const { service, posts } = setup({ get: () => json(200, doneOut({ result: r })) });
    await service.resolveItem(ID, 'R-02', '확인');
    expect(posts()[0].url).toBe(ACTION_URL);
    expect((posts()[0].body as { item_id: string }).item_id).toBe(odd);
  });

  it('같은 분석을 동시에 바꾸면 조회 하나를 나눠 쓴다(요청 · 알림은 동작마다)', async () => {
    const { service, gets, posts, notified } = setup();
    await Promise.all([service.resolveItem(ID, 'R-01', 'a'), service.reopenItem(ID, 'R-02'), service.resolveItem(ID, 'R-05', 'b')]);
    expect(gets()).toHaveLength(1);
    expect(posts().map((p) => (p.body as { type: string }).type).sort()).toEqual(['reopen_item', 'resolve_item', 'resolve_item']);
    expect(notified).toHaveBeenCalledTimes(3);
  });

  it('성공 뒤 조회는 새로 보낸다(쓰기 전에 시작한 조회를 나눠 쓰지 않는다)', async () => {
    const { service, gets } = setup();
    await service.resolveItem(ID, 'R-01', 'a');
    await service.get(ID);
    expect(gets()).toHaveLength(2);
  });
});

describe('없는 검토사항 · 없는 분석', () => {
  it('없는 화면 번호(R-99 · 계약 id · 빈 글 · 탐지 번호 · 소문자) → 요청 없이 MSG_NO_ITEM, 알림 없음', async () => {
    const { service, posts, notified } = setup();
    const results = await Promise.allSettled([
      service.resolveItem(ID, 'R-99', '확인'),
      service.resolveItem(ID, 'lowconf:0', '확인'),
      service.reopenItem(ID, ''),
      service.reopenItem(ID, 'D1-01'),
      service.resolveItem(ID, 'r-01', '확인'),
    ]);
    for (const r of results) {
      expect(r.status).toBe('rejected');
      const reason = (r as PromiseRejectedResult).reason;
      expect(reason).not.toBeInstanceOf(ApiError);
      expect(reason.message).toBe(MSG_NO_ITEM);
    }
    expect(MSG_NO_ITEM).toBe('검토사항을 찾을 수 없습니다.');
    expect(posts()).toHaveLength(0);
    expect(notified).not.toHaveBeenCalled();
  });

  it('옛 결과(items 없음)면 어떤 번호도 없다 — 요청 없이 MSG_NO_ITEM', async () => {
    const { service, posts } = setup({ get: () => json(200, doneOut({ result: contractResult() })) });
    await expect(service.resolveItem(ID, 'R-01', '확인')).rejects.toThrow(MSG_NO_ITEM);
    await expect(service.reopenItem(ID, 'R-01')).rejects.toThrow(MSG_NO_ITEM);
    expect(posts()).toHaveLength(0);
  });

  it('없는 분석(GET 404) → 요청 없이 ApiError(not_found · MSG_NO_ANALYSIS), 동작마다 알림 한 번', async () => {
    const { service, posts, notified } = setup({ get: () => json(404, { detail: '분석 건을 찾을 수 없습니다.' }) });
    const results = await Promise.allSettled([service.resolveItem(ID, 'R-01', '확인'), service.reopenItem(ID, 'R-01')]);
    for (const r of results) {
      const reason = (r as PromiseRejectedResult).reason;
      expect(reason).toBeInstanceOf(ApiError);
      expect(reason).toMatchObject({ status: 404, code: 'not_found', message: MSG_NO_ANALYSIS });
    }
    expect(posts()).toHaveLength(0);
    expect(notified).toHaveBeenCalledTimes(2);
  });

  it('분석 조회가 502 면 그 오류로 · 요청 · 알림 없음', async () => {
    const { service, posts, notified } = setup({ get: () => json(502, { detail: '저장소 오류' }) });
    const err = await service.resolveItem(ID, 'R-01', 'x').catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err).toMatchObject({ code: 'server', message: '저장소 오류' });
    expect(posts()).toHaveLength(0);
    expect(notified).not.toHaveBeenCalled();
  });
});

describe('요청 실패 — 409 · 404 는 떼고 한 번 알린 뒤 같은 오류, 그 밖은 알리지 않는다', () => {
  const failures: [number, string, string][] = [
    [409, 'conflict', '검토사항 상태가 바뀌었습니다. 새로 고친 뒤 다시 시도해 주세요.'],
    [409, 'conflict', '검토를 완료한 분석은 바꿀 수 없습니다.'],
    [409, 'conflict', '검토할 수 없는 분석입니다.'],
    [404, 'not_found', '검토사항을 찾을 수 없습니다.'],
    [404, 'not_found', '분석 건을 찾을 수 없습니다.'],
    [400, 'bad_request', '메모·사유는 500자 이하로 적어 주세요.'],
    [413, 'bad_request', '요청 본문이 너무 큽니다.'],
    [502, 'server', '서버 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.'],
  ];
  for (const [status, code, detail] of failures) {
    const notifies = code === 'conflict' || code === 'not_found';
    for (const which of ['resolve', 'reopen'] as const) {
      it(`${which} ${status} → ${notifies ? '알림 한 번' : '알림 없음'} · ApiError(${code}) — ${detail}`, async () => {
        const { service, notified, gets } = setup({ post: () => json(status, { detail }) });
        const call = which === 'resolve' ? service.resolveItem(ID, 'R-01', '확인') : service.reopenItem(ID, 'R-01');
        const err = await call.catch((e: unknown) => e);
        expect(err).toBeInstanceOf(ApiError);
        expect(err).toMatchObject({ status, code, message: detail });
        expect(notified).toHaveBeenCalledTimes(notifies ? 1 : 0);
        // 떼었으면 다음 조회는 새 요청
        await service.get(ID);
        expect(gets()).toHaveLength(2);
      });
    }
  }

  it('네트워크 오류 → 알림 없이 network', async () => {
    const { service, notified } = setup({
      post: () => {
        throw new TypeError('Failed to fetch');
      },
    });
    await expect(service.resolveItem(ID, 'R-01', '확인')).rejects.toMatchObject({ code: 'network', status: 0 });
    await expect(service.reopenItem(ID, 'R-01')).rejects.toMatchObject({ code: 'network', status: 0 });
    expect(notified).not.toHaveBeenCalled();
  });

  it('연결 판단은 계속 거절(요청 없음)', async () => {
    const { service, seen } = setup();
    await expect(service.decideLink(ID, 'L-01', 'linked', '근거')).rejects.toThrow(MSG_UNSUPPORTED);
    expect(seen).toHaveLength(0);
  });
});

describe('pending — 미확인 탐지 항목 · 미해결 검토사항(연결은 늘 빈 목록)', () => {
  const allConfirmed = () => Object.fromEntries((itemsResult().findings as { id: string }[]).map((f) => [f.id, { status: 'confirmed' }]));

  it('미해결 검토사항만 openI(서버 순서) · any', async () => {
    const { service, posts } = setup({
      get: () => json(200, doneOut({ items: { 'missing:1:applicant_name_detected': { resolved: true }, 'other:5': { resolved: true }, 'lowconf:3': { resolved: 'true' } } })),
    });
    const p = await service.pending(ID);
    expect(p.openI.map((i) => i.id)).toEqual(['R-01', 'R-03', 'R-04', 'R-05', 'R-06', 'R-07']);
    expect(p.openI.every((i) => !i.resolved)).toBe(true);
    expect(p.openF).toHaveLength(19);
    expect(p.openL).toEqual([]);
    expect(p.any).toBe(true);
    expect(posts()).toHaveLength(0);
  });

  it('탐지 항목을 모두 확인해도 미해결 검토사항이 있으면 any true', async () => {
    const { service } = setup({ get: () => json(200, doneOut({ findings: allConfirmed() })) });
    const p = await service.pending(ID);
    expect(p.openF).toEqual([]);
    expect(p.openI).toHaveLength(8);
    expect(p.any).toBe(true);
  });

  it('둘 다 없으면 any false', async () => {
    const items = Object.fromEntries((itemsResult().items as { id: string }[]).map((i) => [i.id, { resolved: true }]));
    const { service } = setup({ get: () => json(200, doneOut({ items, findings: allConfirmed() })) });
    expect(await service.pending(ID)).toEqual({ openF: [], openI: [], openL: [], any: false });
  });

  it('검토사항이 없는 옛 결과 · 없는 분석 → openI []', async () => {
    const old = setup({ get: () => json(200, doneOut({ result: contractResult() })) });
    expect((await old.service.pending(ID)).openI).toEqual([]);
    const missing = setup({ get: () => json(404, { detail: '분석 건을 찾을 수 없습니다.' }) });
    expect(await missing.service.pending(ID)).toEqual({ openF: [], openI: [], openL: [], any: false });
  });
});
