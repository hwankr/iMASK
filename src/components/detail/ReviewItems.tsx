'use client';

import { Button, Icon, cx } from '@/components/ui';
import type { DetailActions } from './detailActions';
import type { ItemModel } from './detailModel';
import { SpriteIcon } from './SpriteIcon';
import styles from './ReviewItems.module.css';

export interface ReviewItemsProps {
  keep: string | null;
  nOpen: number;
  nDone: number;
  items: ItemModel[];
  locked: boolean;
  /** 근거 위치 링크 — 문서 · 쪽을 바꾸고 그 위치로(휴대폰이면 원문 탭으로) */
  onEvidence: (rid: string, idx: number) => void;
  /** '연결 보기' — 문서 간 연결 탭의 그 카드로 */
  onOpenLink: (lid: string) => void;
  actions: DetailActions;
}

/**
 * 검토 필요 탭(Main 515–542) — '유지' 안내(rs.keep), 미해결 · 해결 건수, 검토사항 행
 * (유형 · ID · 해결 상태, 제목, 설명, 위치, 할 일, 처리 내용, 근거 위치 · 연결 보기 · 다시 분석 · 해결 · 다시 열기).
 */
export function ReviewItems({ keep, nOpen, nDone, items, locked, onEvidence, onOpenLink, actions }: ReviewItemsProps) {
  return (
    <>
      {keep ? (
        <div className={styles.keep}>
          <span className={styles.keepIcon}>
            <Icon name="dg-i-alert" size={17} strokeWidth={2.1} />
          </span>
          <span>{keep}</span>
        </div>
      ) : null}
      <div className={styles.count}>
        미해결 <strong className={styles.countOpen}>{nOpen}</strong>건 · 해결 {nDone}건
      </div>
      {items.map((it) => (
        <article key={it.id} data-card={it.id} className={cx(styles.item, it.sel && styles.sel, it.resolved && styles.resolved)}>
          <div className={styles.head}>
            <span className={styles.type}>
              <Icon name={it.icon} size={13} strokeWidth={2.2} />
              {it.type}
            </span>
            <span className={styles.id}>{it.id}</span>
            <span className={styles.state}>
              <Icon name={it.resolved ? 'dg-i-check' : 'dg-i-circle'} size={13} strokeWidth={2.4} />
              {it.resolved ? '해결' : '미해결'}
            </span>
          </div>
          <strong className={styles.title}>{it.title}</strong>
          <p className={styles.desc}>{it.desc}</p>
          <div className={styles.where}>
            <Icon name="dg-i-file" size={13} />
            {it.where}
          </div>
          <div className={styles.todo}>
            <strong>할 일</strong> · {it.next}
          </div>
          {it.resolved ? (
            <div className={styles.done}>
              <span className={styles.doneIcon}>
                <Icon name="dg-i-check" size={15} strokeWidth={2.4} />
              </span>
              <span>{it.resolvedText}</span>
            </div>
          ) : null}
          <div className={styles.actions}>
            {it.evidence.map((ev, i) => (
              <Button key={i} size="item" variant="outline" icon="dg-i-file" onClick={() => onEvidence(it.id, i)}>
                {ev.label}
              </Button>
            ))}
            {it.linkId ? (
              <Button size="item" variant="outline" icon="dg-i-link" onClick={() => onOpenLink(it.linkId as string)}>
                연결 보기
              </Button>
            ) : null}
            {it.canRetry ? (
              <Button size="item" variant="outline" icon="dg-i-refresh" disabled={it.retrying} onClick={() => actions.retry(it.retryDoc ?? undefined)} className={styles.retry}>
                {it.retryLabel}
              </Button>
            ) : null}
            {it.canResolve ? (
              <Button size="item" variant="primary" icon="dg-i-check" disabled={locked} onClick={() => actions.resolveItem(it.id)}>
                해결로 표시
              </Button>
            ) : null}
            {it.canReopen ? (
              <Button size="item" variant="ghost" disabled={locked} onClick={() => actions.reopenItem(it.id)}>
                다시 열기
              </Button>
            ) : null}
          </div>
        </article>
      ))}
      {items.length === 0 ? (
        <div className={styles.empty}>
          <span className={styles.emptyIcon}>
            <SpriteIcon name="dg-i-check-circle" className={styles.icon26} />
          </span>
          <strong className={styles.emptyTitle}>확인이 필요한 문제가 없습니다</strong>
          <span className={styles.emptyText}>판독 실패, 잘린 페이지, 값 불일치, 연결 근거 부족 같은 문제가 발견되면 이곳에 표시됩니다.</span>
        </div>
      ) : null}
    </>
  );
}
