import { describe, expect, it } from 'vitest';
import { findingNumber, markdownLines, readFile, readOverall } from './contract';

describe('markdownLines — Markdown → 줄 목록', () => {
  it('문자열이 아니면 []', () => {
    for (const v of [null, undefined, 3, {}, [], true]) expect(markdownLines(v)).toEqual([]);
    expect(markdownLines('')).toEqual([]);
  });

  it('제목 줄 · 빈 줄을 빼고 앞뒤 공백을 뗀다', () => {
    expect(markdownLines('## 위험도 판정\n\n   **상**으로 판단됩니다.   \n# 제목\n\t\n###### 작은 제목')).toEqual(['상으로 판단됩니다.']);
  });

  it('목록 기호(- · * · + · 1. · 2))를 뗀다 — 기호 뒤에 공백이 없으면 글자로 둔다', () => {
    expect(markdownLines('- 가\n* 나\n+ 다\n1. 라\n12. 마\n2) 바\n-5,000원 차감\n3.5% 금리\n*강조*')).toEqual(['가', '나', '다', '라', '마', '바', '-5,000원 차감', '3.5% 금리', '*강조*']);
  });

  it('굵게 표시(**)를 지운다 — 줄 앞의 **굵게**를 목록 기호로 보지 않는다', () => {
    expect(markdownLines('**고유식별정보**가 있습니다\n- **신용도판단정보** | 처리: **접근 제한**')).toEqual(['고유식별정보가 있습니다', '신용도판단정보 | 처리: 접근 제한']);
  });

  it('인용 표시(【†3】 · 【3†source】 · 【…】)를 지운다', () => {
    expect(markdownLines('판단됩니다.【†1】\n있습니다.【†2】【†3】\n연체 정보【3†source】가 있습니다. \n가 【†4】 나')).toEqual(['판단됩니다.', '있습니다.', '연체 정보가 있습니다.', '가 나']);
  });

  it('지운 뒤 빈 줄 · 구분선 · 기호만 있는 줄은 뺀다', () => {
    expect(markdownLines('- 【†1】\n**\n---\n* * *\n___\n-\n1.\n- **【†2】**\n남는 줄')).toEqual(['남는 줄']);
  });

  it('CRLF · CR 줄바꿈도 나눈다', () => {
    expect(markdownLines('가\r\n- 나\r다')).toEqual(['가', '나', '다']);
  });
});

describe('readFile · readOverall · findingNumber', () => {
  it('readFile — documents 첫 행(없거나 객체가 아니면 null, 빠진 값은 빈 값)', () => {
    expect(readFile([{ id: 'd1', filename: 'a.pdf', mime_type: 'application/pdf', size_bytes: 10 }, { id: 'd2' }])).toEqual({ id: 'd1', name: 'a.pdf', mime: 'application/pdf', size: 10 });
    expect(readFile([{ size_bytes: -1 }])).toEqual({ id: '', name: '', mime: '', size: 0 });
    expect(readFile([{ size_bytes: '10' }])?.size).toBe(0);
    for (const v of [[], null, undefined, 'x', [null], ['x'], {}]) expect(readFile(v)).toBeNull();
  });

  it('readOverall — 객체가 아니면 null, 빠진 값 · 문자열 아님은 빈 값', () => {
    expect(readOverall({ overall: { level: '상', text: 't', next_stage: '권장_조치', next_text: 'n' } })).toEqual({ level: '상', text: 't', nextStage: '권장_조치', nextText: 'n' });
    expect(readOverall({ overall: { level: null } })).toEqual({ level: '', text: '', nextStage: '', nextText: '' });
    for (const v of [null, 'x', [], {}, { overall: null }, { overall: [] }, { overall: 'x' }]) expect(readOverall(v)).toBeNull();
  });

  it('findingNumber — D<서류 목록 순번>-<두 자리>(순번에 더하지 않는다)', () => {
    expect(findingNumber(1, 1)).toBe('D1-01');
    expect(findingNumber(5, 12)).toBe('D5-12');
    expect(findingNumber(2, 100)).toBe('D2-100');
  });
});
