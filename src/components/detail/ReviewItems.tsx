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
  /** 해결 · 다시 열기를 막는다(검토 완료 · 검토 기록을 불러오지 못한 실제 분석 — ResultsModel.itemsLocked) */
  locked: boolean;
  /** 검토사항이 없을 때 제목 아래 설명 줄(빈 글이면 제목만 — 실제 분석) */
  emptyText: string;
  /** 근거 위치 링크 — 문서 · 쪽을 바꾸고 그 위치로(휴대폰이면 원문 탭으로) */
  onEvidence: (rid: string, idx: number) => void;
  /** '연결 보기' — 문서 간 연결 탭의 그 카드로 */
  onOpenLink: (lid: string) => void;
  actions: DetailActions;
}

/**
 * 검토 필요 탭(Main 515–542) — '유지' 안내(rs.keep), 미해결 · 해결 건수, 검토사항 행
 * (유형 · ID · 해결 상태, 제목, 설명, 위치, 할 일, 처리 내용, 근거 위치 · 연결 보기 · 다시 분석 · 해결 · 다시 열기).
 * 실제 분석도 같은 행을 그린다(서버가 만든 검토사항 글 그대로). 검토사항이 없으면 제목 + 설명 줄(emptyText — 실제 분석은 제목만).
 */
export function ReviewItems({ keep, nOpen, nDone, items, locked, emptyText, onEvidence, onOpenLink, actions }: ReviewItemsProps) {
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
              <Button size="item" variant="outline" icon="dg-i-refresh" disabled={it.retrying} onClick={() => actions.retry(it.retryDoc ?? undefined)} className={styles.retry} data-slot="retry">
                {it.retryLabel}
              </Button>
            ) : null}
            {it.canResolve ? (
              <Button size="item" variant="primary" icon="dg-i-check" disabled={locked} onClick={() => actions.resolveItem(it.id)} data-slot="resolve">
                해결로 표시
              </Button>
            ) : null}
            {it.canReopen ? (
              <Button size="item" variant="ghost" disabled={locked} onClick={() => actions.reopenItem(it.id)} data-slot="resolve">
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
          {emptyText ? <span className={styles.emptyText}>{emptyText}</span> : null}
        </div>
      ) : null}
    </>
  );
}
