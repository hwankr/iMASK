import Link from 'next/link';
import type { ButtonHTMLAttributes, MouseEvent } from 'react';
import type { IconName } from '@/display/icon-names';
import { cx } from './cx';
import { Icon, type IconSize, type IconStroke } from './Icon';
import styles from './IconButton.module.css';

/** 크기(px) — 디자인에 쓰인 값. 휴대폰에서는 보이는 크기와 관계없이 누르는 영역이 44px 이상이다. */
export type IconButtonSize = 32 | 34 | 36 | 40 | 44;

/**
 * 모양
 * - ghost: 바탕 없음 · 진한 보조 글자(--ink-2), 올리면 회색(닫기·뒤로)
 * - muted: 바탕 없음 · 보조 글자(--ink-3), 올리면 회색 + 남색(목록에서 제거·접기)
 * - secondary: 회색 채움(보고서·다음 페이지)
 * - danger: 옅은 빨강 채움(지우기 — 공통 Button danger 와 같은 토큰)
 */
export type IconButtonVariant = 'ghost' | 'muted' | 'secondary' | 'danger';

interface CommonProps {
  /** 필수 — aria-label 과 툴팁 글자 */
  label: string;
  icon: IconName;
  size?: IconButtonSize;
  variant?: IconButtonVariant;
  iconSize?: IconSize;
  strokeWidth?: IconStroke;
  /** 툴팁 위치. 기본 아래 */
  tooltip?: 'bottom' | 'top' | 'none';
  className?: string;
}

export interface IconButtonAsButtonProps
  extends CommonProps,
    Omit<ButtonHTMLAttributes<HTMLButtonElement>, 'className' | 'children' | 'aria-label'> {
  href?: undefined;
}

export interface IconButtonAsLinkProps extends CommonProps {
  href: string;
  onClick?: (event: MouseEvent<HTMLAnchorElement>) => void;
}

export type IconButtonProps = IconButtonAsButtonProps | IconButtonAsLinkProps;

const DEFAULT_ICON: Record<IconButtonSize, IconSize> = { 32: 16, 34: 18, 36: 18, 40: 20, 44: 20 };

function iconButtonClass(size: IconButtonSize, variant: IconButtonVariant, className?: string) {
  return cx(styles.button, styles[`s${size}`], styles[variant], className);
}

function Inner({ label, icon, size, iconSize, strokeWidth = 2.2, tooltip = 'bottom' }: Pick<CommonProps, 'label' | 'icon' | 'iconSize' | 'strokeWidth' | 'tooltip'> & { size: IconButtonSize }) {
  return (
    <>
      <Icon name={icon} size={iconSize ?? DEFAULT_ICON[size]} strokeWidth={strokeWidth} />
      {tooltip !== 'none' ? (
        <span className={cx(styles.tip, tooltip === 'top' && styles.tipTop)} aria-hidden="true">
          {label}
        </span>
      ) : null}
    </>
  );
}

/**
 * 아이콘만 있는 버튼 — `label` 이 aria-label 이 되고, 마우스 올림·키보드 포커스 때 툴팁으로 보인다.
 * 누름 scale(.92). `href` 가 있으면 Next <Link> 로 그린다.
 */
export function IconButton(props: IconButtonProps) {
  if (props.href !== undefined) return <IconLink {...props} />;
  const { label, icon, size = 40, variant = 'ghost', iconSize, strokeWidth, tooltip, className, type = 'button', ...rest } = props;
  return (
    <button {...rest} type={type} aria-label={label} className={iconButtonClass(size, variant, className)}>
      <Inner label={label} icon={icon} size={size} iconSize={iconSize} strokeWidth={strokeWidth} tooltip={tooltip} />
    </button>
  );
}

function IconLink({ href, onClick, label, icon, size = 40, variant = 'ghost', iconSize, strokeWidth, tooltip, className }: IconButtonAsLinkProps) {
  return (
    <Link href={href} onClick={onClick} aria-label={label} className={iconButtonClass(size, variant, className)}>
      <Inner label={label} icon={icon} size={size} iconSize={iconSize} strokeWidth={strokeWidth} tooltip={tooltip} />
    </Link>
  );
}
