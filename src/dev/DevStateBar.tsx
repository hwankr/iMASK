'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useEffect } from 'react';
import type { StateId } from '@/services/analysis-service';
import { statePosition } from './states';
import styles from './DevStateBar.module.css';

/** 이전·다음 상태 단축키 — 화면 안의 화살표·Home·End(탭·드롭다운)와 겹치지 않는 대괄호 */
export const PREV_KEY = '[';
export const NEXT_KEY = ']';

type ShortcutEvent = Pick<KeyboardEvent, 'key' | 'altKey' | 'ctrlKey' | 'metaKey' | 'repeat' | 'defaultPrevented' | 'isComposing'>;

/** 글자를 쓰는 입력 요소인지 — 체크박스·라디오·버튼 같은 입력은 글자를 받지 않는다 */
const NON_TEXT_INPUTS = ['checkbox', 'radio', 'button', 'submit', 'reset', 'range', 'file', 'color'];

/**
 * 단축키를 무시할 때 — 대괄호가 아닌 키, 조합 키, 길게 누름, 다른 처리기가 이미 쓴 키, 한글 조합 중, 글자 입력칸.
 * 모달이 열려 있어도 동작한다(상세 '분류 수정' · 보고서 내보내기처럼 모달로 시작하는 상태를 바로 넘길 수 있게).
 */
export function shouldIgnoreShortcut(e: ShortcutEvent, target: EventTarget | null): boolean {
  if (e.key !== PREV_KEY && e.key !== NEXT_KEY) return true;
  if (e.altKey || e.ctrlKey || e.metaKey || e.repeat || e.defaultPrevented || e.isComposing) return true;
  if (typeof HTMLElement !== 'undefined' && target instanceof HTMLElement) {
    if (target.isContentEditable) return true;
    const tag = target.tagName;
    if (tag === 'TEXTAREA' || tag === 'SELECT') return true;
    if (tag === 'INPUT') {
      if (!NON_TEXT_INPUTS.includes((target as HTMLInputElement).type)) return true;
    }
  }
  return false;
}

/**
 * /dev/states/[state] 미리보기 위에 붙는 막대 — ← 상태 목록 · n / 23 · 제목 · 이전 · 다음.
 * 키보드: `[` 이전 상태, `]` 다음 상태(입력칸에 글자를 쓰는 중이면 무시).
 * 상태를 바꾸면 StatePreview 의 PreparedState 가 새 상태로 다시 그려지며 데모 서비스를 다시 준비한다.
 */
export function DevStateBar({ stateId }: { stateId: StateId }) {
  const router = useRouter();
  const pos = statePosition(stateId);
  const prevHref = pos?.prev ? `/dev/states/${pos.prev.id}` : null;
  const nextHref = pos?.next ? `/dev/states/${pos.next.id}` : null;

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (shouldIgnoreShortcut(e, e.target)) return;
      const href = e.key === PREV_KEY ? prevHref : nextHref;
      if (!href) return;
      e.preventDefault();
      router.push(href);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [router, prevHref, nextHref]);

  if (!pos) return null;
  const { state, number, total, prev, next } = pos;
  return (
    <nav className={styles.bar} aria-label="개발용 상태 이동">
      <Link className={styles.back} href="/dev/states">
        ← 상태 목록
      </Link>
      <span className={styles.sep} aria-hidden="true">·</span>
      {number === null ? (
        <span className={styles.phone}>휴대폰 전용</span>
      ) : (
        <span className={styles.count}>{`${number} / ${total}`}</span>
      )}
      <span className={styles.sep} aria-hidden="true">·</span>
      <span className={styles.title} aria-current="page">
        {state.title}
      </span>
      <span className={styles.moves}>
        {prev && prevHref ? (
          <Link className={styles.move} href={prevHref} title={`${prev.title} (키보드 ${PREV_KEY})`} aria-keyshortcuts={PREV_KEY}>
            이전
            <kbd className={styles.key} aria-hidden="true">{PREV_KEY}</kbd>
          </Link>
        ) : (
          <span className={styles.move} aria-disabled="true">이전</span>
        )}
        {next && nextHref ? (
          <Link className={styles.move} href={nextHref} title={`${next.title} (키보드 ${NEXT_KEY})`} aria-keyshortcuts={NEXT_KEY}>
            다음
            <kbd className={styles.key} aria-hidden="true">{NEXT_KEY}</kbd>
          </Link>
        ) : (
          <span className={styles.move} aria-disabled="true">다음</span>
        )}
      </span>
    </nav>
  );
}
