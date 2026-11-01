import Link from 'next/link';
import type { ButtonHTMLAttributes, MouseEvent, ReactElement, ReactNode } from 'react';
import type { IconName } from '@/display/icon-names';
import { cx } from './cx';
import { GuardedButton } from './GuardedButton';
import { Icon, type IconSize, type IconStroke } from './Icon';
import { Spinner } from './Spinner';
import styles from './Button.module.css';

/**
 * 모양 — 보드 02 와 Main 마크업에 나온 것
 * - primary: 채운 초록. 그 화면의 다음 행동에만
 * - secondary: 회색 채움 · ghost: 글자 버튼(바탕 없음)
 * - soft: 옅은 초록(같은 사람·같은 건 맞음) · danger: 옅은 빨강(오류 확인) · dark: 남색(파일 선택)
 * - outline: 흰 바탕 + 안쪽 테두리(펼친 행 안의 보조 행동)
 */
export type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'soft' | 'danger' | 'dark' | 'outline';

/**
 * 크기
 * - sm: --ctl-sm(34 · 휴대폰 40) · md: --ctl(40 · 휴대폰 44) — 기본 · item: 36(펼친 행 안의 항목 행동)
 * - lg: 44(보드 02) · xl: 52(큰 주요 행동 — 새 분석·분석 시작)
 */
export type ButtonSize = 'sm' | 'md' | 'item' | 'lg' | 'xl';

interface CommonProps {
  variant?: ButtonVariant;
  size?: ButtonSize;
  /** 왼쪽 아이콘 — 아이콘 이름이면 크기에 맞춰 그린다. 직접 그린 요소도 받는다. */
  icon?: IconName | ReactElement;
  /** 아이콘 선 굵기(아이콘 이름을 줄 때). 기본은 크기별 디자인 값. */
  iconStrokeWidth?: IconStroke;
  /**
   * 로딩 — 돌림 표시 + 글자(예: '분석 요청 중…'). aria-busy + aria-disabled.
   * 포커스는 그대로 두고 누름을 막는다: onClick 을 부르지 않고, type="submit" 이어도 폼을 제출하지 않는다
   * (마우스·Enter·Space·입력칸 Enter 모두). `aria-disabled` 를 직접 줘도 같게 막힌다.
   */
  loading?: boolean;
  /** 주요 버튼 그림자(보드 02 '새 분석', 목록 '새 분석') */
  raised?: boolean;
  /** 가로로 꽉 채움 */
  block?: boolean;
  className?: string;
  children?: ReactNode;
}

export interface ButtonAsButtonProps extends CommonProps, Omit<ButtonHTMLAttributes<HTMLButtonElement>, 'className' | 'children'> {
  href?: undefined;
}

export interface ButtonAsLinkProps extends CommonProps {
  /** 있으면 Next <Link> 로 그린다 */
  href: string;
  onClick?: (event: MouseEvent<HTMLAnchorElement>) => void;
  disabled?: undefined;
  'aria-label'?: string;
  'aria-current'?: 'page' | 'step' | 'location' | 'true' | 'false';
  title?: string;
  id?: string;
  loading?: undefined;
}

export type ButtonProps = ButtonAsButtonProps | ButtonAsLinkProps;

const ICON_SIZE: Record<ButtonSize, IconSize> = { sm: 15, md: 17, item: 15, lg: 17, xl: 18 };

function defaultStroke(size: ButtonSize, variant: ButtonVariant): IconStroke {
  if (size === 'xl') return 2.4;
  if (size === 'item') return variant === 'primary' ? 2.6 : 2;
  return variant === 'ghost' ? 2.2 : 2.1;
}

function renderIcon(icon: CommonProps['icon'], size: ButtonSize, variant: ButtonVariant, stroke?: IconStroke) {
  if (!icon) return null;
  if (typeof icon === 'string') return <Icon name={icon} size={ICON_SIZE[size]} strokeWidth={stroke ?? defaultStroke(size, variant)} />;
  return icon;
}

/**
 * 버튼 — 보드 02. 마우스 올림(색이 한 단계 진해짐), 누름 scale(.97) 0.12초, 비활성, 로딩.
 * `href` 가 있으면 Next <Link> 로, 없으면 <button type="button"> 으로 그린다.
 */
export function Button(props: ButtonProps) {
  if (props.href !== undefined) return <LinkButton {...props} />;
  const {
    variant = 'primary',
    size = 'md',
    icon,
    iconStrokeWidth,
    loading = false,
    raised = false,
    block = false,
    className,
    children,
    type = 'button',
    onClick,
    ...rest
  } = props;
  const ariaDisabled = rest['aria-disabled'];
  /* 로딩 또는 비활성 표시(aria-disabled) — 누름·제출을 막는다(GuardedButton) */
  const blocked = loading || ariaDisabled === true || ariaDisabled === 'true';
  return (
    <GuardedButton
      {...rest}
      type={type}
      className={buttonClass({ variant, size, raised, block, loading, withIcon: loading || !!icon, className })}
      aria-busy={loading || undefined}
      aria-disabled={loading || ariaDisabled || undefined}
      blocked={blocked}
      onClick={onClick}
    >
      {loading ? <Spinner size={16} weight={size === 'lg' || size === 'xl' ? 'heavy' : 'medium'} /> : renderIcon(icon, size, variant, iconStrokeWidth)}
      {children}
    </GuardedButton>
  );
}

function LinkButton({
  href,
  variant = 'primary',
  size = 'md',
  icon,
  iconStrokeWidth,
  raised = false,
  block = false,
  className,
  children,
  onClick,
  title,
  id,
  ...aria
}: ButtonAsLinkProps) {
  return (
    <Link
      href={href}
      className={buttonClass({ variant, size, raised, block, withIcon: !!icon, className })}
      onClick={onClick}
      title={title}
      id={id}
      aria-label={aria['aria-label']}
      aria-current={aria['aria-current']}
    >
      {renderIcon(icon, size, variant, iconStrokeWidth)}
      {children}
    </Link>
  );
}

/** 버튼 모양 클래스 — 다른 요소(예: label 로 감싼 파일 선택)에 버튼 모양을 입힐 때도 쓴다. */
export function buttonClass({
  variant = 'primary',
  size = 'md',
  raised = false,
  block = false,
  loading = false,
  withIcon = false,
  className,
}: {
  variant?: ButtonVariant;
  size?: ButtonSize;
  raised?: boolean;
  block?: boolean;
  loading?: boolean;
  /** 왼쪽 아이콘이 있으면 왼쪽 여백이 줄어든다(디자인 값) */
  withIcon?: boolean;
  className?: string;
}): string {
  return cx(
    styles.button,
    styles[variant],
    styles[size],
    withIcon && styles.withIcon,
    raised && styles.raised,
    block && styles.block,
    loading && styles.loading,
    className,
  );
}
