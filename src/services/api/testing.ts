/* ==========================================================================
   테스트 도우미(실제 분석 서비스) — 가짜 fetch · AnalysisOut · 목록 항목 만들기 · 계약 모양 결과(고정 자료).
   앱 코드는 import 하지 않는다(테스트 전용).
   고정 자료 fixtures/done-result.json = 합성 묶음(testdocs/iMASK_smoke_bundle.pdf, 6쪽 = 서류 6개)의 공통 계약
   result(stages 없음). 다음 작업의 가짜 백엔드도 같은 파일을 읽는다. items 키가 없다(옛 결과 = 검토사항 0개).
   고정 자료 fixtures/items-result.json = 위 자료의 사본 + 서버가 계산한 검토사항 result.items 8개(BRIEF §5.3 글 · 근거 규칙):
   서류 index 1 이 필수 항목 검증에 실패했다고 보고 validation 'red' + missing 1개, 나머지는 위 자료에서 규칙대로 나오는
   lowconf 4 · nolocation 2 · other 1(검증 checks 는 result 에 없으므로 missing 은 응답 모양으로만 넣었다). 항목마다 link_id null.
   고정 자료 fixtures/final-flow-result.json = 최종 흐름 워크플로우 결과를 손으로 만든 것(스펙 T3 A·B 계약 모양 — 값은 지어낸 것):
   서류 5개(자동이체 신청서 · FATCA/CRS 본인확인서 · 소득 증빙(2쪽) · 위임장 · 기타), 탐지 7개(위치 없음 2), 검토사항 8개
   (missing · nolocation · lowconf · mismatch(link_id) · weaklink(link_id) · other), 연결 3개(check 2 · confirmed 1), decision, bundle_check.
   키 · 꼴은 백엔드 실제 출력과 같다(tests/test_final_flow_fixture_sync.py).
   고정 자료 fixtures/final-flow-{C,D,E}.json = 최종 흐름 고정 응답(tests/fixtures/final_flow/)을 **백엔드가 만든** 조회 응답 result 그대로
   (tests/test_final_flow_fixture_sync.py 가 바이트까지 같은지 지킨다 — 손으로 고치지 않는다):
   C 불일치(mismatch · linked) · D 빈 신청인(weaklink · missing) · E 팀원 서식(linked 2 · other).
   ========================================================================== */

import type { AnalysisListItemOut, AnalysisOut, DocumentOut } from './client';
import doneResultFixture from './fixtures/done-result.json';
import finalFlowCFixture from './fixtures/final-flow-C.json';
import finalFlowDFixture from './fixtures/final-flow-D.json';
import finalFlowEFixture from './fixtures/final-flow-E.json';
import finalFlowResultFixture from './fixtures/final-flow-result.json';
import itemsResultFixture from './fixtures/items-result.json';

/** 가짜 fetch 가 받은 요청 */
export interface SeenRequest {
  url: string;
  method: string;
  headers: Record<string, string>;
  body: unknown;
}

export type FakeRoute = (req: SeenRequest) => Response | Promise<Response>;

/** JSON 응답 */
export function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
}

/** 요청을 기록하고 route 로 답하는 가짜 fetch */
export function fakeFetch(route: FakeRoute): { fetch: typeof fetch; seen: SeenRequest[] } {
  const seen: SeenRequest[] = [];
  const f = (async (input: RequestInfo | URL, init?: RequestInit) => {
    const headers: Record<string, string> = {};
    new Headers(init?.headers).forEach((v, k) => {
      headers[k] = v;
    });
    const req: SeenRequest = {
      url: String(input),
      method: init?.method ?? 'GET',
      headers,
      body: typeof init?.body === 'string' ? JSON.parse(init.body) : undefined,
    };
    seen.push(req);
    return route(req);
  }) as typeof fetch;
  return { fetch: f, seen };
}

/** documents 행 */
export function documentOut(patch: Partial<DocumentOut> = {}): DocumentOut {
  return {
    id: 'd0c00000-0000-4000-8000-000000000001',
    filename: 'iMASK_smoke_bundle.pdf',
    size_bytes: 322053,
    mime_type: 'application/pdf',
    upstage_file_id: null,
    created_at: '2026-11-02T05:10:00.123456+00:00',
    ...patch,
  };
}

/** 완료된 합성 묶음의 result(요약 + 단계 몇 개) */
export function doneResult(): Record<string, unknown> {
  return {
    format: 'imask-upstage-v1',
    job: { id: 'job_test', status: 'completed', config_id: '3', created_at: 1, usage: null },
    summary: {
      stage_names: ['step_1_parse', 'step_2_classify'],
      stage_counts: { step_1_parse: 1 },
      document_count: 6,
      document_types: ['loan_application', 'consent_form', 'income_proof', 'power_of_attorney', 'debt_transaction', 'Other'],
      extracted_document_count: 5,
      risk_level: '상',
      final_stage: '권장_조치',
      other_document_count: 1,
    },
    stages: [
      { name: 'step_1_parse', key: '서류-인식', step_type: 'parse', status: 'completed', data: { content: '# 제목' }, additional_values: null, contents: [] },
      { name: 'Information Extract - 민감정보_추출', key: '민감정보_추출', status: 'completed', data: { 성명: '홍길동' }, additional_values: { 성명: { confidence: 0.9 } }, contents: [{}, {}] },
      { name: 'Information Extract - 민감정보_추출', key: '민감정보_추출', status: 'completed', data: {}, additional_values: null, contents: [] },
      { name: 'Instruct - 권장_조치', key: null, status: 'failed', data: '문장', additional_values: null, contents: [] },
    ],
  };
}

/** 공통 계약 모양의 완료 결과(fixtures/done-result.json) — 깊은 복사본이라 고쳐도 다른 테스트에 번지지 않는다 */
export function contractResult(): Record<string, unknown> {
  return structuredClone(doneResultFixture) as unknown as Record<string, unknown>;
}

/** 검토사항이 든 공통 계약 결과(fixtures/items-result.json) — 깊은 복사본 */
export function itemsResult(): Record<string, unknown> {
  return structuredClone(itemsResultFixture) as unknown as Record<string, unknown>;
}

/** 최종 흐름 워크플로우 결과(fixtures/final-flow-result.json — 손으로 만든 모양) — 깊은 복사본 */
export function finalFlowResult(): Record<string, unknown> {
  return structuredClone(finalFlowResultFixture) as unknown as Record<string, unknown>;
}

const FINAL_FLOW_RUNS = { C: finalFlowCFixture, D: finalFlowDFixture, E: finalFlowEFixture } as const;

/** 백엔드가 고정 응답으로 만든 최종 흐름 결과(fixtures/final-flow-{C,D,E}.json) — 깊은 복사본 */
export function finalFlowRun(key: keyof typeof FINAL_FLOW_RUNS): Record<string, unknown> {
  return structuredClone(FINAL_FLOW_RUNS[key]) as unknown as Record<string, unknown>;
}

/** AnalysisOut */
export function analysisOut(patch: Partial<AnalysisOut> = {}): AnalysisOut {
  return {
    id: 'ab12cd34-0000-4000-8000-000000000000',
    name: '합성 묶음',
    status: 'queued',
    upstage_job_id: null,
    error: null,
    result: null,
    // 서울 2026-11-02 14:10
    created_at: '2026-11-02T05:10:00.123456+00:00',
    updated_at: '2026-11-02T05:10:34.900000+00:00',
    documents: [documentOut()],
    upstage_status: null,
    poll_error: null,
    ...patch,
  };
}

/** GET /analyses 항목 */
export function listItemOut(patch: Partial<AnalysisListItemOut> = {}): AnalysisListItemOut {
  return {
    id: 'ab12cd34-0000-4000-8000-000000000000',
    name: '합성 묶음',
    status: 'queued',
    error: null,
    created_at: '2026-11-02T05:10:00.123456+00:00',
    updated_at: '2026-11-02T05:10:34.900000+00:00',
    started_at: null,
    documents: [{ filename: 'iMASK_smoke_bundle.pdf', size_bytes: 322053, mime_type: 'application/pdf' }],
    risk_level: null,
    review: 'none',
    ...patch,
  };
}
