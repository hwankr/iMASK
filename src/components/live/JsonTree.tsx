'use client';

/* ==========================================================================
   JSON 나무 — 접고 펴는 결과 보기(실제 분석의 단계별 결과)
   - 객체·배열은 <details>(요약: 키 이름 + '{…} 17개 키' / '[…] 5개'). 펼칠 때만 자식을 그린다
     (서류-인식 단계의 elements 처럼 큰 값을 한꺼번에 그리면 느리다). 자식이 많으면 100개씩 더 보여 준다.
   - 맨 위 한 단계만 처음에 펼친다(defaultOpen).
   - 문자열은 줄바꿈을 그대로(Markdown 본문), 숫자·참거짓·null 은 색으로 구분한다.
   - 키보드: <summary> 기본 동작(Enter·Space)으로 열고 닫는다.
   ========================================================================== */

import { useState } from 'react';
import styles from './JsonTree.module.css';

/** 한 번에 그리는 자식 수 */
const CHUNK = 100;

export interface JsonTreeProps {
  /** 맨 위 이름(예: 'data') */
  name: string;
  value: unknown;
  /** 맨 위를 처음에 펼칠지(기본 true) */
  defaultOpen?: boolean;
}

export function JsonTree({ name, value, defaultOpen = true }: JsonTreeProps) {
  return (
    <div className={styles.tree}>
      <JsonNode name={name} value={value} defaultOpen={defaultOpen} />
    </div>
  );
}

type Container = Record<string, unknown> | unknown[];

const isContainer = (v: unknown): v is Container => typeof v === 'object' && v !== null;

function sizeOf(v: Container): number {
  return Array.isArray(v) ? v.length : Object.keys(v).length;
}

function JsonNode({ name, value, defaultOpen = false }: { name: string; value: unknown; defaultOpen?: boolean }) {
  if (isContainer(value) && sizeOf(value) > 0) return <JsonBranch name={name} value={value} defaultOpen={defaultOpen} />;
  return (
    <div className={styles.leaf}>
      <span className={styles.key}>{name}</span>
      <JsonValue value={value} />
    </div>
  );
}

function JsonBranch({ name, value, defaultOpen }: { name: string; value: Container; defaultOpen: boolean }) {
  const [open, setOpen] = useState(defaultOpen);
  const [limit, setLimit] = useState(CHUNK);
  const array = Array.isArray(value);
  const n = sizeOf(value);
  const entries: [string, unknown][] | null = open ? (array ? value.map((v, i) => [`[${i}]`, v]) : Object.entries(value)) : null;
  const rest = entries ? entries.length - limit : 0;
  return (
    <details className={styles.branch} open={open} onToggle={(e) => setOpen(e.currentTarget.open)}>
      <summary className={styles.summary}>
        <span className={styles.key}>{name}</span>
        <span className={styles.meta}>{array ? `[…] ${n}개` : `{…} ${n}개 키`}</span>
      </summary>
      {entries ? (
        <ul className={styles.children}>
          {entries.slice(0, limit).map(([k, v]) => (
            <li key={k} className={styles.child}>
              <JsonNode name={k} value={v} />
            </li>
          ))}
          {rest > 0 ? (
            <li className={styles.child}>
              <button type="button" className={styles.more} onClick={() => setLimit((l) => l + CHUNK)}>
                {Math.min(CHUNK, rest)}개 더 보기 (남은 {rest}개)
              </button>
            </li>
          ) : null}
        </ul>
      ) : null}
    </details>
  );
}

function JsonValue({ value }: { value: unknown }) {
  if (value === null || value === undefined) return <span className={styles.null}>null</span>;
  if (typeof value === 'string') return value ? <span className={styles.str}>{value}</span> : <span className={styles.meta}>&quot;&quot; (빈 글자)</span>;
  if (typeof value === 'number') return <span className={styles.num}>{String(value)}</span>;
  if (typeof value === 'boolean') return <span className={styles.bool}>{value ? 'true' : 'false'}</span>;
  if (Array.isArray(value)) return <span className={styles.meta}>[] 빈 목록</span>;
  if (typeof value === 'object') return <span className={styles.meta}>{'{}'} 빈 객체</span>;
  return <span className={styles.str}>{String(value)}</span>;
}
