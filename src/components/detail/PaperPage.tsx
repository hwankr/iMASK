'use client';

import { Fragment, type CSSProperties } from 'react';
import { Icon, cx } from '@/components/ui';
import type { BlockModel, HighlightVars, SegmentModel } from './detailModel';
import styles from './Paper.module.css';

/** 하이라이트 색 변수 — ② 위험 색(var(--hi-soft) 등)을 CSS 변수로 넘긴다 */
function hlStyle(v: HighlightVars, on: boolean): CSSProperties {
  return {
    '--hl-soft': v.soft,
    '--hl-solid': v.solid,
    '--hl-on': v.onBg,
    '--pc': on ? v.pc : 'transparent',
    '--ph': on ? v.ph : 'transparent',
  } as CSSProperties;
}

interface RenderCtx {
  /** 고른 위치 이름표 */
  tag: { text: string; bg: string };
  /** 선택 신호 클래스(dg-ring-a/b 번갈아) */
  ring: string;
  onPick: (findingId: string) => void;
}

function Tag({ ctx, className }: { ctx: RenderCtx; className?: string }) {
  return (
    <span aria-hidden="true" className={cx(styles.tag, className)} style={{ '--tag-bg': ctx.tag.bg } as CSSProperties}>
      {ctx.tag.text}
    </span>
  );
}

/** 글 조각 — 일반 글자 · 하이라이트 버튼(탐지 위치) · 표시(고른 다른 위치) · 이름표 */
function Segs({ segs, ctx, place = 'text' }: { segs: SegmentModel[]; ctx: RenderCtx; place?: 'text' | 'stamp' | 'foot' }) {
  return (
    <>
      {segs.map((s, i) => {
        if (s.kind === 'plain') return <Fragment key={i}>{s.text}</Fragment>;
        if (s.kind === 'hl') {
          return (
            <button
              key={i}
              type="button"
              data-anchor={s.anchor}
              aria-label={s.aria}
              aria-pressed={s.pressed}
              className={cx(styles.hl, s.fp && styles.fp, s.on && styles.on, s.on && ctx.ring, place === 'stamp' && styles.stampHl)}
              style={hlStyle(s.vars, s.on)}
              onClick={() => ctx.onPick(s.findingId)}
            >
              {s.shown}
              {s.tag && place !== 'stamp' ? <Tag ctx={ctx} /> : null}
            </button>
          );
        }
        return (
          <span key={i} data-anchor={s.anchor} className={cx(styles.mark, ctx.ring)} style={hlStyle(s.vars, true)}>
            {s.text}
            {s.tag && place === 'text' ? <Tag ctx={ctx} /> : null}
            {s.tag && place === 'stamp' ? <Tag ctx={ctx} className={styles.tagStamp} /> : null}
          </span>
        );
      })}
    </>
  );
}

const ALIGN = { left: styles.left, right: styles.right, center: styles.center } as const;

function Block({ b, ctx }: { b: BlockModel; ctx: RenderCtx }) {
  switch (b.t) {
    case 'bar':
      return (
        <div className={styles.bar}>
          <span className={styles.barLeft}>{b.left}</span>
          <span>{b.right}</span>
        </div>
      );
    case 'title':
      return (
        <div className={styles.titleBlock}>
          <div className={styles.titleText}>{b.text}</div>
          {b.sub ? <div className={styles.titleSub}>{b.sub}</div> : null}
        </div>
      );
    case 'sec':
      return <div className={styles.sec}>{b.text}</div>;
    case 'kv':
      return (
        <div className={cx(styles.kv, b.cols === 3 ? styles.kv3 : styles.kv2)}>
          {b.items.map((it, i) => (
            <div key={i} className={styles.kvItem} style={{ gridColumn: 'span ' + it.span }}>
              <div className={styles.kvLabel}>{it.k}</div>
              <div className={styles.kvValue}>
                <Segs segs={it.segs} ctx={ctx} />
              </div>
            </div>
          ))}
        </div>
      );
    case 'table':
      return (
        <table className={styles.table}>
          <thead>
            <tr>
              {b.head.map((h, i) => (
                <th key={i} className={cx(styles.th, ALIGN[h.align])}>
                  {h.text}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {b.rows.map((row, r) => (
              <tr key={r}>
                {row.map((cell, c) => (
                  <td key={c} className={cx(styles.td, ALIGN[cell.align])}>
                    <Segs segs={cell.segs} ctx={ctx} />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      );
    case 'p':
      return (
        <p className={cx(styles.p, b.small && styles.small)}>
          <Segs segs={b.segs} ctx={ctx} />
        </p>
      );
    case 'checks':
      return (
        <div className={styles.checks}>
          {b.items.map((c, i) => (
            <div key={i} className={styles.check}>
              <span aria-hidden="true" className={styles.box}>
                {c.on ? (
                  <svg className={styles.boxMark} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={3.2} strokeLinecap="round" strokeLinejoin="round">
                    <path d="m5 12.5 4.5 4.5L19 7.5" />
                  </svg>
                ) : null}
              </span>
              <span>{c.text}</span>
            </div>
          ))}
        </div>
      );
    case 'sign':
      return (
        <div className={styles.sign}>
          <div className={styles.signDate}>{b.date}</div>
          {b.items.map((it, i) => (
            <div key={i} className={styles.signRow}>
              <span className={styles.signRole}>{it.k}</span>
              <span className={styles.signName}>
                <Segs segs={it.segs} ctx={ctx} />
              </span>
              <span className={styles.signMark}>{it.suffix}</span>
            </div>
          ))}
        </div>
      );
    case 'stamp':
      return (
        <div className={styles.stamp}>
          {b.lines.map((ln, i) => (
            <div key={i}>
              <Segs segs={ln} ctx={ctx} place="stamp" />
            </div>
          ))}
        </div>
      );
    case 'blur':
      return (
        <div data-anchor={b.anchor} className={cx(styles.blur, b.on && styles.blockOn, b.on && ctx.ring)} style={hlStyle(b.vars, b.on)}>
          <div aria-hidden="true" className={styles.blurText}>
            {b.lines.map((ln, i) => (
              <div key={i}>{ln}</div>
            ))}
          </div>
          <div className={styles.blurCover}>
            <span className={styles.flag}>
              <Icon name="dg-i-eye-off" size={14} />
              {b.label}
            </span>
          </div>
          {b.tag ? <Tag ctx={ctx} className={styles.tagBlock} /> : null}
        </div>
      );
    case 'cut':
      return (
        <div data-anchor={b.anchor} className={cx(styles.cut, b.on && styles.blockOn, b.on && ctx.ring)} style={hlStyle(b.vars, b.on)}>
          <div className={styles.cutGhost}>{b.ghost}</div>
          <svg aria-hidden="true" className={styles.cutEdge} width="100%" height="10" viewBox="0 0 100 10" preserveAspectRatio="none">
            <polygon points="0,0 3,7 6,2 9,8 12,3 15,9 18,2 21,7 24,3 27,9 30,2 33,8 36,3 39,7 42,2 45,9 48,3 51,8 54,2 57,7 60,3 63,9 66,2 69,8 72,3 75,7 78,2 81,9 84,3 87,8 90,2 93,7 96,3 100,8 100,10 0,10" />
          </svg>
          <div className={styles.cutBody}>
            <span className={cx(styles.flag, styles.flagCut)}>
              <Icon name="dg-i-scissors" size={14} />
              {b.label}
            </span>
          </div>
          {b.tag ? <Tag ctx={ctx} className={styles.tagBlock} /> : null}
        </div>
      );
    case 'foot':
      return (
        <div className={styles.foot}>
          <div className={styles.footInner}>
            <span>
              <Segs segs={b.segs} ctx={ctx} place="foot" />
            </span>
            <span>{b.right}</span>
          </div>
        </div>
      );
  }
}

export interface PaperPageProps {
  blocks: BlockModel[];
  /** 종이 이름(문서 이름 + 쪽) */
  ariaLabel: string;
  scan: boolean;
  /** 쪽 떠오름 dg-page-a(true) / dg-page-b(false) */
  pageFlip: boolean;
  /** 선택 신호 dg-ring-a(true) / dg-ring-b(false) */
  ringFlip: boolean;
  tag: { text: string; bg: string };
  onPickFinding: (findingId: string) => void;
}

/** 샘플 문서 한 쪽(Main 408–423) — 블록 12종을 그린다. 실제 PDF 뷰어가 아니라 가상 서식 화면이다. */
export function PaperPage({ blocks, ariaLabel, scan, pageFlip, ringFlip, tag, onPickFinding }: PaperPageProps) {
  const ctx: RenderCtx = { tag, ring: ringFlip ? styles.ringA : styles.ringB, onPick: onPickFinding };
  return (
    <article aria-label={ariaLabel} className={cx(styles.paper, pageFlip ? styles.pageA : styles.pageB, scan && styles.scan)}>
      {blocks.map((b, i) => (
        <Block key={i} b={b} ctx={ctx} />
      ))}
    </article>
  );
}
