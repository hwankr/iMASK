'use client';

/* ==========================================================================
   보고서 화면 — /analyses/[id]/report (Main.dc.html 603–702)
   - 데이터는 useAnalysis(id) 로만 받는다. 불러오는 중에는 뼈대, 없는 ID 면 목록(/ — `/demo` 아래면 /demo)으로 돌려보낸다(replace).
   - 이동 주소(목록 · '상세 검토로 돌아가기')는 지금 기준 경로(useRouteBase)로 만든다(src/lib/routes.ts).
   - 위험등급·근거는 서비스 값 그대로, 민감한 값은 마스킹된 표시값만 보여 준다(reportModel).
   - 결과 내보내기: service.buildExport → 브라우저 다운로드(lib/download) → 'handed' → service.logExport
     (검토 이력에 '결과 내보내기' 기록 — 변경 알림으로 보고서의 검토 기록 구역이 다시 그려진다). 기록 실패는 삼키고 결과 표시는 그대로.
   - 실제 분석(Analysis.raw 있음)은 그리기 전에 reportGate 로 가른다: 대기 · 분석 중 · 실패 · 일부 실패 · 옛 형식은 짧은 안내
     (LiveReportNotice — 제목 + 상세로 가기), 검토 기록을 읽지 못한 분석은 불러오기 실패 블록(다시 불러오기), 보고서 대상만 본문.
     본문은 원문 값을 지운 안전한 사본(reportSafeAnalysis)으로만 그린다. 생성 시각은 서울 시각(데모는 브라우저 시각 그대로).
   ========================================================================== */

import { useRouter } from 'next/navigation';
import { useEffect, useMemo, useRef, useState } from 'react';
import { LiveReportNotice } from '@/components/live/LiveReportNotice';
import { Button, Icon, Skeleton, VisuallyHidden } from '@/components/ui';
import type { ExportFormat } from '@/display/rules';
import { downloadFile } from '@/lib/download';
import { fmtDT, nowStr } from '@/lib/format';
import { detailHref, listHref } from '@/lib/routes';
import { useAnalysis, useRouteBase, useService } from '@/services/react';
import { reportClock, reportSafeAnalysis } from '@/services/report-safe';
import type { Analysis, ExportFile } from '@/services/types';
import { ExportModal } from './ExportModal';
import { BUILD_FAILED_MESSAGE, freshExport, type ExportUiState } from './exportModel';
import { reportGate } from './reportGate';
import { ReportHead } from './ReportHead';
import { ReportHistory } from './ReportHistory';
import { ReportMemo, ReportReasons, ReportRecs, ReportRemaining } from './ReportLists';
import { reportView } from './reportModel';
import { ReportSummary } from './ReportSummary';
import { ReportDocTable, ReportFindings } from './ReportTables';
import styles from './ReportScreen.module.css';

/** /dev/states 용 처음 상태 — 내보내기 모달을 이 상태로 열어 둔다(report-saved · report-failed) */
export interface ReportInitial {
  exportModal?: ExportUiState;
}

export interface ReportScreenProps {
  id: string;
  initial?: ReportInitial;
}

/** 보고서 화면 — 데이터를 불러와 보고서를 그린다 */
export function ReportScreen({ id, initial }: ReportScreenProps) {
  const router = useRouter();
  const base = useRouteBase();
  const { data, error, refresh } = useAnalysis(id);

  /* 없는 ID — 프로토타입처럼 그 기준의 목록으로(기록을 남기지 않음) */
  useEffect(() => {
    if (data === null) router.replace(listHref(base));
  }, [data, router, base]);

  if (data === undefined) {
    if (error) return <ReportLoadFailed onRetry={() => void refresh()} />;
    return <ReportSkeleton />;
  }
  if (data === null) return <ReportSkeleton label="분석 건을 찾을 수 없어 목록으로 돌아갑니다." />;
  /* 실제 분석 — 보고서 대상만 본문(데모 분석은 늘 'report') */
  const gate = reportGate(data);
  if (gate === 'waiting' || gate === 'unavailable') return <LiveReportNotice id={id} kind={gate} />;
  if (gate === 'loadFailed') return <ReportLoadFailed onRetry={() => void refresh()} />;
  return <ReportBody analysis={data} initial={initial} />;
}

/** 불러오기 실패 — 조회 오류, 또는 검토 기록을 읽지 못한 실제 분석 */
function ReportLoadFailed({ onRetry }: { onRetry: () => void }) {
  return (
    <div className={styles.screen}>
      <p role="alert" className={styles.error}>
        보고서를 불러오지 못했습니다.
        <Button size="sm" variant="secondary" onClick={onRetry}>
          다시 불러오기
        </Button>
      </p>
    </div>
  );
}

function ReportBody({ analysis: a, initial }: { analysis: Analysis; initial?: ReportInitial }) {
  const service = useService();
  const base = useRouteBase();
  /* 실제 분석은 원문 값을 지운 안전한 사본으로만 그린다(데모는 같은 객체) — 분석이 바뀔 때만 다시 만든다(모달 상태로 다시 그려도 그대로) */
  const v = useMemo(() => reportView(reportSafeAnalysis(a)), [a]);
  /* 보고서를 연 시각(원본 generatedAt: fmtDT(nowStr()) — 실제 분석은 서울 시각) — 다시 그려도 바뀌지 않게 처음 값을 둔다 */
  const [generatedAt] = useState(() => fmtDT(reportClock(a)));

  const [exportOpen, setExportOpen] = useState(() => !!initial?.exportModal);
  const [exp, setExp] = useState<ExportUiState>(() => initial?.exportModal ?? freshExport());
  /* 모달을 열고 닫을 때마다 바뀐다 — 닫은 뒤 늦게 끝난 내보내기는 다시 연 모달의 상태를 덮지 않는다 */
  const session = useRef(0);
  const busy = useRef(false);
  const alive = useRef(true);
  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);

  /* 원본 openExport — 고른 형식은 남기고 나머지는 새로 */
  const openExport = () => {
    session.current += 1;
    setExp((e) => freshExport(e.format));
    setExportOpen(true);
  };
  const closeExport = () => {
    session.current += 1;
    setExportOpen(false);
  };
  /* 만드는 중에는 형식을 바꾸지 않는다 */
  const pickFormat = (format: ExportFormat) => {
    if (busy.current) return;
    setExp(freshExport(format));
  };

  /* 원본 doExport */
  const runExport = async () => {
    if (!service || busy.current) return;
    busy.current = true;
    const mine = session.current;
    const format = exp.format;
    const current = () => alive.current && mine === session.current;
    setExp((e) => ({ ...e, state: 'working', msg: '' }));
    let file: ExportFile | null = null;
    try {
      file = await service.buildExport(a.id, format);
    } catch {
      file = null;
    }
    if (!file) {
      busy.current = false;
      if (current()) setExp((e) => ({ ...e, state: 'failed', file: null, msg: BUILD_FAILED_MESSAGE }));
      return;
    }
    const res = downloadFile(file);
    if (res.state === 'handed') {
      try {
        await service.logExport(a.id, file, 'handed');
      } catch {
        /* 기록을 남기지 못해도 파일은 이미 넘겼다 — 결과 표시는 그대로 */
      }
    }
    busy.current = false;
    if (!current()) return;
    const made = file;
    setExp((e) => ({ ...e, state: res.state, file: made, msg: res.state === 'failed' ? res.message : '', at: nowStr() }));
  };

  return (
    <div className={styles.screen}>
      <div className={styles.bar}>
        <div className={styles.barInner}>
          <Button href={detailHref(base, a.id)} variant="ghost" icon="dg-i-arrow-left" className={styles.back}>
            상세 검토로 돌아가기
          </Button>
          <div className={styles.barRight}>
            <span className={styles.maskNote}>
              <Icon name="dg-i-eye-off" size={15} />
              민감한 값은 마스킹된 형태로 내보냅니다
            </span>
            <Button
              variant="primary"
              size="lg"
              icon="dg-i-download"
              iconStrokeWidth={2.2}
              raised
              className={styles.exportBtn}
              onClick={openExport}
              aria-haspopup="dialog"
            >
              결과 내보내기
            </Button>
          </div>
        </div>
      </div>

      <article aria-labelledby="rp-title" className={styles.article}>
        <ReportHead v={v} generatedAt={generatedAt} />
        <ReportSummary v={v} />
        <ReportReasons v={v} />
        <ReportDocTable v={v} />
        <ReportFindings v={v} />
        <ReportRemaining v={v} />
        <ReportRecs v={v} />
        <ReportMemo v={v} />
        <ReportHistory v={v} />
        <footer className={styles.footer}>
          {v.footer.map((line) => (
            <span key={line}>{line}</span>
          ))}
        </footer>
      </article>

      <ExportModal
        open={exportOpen}
        onClose={closeExport}
        analysisName={a.name}
        code={a.code}
        live={v.liveJsonDesc}
        state={exp}
        onPickFormat={pickFormat}
        onExport={() => void runExport()}
      />
    </div>
  );
}

/** 불러오는 중 뼈대 — 위쪽 막대 자리 · 제목 · 요약 줄 */
function ReportSkeleton({ label = '보고서를 불러오는 중입니다.' }: { label?: string }) {
  return (
    <div className={styles.screen} aria-busy="true">
      <VisuallyHidden>
        <span role="status">{label}</span>
      </VisuallyHidden>
      <div className={styles.bar} aria-hidden="true">
        <div className={styles.barInner}>
          <Skeleton width={18} />
        </div>
      </div>
      <div className={styles.article} aria-hidden="true">
        <div className={styles.skHead}>
          <Skeleton width={30} />
          <Skeleton size="title" width={46} />
        </div>
        <div className={styles.skHead}>
          <Skeleton width={92} />
          <Skeleton width={84} />
          <Skeleton width={66} />
        </div>
      </div>
    </div>
  );
}
