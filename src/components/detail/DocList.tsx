'use client';

import type { CSSProperties } from 'react';
import { Icon, IconButton, Spinner, cx } from '@/components/ui';
import { RISK } from '@/display/rules';
import type { DocModel } from './detailModel';
import { Tip } from './Tip';
import styles from './DocList.module.css';

export interface PanelProps {
  id?: string;
  role?: 'tabpanel';
  'aria-labelledby'?: string;
}

export interface DocListProps {
  docs: DocModel[];
  onPick: (docId: string) => void;
  /** 접기 버튼(휴대폰에는 없다) */
  onCollapse?: () => void;
  mobile: boolean;
  panel?: PanelProps;
}

function DocStatus({ d }: { d: DocModel }) {
  const style = { '--st-fg': d.status.fg } as CSSProperties;
  return (
    <span className={styles.st} style={style}>
      {d.status.spin ? <Spinner size={12} /> : <Icon name={d.status.icon} size={14} strokeWidth={2.1} />}
      {d.status.label}
      {d.hasCount ? <span className={styles.nFind}>· 탐지 {d.nFind}</span> : null}
      {d.hasHigh ? <span className={styles.nHigh}>· {RISK.high.label} {d.nHigh}</span> : null}
    </span>
  );
}

/**
 * 펼친 문서 목록(Main 371–391) — 문서마다 상태(회전 · 정지 아이콘), 탐지 건수, 고위험 표시, 고른 문서.
 * 누르면 그 문서 1쪽(휴대폰이면 원문 탭으로).
 */
export function DocList({ docs, onPick, onCollapse, mobile, panel }: DocListProps) {
  return (
    <aside aria-label="문서 목록" className={cx(styles.aside, mobile && styles.mobile)} {...panel}>
      <div className={styles.head}>
        <h2 className={styles.h2}>
          문서 <span className={styles.count}>{docs.length}</span>
        </h2>
        {onCollapse ? (
          <IconButton label="문서 목록 접기" icon="dg-i-panel" size={34} variant="muted" iconSize={18} strokeWidth={1.9} aria-expanded onClick={onCollapse} />
        ) : null}
      </div>
      <ul className={styles.list}>
        {docs.map((d) => (
          <li key={d.id}>
            <button type="button" className={cx(styles.doc, d.cur && styles.cur)} aria-current={d.cur ? 'true' : undefined} onClick={() => onPick(d.id)}>
              <span aria-hidden="true" className={styles.tile}>
                {d.ext}
              </span>
              <span className={styles.texts}>
                <span className={styles.title}>{d.title}</span>
                <span className={styles.file}>{d.file}</span>
                <span className={styles.meta}>{d.meta}</span>
                <DocStatus d={d} />
              </span>
            </button>
          </li>
        ))}
      </ul>
    </aside>
  );
}

export interface DocRailProps {
  docs: DocModel[];
  onPick: (docId: string) => void;
  onExpand: () => void;
}

/** 접힌 레일(Main 393–398) — 문서 번호 · 형식 · 상태 점. 펼치기 버튼(aria-expanded=false) */
export function DocRail({ docs, onPick, onExpand }: DocRailProps) {
  return (
    <aside aria-label="문서 목록 (접힘)" className={styles.rail}>
      <Tip label="문서 목록 펼치기" side="right">
        <IconButton
          label="문서 목록 펼치기"
          icon="dg-i-panel"
          size={40}
          iconSize={19}
          strokeWidth={1.9}
          tooltip="none"
          aria-expanded={false}
          onClick={onExpand}
          className={styles.railToggle}
        />
      </Tip>
      <span aria-hidden="true" className={styles.sep} />
      <ul className={styles.railList}>
        {docs.map((d) => (
          <li key={d.id}>
            <button
              type="button"
              className={cx(styles.railDoc, d.cur && styles.cur)}
              aria-label={d.railLabel}
              aria-current={d.cur ? 'true' : undefined}
              title={d.title}
              onClick={() => onPick(d.id)}
            >
              <span className={styles.railIdx}>{d.idx}</span>
              <span className={styles.railExt}>{d.ext}</span>
              <span aria-hidden="true" className={styles.dot} style={{ '--dot': d.status.dot } as CSSProperties} />
            </button>
          </li>
        ))}
      </ul>
    </aside>
  );
}
