'use client';

/* ==========================================================================
   실제 분석 원문 한 쪽 — 원본 파일(PDF 는 pdf.js 캔버스, PNG · JPEG 는 이미지) 위에 탐지 위치 상자를 겹쳐 그린다.
   - 종이 폭은 데모 종이와 같은 --paper-w, 배율은 --paper-zoom(CSS zoom). 쪽 비율은 실제 쪽 크기(PDF 쪽 · 이미지 원래 크기).
     쪽 크기를 알기 전에는 앞 쪽(없으면 A4) 비율로 자리를 잡아 두어 위치 상자가 먼저 생긴다(스크롤 대상).
   - PDF 캔버스는 화면 폭 × 배율 × 기기 픽셀 배율로 선명하게 그리되 캔버스 크기에 상한을 둔다(src/lib/pageBox.ts).
     쪽 · 배율이 바뀌면 그리던 것을 취소하고 새 캔버스에 그린 뒤 바꿔 끼운다(배율만 바뀌면 그동안 앞 캔버스를 늘여 보인다).
   - 위치 상자: 0~1 비율 꼭짓점 → 쪽 위 사각형(px, boxRect). 진짜 버튼이고, 누르면 그 탐지 항목을 고른다.
     고른 항목의 상자는 테두리 · 신호(dg-ring-a/b) · 첫 상자 위 이름표, 마스킹 미리보기면 검은 상자로 가린다(글자 없음).
   - 캔버스만 그린다(주석 · 텍스트 레이어 없음). 쪽 크기를 알게 되면 onPageReady 로 알려 고른 위치로 다시 스크롤하게 한다.
   - 휴대폰에서만 누름 영역을 넓힌다(hitAreas — 화면 44px · 배율 보정, 서로 다른 항목끼리는 가운데에서 나눠 겹치지 않음).
     보이는 상자 · 마스킹 크기는 그대로이고, 넓힌 영역은 투명 ::after(--hit-* 변수)라 데스크톱 · 태블릿은 전과 같다.
   ========================================================================== */

import { useEffect, useEffectEvent, useRef, useState, type CSSProperties } from 'react';
import { Button, Spinner, VisuallyHidden, cx } from '@/components/ui';
import { boxRect, canvasScale, hitAreas, type PxRect } from '@/lib/pageBox';
import type { HighlightVars, LiveViewerModel } from './detailModel';
import type { LiveFileState } from './liveFile';
import { PDF_RENDER_FAILED } from './liveViewerModel';
import type { OpenedPdf } from './pdfRuntime';
import paperStyles from './Paper.module.css';
import styles from './LivePaper.module.css';

/** 쪽 크기를 알기 전의 비율(세로 ÷ 가로) — A4 */
const DEFAULT_ASPECT = Math.SQRT2;

type ReadyFile = Extract<LiveFileState, { status: 'ready' }>;

export interface LivePaperProps {
  live: LiveViewerModel;
  file: ReadyFile;
  /** 종이 이름(문서 이름 + 쪽) */
  ariaLabel: string;
  /** 실제 배율 */
  zoom: number;
  /** 종이 폭(px) — --paper-w 를 잰 값. 0 이면 아직 모름(상자 · 캔버스를 그리지 않는다) */
  paperW: number;
  /** 쪽이 바뀌었는지 알아보는 서명 */
  pageKey: string;
  pageFlip: boolean;
  ringFlip: boolean;
  tag: { text: string; bg: string };
  onPickFinding: (findingId: string) => void;
  onRetryFile: () => void;
  /** 이 쪽의 크기를 알게 됐다(위치 상자가 제자리에 있다) */
  onPageReady: () => void;
  /** 휴대폰 배치 — 누름 영역을 넓힌다 */
  mobile?: boolean;
}

/** 위치 상자 색 · 선택 변수 — 데모 하이라이트와 같은 이름(--hl-*, --pc, --ph) */
function boxVars(v: HighlightVars, on: boolean): Record<string, string> {
  return { '--hl-soft': v.soft, '--hl-solid': v.solid, '--hl-on': v.onBg, '--pc': on ? v.pc : 'transparent', '--ph': on ? v.ph : 'transparent' };
}

/** 넓힌 누름 영역 → ::after 위치 변수(보이는 사각형 기준, 쪽 px — 종이의 CSS zoom 이 함께 곱한다) */
function hitVars(r: PxRect, e: PxRect | undefined): Record<string, string> {
  if (!e) return {};
  return {
    '--hit-t': `${e.y - r.y}px`,
    '--hit-l': `${e.x - r.x}px`,
    '--hit-r': `${r.x + r.w - (e.x + e.w)}px`,
    '--hit-b': `${r.y + r.h - (e.y + e.h)}px`,
  };
}

export function LivePaper({ live, file, ariaLabel, zoom, paperW, pageKey, pageFlip, ringFlip, tag, onPickFinding, onRetryFile, onPageReady, mobile = false }: LivePaperProps) {
  const pageNo = live.filePage;
  const pdf: OpenedPdf | null = file.kind === 'pdf' ? file.pdf : null;

  /** PDF 쪽 크기(PDF 단위) — 어느 문서 · 쪽의 값인지 함께 둔다(바뀐 쪽에는 앞 값을 쓰지 않음) */
  const [pdfSize, setPdfSize] = useState<{ pdf: OpenedPdf; page: number; w: number; h: number } | null>(null);
  /** 캔버스 자리에 지금 그려 둔 쪽 */
  const [drawn, setDrawn] = useState<{ pdf: OpenedPdf; page: number } | null>(null);
  /** 그리지 못한 쪽 */
  const [failed, setFailed] = useState<{ pdf: OpenedPdf; page: number } | null>(null);
  const hostRef = useRef<HTMLDivElement>(null);

  const known =
    file.kind === 'image' ? { w: file.width, h: file.height } : pdfSize && pdfSize.pdf === pdf && pdfSize.page === pageNo ? { w: pdfSize.w, h: pdfSize.h } : null;
  const kw = known ? known.w : 0;
  const kh = known ? known.h : 0;
  // 쪽 크기를 알기 전에는 앞 쪽 비율(같은 파일), 그것도 없으면 A4
  const aspect = known ? kh / kw : pdfSize && pdfSize.pdf === pdf ? pdfSize.h / pdfSize.w : DEFAULT_ASPECT;
  const isDrawn = file.kind === 'image' || (!!drawn && drawn.pdf === pdf && drawn.page === pageNo);
  const isFailed = !!failed && failed.pdf === pdf && failed.page === pageNo;

  /* PDF 쪽 크기 */
  useEffect(() => {
    if (!pdf) return;
    let alive = true;
    pdf.pageSize(pageNo).then(
      (s) => {
        if (alive) setPdfSize({ pdf, page: pageNo, w: s.width, h: s.height });
      },
      () => {
        if (alive) setFailed({ pdf, page: pageNo });
      },
    );
    return () => {
      alive = false;
    };
  }, [pdf, pageNo]);

  /* PDF 쪽 그리기 — 쪽 · 배율 · 폭이 바뀌면 앞 그리기를 취소한다 */
  useEffect(() => {
    const host = hostRef.current;
    if (!pdf || !host || !kw || !kh || !paperW) return;
    const dpr = typeof window !== 'undefined' && window.devicePixelRatio > 0 ? window.devicePixelRatio : 1;
    const scale = canvasScale(kw, kh, (paperW / kw) * zoom * dpr);
    const job = pdf.render(pageNo, scale);
    let alive = true;
    job.promise.then(
      (canvas) => {
        if (!alive || !canvas) return;
        canvas.className = styles.canvas;
        canvas.setAttribute('aria-hidden', 'true');
        host.replaceChildren(canvas);
        setDrawn({ pdf, page: pageNo });
      },
      () => {
        if (alive) setFailed({ pdf, page: pageNo });
      },
    );
    return () => {
      alive = false;
      job.cancel();
    };
  }, [pdf, pageNo, kw, kh, paperW, zoom]);

  /* 쪽 크기를 알게 되면(쪽마다 한 번) 알린다 */
  const readyKey = known ? `${pageKey}|${kw}x${kh}` : '';
  const notifyReady = useEffectEvent(() => onPageReady());
  useEffect(() => {
    if (readyKey) notifyReady();
  }, [readyKey]);

  const size = { width: paperW, height: paperW * aspect };
  const ring = ringFlip ? paperStyles.ringA : paperStyles.ringB;
  // 그릴 수 있는 상자(쪽 px) — 휴대폰이면 누름 영역도
  const drawable =
    paperW > 0
      ? live.boxes.flatMap((b) => {
          const r = boxRect(b.points, size);
          return r ? [{ b, r }] : [];
        })
      : [];
  const hits =
    mobile && drawable.length ? hitAreas(drawable.map(({ b, r }) => ({ key: b.anchor, group: b.findingId, rect: r })), { zoom, page: size }) : null;
  const pageStyle = { '--page-aspect': aspect } as CSSProperties;

  return (
    <article aria-label={ariaLabel} className={cx(styles.page, pageFlip ? styles.pageA : styles.pageB)} style={pageStyle} data-file-page={pageNo}>
      {file.kind === 'image' ? (
        // eslint-disable-next-line @next/next/no-img-element -- 브라우저 메모리의 object URL(원본 파일)이라 next/image 를 쓰지 않는다
        <img src={file.url} alt="" aria-hidden="true" draggable={false} className={styles.image} />
      ) : (
        <div ref={hostRef} className={cx(styles.host, !isDrawn && styles.stale)} />
      )}

      {drawable.map(({ b, r }) => {
        const style = { left: r.x, top: r.y, width: r.w, height: r.h, ...boxVars(b.vars, b.on), ...hitVars(r, hits?.get(b.anchor)) } as CSSProperties;
        return (
          <button
            key={b.anchor}
            type="button"
            data-anchor={b.anchor}
            data-selected={b.on ? 'true' : undefined}
            data-masked={b.masked ? 'true' : undefined}
            aria-label={b.aria}
            className={cx(styles.box, b.on && styles.on, b.on && ring, b.masked && styles.masked)}
            style={style}
            onClick={() => onPickFinding(b.findingId)}
          >
            {b.tag ? (
              <span aria-hidden="true" className={paperStyles.tag} style={{ '--tag-bg': tag.bg } as CSSProperties}>
                {tag.text}
              </span>
            ) : null}
          </button>
        );
      })}

      {!isDrawn && !isFailed ? (
        <span role="status" className={styles.drawing}>
          <Spinner size={22} />
          <VisuallyHidden>쪽을 그리는 중입니다.</VisuallyHidden>
        </span>
      ) : null}
      {isFailed ? (
        <div role="alert" className={styles.error}>
          <span>{PDF_RENDER_FAILED}</span>
          <Button size="sm" variant="secondary" icon="dg-i-refresh" onClick={onRetryFile}>
            다시 시도
          </Button>
        </div>
      ) : null}
    </article>
  );
}
