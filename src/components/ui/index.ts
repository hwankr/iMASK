/* 공통 컴포넌트 — 화면(T4~T8)은 여기서 가져다 쓴다. 값·라벨은 ② src/display/rules.ts 에서 온다. */
export { cx } from './cx';
export { Icon, type IconProps, type IconSize, type IconStroke } from './Icon';
export { IconSprite } from './IconSprite';
export { Spinner, type SpinnerProps, type SpinnerSize, type SpinnerWeight } from './Spinner';
export { VisuallyHidden } from './VisuallyHidden';

/* 01 상태 표기 */
export { RiskBadge, type RiskBadgeProps, type RiskBadgeSize } from './RiskBadge';
export { AnalysisStatusLabel, type AnalysisStatusLabelProps, type AnalysisStatusSize } from './AnalysisStatusLabel';
export { ReviewStatusPill, type ReviewStatusPillProps, type ReviewStatusSize } from './ReviewStatusPill';
export { FindingStatusLabel, type FindingStatusLabelProps } from './FindingStatusLabel';

/* 02 버튼 */
export { Button, buttonClass, type ButtonProps, type ButtonSize, type ButtonVariant } from './Button';
export { IconButton, type IconButtonProps, type IconButtonSize, type IconButtonVariant } from './IconButton';

/* 03 입력과 선택 */
export { TextField, type TextFieldProps } from './TextField';
export { SearchField, type SearchFieldProps } from './SearchField';
export { Dropdown, type DropdownOption, type DropdownProps, type DropdownVariant } from './Dropdown';
export { SegmentedTabs, tabPanelProps, type SegmentedTab, type SegmentedTabsProps } from './SegmentedTabs';
export { FilterChips, type FilterChip, type FilterChipsProps } from './FilterChips';
export { Switch, type SwitchProps } from './Switch';
export { RadioList, type RadioListProps, type RadioOption } from './RadioList';

/* 06 알림과 진행 */
export { Modal, type ModalButton, type ModalProps, type ModalWidth } from './Modal';
export { Toast, ToastProvider, useToast, TOAST_DURATION_MS, type ToastAction, type ToastFn, type ToastKind, type ToastOptions } from './Toast';
export { LiveRegion, LiveRegionProvider, useAnnounce } from './LiveRegion';
export { Banner, type BannerAction, type BannerProps, type BannerVariant } from './Banner';
export { IndeterminateBar, type IndeterminateBarProps } from './IndeterminateBar';
export { Skeleton, SkeletonCard, type SkeletonCardProps, type SkeletonProps } from './Skeleton';

/* 07 움직임 */
export { CountUp, type CountUpProps } from './CountUp';
