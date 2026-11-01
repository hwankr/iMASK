import type { ReactNode } from 'react';
import type { IconName } from '@/display/icon-names';
import { cx } from './cx';
import { Icon } from './Icon';
import { IndeterminateBar } from './IndeterminateBar';
import { Spinner } from './Spinner';
import styles from './Banner.module.css';

/**
 * 띠 종류 — 프로토타입 bannerVM 의 색 조합
 * - running: 분석 중(돌림 표시 + 흐르는 막대) · partial: 일부 실패 · failed: 실패
 * - done: 검토 완료 · info: 정보(대기 등)
 */
export type BannerVariant = 'running' | 'partial' | 'failed' | 'done' | 'info';

export interface BannerAction {
  label: string;
  onClick: () => void;
  disabled?: boolean;
}

export interface BannerProps {
  variant: BannerVariant;
  /** 굵은 제목(띠 색 글자) */
  title: ReactNode;
  /** 설명(진한 보조 글자) */
  description?: ReactNode;
  /** 기본 아이콘 대신 쓸 아이콘(예: 대기 = dg-i-clock). running 에서는 돌림 표시가 나온다. */
  icon?: IconName;
  /** 오른쪽 행동 버튼(흰 34px 버튼) */
  actions?: readonly BannerAction[];
  /** 행동 자리에 직접 그릴 것(actions 대신) */
  actionSlot?: ReactNode;
  /**
   * band(기본): 화면 위 꽉 찬 띠(상세 화면 358–366, 좌우 여백 = --gutter)
   * card: 둥근 띠(보드 06)
   */
  shape?: 'band' | 'card';
  className?: string;
}

const DEFAULT_ICON: Record<BannerVariant, IconName> = {
  running: 'dg-i-clock',
  partial: 'dg-i-alert',
  failed: 'dg-i-x-circle',
  done: 'dg-i-check-badge',
  info: 'dg-i-info',
};

/**
 * 화면 위 띠 — 아이콘 · 제목 · 설명 · 행동. role="status" 로 바뀐 상태를 알린다.
 * 분석 중(running)은 진행률 숫자 대신 아래 가장자리에 흐르는 막대를 둔다.
 */
export function Banner({ variant, title, description, icon, actions, actionSlot, shape = 'band', className }: BannerProps) {
  const running = variant === 'running';
  const hasActions = !!actionSlot || (actions && actions.length > 0);
  return (
    <div role="status" className={cx(styles.banner, styles[variant], styles[shape], className)}>
      <span className={styles.icon}>{running ? <Spinner size={16} /> : <Icon name={icon ?? DEFAULT_ICON[variant]} size={18} strokeWidth={2.1} />}</span>
      <div className={styles.text}>
        <strong className={styles.title}>{title}</strong>
        {description ? (
          <>
            {' '}
            <span className={styles.desc}>{description}</span>
          </>
        ) : null}
      </div>
      {hasActions ? (
        <div className={styles.actions}>
          {actionSlot ??
            actions?.map((a) => (
              <button key={a.label} type="button" className={styles.action} onClick={a.onClick} disabled={a.disabled}>
                {a.label}
              </button>
            ))}
        </div>
      ) : null}
      {running ? <IndeterminateBar variant="edge" tone="run" /> : null}
    </div>
  );
}
