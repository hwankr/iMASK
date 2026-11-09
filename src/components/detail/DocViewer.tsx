'use client';

import Link from 'next/link';
import { useCallback, useEffect, useEffectEvent, useLayoutEffect, useRef, useState } from 'react';
import type { CSSProperties } from 'react';
import { Button, Icon, IconButton, SkeletonCard, Spinner, cx } from '@/components/ui';
import { useReplayToggle } from '@/lib/hooks';
import { newAnalysisHref, type RouteBase } from '@/lib/routes';
import { useRouteBase } from '@/services/react';
import { liveFilePlaceholder, type PlaceholderModel, type ViewerModel } from './detailModel';
import type { PanelProps } from './DocList';
import { LivePaper } from './LivePaper';
import type { LiveFileState } from './liveFile';
import { MASK_PDF_BUSY_LABEL, MASK_PDF_LABEL } from './maskPdf';
import { PaperPage } from './PaperPage';
import { createPageFlipMemo, wheelPageFlip, type PageFlipMemo } from './pageFlip';
import { Tip } from './Tip';
import { createWheelZoomMemo, isPinchWheel, wheelZoom, WHEEL_IDLE_MS, type WheelZoomMemo } from './wheelZoom';
import styles from './DocViewer.module.css';

/** 체험용 샘플로 새 분석을 시작하는 주소(T5 가 ?sample=1 을 읽는다) — 그 기준 경로(`/demo` 아래면 `/demo/analyses/new?sample=1`) */
export function trySampleHref(base: RouteBase): string {
  return newAnalysisHref(base, { sample: true });
}

export interface DocViewerProps {
  v: ViewerModel;
  mobile: boolean;
  /** 좁은 뷰어(700px 미만) — 도구 줄 글자가 줄어든다(원본 vCompact) */
  compact: boolean;
  scrollRef: (el: HTMLElement | null) => void;
  onPrev: () => void;
  onNext: () => void;
  /** 쪽 끝에서 더 굴려 넘긴다 — 1 다음 쪽(맨 위부터), -1 앞 쪽(맨 아래부터) */
  onScrollFlip: (dir: 1 | -1) => void;
  onZoomOut: () => void;
  onZoomIn: () => void;
  /** Ctrl + 휠 · 트랙패드 오므리기 — 이 배율로(0.1 단위로 맞춘 값) */
  onZoomTo: (zoom: number) => void;
  onFit: () => void;
  onToggleMask: () => void;
  onPickFinding: (findingId: string) => void;
  /** 미리보기 대신 화면의 '이 문서 다시 분석'(T7) */
  onRetryDoc: (docId: string) => void;
  panel?: PanelProps;
  /** 실제 분석 — 원본 파일 상태와 처리기(데모는 없음) */
  live?: DocViewerLive;
}

/** 실제 분석 원문 — 원본 파일(상세 화면에서 한 번 받음) */
export interface DocViewerLive {
  file: LiveFileState;
  /** 종이 폭(px) — 잰 --paper-w. 재기 전이면 0 */
  paperW: number;
  /** '다시 시도' — 원본 파일을 다시 받는다 */
  onRetryFile: () => void;
  /** 쪽 크기를 알게 됐다 — 고른 위치로 다시 스크롤 */
  onPageReady: () => void;
  /** 마스킹 미리보기 공지의 '가린 PDF 내려받기'(useMaskedPdf) */
  maskPdf: { ready: boolean; busy: boolean; run: () => void };
}

/** 공지 안 버튼 — 지금은 '가린 PDF 내려받기' 하나(실제 분석 서류의 마스킹 미리보기 공지) */
function NoticeAction({ live }: { live: DocViewerLive }) {
  const m = live.maskPdf;
  return (
    <Button size="sm" variant="outline" icon="dg-i-download" loading={m.busy} disabled={!m.ready} onClick={m.run} data-slot="mask-pdf">
      {m.busy ? MASK_PDF_BUSY_LABEL : MASK_PDF_LABEL}
    </Button>
  );
}

/**
 * 미리보기 대신 화면. role 은 실제 분석 원본 파일 상태에만 준다(받는 중 · 여는 중 = status, 실패 = alert —
 * 낭독기가 바뀐 상태를 읽는다). 데모 화면은 role 없이 전과 같다.
 */
function Placeholder({
  ph,
  docId,
  onRetryDoc,
  onRetryFile,
  role,
}: {
  ph: PlaceholderModel;
  docId: string;
  onRetryDoc: (docId: string) => void;
  onRetryFile?: () => void;
  role?: 'status' | 'alert';
}) {
  const action = ph.action;
  const base = useRouteBase();
  return (
    <div className={styles.ph} role={role}>
      <span className={cx(styles.phIcon, ph.tone === 'err' && styles.phErr, ph.tone === 'run' && styles.phRun)}>
        {ph.spin ? <Spinner size={24} /> : <Icon name={ph.icon} size={28} strokeWidth={1.9} />}
      </span>
      <strong className={styles.phTitle}>{ph.title}</strong>
      <span className={styles.phText}>{ph.text}</span>
      {ph.skeleton ? <SkeletonCard look="viewer" lines={[46, 92, 78, 86, 58]} className={styles.phSkeleton} /> : null}
      {action && action.key === 'trySample' ? (
        <Link href={trySampleHref(base)} className={cx(styles.bigBtn, styles.phBtn)}>
          <Icon name={action.icon} size={17} strokeWidth={2.2} />
          {action.label}
        </Link>
      ) : null}
      {action && action.key === 'retryDoc' ? (
        <button type="button" className={cx(styles.bigBtn, styles.phBtn)} disabled={action.disabled} onClick={() => onRetryDoc(docId)} data-slot="retry-doc">
          <Icon name={action.icon} size={17} strokeWidth={2.2} />
          {action.label}
        </button>
      ) : null}
      {action && action.key === 'retryFile' && onRetryFile ? (
        <button type="button" className={cx(styles.bigBtn, styles.phBtn)} disabled={action.disabled} onClick={onRetryFile} data-slot="retry-file">
          <Icon name={action.icon} size={17} strokeWidth={2.2} />
          {action.label}
        </button>
      ) : null}
      {ph.note ? <span className={styles.phNote}>{ph.note}</span> : null}
    </div>
  );
}

/** 휠로 바꾼 배율 — 그 배율을 그리면 커서 아래 자리(종이 기준 비율 · 화면 좌표)가 그대로 오게 스크롤을 옮기고 지운다 */
interface WheelZoomPending {
  zoom: number;
  /** 휠 이벤트 시각(ms — performance.now 와 같은 기준) */
  at: number;
  anchor: { x: number; y: number; fx: number; fy: number } | null;
}

/** 원문 종이 — 데모 PaperPage · 실제 분석 LivePaper 모두 스크롤 영역 바로 아래 article 하나다 */
function paperIn(scroller: HTMLElement | null): HTMLElement | null {
  return scroller ? scroller.querySelector<HTMLElement>(':scope > article') : null;
}

/**
 * 원문 뷰어(Main 402–456) — 문서 이름 줄, 공지(v.notices), 샘플 문서 한 쪽, 미리보기 대신 화면(placeholderVM),
 * 떠 있는 도구 줄(쪽 이동 · 확대 · 축소 · 화면 맞춤 · 마스킹 미리보기).
 * 쪽이 바뀌면 종이가 떠오르고(dg-page-a/b), 고를 때마다 테두리 신호가 다시 돈다(dg-ring-a/b).
 * 뷰어 안의 Ctrl + 휠(트랙패드 오므리기 포함)은 브라우저 화면 확대 대신 원문 배율을 바꾼다(wheelZoom.ts).
 * 쪽 이동은 태블릿 · 데스크톱이면 원문 양옆의 둥근 버튼(도구 줄에는 쪽 번호만), 휴대폰이면 도구 줄 버튼이다.
 * 쪽 끝(아래 · 위)에서 더 굴리면 다음 · 앞 쪽으로 넘어간다(pageFlip.ts).
 */
export function DocViewer({
  v,
  mobile,
  compact,
  scrollRef,
  onPrev,
  onNext,
  onScrollFlip,
  onZoomOut,
  onZoomIn,
  onZoomTo,
  onFit,
  onToggleMask,
  onPickFinding,
  onRetryDoc,
  panel,
  live,
}: DocViewerProps) {
  const pageFlip = !useReplayToggle(v.pageKey);
  const ringFlip = !useReplayToggle(v.ringKey);
  // 떠 있는 도구 줄의 실제 높이(휴대폰만) — 좁은 휴대폰에서 두 줄로 접히면 CSS 가 스크롤 아래 여백을 그만큼 늘린다
  // (DocViewer.module.css 휴대폰 .scroll). 태블릿 · 데스크톱은 재지 않고 변수도 넘기지 않는다.
  const barRef = useRef<HTMLDivElement>(null);
  const [barH, setBarH] = useState<number | null>(null);
  useEffect(() => {
    const el = barRef.current;
    if (!mobile || !el || typeof ResizeObserver === 'undefined') return;
    const ro = new ResizeObserver(([entry]) => {
      setBarH(entry.borderBoxSize?.[0]?.blockSize ?? el.offsetHeight);
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, [mobile]);
  const barVar = mobile && barH !== null ? { '--viewer-bar-h': `${barH}px` } : null;

  // Ctrl + 휠 — React 의 onWheel 은 수동(passive) 리스너라 브라우저 확대를 막지 못해 뷰어(도구 줄 포함)에 직접 붙인다.
  // 쪽이 없을 때(받는 중 · 실패)도 뷰어 안에서는 브라우저 확대를 막고 배율만 그대로 둔다.
  const rootEl = useRef<HTMLElement>(null);
  const scrollEl = useRef<HTMLDivElement | null>(null);
  const setScrollEl = useCallback(
    (el: HTMLDivElement | null) => {
      scrollEl.current = el;
      scrollRef(el);
    },
    [scrollRef],
  );
  const wheelPending = useRef<WheelZoomPending | null>(null);
  const onCtrlWheel = useEffectEvent((e: WheelEvent, ctrlHeld: boolean, memo: WheelZoomMemo) => {
    if (!e.ctrlKey) return;
    e.preventDefault();
    if (v.noPage) return;
    // 앞 휠의 배율을 아직 그리지 않았으면 그 배율에서 이어 간다
    const p = wheelPending.current;
    const cur = p && e.timeStamp - p.at < WHEEL_IDLE_MS ? p.zoom : v.zoom;
    const next = wheelZoom(cur, e, isPinchWheel(e, ctrlHeld), memo);
    if (next === null) return;
    const r = paperIn(scrollEl.current)?.getBoundingClientRect();
    const anchor = r && r.width > 0 && r.height > 0 ? { x: e.clientX, y: e.clientY, fx: (e.clientX - r.left) / r.width, fy: (e.clientY - r.top) / r.height } : null;
    wheelPending.current = { zoom: next, at: e.timeStamp, anchor };
    onZoomTo(next);
  });
  // 쪽 끝에서 더 굴리면 다음 · 앞 쪽 — 원문 페이지 영역 안의 휠만 본다(옆 버튼 · 도구 줄 위는 스크롤도 되지 않는다)
  const onEdgeWheel = useEffectEvent((e: WheelEvent, memo: PageFlipMemo) => {
    const sc = scrollEl.current;
    if (!sc || !(e.target instanceof Node) || !sc.contains(e.target)) return;
    const flip = wheelPageFlip(
      {
        deltaX: e.deltaX,
        deltaY: e.deltaY,
        deltaMode: e.deltaMode,
        shiftKey: e.shiftKey,
        timeStamp: e.timeStamp,
        top: sc.scrollTop,
        height: sc.scrollHeight,
        client: sc.clientHeight,
        canPrev: !v.noPrev,
        canNext: !v.noNext,
      },
      memo,
    );
    if (!flip) return;
    e.preventDefault();
    if (flip !== 'swallow') onScrollFlip(flip === 'next' ? 1 : -1);
  });
  useEffect(() => {
    const el = rootEl.current;
    if (!el) return;
    const memo = createWheelZoomMemo();
    const flipMemo = createPageFlipMemo();
    // 실제 Ctrl 키가 눌려 있는지 — 키 · 포인터 이벤트의 ctrlKey 로 안다(트랙패드 오므리기 휠은 ctrlKey 지만 실제 키는 떼어져 있다)
    let ctrlHeld = false;
    const track = (e: KeyboardEvent | PointerEvent) => {
      ctrlHeld = e.ctrlKey;
    };
    const release = () => {
      ctrlHeld = false;
    };
    const wheel = (e: WheelEvent) => (e.ctrlKey ? onCtrlWheel(e, ctrlHeld, memo) : onEdgeWheel(e, flipMemo));
    el.addEventListener('wheel', wheel, { passive: false });
    window.addEventListener('keydown', track);
    window.addEventListener('keyup', track);
    window.addEventListener('pointermove', track, { passive: true });
    window.addEventListener('blur', release);
    return () => {
      el.removeEventListener('wheel', wheel);
      window.removeEventListener('keydown', track);
      window.removeEventListener('keyup', track);
      window.removeEventListener('pointermove', track);
      window.removeEventListener('blur', release);
    };
  }, []);
  // 휠로 바꾼 배율을 그렸으면(칠하기 전) 커서 아래에 같은 자리가 오도록 스크롤을 옮긴다
  useLayoutEffect(() => {
    const p = wheelPending.current;
    if (!p) return;
    if (performance.now() - p.at > 1000) {
      wheelPending.current = null;
      return;
    }
    if (Math.abs(p.zoom - v.zoom) > 0.001) return;
    wheelPending.current = null;
    const scroller = scrollEl.current;
    if (!p.anchor || !scroller) return;
    // 동작 줄이기(prefers-reduced-motion)면 globals.css 가 모든 속성에 아주 짧은 전환을 걸어, 새 배율(zoom · 글자 크기 …)이
    // 다음 프레임에야 잡힌다 — 끝내 놓고 잰다(그렇지 않으면 옛 크기로 재고 스크롤 범위도 옛 크기에 묶인다)
    for (const a of scroller.getAnimations({ subtree: true })) if (a instanceof CSSTransition) a.finish();
    const r = paperIn(scroller)?.getBoundingClientRect();
    if (!r) return;
    scroller.scrollBy({ left: r.left + p.anchor.fx * r.width - p.anchor.x, top: r.top + p.anchor.fy * r.height - p.anchor.y, behavior: 'instant' });
  });
  // 세로 스크롤 막대 폭 — 오른쪽 쪽 이동 버튼을 그만큼 안쪽에 둔다(막대가 생기고 없어지면 내용 폭이 바뀌어 다시 잰다)
  const [sbW, setSbW] = useState(0);
  useEffect(() => {
    const el = scrollEl.current;
    if (!el || typeof ResizeObserver === 'undefined') return;
    const ro = new ResizeObserver(() => setSbW(Math.max(0, el.offsetWidth - el.clientWidth)));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  // 옆 버튼으로 끝 쪽에 가면 그 버튼이 사라진다 — 포커스를 원문 페이지 영역으로 옮겨 잃지 않게 한다
  const onSideNav = (dir: 1 | -1) => {
    const edge = dir > 0 ? v.page + 1 >= v.pageCount : v.page - 1 <= 1;
    if (dir > 0) onNext();
    else onPrev();
    if (edge) scrollEl.current?.focus({ preventScroll: true });
  };
  const zoomStyle = { '--paper-zoom': v.zoom, '--viewer-sb': `${sbW}px`, ...barVar } as CSSProperties;
  // 옆 쪽 이동 버튼이 있는가(여러 쪽 서류) — 있으면 스크롤 좌우 여백을 버튼 자리만큼 넓혀 화면 맞춤 종이가 버튼 밑으로 들어가지 않게 한다
  const hasSideNav = !(v.noPrev && v.noNext);
  const wide = !compact;
  const mid = compact && !mobile;
  // 실제 분석 서류 — 원본 파일을 받는 중 · 실패 · 쪽 없음이면 그 화면, 아니면 원본 쪽
  const liveFile = v.live && live ? live.file : null;
  const livePh = v.live && liveFile ? liveFilePlaceholder(liveFile, v.live.filePage) : null;

  return (
    <section ref={rootEl} aria-label="원문 뷰어" className={styles.viewer} style={zoomStyle} {...panel}>
      <div ref={setScrollEl} tabIndex={0} aria-label="원문 페이지 영역" className={cx(styles.scroll, hasSideNav && styles.scrollNav)}>
        <div className={cx(styles.fit, styles.nameLine)}>
          <span className={styles.nameIcon}>
            <Icon name="dg-i-file" size={15} />
          </span>
          <span className={styles.name}>{v.docName}</span>
          {v.hasPage ? <span className={styles.pageNo}>· {v.pageLabel}쪽</span> : null}
        </div>
        {v.notices.length ? (
          <div className={cx(styles.fit, styles.notices)}>
            {v.notices.map((nt) => {
              // 공지 안 버튼(실제 분석만) — 공지 폭이 넓으면 오른쪽, 좁으면(휴대폰 · 좁은 뷰어 · 작은 배율) 글 아래(CSS 컨테이너 쿼리)
              const act = nt.action === 'maskPdf' && live ? live : null;
              return (
                <div key={nt.tone + nt.title} role="note" className={cx(styles.notice, styles[nt.tone], act && styles.withAct)}>
                  <span className={styles.noticeIcon}>
                    <Icon name={nt.icon} size={17} strokeWidth={2.1} />
                  </span>
                  <div>
                    <strong className={styles.noticeTitle}>{nt.title}</strong> <span className={cx(styles.noticeText, nt.pre && styles.noticePre)}>{nt.text}</span>
                  </div>
                  {act ? (
                    <div className={styles.noticeAct}>
                      <NoticeAction live={act} />
                    </div>
                  ) : null}
                </div>
              );
            })}
          </div>
        ) : null}
        {v.live && live ? (
          livePh && v.doc ? (
            <Placeholder ph={livePh} docId={v.doc.id} onRetryDoc={onRetryDoc} onRetryFile={live.onRetryFile} role={livePh.tone === 'err' ? 'alert' : 'status'} />
          ) : liveFile && liveFile.status === 'ready' ? (
            <LivePaper
              live={v.live}
              file={liveFile}
              ariaLabel={v.pageAria}
              zoom={v.zoom}
              paperW={live.paperW}
              pageKey={v.pageKey}
              pageFlip={pageFlip}
              ringFlip={ringFlip}
              tag={v.tag}
              onPickFinding={onPickFinding}
              onRetryFile={live.onRetryFile}
              onPageReady={live.onPageReady}
              mobile={mobile}
            />
          ) : null
        ) : v.hasPage ? (
          <PaperPage blocks={v.blocks} ariaLabel={v.pageAria} scan={v.scan} pageFlip={pageFlip} ringFlip={ringFlip} tag={v.tag} onPickFinding={onPickFinding} />
        ) : null}
        {v.placeholder && v.doc ? <Placeholder ph={v.placeholder} docId={v.doc.id} onRetryDoc={onRetryDoc} /> : null}
      </div>

      {/* 쪽 이동 — 원문 양옆(태블릿 · 데스크톱). 넘길 쪽이 없는 쪽 버튼은 그리지 않는다 */}
      {hasSideNav ? (
        <div className={styles.sideNav}>
          <div className={styles.sideRow}>
            {v.noPrev ? null : <IconButton label="이전 페이지" icon="dg-i-chev-left" size={36} iconSize={20} strokeWidth={2.2} onClick={() => onSideNav(-1)} className={styles.side} />}
            {v.noNext ? null : <IconButton label="다음 페이지" icon="dg-i-chev-right" size={36} iconSize={20} strokeWidth={2.2} onClick={() => onSideNav(1)} className={cx(styles.side, styles.sideNext)} />}
          </div>
        </div>
      ) : null}

      <div className={styles.barWrap}>
        <div ref={barRef} className={styles.bar}>
          <div role="group" aria-label="페이지 이동" className={styles.group}>
            <IconButton label="이전 페이지" icon="dg-i-chev-left" size={34} iconSize={18} strokeWidth={2.2} tooltip="top" disabled={v.noPrev} onClick={onPrev} className={cx(styles.tool, styles.hitPrev, styles.barNav)} />
            <span aria-live="polite" className={styles.label}>
              {v.pageLabel}
            </span>
            <IconButton label="다음 페이지" icon="dg-i-chev-right" size={34} iconSize={18} strokeWidth={2.2} tooltip="top" disabled={v.noNext} onClick={onNext} className={cx(styles.tool, styles.hitNext, styles.barNav)} />
          </div>
          <span aria-hidden="true" className={styles.div} />
          <div role="group" aria-label="확대와 축소" className={styles.group}>
            <IconButton label="축소" icon="dg-i-zoom-out" size={34} iconSize={18} strokeWidth={2} tooltip="top" disabled={v.noOut} onClick={onZoomOut} className={cx(styles.tool, styles.hitZoomOut)} />
            <span className={cx(styles.label, styles.label2)}>{v.zoomLabel}</span>
            <IconButton label="확대" icon="dg-i-zoom-in" size={34} iconSize={18} strokeWidth={2} tooltip="top" disabled={v.noIn} onClick={onZoomIn} className={cx(styles.tool, styles.hitZoomIn)} />
            <Tip label="화면 맞춤" side="top" hidden={wide}>
              <button type="button" aria-pressed={v.isFit} aria-label="화면 맞춤" disabled={v.noPage} onClick={onFit} className={cx(styles.fitBtn, v.isFit && styles.fitOn)}>
                <Icon name="dg-i-fit" size={15} strokeWidth={2.1} />
                {wide ? '화면 맞춤' : null}
              </button>
            </Tip>
          </div>
          <span aria-hidden="true" className={styles.div} />
          <Tip label="화면에서만 가려 보는 미리보기입니다" side="top">
            <button type="button" aria-pressed={v.mask} aria-label="마스킹 미리보기" disabled={v.noMask} onClick={onToggleMask} className={cx(styles.maskBtn, v.mask && styles.maskOn)}>
              {mobile ? <Icon name="dg-i-eye-off" size={17} /> : null}
              <span aria-hidden="true" className={styles.track}>
                <span className={styles.knob} />
              </span>
              {wide ? '마스킹 미리보기' : null}
              {mid ? '마스킹' : null}
            </button>
          </Tip>
        </div>
      </div>
    </section>
  );
}
