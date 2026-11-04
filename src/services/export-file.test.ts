/* 내보내기 파일 공용 모듈 — 데모 바이트 그대로(T0 기준 sha256) · 실제 분석 파일(합성 고정 자료) · 수식 막기 · 글 정리(크기).
   원문 값은 테스트 출력에 옮기지 않는다(있음/없음 · 개수만). */
import { createHash } from 'node:crypto';
import { readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { CONFIG } from '@/config/app';
import { toAnalysis } from './api/mapping';
import { analysisOut, contractResult } from './api/testing';
import { createDemoService, type DemoService } from './demo';
import { CSV_COLUMNS, buildExportFile, csvCell, isFormulaLike, wellFormed } from './export-file';
import { reportSafeAnalysis } from './report-safe';
import type { Analysis } from './types';

const sha256 = (text: string) => createHash('sha256').update(Buffer.from(text, 'utf8')).digest('hex');
/** T0 기준과 같은 규칙 — JSON 의 생성 시각 줄을 뺀다 */
const withoutGeneratedAt = (text: string) => text.replace(/\n\s*"생성시각": "[^"]*",/, '\n<생성시각>');
const bytes = (text: string) => new TextEncoder().encode(text).length;

/* ---------- 데모 — 바이트 그대로 ---------- */

describe('데모 내보내기 — T0 기준 파일과 바이트가 같다(JSON 은 생성 시각 줄 제외)', () => {
  let svc: DemoService;
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date(2026, 10, 4, 13, 40, 0));
    svc = createDemoService();
  });
  afterEach(() => {
    svc.dispose();
    vi.useRealTimers();
  });

  const T0 = {
    A1: { csv: ['7e3b50a47c13236da8260959de1440d57fb6d7fdeb36d07771403ca257b3f735', 6127], json: ['0ca7c0665c3bacaa56fb7028a2c0a9116ffddcd27b553d62967f23dcaee54723', 22021] },
    A5: { csv: ['529073f0a60cb7dabcb8bba3fb46dde240e7f07cc6b4a5bd87d6501155943936', 1211], json: ['37d76551007902798ccbe1c67c218ed0c6a0b45fcab38246bd7e4c5b64526540', 5172] },
  } as const;

  for (const id of ['A1', 'A5'] as const) {
    it(`${id} CSV — sha256 · 크기`, async () => {
      const file = await svc.buildExport(id, 'csv');
      expect(file.size).toBe(T0[id].csv[1]);
      expect(sha256(file.text)).toBe(T0[id].csv[0]);
      expect(file.size).toBe(new Blob([file.text]).size);
    });
    it(`${id} JSON — 생성 시각 줄을 뺀 sha256 · 크기`, async () => {
      const file = await svc.buildExport(id, 'json');
      expect(file.size).toBe(T0[id].json[1]);
      expect(sha256(withoutGeneratedAt(file.text))).toBe(T0[id].json[0]);
      expect(JSON.parse(file.text).보고서.생성시각).toBe('2026.11.04 13:40');
    });
  }

  it('데모 샘플 CSV 에는 수식으로 읽힐 칸이 없다(수식 막기가 데모 바이트를 바꾸지 않는다)', async () => {
    for (const id of ['A1', 'A2', 'A3', 'A4', 'A5', 'A6']) {
      const file = await svc.buildExport(id, 'csv');
      expect(file.text.includes(`"'`), id).toBe(false);
    }
  });
});

/* ---------- 실제 분석 ---------- */

const NEW_REVIEW = { status: 'needed', memo: '', memo_at: null, reviewer: '', reviewed_at: null, completion_note: '', findings: {}, history: [], version: 1 };

/** 합성 고정 자료(done-result.json) + 검토 기록 → toAnalysis */
function liveAnalysis(review: Record<string, unknown> = NEW_REVIEW, edit?: (r: Record<string, unknown>) => void): Analysis {
  const result = contractResult();
  edit?.(result);
  return toAnalysis(analysisOut({ status: 'done', result, upstage_job_id: 'job_test', upstage_status: 'completed', review: structuredClone(review) }));
}

/** 원래 분석의 대상 원문 값 — live.value 가 masked 와 다르고 2 코드 포인트 이상 */
const rawValues = (a: Analysis) =>
  a.findings.map((f) => f.live?.value ?? '').filter((v, i) => v && Array.from(v).length >= 2 && v !== a.findings[i].masked);

const liveFile = (a: Analysis, format: 'csv' | 'json') =>
  buildExportFile(reportSafeAnalysis(a), format, { brand: CONFIG.brandName, generatedAt: '2026-11-04 15:07', live: true });

/** CSV 글 → 줄마다 칸(따옴표 규칙대로 읽는다) */
function parseCsv(text: string): string[][] {
  const body = text.replace(/^﻿/, '');
  const rows: string[][] = [];
  let row: string[] = [];
  let cell = '';
  let quoted = false;
  for (let i = 0; i < body.length; i++) {
    const ch = body[i];
    if (quoted) {
      if (ch === '"' && body[i + 1] === '"') {
        cell += '"';
        i++;
      } else if (ch === '"') quoted = false;
      else cell += ch;
    } else if (ch === '"') quoted = true;
    else if (ch === ',') {
      row.push(cell);
      cell = '';
    } else if (ch === '\r' && body[i + 1] === '\n') {
      row.push(cell);
      rows.push(row);
      row = [];
      cell = '';
      i++;
    } else cell += ch;
  }
  return rows;
}

describe('실제 분석 파일 — 합성 고정 자료', () => {
  const a = liveAnalysis();

  it('고정 자료는 보고서 대상이고 원문 값(masked 와 다른 2자 이상)이 있다', () => {
    expect(a.raw?.detailReady).toBe(true);
    expect(a.raw?.reviewable).toBe(true);
    expect(rawValues(a).length).toBeGreaterThanOrEqual(10);
  });

  it('CSV — 데모와 같은 17열 · BOM · CRLF · 적용규칙 빈 값 · 미평가 · 파일 이름', () => {
    const file = liveFile(a, 'csv');
    expect(file.name).toBe(`${CONFIG.brandName}_${a.code}_검토결과_탐지항목.csv`);
    expect(file.name).toMatch(/^iMASK_DG-\d{8}-[0-9A-F]{4}_검토결과_탐지항목\.csv$/);
    expect(file.mime).toBe('text/csv;charset=utf-8');
    expect(file.text.startsWith('﻿')).toBe(true);
    expect(file.text.endsWith('\r\n')).toBe(true);
    const rows = parseCsv(file.text);
    expect(rows[0]).toEqual([...CSV_COLUMNS]);
    expect(rows).toHaveLength(1 + a.findings.length);
    const col = (name: string) => CSV_COLUMNS.indexOf(name as (typeof CSV_COLUMNS)[number]);
    expect(rows.slice(1).every((r) => r.length === 17)).toBe(true);
    expect(rows.slice(1).every((r) => r[col('적용규칙')] === '')).toBe(true);
    const unrated = a.findings.filter((f) => f.risk === 'unrated').length;
    expect(unrated).toBeGreaterThan(0);
    expect(rows.slice(1).filter((r) => r[col('위험등급')] === '미평가')).toHaveLength(unrated);
    expect(rows.slice(1).map((r) => r[col('표시값_마스킹')])).toEqual(a.findings.map((f) => f.masked));
    expect(file.size).toBe(bytes(file.text));
    expect(file.preview).toBe(file.text.slice(1).split('\r\n').slice(0, 6).join('\n'));
  });

  it('JSON — 최상위 키(검토사항 · 문서간연결 없음, 순서 그대로) · 데모데이터 false · 생성 시각(받은 서울 시각)', () => {
    const file = liveFile(a, 'json');
    expect(file.name).toBe(`${CONFIG.brandName}_${a.code}_검토결과.json`);
    const obj = JSON.parse(file.text);
    expect(Object.keys(obj)).toEqual(['보고서', '분석', '대상문서', '주요위험사유', '탐지항목', '권장조치', '검토메모', '검토이력']);
    expect(obj.보고서).toEqual({ 서비스: CONFIG.brandName, 생성시각: '2026.11.04 15:07', 데모데이터: false, 마스킹: '민감한 값은 마스킹된 표시값만 포함' });
    expect(Object.keys(obj.분석)).toEqual(['분석ID', '분석명', '접수일시', '분석상태', '위험등급', '검토상태', '검토자', '검토완료시각']);
    expect(obj.분석.분석ID).toBe(a.code);
    expect(obj.탐지항목).toHaveLength(a.findings.length);
    expect(Object.keys(obj.탐지항목[0])).toEqual([...CSV_COLUMNS]);
    expect(obj.탐지항목.every((r: Record<string, unknown>) => r.적용규칙 === '')).toBe(true);
    expect(obj.주요위험사유).toEqual(a.riskReasons);
    expect(obj.권장조치).toEqual(a.recs);
    expect(file.size).toBe(bytes(file.text));
  });

  it('원문 값 없음 — 원래 live.value(masked 와 다르고 2자 이상) 어느 것도 CSV · JSON 글에 없다', () => {
    const raws = rawValues(a);
    for (const format of ['csv', 'json'] as const) {
      const text = liveFile(a, format).text;
      const leaked = raws.filter((v) => text.includes(v));
      expect(leaked.length, format + ' 에 원문 값이 ' + leaked.length + '개 있음').toBe(0);
    }
  });

  it('원문 값을 워크플로우 글(위험 사유 · 권장 조치 · 판단 근거)에 심어도 파일에는 masked 로 들어간다', () => {
    const raws = rawValues(a);
    const planted = liveAnalysis(NEW_REVIEW, (r) => {
      const findings = r.findings as Record<string, unknown>[];
      const overall = r.overall as Record<string, unknown>;
      overall.text = '- 사유 ' + raws[0] + ' 확인\n- 둘째 ' + raws[1];
      overall.next_text = '- 조치 ' + raws[2];
      findings[0].risk_reason = '근거 ' + raws[3] + ' · ' + raws[0];
    });
    for (const format of ['csv', 'json'] as const) {
      const text = liveFile(planted, format).text;
      expect(raws.filter((v) => text.includes(v)).length, format).toBe(0);
    }
    const obj = JSON.parse(liveFile(planted, 'json').text);
    const masked0 = planted.findings[a.findings.findIndex((f) => f.live?.value === raws[0])].masked;
    expect(obj.주요위험사유[0]).toBe('사유 ' + masked0 + ' 확인');
  });

  it('수식 막기 — 메모 · 라벨 · masked · 판단 근거가 = + - @ 탭 CR 앞 공백 전각으로 시작하면 \' 를 붙이고 따옴표로 감싼다', () => {
    const LEADS = ['=1+1', '+82', '-1', '@SUM(A1)', '\tX', '\rX', ' =1', '＝1', '＋1', '－1', '＠A', '\nX', '　=1'];
    const ids = a.findings.slice(0, LEADS.length).map((f) => f.live!.id);
    const review = {
      ...NEW_REVIEW,
      findings: Object.fromEntries(ids.map((id, i) => [id, { status: 'confirmed', memo: LEADS[i] }])),
    };
    const b = liveAnalysis(review, (r) => {
      const findings = r.findings as Record<string, unknown>[];
      findings[0].label = '=HYPERLINK("x")';
      findings[1].masked = '-***';
      findings[2].risk_reason = '+근거';
    });
    const file = liveFile(b, 'csv');
    const rows = parseCsv(file.text);
    const memoCol = CSV_COLUMNS.indexOf('담당자메모');
    LEADS.forEach((lead, i) => {
      expect(rows[1 + i][memoCol], JSON.stringify(lead)).toBe("'" + lead);
    });
    expect(rows[1][CSV_COLUMNS.indexOf('세부항목')]).toBe('\'=HYPERLINK("x")');
    expect(rows[2][CSV_COLUMNS.indexOf('표시값_마스킹')]).toBe("'-***");
    expect(rows[3][CSV_COLUMNS.indexOf('판단근거')]).toBe("'+근거");
    // 원래 글에는 그대로 감싼 꼴로 들어간다
    expect(file.text).toContain(',"\'=1+1",');
    expect(file.text).toContain(',"\'=HYPERLINK(""x"")",');
    // 숫자 칸(페이지)은 막지 않는다 · 수식이 아닌 글은 그대로
    expect(rows.slice(1).every((r) => /^\d+$/.test(r[CSV_COLUMNS.indexOf('페이지')]))).toBe(true);
    // JSON 은 값 그대로(수식 막기는 CSV 만)
    const obj = JSON.parse(liveFile(b, 'json').text);
    expect(obj.탐지항목[0].담당자메모).toBe('=1+1');
  });

  it('짝 없는 서로게이트가 든 메모 · 이름 · 라벨 · masked → text 에 U+FFFD, size = UTF-8 바이트 = Blob 크기', () => {
    const LONE_HI = '\uD800';
    const LONE_LO = '\uDC00';
    const id0 = a.findings[0].live!.id;
    const b = liveAnalysis({ ...NEW_REVIEW, memo: '검토' + LONE_LO + '메모', findings: { [id0]: { status: 'open', memo: '메모' + LONE_HI } } }, (r) => {
      const findings = r.findings as Record<string, unknown>[];
      findings[1].label = '라벨' + LONE_HI + 'x';
      findings[2].masked = LONE_LO + '***';
    });
    const named = { ...b, name: '이름' + LONE_HI + '😀' };
    for (const format of ['csv', 'json'] as const) {
      const file = liveFile(named, format);
      expect(file.text.includes('�'), format).toBe(true);
      expect(/[\uD800-\uDFFF]/u.test(file.text), format).toBe(false);
      expect(file.text.includes('😀') || format === 'csv', format).toBe(true);
      expect(file.size, format).toBe(new TextEncoder().encode(file.text).length);
      expect(file.size, format).toBe(new Blob([file.text]).size);
      expect(file.text.includes('\\ud800') || file.text.includes('\\udc00'), format).toBe(false);
    }
    const csv = parseCsv(liveFile(named, 'csv').text);
    expect(csv[1][CSV_COLUMNS.indexOf('담당자메모')]).toBe('메모�');
    expect(JSON.parse(liveFile(named, 'json').text).분석.분석명).toBe('이름�😀');
  });

  it('이름 · 메모 · 사유는 담당자 글 그대로 넣는다(마스킹하지 않음)', () => {
    const b = liveAnalysis({ ...NEW_REVIEW, memo: '검토 메모입니다', completion_note: '' });
    const obj = JSON.parse(liveFile(b, 'json').text);
    expect(obj.검토메모).toBe('검토 메모입니다');
    expect(obj.분석.분석명).toBe(b.name);
  });
});

describe('탐지 0건', () => {
  it('실제 분석 — BOM · 17열 머리 줄 · 끝 CRLF · size · 미리보기', () => {
    const a = liveAnalysis(NEW_REVIEW, (r) => {
      r.findings = [];
    });
    expect(a.raw?.detailReady).toBe(true);
    expect(a.findings).toHaveLength(0);
    const file = liveFile(a, 'csv');
    const head = CSV_COLUMNS.join(',');
    expect(file.text).toBe('﻿' + head + '\r\n');
    expect(parseCsv(file.text)).toEqual([[...CSV_COLUMNS]]);
    expect(file.size).toBe(new TextEncoder().encode(file.text).length);
    expect(file.size).toBe(new Blob([file.text]).size);
    expect(file.preview).toBe(head);
    const json = JSON.parse(liveFile(a, 'json').text);
    expect(json.탐지항목).toEqual([]);
  });

  it("데모 — 지금 그대로 '항목ID' 한 열", async () => {
    const svc = createDemoService();
    try {
      const a1 = await svc.get('A1');
      if (!a1) throw new Error('A1');
      const file = buildExportFile({ ...a1, findings: [] }, 'csv', { brand: CONFIG.brandName, generatedAt: '2026-11-04 15:07', live: false });
      expect(file.text).toBe('﻿항목ID\r\n');
      expect(file.size).toBe(13);
      expect(file.preview).toBe('항목ID');
    } finally {
      svc.dispose();
    }
  });
});

describe('아주 긴 원문 값 — 안전한 사본 → 파일', () => {
  /** 실행 중에 만드는 긴 합성 값(한글 음절) */
  const big = (seed: number, len: number) => {
    const out: string[] = [];
    for (let i = 0; i < len; i++) out.push(String.fromCodePoint(0xac00 + ((i * 7 + seed) % 11172)));
    return out.join('');
  };

  for (const len of [65536, 262144]) {
    it(`${len} 코드 포인트 값을 워크플로우 글에 심어도 CSV · JSON 이 예외 없이 만들어지고 원문 값이 없다`, () => {
      const value = big(len, len);
      const other = big(len + 1, 70000);
      const a = liveAnalysis(NEW_REVIEW, (r) => {
        const findings = r.findings as Record<string, unknown>[];
        findings[0].value = value;
        findings[0].masked = '***';
        findings[1].value = other;
        findings[1].masked = '';
        findings[2].risk_reason = '근거 ' + value + ' · ' + other;
        const overall = r.overall as Record<string, unknown>;
        overall.text = '- 사유 ' + value;
        overall.next_text = '- 조치 ' + other;
      });
      for (const format of ['csv', 'json'] as const) {
        const text = liveFile(a, format).text;
        expect(text.includes(value.slice(5000, 5064)), format).toBe(false);
        expect(text.includes(other.slice(100, 164)), format).toBe(false);
        expect(rawValues(a).filter((v) => text.includes(v)).length, format).toBe(0);
      }
      const obj = JSON.parse(liveFile(a, 'json').text);
      expect(obj.주요위험사유).toEqual(['사유 ***']);
      expect(obj.권장조치).toEqual(['조치 ' + '*'.repeat(70000)]);
    });
  }
});

describe('칸 도우미', () => {
  it('isFormulaLike — 첫 글자 집합과 앞 공백', () => {
    for (const s of ['=', '+1', '-', '@', '＝', '＋', '－', '＠', '\t', '\r', '\n', ' =1', '   +1', ' -1', '　@x']) expect(isFormulaLike(s), JSON.stringify(s)).toBe(true);
    for (const s of ['', 'a=1', '1-2', '높음', '010-****-1234', 'D1-01', '( =1)', '*-1']) expect(isFormulaLike(s), JSON.stringify(s)).toBe(false);
  });

  it('csvCell — 숫자는 그대로(음수 포함), 따옴표 규칙, 수식 막기', () => {
    expect(csvCell(-1)).toBe('-1');
    expect(csvCell(12)).toBe('12');
    expect(csvCell(null)).toBe('');
    expect(csvCell('a,b')).toBe('"a,b"');
    expect(csvCell('a"b')).toBe('"a""b"');
    expect(csvCell('=1')).toBe('"\'=1"');
    expect(csvCell('-"x"')).toBe('"\'-""x"""');
    expect(csvCell('plain')).toBe('plain');
  });

  it('wellFormed — 짝 없는 서로게이트만 U+FFFD, 짝이 맞는 쌍은 그대로', () => {
    expect(wellFormed('a\uD800b')).toBe('a�b');
    expect(wellFormed('\uDC00')).toBe('�');
    expect(wellFormed('😀')).toBe('😀');
    expect(wellFormed('😀\uD83D')).toBe('😀�');
  });
});

describe('모듈 경계', () => {
  const root = fileURLToPath(new URL('.', import.meta.url));
  const read = (p: string) => readFileSync(join(root, p), 'utf8');
  const imports = (text: string) => [...text.matchAll(/from\s+'([^']+)'/g)].map((m) => m[1]);

  it('공용 모듈 · 안전한 사본은 샘플 · 데모 코어 · 실제 서비스를 import 하지 않는다', () => {
    for (const f of ['export-file.ts', 'report-safe.ts']) {
      for (const spec of imports(read(f))) {
        expect(spec, f).not.toMatch(/samples|\/demo|demo\/|api\/service|\.\/api$|api\/index/);
      }
    }
  });

  it('실제 분석 서비스(src/services/api)는 데모 코어 · 샘플을 import 하지 않는다', () => {
    const dir = join(root, 'api');
    for (const f of readdirSync(dir).filter((x) => x.endsWith('.ts') && !x.endsWith('.test.ts'))) {
      for (const spec of imports(readFileSync(join(dir, f), 'utf8'))) {
        expect(spec, f).not.toMatch(/samples|\/demo|^\.\.\/demo|demo\//);
      }
    }
  });
});
