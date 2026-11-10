/* ④ 데모 서비스 테스트 — 비동기 겉면(AnalysisService + DemoControls)을 실제 화면이 쓰는 방식으로 부른다.
   기대값은 프로토타입(Main.dc.html ③·④)의 값이다. 타이머는 가짜 타이머로 진행한다. */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { CONFIG } from '@/config/app';
import { FP_REASONS } from '@/display/rules';
import type { ServiceEvent, StateId } from '../analysis-service';
import { ApiError } from '../api/client';
import { getDemoControls } from '../index';
import type { Analysis, Highlight, PageBlock, UploadFile } from '../types';
import { createDemoService, isDemoService, type DemoService } from './index';

let svc: DemoService;

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date(2026, 10, 1, 10, 0, 0)); // 2026-11-01 10:00(로컬)
  svc = createDemoService();
});

afterEach(() => {
  svc.dispose();
  vi.useRealTimers();
});

const must = async (id: string): Promise<Analysis> => {
  const a = await svc.get(id);
  if (!a) throw new Error('no analysis ' + id);
  return a;
};
const finding = (a: Analysis, id: string) => a.findings.find((f) => f.id === id)!;
const item = (a: Analysis, id: string) => a.items.find((i) => i.id === id)!;
const link = (a: Analysis, id: string) => a.links.find((l) => l.id === id)!;
const lastLog = (a: Analysis) => a.history[a.history.length - 1];
const userFile = (name: string, ext: string, size: number): UploadFile => ({ id: 'f-' + name, name, ext, size, kind: 'user', state: 'ready', error: '' });

describe('1. list() — 샘플 6건과 미리 해 둔 검토 동작', () => {
  it('A1~A6 을 프로토타입 값으로 돌려준다', async () => {
    const list = await svc.list();
    const summary = list.map((a) => [a.id, a.code, a.status, a.risk, a.review, a.docs.length, a.findings.length, a.items.length, a.links.length]);
    expect(summary).toEqual([
      ['A1', 'IM-20261030-0007', 'done', 'high', 'needed', 3, 23, 5, 3],
      ['A2', 'IM-20261029-0003', 'done', 'medium', 'none', 2, 6, 0, 1],
      ['A3', 'IM-20261031-0002', 'running', 'unrated', 'none', 3, 0, 0, 0],
      ['A4', 'IM-20261030-0002', 'partial', 'high', 'needed', 3, 7, 2, 1],
      ['A5', 'IM-20261028-0011', 'done', 'low', 'done', 1, 4, 0, 0],
      ['A6', 'IM-20261030-0011', 'failed', 'unrated', 'needed', 1, 0, 1, 0],
    ]);
    expect(list.map((a) => a.name)).toEqual(['대출상담 서류 묶음', '소득증빙 확인', '신규 접수 서류', '거래내역 스캔본', '마스킹된 상담 서류', '손상된 문서 파일']);
    // 첫 이력(분석 요청 · 최초 AI 결과)
    expect(list[0].history.slice(0, 2)).toEqual([
      { id: 'S1', at: '2026-10-30 14:22', actor: CONFIG.user.name, kind: 'request', target: '분석 건', change: '문서 3개 분석 요청', reason: '' },
      { id: 'S2', at: '2026-10-30 14:31', actor: '시스템', kind: 'ai', target: '분석 건', change: '분석 완료 · 탐지 23건 · 위험등급 상 · 검토사항 5건', reason: '' },
    ]);
    expect(list[3].history[1].change).toBe('분석 일부 실패 · 문서 1개 실패 · 탐지 7건 · 위험등급 상 · 검토사항 2건');
    expect(list[5].history[1].change).toBe('분석 실패 · 파일을 열 수 없음 · 위험등급 미평가');
    expect(list[2].history.map((h) => h.kind)).toEqual(['request']); // 분석 중 — AI 결과 없음
  });

  it('seedReviewActions 가 적용되어 있다(A1 F-01 · F-10 · F-12, A5 검토 완료)', async () => {
    const a1 = await must('A1');
    expect(finding(a1, 'F-01')).toMatchObject({ status: 'confirmed', memo: '원본 보관 전 마스킹 사본으로 교체 필요', updatedAt: '2026-10-30 16:05' });
    expect(finding(a1, 'F-10')).toMatchObject({ status: 'false_positive', fpType: FP_REASONS[0], fpNote: '은행 양식 관리번호로 개인 계좌번호가 아님', updatedAt: '2026-10-30 16:10' });
    expect(finding(a1, 'F-12')).toMatchObject({ status: 'reclassified', subject: '기타 · 은행 직원', reclassNote: '상담 직원 서명란에 적힌 직원 성명' });
    expect(finding(a1, 'F-12').ai).toEqual({ cat: '이름', subject: '신청인', exposure: '전체 노출' }); // 최초 AI 결과는 그대로
    expect(a1.history.slice(2).map((h) => [h.id, h.at, h.kind, h.target, h.change, h.reason])).toEqual([
      ['H101', '2026-10-30 16:05', 'confirm', 'F-01 고유식별정보', '미확인 → 확인함', ''],
      ['H102', '2026-10-30 16:05', 'fmemo', 'F-01 고유식별정보', '항목 메모 저장', '원본 보관 전 마스킹 사본으로 교체 필요'],
      ['H103', '2026-10-30 16:10', 'fp', 'F-10 계좌번호 형식 숫자열', '계좌번호 → 오탐 (개인정보가 아닌 번호·문구)', '은행 양식 관리번호로 개인 계좌번호가 아님'],
      ['H104', '2026-10-30 16:14', 'reclass', 'F-12 서명란 성명', '정보주체: 신청인 → 기타 · 은행 직원', '상담 직원 서명란에 적힌 직원 성명'],
    ]);

    const a5 = await must('A5');
    expect(a5.findings.map((f) => [f.id, f.status])).toEqual([['P-01', 'confirmed'], ['P-02', 'confirmed'], ['P-03', 'confirmed'], ['P-04', 'confirmed']]);
    expect(a5).toMatchObject({ review: 'done', reviewer: CONFIG.user.name, reviewedAt: '2026-10-29 09:12', memo: '모든 개인정보가 원본에서 가려져 있어 추가 조치가 필요하지 않습니다.', memoAt: '2026-10-29 09:11' });
    expect(a5.history.slice(2).map((h) => [h.at, h.kind, h.change])).toEqual([
      ['2026-10-29 09:10', 'confirm', '미확인 → 확인함'],
      ['2026-10-29 09:11', 'memo', '검토 메모 저장'],
      ['2026-10-29 09:12', 'complete', '미검토 → 검토 완료'],
    ]);
  });
});

describe('2. 조회 결과는 깊은 복사본', () => {
  it('돌려받은 객체를 고쳐도 다음 get() · list() 결과는 그대로다', async () => {
    const before = await must('A1');
    const copy = await must('A1');
    copy.name = '바뀐 이름';
    copy.findings[0].status = 'false_positive';
    copy.findings[0].ai.cat = '주소';
    copy.history.push({ ...copy.history[0], id: 'X' });
    (copy.docs[0].pages![0][2] as Extract<PageBlock, { t: 'kv' }>).items[0][0] = '바뀜';
    const list = await svc.list();
    list.pop();
    list[0].review = 'done';
    const pend = await svc.pending('A1');
    pend.openF.length = 0;
    const files = await svc.sampleFiles();
    files[0].name = 'x.pdf';

    expect(await svc.get('A1')).toEqual(before);
    expect(await svc.list()).toHaveLength(6);
    expect((await svc.pending('A1')).openF).toHaveLength(20);
    expect((await svc.sampleFiles())[0].name).toBe('개인여신거래신청서_20261029.pdf');
    expect(await svc.get('A1')).not.toBe(await svc.get('A1'));
  });

  it('없는 ID 는 null, 없는 분석의 pending 은 빈 목록', async () => {
    expect(await svc.get('A999')).toBeNull();
    expect(await svc.pending('A999')).toEqual({ openF: [], openI: [], openL: [], any: false });
  });
});

describe('3. 탐지 항목 검토 동작', () => {
  it('confirmMany 는 미확인만 바꾸고 이력을 하나만 남긴다', async () => {
    const n = (await must('A1')).history.length;
    await svc.confirmMany('A1', ['F-01', 'F-02', 'F-10', 'F-03', 'F-12', 'F-99']);
    const a = await must('A1');
    expect(['F-01', 'F-02', 'F-03', 'F-10', 'F-12'].map((id) => finding(a, id).status)).toEqual(['confirmed', 'confirmed', 'confirmed', 'false_positive', 'reclassified']);
    expect(finding(a, 'F-02').updatedAt).toBe('2026-11-01 10:00');
    expect(a.history).toHaveLength(n + 1);
    expect(lastLog(a)).toMatchObject({ kind: 'confirm', actor: CONFIG.user.name, at: '2026-11-01 10:00', target: '탐지 항목 2건', change: '미확인 → 확인함', reason: 'F-02, F-03' });
    // 바꿀 것이 없으면 이력도 없다
    await svc.confirmMany('A1', ['F-01', 'F-02']);
    expect((await must('A1')).history).toHaveLength(n + 1);
  });

  it('setStatus 는 확인함 · 미확인을 오가며 이력을 남긴다', async () => {
    await svc.setStatus('A1', 'F-01', 'open', '다시 확인 필요');
    const a = await must('A1');
    expect(finding(a, 'F-01').status).toBe('open');
    expect(lastLog(a)).toMatchObject({ kind: 'unconfirm', target: 'F-01 고유식별정보', change: '확인함 → 미확인', reason: '다시 확인 필요' });
  });

  it('markFalsePositive → restore: 분류를 고친 적이 없으면 미확인으로', async () => {
    await svc.markFalsePositive('A1', 'F-02', '다른 정보 종류를 잘못 인식', '메모 A');
    let a = await must('A1');
    expect(finding(a, 'F-02')).toMatchObject({ status: 'false_positive', fpType: '다른 정보 종류를 잘못 인식', fpNote: '메모 A' });
    expect(lastLog(a)).toMatchObject({ kind: 'fp', target: 'F-02 신청인 성명', change: '이름 → 오탐 (다른 정보 종류를 잘못 인식)', reason: '메모 A' });

    await svc.restore('A1', 'F-02', '오탐 아님');
    a = await must('A1');
    expect(finding(a, 'F-02')).toMatchObject({ status: 'open', fpType: '', fpNote: '' });
    expect(lastLog(a)).toMatchObject({ kind: 'restore', change: '오탐 → 미확인', reason: '오탐 아님' });
  });

  it('markFalsePositive → restore: 분류를 고친 적이 있으면 분류 수정으로', async () => {
    await svc.markFalsePositive('A1', 'F-12', '기타', '');
    await svc.restore('A1', 'F-12');
    const a = await must('A1');
    expect(finding(a, 'F-12').status).toBe('reclassified');
    expect(lastLog(a)).toMatchObject({ kind: 'restore', target: 'F-12 서명란 성명', change: '오탐 → 분류 수정', reason: '' });
  });

  it('reclassify: 바뀐 것만 기록하고, 바뀐 것이 없으면 false', async () => {
    const n = (await must('A1')).history.length;
    expect(await svc.reclassify('A1', 'F-03', { cat: '연락처·이메일', subject: '신청인' }, '같음')).toBe(false);
    expect((await must('A1')).history).toHaveLength(n);
    expect(await svc.reclassify('A1', 'F-99', { cat: '주소' }, '없음')).toBe(false);

    expect(await svc.reclassify('A1', 'F-03', { cat: '기타 개인정보', subject: '보증인', exposure: '전체 노출' }, '보증인 번호')).toBe(true);
    const a = await must('A1');
    expect(finding(a, 'F-03')).toMatchObject({ status: 'reclassified', cat: '기타 개인정보', subject: '보증인', exposure: '전체 노출', reclassNote: '보증인 번호' });
    expect(finding(a, 'F-03').ai).toEqual({ cat: '연락처·이메일', subject: '신청인', exposure: '전체 노출' });
    expect(lastLog(a)).toMatchObject({ kind: 'reclass', target: 'F-03 휴대전화번호', change: '정보 종류: 연락처·이메일 → 기타 개인정보, 정보주체: 신청인 → 보증인', reason: '보증인 번호' });
  });

  it('saveFindingMemo: 저장 · 삭제', async () => {
    await svc.saveFindingMemo('A1', 'F-05', '주소 가림 필요');
    let a = await must('A1');
    expect(finding(a, 'F-05').memo).toBe('주소 가림 필요');
    expect(lastLog(a)).toMatchObject({ kind: 'fmemo', target: 'F-05 주소', change: '항목 메모 저장', reason: '주소 가림 필요' });
    await svc.saveFindingMemo('A1', 'F-05', '');
    a = await must('A1');
    expect(finding(a, 'F-05').memo).toBe('');
    expect(lastLog(a)).toMatchObject({ change: '항목 메모 삭제', reason: '' });
  });
});

describe('4. 검토사항 · 문서 간 연결', () => {
  it('resolveItem / reopenItem', async () => {
    await svc.resolveItem('A1', 'R-01', '재스캔 요청');
    let a = await must('A1');
    expect(item(a, 'R-01')).toMatchObject({ resolved: true, note: '재스캔 요청', resolvedAt: '2026-11-01 10:00', resolvedBy: CONFIG.user.name });
    expect(lastLog(a)).toMatchObject({ kind: 'resolve', target: 'R-01 판독 불가', change: '미해결 → 해결', reason: '재스캔 요청' });

    await svc.reopenItem('A1', 'R-01');
    a = await must('A1');
    expect(item(a, 'R-01').resolved).toBe(false);
    expect(lastLog(a)).toMatchObject({ kind: 'reopenItem', target: 'R-01 판독 불가', change: '해결 → 미해결', reason: '' });
  });

  it('decideLink 는 그 연결에 묶인 검토사항을 함께 해결한다', async () => {
    const n = (await must('A1')).history.length;
    await svc.decideLink('A1', 'L-02', 'linked', '고객 통화로 확인');
    let a = await must('A1');
    expect(link(a, 'L-02')).toMatchObject({ decision: 'linked', decisionNote: '고객 통화로 확인', decidedAt: '2026-11-01 10:00', decidedBy: CONFIG.user.name });
    expect(item(a, 'R-04')).toMatchObject({ resolved: true, note: '문서 간 연결 판단(연결 맞음) — 고객 통화로 확인', resolvedBy: CONFIG.user.name });
    expect(a.history.slice(n).map((h) => [h.kind, h.target, h.change, h.reason])).toEqual([
      ['link', 'L-02 이름만 같은 신청서와 거래내역서', '같은 사람 · 같은 건으로 판단', '고객 통화로 확인'],
      ['resolve', 'R-04 연결 근거 부족', '미해결 → 해결 (연결 판단 반영)', '고객 통화로 확인'],
    ]);

    // 묶인 검토사항이 없는 연결은 연결 판단만 남긴다
    await svc.decideLink('A1', 'L-03', 'unlinked', '관계없음');
    a = await must('A1');
    expect(link(a, 'L-03').decision).toBe('unlinked');
    expect(a.history.slice(n + 2).map((h) => [h.kind, h.change])).toEqual([['link', '연결 아님으로 판단']]);
  });
});

describe('5. pending · 검토 완료 · 다시 열기', () => {
  it('pending() 개수', async () => {
    const p = await svc.pending('A1');
    expect([p.openF.length, p.openI.length, p.openL.length, p.any]).toEqual([20, 5, 2, true]);
    expect(p.openL.map((l) => l.id)).toEqual(['L-02', 'L-03']);
    expect(await svc.pending('A5')).toEqual({ openF: [], openI: [], openL: [], any: false });
  });

  it('completeReview 는 남은 항목을 이력에 적고, reopenReview 로 다시 연다', async () => {
    await svc.completeReview('A1', '나머지는 원본 확인 후 보완');
    let a = await must('A1');
    expect(a).toMatchObject({ review: 'done', reviewer: CONFIG.user.name, reviewedAt: '2026-11-01 10:00', completionNote: '나머지는 원본 확인 후 보완', risk: 'high' });
    expect(lastLog(a)).toMatchObject({ kind: 'complete', target: '분석 건', change: '검토 대기 → 검토 완료 (남은 항목: 미확인 탐지 20건, 미해결 검토사항 5건, 확인 필요 연결 2건)', reason: '나머지는 원본 확인 후 보완' });
    expect(finding(a, 'F-02').status).toBe('open'); // 최초 탐지 결과는 그대로

    await svc.reopenReview('A1', '추가 서류 접수');
    a = await must('A1');
    expect(a).toMatchObject({ review: 'needed', reviewedAt: '' });
    expect(lastLog(a)).toMatchObject({ kind: 'reopen', change: '검토 완료 → 검토 대기', reason: '추가 서류 접수' });
  });

  it('남은 항목이 없으면 문구에 붙이지 않는다', async () => {
    await svc.completeReview('A2', '');
    const a = await must('A2');
    // A2: 미확인 탐지 6건만 남음
    expect(lastLog(a).change).toBe('미검토 → 검토 완료 (남은 항목: 미확인 탐지 6건)');
    expect(lastLog(await must('A5')).change).toBe('미검토 → 검토 완료');
  });
});

describe('6. buildExport', () => {
  /** 원문 위치 조각 중 마스킹 값이 원문과 다른 것(민감한 원문 값) */
  const rawSensitive = (a: Analysis): string[] => {
    const out: string[] = [];
    const walk = (v: unknown): void => {
      if (Array.isArray(v)) v.forEach(walk);
      else if (v && typeof v === 'object') {
        const h = v as Partial<Highlight>;
        if (typeof h.a === 'string' && typeof h.x === 'string' && typeof h.m === 'string') {
          if (h.m && h.m !== h.x) out.push(h.x);
        } else Object.values(v).forEach(walk);
      }
    };
    walk(a.docs);
    return out;
  };

  it('CSV: BOM · CRLF · 열 이름 · 파일 이름 · 마스킹된 값만', async () => {
    const file = await svc.buildExport('A1', 'csv');
    expect(file.format).toBe('csv');
    expect(file.name).toBe(`${CONFIG.brandName}_IM-20261030-0007_검토결과_탐지항목.csv`);
    expect(file.mime).toBe('text/csv;charset=utf-8');
    expect(file.text.startsWith('﻿')).toBe(true);
    expect(file.text.endsWith('\r\n')).toBe(true);
    const rows = file.text.slice(1).split('\r\n');
    expect(rows[0]).toBe('항목ID,정보종류,세부항목,표시값_마스킹,정보주체,문서,페이지,원문위치,노출상태,위험등급,판단근거,적용규칙,확인상태,담당자메모,최초AI_정보종류,최초AI_정보주체,최초AI_노출상태');
    expect(rows).toHaveLength(1 + 23 + 1); // 머리 + 23행 + 끝 빈 줄
    expect(rows[1]).toBe('F-01,고유식별정보,주민등록번호,920314-2******,신청인,개인 여신거래 신청서,1,확인됨,전체 노출,상,주민등록번호 13자리가 마스킹 없이 기재되어 있습니다.,PII-ID-001,확인함,원본 보관 전 마스킹 사본으로 교체 필요,고유식별정보,신청인,전체 노출');
    expect(rows[23]).toContain('F-23,고유식별정보,주민등록번호로 보이는 문자열,920314-2******,신청인,급여계좌 거래내역서,2,위치 확인 필요,');
    expect(file.size).toBe(new TextEncoder().encode(file.text).length);
    expect(file.preview).toBe(rows.slice(0, 6).join('\n'));

    const a1 = await must('A1');
    const raw = rawSensitive(a1);
    expect(raw).toContain('920314-2847516');
    expect(raw).toContain('302-1184-5521-07');
    for (const x of raw) expect(file.text, x).not.toContain(x);

    // 쉼표 · 따옴표 · 줄바꿈이 든 값은 따옴표로 감싼다
    await svc.saveFindingMemo('A1', 'F-02', '메모, "인용"\n둘째 줄');
    const f2 = await svc.buildExport('A1', 'csv', '브랜드');
    expect(f2.name).toBe('브랜드_IM-20261030-0007_검토결과_탐지항목.csv');
    expect(f2.text).toContain(',"메모, ""인용""\n둘째 줄",');
  });

  it('JSON: 최상위 키 · 파일 이름 · 마스킹된 값만', async () => {
    const file = await svc.buildExport('A1', 'json');
    expect(file.name).toBe(`${CONFIG.brandName}_IM-20261030-0007_검토결과.json`);
    expect(file.mime).toBe('application/json');
    const obj = JSON.parse(file.text);
    expect(Object.keys(obj)).toEqual(['보고서', '분석', '대상문서', '주요위험사유', '탐지항목', '검토사항', '문서간연결', '권장조치', '검토메모', '검토이력']);
    expect(obj.보고서).toEqual({ 서비스: CONFIG.brandName, 생성시각: '2026.11.01 10:00', 데모데이터: true, 마스킹: '민감한 값은 마스킹된 표시값만 포함' });
    expect(obj.분석).toEqual({ 분석ID: 'IM-20261030-0007', 분석명: '대출상담 서류 묶음', 접수일시: '2026.10.30 14:22', 분석상태: '완료', 위험등급: '상', 검토상태: '검토 대기', 검토자: '', 검토완료시각: '' });
    expect(obj.대상문서[0]).toEqual({ 문서: '개인 여신거래 신청서', 파일명: '개인여신거래신청서_20261029.pdf', 형식: 'PDF', 페이지: 2, 처리상태: '완료', 오류: '' });
    expect(obj.탐지항목).toHaveLength(23);
    expect(obj.검토사항[3]).toEqual({ ID: 'R-04', 유형: '연결 근거 부족', 내용: '연결 근거가 부족한 문서', 상태: '미해결', 처리내용: '' });
    expect(obj.문서간연결.map((l: { 판단: string }) => l.판단)).toEqual(['연결 근거 확인됨', '연결 확인 필요', '연결 확인 필요']);
    expect(obj.검토이력[0]).toEqual({ 시각: '2026.10.30 14:22', 처리자: CONFIG.user.name, 구분: '분석 요청', 대상: '분석 건', 내용: '문서 3개 분석 요청', 사유: '' });
    expect(file.preview).toBe(file.text.split('\n').slice(0, 16).join('\n'));
    for (const x of rawSensitive(await must('A1'))) expect(file.text, x).not.toContain(x);
  });

  it('없는 분석은 거절된다', async () => {
    await expect(svc.buildExport('A999', 'csv')).rejects.toThrow('A999');
  });

  it('logExport 는 형식 · 크기 · 결과를 이력에 남긴다', async () => {
    const file = await svc.buildExport('A1', 'csv');
    await svc.logExport('A1', file, 'saved');
    expect(lastLog(await must('A1'))).toMatchObject({ kind: 'export', target: file.name, change: expect.stringMatching(/^CSV · \d+KB · 저장 완료$/), reason: '민감한 값 마스킹' });
    await svc.logExport('A1', await svc.buildExport('A1', 'json'), 'handed');
    expect(lastLog(await must('A1')).change).toMatch(/^JSON · \d+KB · 다운로드 요청$/);
  });
});

describe('7. 분석 요청', () => {
  it('샘플 파일: requestMs 뒤 ID → 대기 → 분석 중 → 완료, done 이벤트', async () => {
    const events: (ServiceEvent | undefined)[] = [];
    svc.subscribe((e) => events.push(e));
    const files = await svc.sampleFiles();
    expect(files.map((f) => [f.name, f.kind, f.state])).toEqual([
      ['개인여신거래신청서_20261029.pdf', 'sample', 'ready'],
      ['근로소득원천징수영수증_2025.pdf', 'sample', 'ready'],
      ['급여계좌_거래내역서.pdf', 'sample', 'ready'],
    ]);

    let id: string | undefined;
    void svc.requestAnalysis({ name: '김서연 대출상담 서류 (샘플)', files }).then((v) => (id = v));
    await vi.advanceTimersByTimeAsync(0);
    // 분석 건은 곧바로 '대기'로 생긴다(목록 맨 앞)
    const queued = (await svc.list())[0];
    expect(queued).toMatchObject({ name: '김서연 대출상담 서류 (샘플)', status: 'queued', risk: 'unrated', review: 'none', demoQueued: false });
    expect(queued.code).toMatch(/^IM-20261101-\d{4}$/);
    expect(queued.docs.map((d) => d.status)).toEqual(['queued', 'queued', 'queued']);
    expect(id).toBeUndefined();

    await vi.advanceTimersByTimeAsync(CONFIG.sim.requestMs - 1);
    expect(id).toBeUndefined();
    await vi.advanceTimersByTimeAsync(1);
    expect(id).toBe(queued.id);

    await vi.advanceTimersByTimeAsync(CONFIG.sim.startMs);
    let a = await must(queued.id);
    expect(a.status).toBe('running');
    expect(a.docs.map((d) => d.status)).toEqual(['running', 'queued', 'queued']);

    await vi.advanceTimersByTimeAsync(CONFIG.sim.docMs);
    a = await must(queued.id);
    expect(a.docs.map((d) => d.status)).toEqual(['done', 'running', 'queued']);
    expect(events.some((e) => e?.type === 'done')).toBe(false);

    await vi.advanceTimersByTimeAsync(CONFIG.sim.docMs * 2);
    a = await must(queued.id);
    expect(a).toMatchObject({ status: 'done', risk: 'high', review: 'needed', analyzedAt: '2026-11-01 10:00' });
    expect(a.docs.map((d) => d.status)).toEqual(['done', 'done', 'done']);
    expect([a.findings.length, a.items.length, a.links.length]).toEqual([23, 5, 3]);
    expect(lastLog(a)).toMatchObject({ actor: '시스템', kind: 'ai', change: '분석 완료 · 탐지 23건 · 위험등급 상 · 검토사항 5건' });
    expect(events.filter((e) => e !== undefined)).toEqual([{ type: 'done', id: queued.id, name: '김서연 대출상담 서류 (샘플)', items: 5, findings: 23 }]);
    expect(events.filter((e) => e === undefined).length).toBeGreaterThan(3); // 단계마다 변경 알림
  });

  it('직접 올린 파일: 대기에 머문다(demoQueued)', async () => {
    const p = svc.requestAnalysis({ name: '내 서류', files: [userFile('신청서.pdf', 'PDF', 1000), userFile('통장.jpg', 'JPG', 2000)] });
    await vi.advanceTimersByTimeAsync(CONFIG.sim.requestMs);
    const id = await p;
    await vi.advanceTimersByTimeAsync(60_000);
    const a = await must(id);
    expect(a).toMatchObject({ status: 'queued', demoQueued: true, risk: 'unrated' });
    expect(a.docs).toEqual([
      { id: 'u1', title: '신청서.pdf', name: '신청서.pdf', ext: 'PDF', size: 1000, status: 'queued', pageCount: null, pages: null, error: '' },
      { id: 'u2', title: '통장.jpg', name: '통장.jpg', ext: 'JPG', size: 2000, status: 'queued', pageCount: null, pages: null, error: '' },
    ]);
    expect(a.history.map((h) => [h.kind, h.change])).toEqual([['request', '문서 2개 분석 요청']]);
  });
});

describe('8. 다시 분석', () => {
  it('retryMs 뒤 같은 이유로 다시 실패한다', async () => {
    const p = svc.retry('A4', 't2');
    let r: unknown;
    void p.then((v) => (r = v));
    await vi.advanceTimersByTimeAsync(0);
    let a = await must('A4');
    expect(a).toMatchObject({ status: 'running', retrying: true });
    expect(a.docs.find((d) => d.id === 't2')!.status).toBe('running');
    // 다시 분석 중에는 또 요청할 수 없다
    expect(await svc.retry('A4')).toEqual({ ok: false, message: '' });

    await vi.advanceTimersByTimeAsync(CONFIG.sim.retryMs - 1);
    expect(r).toBeUndefined();
    await vi.advanceTimersByTimeAsync(1);
    const reason = '이미지 해상도가 낮아 글자를 읽지 못했습니다. (가로 640px · 권장 1,500px 이상)';
    expect(r).toEqual({ ok: false, message: reason });
    a = await must('A4');
    expect(a).toMatchObject({ status: 'partial', retrying: false });
    expect(a.docs.find((d) => d.id === 't2')!.status).toBe('failed');
    expect(a.history.slice(-2).map((h) => [h.actor, h.kind, h.target, h.change, h.reason])).toEqual([
      [CONFIG.user.name, 'retry', '거래내역_02.jpg', '같은 파일로 다시 분석 요청', ''],
      ['시스템', 'retry', '거래내역_02.jpg', '다시 분석했지만 같은 이유로 실패', reason],
    ]);
  });

  it('실패 문서가 없으면 바로 ok:false, A6 는 상태가 실패로 돌아온다', async () => {
    expect(await svc.retry('A1')).toEqual({ ok: false, message: '' });
    expect(await svc.retry('A999')).toEqual({ ok: false, message: '' });
    const p = svc.retry('A6');
    await vi.advanceTimersByTimeAsync(CONFIG.sim.retryMs);
    expect(await p).toEqual({ ok: false, message: '파일 구조가 손상되어 열 수 없습니다. (PDF 끝 표시가 없습니다)' });
    expect((await must('A6')).status).toBe('failed');
  });
});

describe('9. DemoControls.prepare(state)', () => {
  const ALL: StateId[] = ['list', 'list-empty', 'list-noresults', 'upload', 'upload-selected', 'upload-unsupported', 'upload-limit', 'upload-failed', 'upload-requesting', 'detail', 'detail-queued', 'detail-running', 'detail-partial', 'detail-failed', 'detail-completed', 'detail-nolocation', 'detail-review', 'detail-links', 'detail-edit', 'detail-complete', 'detail-docs', 'detail-results', 'report', 'report-saved', 'report-failed'];
  const EXPECTED: Partial<Record<StateId, string>> = {
    detail: 'A1', 'detail-results': 'A1', 'detail-docs': 'A1', 'detail-nolocation': 'A1', 'detail-review': 'A1', 'detail-links': 'A1', 'detail-edit': 'A1', 'detail-complete': 'A1',
    'detail-running': 'A3', 'detail-partial': 'A4', 'detail-failed': 'A6', 'detail-completed': 'A5',
    report: 'A1', 'report-saved': 'A1', 'report-failed': 'A1',
  };

  it('상태별 analysisId 가 표대로다', async () => {
    for (const s of ALL) {
      const r = await svc.prepare(s);
      if (s === 'detail-queued') expect(r.analysisId, s).toMatch(/^A\d+$/);
      else expect(r.analysisId, s).toBe(EXPECTED[s]);
      if (!EXPECTED[s] && s !== 'detail-queued') expect(r, s).toEqual({});
    }
  });

  it('list-empty → 빈 목록, 다시 prepare 하면 먼저 reset 된다', async () => {
    await svc.prepare('list-empty');
    expect(await svc.list()).toEqual([]);
    await svc.prepare('list');
    expect((await svc.list()).map((a) => a.id)).toEqual(['A1', 'A2', 'A3', 'A4', 'A5', 'A6']);
  });

  it('detail-queued → 새 대기 분석(직접 올린 파일 2개), 다시 열면 순번이 이어진 새 ID', async () => {
    const { analysisId } = await svc.prepare('detail-queued');
    const a = await must(analysisId!);
    expect(a).toMatchObject({ name: '김○○ 대출 서류 (직접 올린 파일)', status: 'queued', demoQueued: true });
    expect(a.docs.map((d) => [d.name, d.ext, d.size])).toEqual([['대출서류_스캔.pdf', 'PDF', 3145728], ['통장사본_촬영.jpg', 'JPG', 912384]]);
    expect((await svc.list())[0].id).toBe(analysisId);
    expect(await svc.list()).toHaveLength(7);

    // 원본처럼 같은 코어의 reset() 뒤에 만들므로 seq 가 이어진다(앞 대기 건은 reset 으로 지워짐)
    const second = (await svc.prepare('detail-queued')).analysisId!;
    expect(Number(second.slice(1))).toBeGreaterThan(Number(analysisId!.slice(1)));
    expect(await must(second)).toMatchObject({ name: '김○○ 대출 서류 (직접 올린 파일)', status: 'queued', demoQueued: true });
    expect(await svc.get(analysisId!)).toBeNull();
    expect(await svc.list()).toHaveLength(7);
    // 원본 스크립트 실행 값: 처음 reset(H101~H107) → reset(H108~H114) + createQueued = A115,
    // 다시 reset(H117~H123) + createQueued = A124 (evidence/T3-impl/fix1/prepare-queued-fidelity.json)
    expect([analysisId, second]).toEqual(['A115', 'A124']);
  });

  it('report → A1 검토 완료(demoProgressA1)', async () => {
    const { analysisId } = await svc.prepare('report');
    const a = await must(analysisId!);
    expect(a).toMatchObject({ review: 'done', reviewer: CONFIG.user.name, reviewedAt: '2026-10-30 16:40', completionNote: '판독 불가 영역(R-01)과 잘린 페이지(R-02)는 원본 확인 후 보완 예정.' });
    expect(a.memo).toBe('주민등록번호 · 계좌번호가 전체 노출된 서류는 마스킹 사본으로 교체를 요청함.\n거래내역서 2쪽은 원본 재스캔 후 다시 확인 예정.');
    const p = await svc.pending('A1');
    expect([p.openF.length, p.openI.map((i) => i.id), p.openL.length]).toEqual([0, ['R-01', 'R-02'], 0]);
    expect(lastLog(a)).toMatchObject({ at: '2026-10-30 16:40', kind: 'complete', change: '검토 대기 → 검토 완료 (남은 항목: 미해결 검토사항 2건)' });
    expect([link(a, 'L-02').decision, link(a, 'L-03').decision]).toEqual(['linked', 'unlinked']);
    // 다른 상태로 가면 reset 되어 A1 은 다시 검토 필요
    await svc.prepare('detail');
    expect((await must('A1')).review).toBe('needed');
  });

  it('prepare 는 남은 타이머를 지운다(진행 중이던 요청이 끝나지 않는다)', async () => {
    const events: ServiceEvent[] = [];
    svc.subscribe((e) => e && events.push(e));
    void svc.requestAnalysis({ name: 'x', files: await svc.sampleFiles() });
    await svc.prepare('list');
    await vi.advanceTimersByTimeAsync(60_000);
    expect(events).toEqual([]);
    expect(await svc.list()).toHaveLength(6);
  });

  it('reset · clearAll', async () => {
    await svc.clearAll();
    expect(await svc.list()).toEqual([]);
    await svc.reset();
    expect(await svc.list()).toHaveLength(6);
    expect((await must('A5')).review).toBe('done');
  });

  it('reset 은 순번(seq)을 이어 쓴다 — 샘플 다시 불러오기 뒤 새 분석 ID · code · 이력 ID · 내보내기 이름이 원본과 같다', async () => {
    // 기대값은 원본 Main.dc.html ①~④ 스크립트를 같은 순서로 실행해 얻은 값이다
    // (검증 V-T3-1 reset-fidelity 의 '원본' 열, evidence/T3-impl/fix1/reset-fidelity.json).
    vi.setSystemTime(new Date(2026, 10, 1, 11, 12, 0)); // 2026-11-01 11:12(로컬)
    const notified: (ServiceEvent | undefined)[] = [];
    svc.subscribe((e) => notified.push(e));
    await svc.reset(); // 화면을 연 뒤 '샘플 다시 불러오기'
    expect(notified).toEqual([undefined]); // 바뀐 뒤 구독자에게 알림

    // 시드 이력이 처음 reset 의 H101~H107 뒤에 이어진다(원본 값)
    expect((await must('A1')).history.map((h) => h.id)).toEqual(['S1', 'S2', 'H108', 'H109', 'H110', 'H111']);
    expect((await must('A5')).history.map((h) => h.id)).toEqual(['S8', 'S9', 'H112', 'H113', 'H114']);

    const p = svc.requestAnalysis({ name: 'reset 뒤 신규 요청', files: [] });
    await vi.advanceTimersByTimeAsync(CONFIG.sim.requestMs);
    const id = await p;
    expect(id).toBe('A115');
    const a = await must(id);
    expect([a.id, a.code, a.submittedAt]).toEqual(['A115', 'IM-20261101-0115', '2026-11-01 11:12']);
    expect(a.history.map((h) => h.id)).toEqual(['H116']);

    const csv = await svc.buildExport(id, 'csv');
    expect(csv.name).toBe('iMASK_IM-20261101-0115_검토결과_탐지항목.csv');
    const json = await svc.buildExport(id, 'json');
    expect((JSON.parse(json.text) as { 분석: { 분석ID: string } }).분석.분석ID).toBe('IM-20261101-0115');
  });
});

describe('10. subscribe', () => {
  it('변경마다 알리고, 해제 뒤에는 알리지 않는다', async () => {
    const calls: (ServiceEvent | undefined)[] = [];
    const off = svc.subscribe((e) => calls.push(e));
    await svc.saveMemo('A1', '메모');
    await svc.prepare('report');
    expect(calls).toEqual([undefined, undefined]);

    off();
    await svc.saveMemo('A1', '다시');
    void svc.requestAnalysis({ name: 'x', files: await svc.sampleFiles() });
    await vi.advanceTimersByTimeAsync(60_000);
    expect(calls).toHaveLength(2);
  });

  it('한 구독자의 오류가 다른 구독자 · 동작을 막지 않는다', async () => {
    const errors: unknown[] = [];
    const onError = (e: unknown) => errors.push(e);
    process.on('uncaughtException', onError);
    try {
      const seen: number[] = [];
      svc.subscribe(() => {
        throw new Error('boom');
      });
      svc.subscribe(() => seen.push(1));
      await expect(svc.saveMemo('A1', 'x')).resolves.toBeUndefined();
      expect(seen).toEqual([1]);
      expect((await must('A1')).memo).toBe('x');
      await vi.advanceTimersByTimeAsync(0);
      // 오류는 삼키지 않고 따로(마이크로태스크) 다시 던진다
      expect(errors).toHaveLength(1);
      expect(String(errors[0])).toContain('boom');
    } finally {
      process.off('uncaughtException', onError);
    }
  });
});

describe('services/index · 데모 판별', () => {
  it('getDemoControls 는 데모 서비스에서만 조작 객체를 준다', () => {
    expect(isDemoService(svc)).toBe(true);
    expect(getDemoControls(svc)).toBe(svc);
    const fake = { ...svc };
    expect(getDemoControls(fake)).toBeNull();
    expect(getDemoControls(null)).toBeNull();
  });
});

describe('10. deleteAnalysis — 데모 지우기', () => {
  it('목록 · get 에서 빠지고 알린다(이벤트 없는 알림), 남은 분석은 순서 그대로', async () => {
    const notices: (ServiceEvent | undefined)[] = [];
    svc.subscribe((e) => notices.push(e));
    await expect(svc.deleteAnalysis('A2')).resolves.toBeUndefined();
    expect((await svc.list()).map((a) => a.id)).toEqual(['A1', 'A3', 'A4', 'A5', 'A6']);
    expect(await svc.get('A2')).toBeNull();
    expect(notices).toEqual([undefined]);
  });

  it('없는 id(이미 지운 분석 포함) → 실제 분석과 같은 찾을 수 없음(ApiError not_found)으로 거절, 알림 없음', async () => {
    await svc.deleteAnalysis('A5');
    const notices: unknown[] = [];
    svc.subscribe((e) => notices.push(e));
    for (const id of ['A5', 'A999']) {
      const err = await svc.deleteAnalysis(id).catch((e: unknown) => e);
      expect(err).toBeInstanceOf(ApiError);
      expect(err).toMatchObject({ status: 404, code: 'not_found', message: '분석 건을 찾을 수 없습니다.' });
    }
    expect(notices).toEqual([]);
  });

  it('진행 중인 샘플 분석을 지우면 남은 타이머가 상태를 바꾸거나 done 이벤트를 내지 않는다', async () => {
    const files = await svc.sampleFiles();
    let id: string | undefined;
    void svc.requestAnalysis({ name: '지울 샘플', files }).then((v) => (id = v));
    await vi.advanceTimersByTimeAsync(CONFIG.sim.requestMs + CONFIG.sim.startMs);
    expect(id).toBeDefined();
    expect((await must(id!)).status).toBe('running');
    const events: (ServiceEvent | undefined)[] = [];
    svc.subscribe((e) => events.push(e));
    await svc.deleteAnalysis(id!);
    expect(events).toEqual([undefined]);
    await vi.advanceTimersByTimeAsync(60_000);
    expect(events).toEqual([undefined]); // 남은 단계 타이머의 변경 알림 · done 이벤트 없음
    expect(await svc.get(id!)).toBeNull();
    expect((await svc.list()).some((a) => a.id === id)).toBe(false);
  });

  it('분석 요청 응답 전에 지우면 요청은 그 id 로 끝나고 샘플 진행은 시작하지 않는다', async () => {
    const files = await svc.sampleFiles();
    const p = svc.requestAnalysis({ name: '곧 지울 샘플', files });
    await vi.advanceTimersByTimeAsync(0);
    const queued = (await svc.list())[0];
    const events: (ServiceEvent | undefined)[] = [];
    svc.subscribe((e) => events.push(e));
    await svc.deleteAnalysis(queued.id);
    await expect(p).resolves.toBe(queued.id);
    await vi.advanceTimersByTimeAsync(60_000);
    expect(events).toEqual([undefined]);
    expect(await svc.get(queued.id)).toBeNull();
  });

  it('다시 분석 중에 지우면 그 결과는 이유 없이 끝나고(토스트 없음) 상태 · 이력이 되살아나지 않는다', async () => {
    const p = svc.retry('A6');
    await vi.advanceTimersByTimeAsync(0);
    expect((await must('A6')).retrying).toBe(true);
    const events: (ServiceEvent | undefined)[] = [];
    svc.subscribe((e) => events.push(e));
    await svc.deleteAnalysis('A6');
    await expect(p).resolves.toEqual({ ok: false, message: '' });
    await vi.advanceTimersByTimeAsync(CONFIG.sim.retryMs * 2);
    expect(events).toEqual([undefined]);
    expect(await svc.get('A6')).toBeNull();
  });

  it('다른 분석의 타이머는 그대로 — 지우지 않은 분석은 끝까지 간다', async () => {
    const p = svc.retry('A4', 't2');
    await vi.advanceTimersByTimeAsync(0);
    await svc.deleteAnalysis('A6');
    await vi.advanceTimersByTimeAsync(CONFIG.sim.retryMs);
    expect((await p).message).toContain('이미지 해상도가 낮아');
    expect((await must('A4')).retrying).toBe(false);
  });

  it("'샘플 다시 불러오기'(reset)로 지운 샘플이 되살아난다", async () => {
    await svc.deleteAnalysis('A1');
    await svc.deleteAnalysis('A6');
    expect((await svc.list()).map((a) => a.id)).toEqual(['A2', 'A3', 'A4', 'A5']);
    await svc.reset();
    expect((await svc.list()).map((a) => a.id)).toEqual(['A1', 'A2', 'A3', 'A4', 'A5', 'A6']);
    expect((await must('A1')).findings).toHaveLength(23);
  });

  it('다시 분석 결과 문구는 그대로(같은 이유로 실패 — started 없음)', async () => {
    const p = svc.retry('A6');
    await vi.advanceTimersByTimeAsync(CONFIG.sim.retryMs);
    const r = await p;
    expect(r).toEqual({ ok: false, message: '파일 구조가 손상되어 열 수 없습니다. (PDF 끝 표시가 없습니다)' });
    expect('started' in r).toBe(false);
  });
});
