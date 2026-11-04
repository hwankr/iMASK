/* 보고서를 그릴지(reportGate) · 실제 분석 보고서 안내(LiveReportNotice — 두 제목과 '상세로 가기') */
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { LiveReportNotice, REPORT_UNAVAILABLE_TITLE, REPORT_WAITING_TITLE } from '@/components/live/LiveReportNotice';
import { detailHref } from '@/lib/routes';
import { createService } from '@/services';
import { toAnalysis } from '@/services/api/mapping';
import { analysisOut, contractResult } from '@/services/api/testing';
import { ServiceProvider, type ServiceProviderProps } from '@/services/react';
import { reportGate } from './reportGate';

const NEW_REVIEW = { status: 'needed', memo: '', memo_at: null, reviewer: '', reviewed_at: null, completion_note: '', findings: {}, history: [], version: 1 };
const ID = 'ab12cd34-0000-4000-8000-000000000000';

describe('reportGate', () => {
  it('대기 · 분석 중 → waiting', () => {
    expect(reportGate(toAnalysis(analysisOut({ status: 'queued' })))).toBe('waiting');
    expect(reportGate(toAnalysis(analysisOut({ status: 'running', upstage_job_id: 'job_x' })))).toBe('waiting');
    // 모르는 상태 값은 매핑이 queued 로 읽는다
    expect(reportGate(toAnalysis(analysisOut({ status: 'weird' as never })))).toBe('waiting');
  });

  it('실패 · 일부 실패 · 옛 형식 완료 → unavailable (검토 기록이 와도)', () => {
    expect(reportGate(toAnalysis(analysisOut({ status: 'failed', error: '실패', review: NEW_REVIEW })))).toBe('unavailable');
    expect(reportGate(toAnalysis(analysisOut({ status: 'partial', error: '일부', result: contractResult(), review: NEW_REVIEW })))).toBe('unavailable');
    expect(reportGate(toAnalysis(analysisOut({ status: 'done', result: { format: 'imask-upstage-v1', summary: { risk_level: '상' } }, review: NEW_REVIEW })))).toBe(
      'unavailable',
    );
    expect(reportGate(toAnalysis(analysisOut({ status: 'done', result: null })))).toBe('unavailable');
  });

  it('공통 계약 결과 + 검토 기록 null(reviewable false) → loadFailed', () => {
    const a = toAnalysis(analysisOut({ status: 'done', result: contractResult(), review: null }));
    expect(a.raw?.detailReady).toBe(true);
    expect(a.raw?.reviewable).toBe(false);
    expect(reportGate(a)).toBe('loadFailed');
  });

  it('보고서 대상(완료 + 공통 계약 결과 + 검토 기록) → report — 검토 완료여도', () => {
    expect(reportGate(toAnalysis(analysisOut({ status: 'done', result: contractResult(), review: NEW_REVIEW })))).toBe('report');
    expect(reportGate(toAnalysis(analysisOut({ status: 'done', result: contractResult(), review: { ...NEW_REVIEW, status: 'done', reviewer: '이지은' } })))).toBe('report');
  });

  it('데모 분석은 어떤 상태든 report(지금 그대로)', async () => {
    const svc = createService();
    for (const id of ['A1', 'A3', 'A5', 'A6']) {
      const a = await svc.get(id);
      if (!a) throw new Error(id);
      expect(reportGate(a), id).toBe('report');
    }
  });
});

describe('LiveReportNotice', () => {
  const render = (kind: 'waiting' | 'unavailable') =>
    renderToStaticMarkup(
      createElement(ServiceProvider as (p: Omit<ServiceProviderProps, 'children'>) => ReturnType<typeof ServiceProvider>, { service: createService() }, createElement(LiveReportNotice, { id: ID, kind })),
    );

  it('대기 · 분석 중 제목 + 상세로 가기(기준 경로 함수로 만든 상세 주소), 설명 문단 없음', () => {
    const html = render('waiting');
    expect(html).toContain(`<h1 class="`);
    expect(html).toContain(`>${REPORT_WAITING_TITLE}</h1>`);
    expect(REPORT_WAITING_TITLE).toBe('분석이 끝나면 보고서를 볼 수 있습니다');
    expect(html).toContain(`href="${detailHref('', ID)}"`);
    expect(html).toContain('상세로 가기');
    expect(html).not.toContain('<p');
    expect(html).not.toContain('아직');
  });

  it('실패 · 일부 실패 · 옛 형식 제목', () => {
    const html = render('unavailable');
    expect(REPORT_UNAVAILABLE_TITLE).toBe('보고서를 만들 수 없는 분석입니다');
    expect(html).toContain(`>${REPORT_UNAVAILABLE_TITLE}</h1>`);
    expect(html).toContain(`href="/analyses/${ID}"`);
  });
});
