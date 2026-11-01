'use client';

import type { CSSProperties } from 'react';
import { Button, Icon, cx } from '@/components/ui';
import type { DetailActions } from './detailActions';
import type { LinkModel } from './detailModel';
import styles from './LinkCards.module.css';

export interface LinkCardsProps {
  links: LinkModel[];
  locked: boolean;
  /** '근거 보기' — 그 문서 · 쪽의 연결 근거 위치로(휴대폰이면 원문 탭으로) */
  onPickDoc: (lid: string, idx: number) => void;
  actions: DetailActions;
}

/**
 * 문서 간 연결 탭(Main 544–563) — 연결 카드(상태 · ID · 제목, 문서별 근거 위치, 연결 근거, 부족한 근거,
 * 확인할 내용, 판단 결과, 판단 버튼(T7 모달)), 없음 상태.
 */
export function LinkCards({ links, locked, onPickDoc, actions }: LinkCardsProps) {
  return (
    <>
      <p className={styles.intro}>
        문서 사이에서 같은 사람이나 같은 신청 건을 가리키는 정보를 찾았습니다. 이름만 같은 경우에는 연결된 것으로 보지 않고 ‘연결 확인 필요’로 표시합니다.
      </p>
      {links.map((l) => (
        <article key={l.id} data-card={l.id} className={cx(styles.card, l.sel && styles.sel)}>
          <div className={styles.head}>
            <span className={styles.status} style={{ '--ls-bg': l.status.bg, '--ls-fg': l.status.fg } as CSSProperties}>
              <Icon name={l.status.icon} size={13} strokeWidth={2.2} />
              {l.status.label}
            </span>
            <span className={styles.id}>{l.id}</span>
          </div>
          <strong className={styles.title}>{l.title}</strong>
          <ol className={styles.docs}>
            {l.docs.map((ld, i) => (
              <li key={i} className={cx(styles.doc, ld.on && styles.docOn)}>
                <span aria-hidden="true" className={styles.tile}>
                  {ld.ext}
                </span>
                <div className={styles.docTexts}>
                  <div className={styles.docTitle}>
                    {ld.title} · {ld.page}쪽
                  </div>
                  <div className={styles.docFields}>{ld.fields}</div>
                </div>
                <button type="button" aria-label={ld.aria} className={styles.goBtn} onClick={() => onPickDoc(l.id, i)}>
                  근거 보기
                </button>
              </li>
            ))}
          </ol>
          <div className={styles.basis}>
            <span className={styles.basisLabel}>연결 근거</span>
            <ul className={styles.basisList}>
              {l.basis.map((b, i) => (
                <li key={i} className={styles.basisItem}>
                  <span className={styles.basisIcon}>
                    <Icon name="dg-i-check" size={15} strokeWidth={2.6} />
                  </span>
                  <span>{b}</span>
                </li>
              ))}
            </ul>
          </div>
          {l.missing ? (
            <div className={styles.missing}>
              <span className={styles.missingIcon}>
                <Icon name="dg-i-alert" size={15} strokeWidth={2.2} />
              </span>
              <span>
                <strong>부족한 근거</strong> · {l.missing}
              </span>
            </div>
          ) : null}
          <div className={styles.check}>
            <strong>확인할 내용</strong> · {l.check}
          </div>
          {l.decided ? (
            <div className={styles.decided}>
              <span className={styles.decidedIcon}>
                <Icon name="dg-i-history" size={14} />
              </span>
              <span>{l.decisionText}</span>
            </div>
          ) : null}
          {l.canDecide ? (
            <div className={styles.decide}>
              <Button variant="soft" icon="dg-i-link" iconStrokeWidth={2.2} disabled={locked} onClick={() => actions.decideLink(l.id, 'linked')} className={cx(styles.decideBtn, styles.decideYes)}>
                같은 사람·같은 건 맞음
              </Button>
              <Button variant="secondary" icon="dg-i-link-off" iconStrokeWidth={2.2} disabled={locked} onClick={() => actions.decideLink(l.id, 'unlinked')} className={cx(styles.decideBtn, styles.decideNo)}>
                연결 아님
              </Button>
            </div>
          ) : null}
        </article>
      ))}
      {links.length === 0 ? <div className={styles.empty}>이 분석 건에서는 문서 사이의 연결을 찾지 못했습니다. 문서가 2개 이상이고 공통된 식별 정보가 있을 때 표시됩니다.</div> : null}
    </>
  );
}
