import type { CSSProperties } from 'react';
import { Icon, VisuallyHidden, cx } from '@/components/ui';
import { FSTATUS, RISK } from '@/display/rules';
import type { ReportView } from './reportModel';
import { ReportSection } from './ReportSection';
import styles from './ReportTables.module.css';

const fgStyle = (fg: string) => ({ '--cell-fg': fg }) as CSSProperties;

/* - 표 머리의 등급·확인 상태 라벨은 그릴 때 ② 표시 규칙(RISK·FSTATUS)에서 읽는다(문구를 여기서 다시 적지 않는다).
   - 표 이름: 화면 낭독기가 표 4개를 구분하도록 화면에 안 보이는 <caption>(공통 VisuallyHidden 숨김 규칙)으로 준다.
     보이는 제목과 같은 글자는 한 곳에 둔다. */
const DOC_TABLE_TITLE = '대상 문서와 문서별 확인 결과';
/** 08 구역의 소제목(ReportHistory h3)이자 수정 표의 이름 */
export const CHANGE_TABLE_TITLE = '최초 AI 결과와 담당자 수정';

/** 03 대상 문서와 문서별 확인 결과 — Main 645–648. 실제 분석에는 '남은 검토사항' 열이 없다(docOpenCol) */
export function ReportDocTable({ v }: { v: ReportView }) {
  return (
    <ReportSection n={v.sections.docs} title={DOC_TABLE_TITLE}>
      <div className={styles.scroll}>
        <table className={cx(styles.table, styles.docTable)}>
          <caption>
            <VisuallyHidden>{DOC_TABLE_TITLE}</VisuallyHidden>
          </caption>
          <thead>
            <tr>
              <th scope="col" className={cx(styles.th, styles.nowrap)}>문서</th>
              <th scope="col" className={cx(styles.th, styles.nowrap)}>형식·페이지</th>
              <th scope="col" className={cx(styles.th, styles.nowrap)}>처리 상태</th>
              <th scope="col" className={cx(styles.th, styles.nowrap, styles.right)}>탐지</th>
              <th scope="col" className={cx(styles.th, styles.nowrap, styles.right)}>{RISK.high.label}</th>
              <th scope="col" className={cx(styles.th, styles.nowrap, styles.right)}>담당자 확인</th>
              {v.docOpenCol ? (
                <th scope="col" className={cx(styles.th, styles.nowrap, styles.right)}>
                  남은 검토사항
                </th>
              ) : null}
            </tr>
          </thead>
          <tbody>
            {v.docs.map((d) => (
              <tr key={d.id}>
                <td className={styles.td}>
                  <div className={styles.docTitle}>{d.title}</div>
                  <div className={styles.docFile}>{d.file}</div>
                </td>
                <td className={cx(styles.td, styles.muted, styles.nowrap)}>{d.meta}</td>
                <td className={cx(styles.td, styles.heavy, styles.nowrap, styles.colored)} style={fgStyle(d.statusFg)}>
                  {d.statusLabel}
                </td>
                <td className={cx(styles.td, styles.right, styles.tab)}>{d.nFind}</td>
                <td className={cx(styles.td, styles.right, styles.tab, styles.heavy, d.highOn ? styles.hi : styles.muted)}>{d.nHigh}</td>
                <td className={cx(styles.td, styles.right, styles.tab)}>{d.reviewed}</td>
                {v.docOpenCol ? (
                  <td className={cx(styles.td, styles.right, styles.tab, styles.heavy, d.open ? styles.warn : styles.muted)}>{d.open}</td>
                ) : null}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </ReportSection>
  );
}

/**
 * 04 탐지 항목 요약 — Main 652–656. 정보 종류별 표 + 전체 탐지 항목(펼치기, 표시값 마스킹).
 * 실제 분석에 미평가 항목이 있으면 정보 종류별 표의 '낮음' 뒤에 '미평가' 열(catUnratedCol).
 */
export function ReportFindings({ v }: { v: ReportView }) {
  return (
    <ReportSection n={v.sections.findings} title="탐지 항목 요약">
      <div className={styles.scroll}>
        <table className={cx(styles.table, styles.catTable)}>
          <caption>
            <VisuallyHidden>정보 종류별 탐지 항목 요약</VisuallyHidden>
          </caption>
          <thead>
            <tr>
              <th scope="col" className={styles.th}>정보 종류</th>
              <th scope="col" className={cx(styles.th, styles.right)}>건수</th>
              <th scope="col" className={cx(styles.th, styles.right)}>{RISK.high.label}</th>
              <th scope="col" className={cx(styles.th, styles.right)}>{RISK.medium.label}</th>
              <th scope="col" className={cx(styles.th, styles.right)}>{RISK.low.label}</th>
              {v.catUnratedCol ? (
                <th scope="col" className={cx(styles.th, styles.right)}>
                  {RISK.unrated.label}
                </th>
              ) : null}
              <th scope="col" className={cx(styles.th, styles.right)}>확인</th>
              <th scope="col" className={cx(styles.th, styles.right)}>{FSTATUS.false_positive.label}</th>
            </tr>
          </thead>
          <tbody>
            {v.cats.map((c) => (
              <tr key={c.cat}>
                <td className={cx(styles.td, styles.tdCat, styles.bold)}>{c.cat}</td>
                <td className={cx(styles.td, styles.tdCat, styles.right, styles.tab, styles.heavy)}>{c.n}</td>
                <td className={cx(styles.td, styles.tdCat, styles.right, styles.tab, c.high ? styles.hi : styles.faint)}>{c.high}</td>
                <td className={cx(styles.td, styles.tdCat, styles.right, styles.tab, c.medium ? styles.md : styles.faint)}>{c.medium}</td>
                <td className={cx(styles.td, styles.tdCat, styles.right, styles.tab, c.low ? styles.lo : styles.faint)}>{c.low}</td>
                {v.catUnratedCol ? (
                  <td className={cx(styles.td, styles.tdCat, styles.right, styles.tab, c.unrated ? styles.na : styles.faint)}>{c.unrated}</td>
                ) : null}
                <td className={cx(styles.td, styles.tdCat, styles.right, styles.tab)}>{c.reviewed}</td>
                <td className={cx(styles.td, styles.tdCat, styles.right, styles.tab)}>{c.fp}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <details className={styles.details}>
        <summary className={styles.summary}>
          <Icon name="dg-i-chev-down" size={16} strokeWidth={2.2} />
          전체 탐지 항목 {v.nFind}건 (표시값 마스킹)
        </summary>
        <div className={cx(styles.scroll, styles.detailsBody)}>
          <table className={cx(styles.table, styles.small)}>
            <caption>
              <VisuallyHidden>전체 탐지 항목 {v.nFind}건 (표시값 마스킹)</VisuallyHidden>
            </caption>
            <thead>
              <tr>
                <th scope="col" className={cx(styles.th, styles.thSm)}>ID</th>
                <th scope="col" className={cx(styles.th, styles.thSm)}>정보 종류</th>
                <th scope="col" className={cx(styles.th, styles.thSm)}>표시값</th>
                <th scope="col" className={cx(styles.th, styles.thSm)}>정보주체</th>
                <th scope="col" className={cx(styles.th, styles.thSm)}>문서·쪽</th>
                <th scope="col" className={cx(styles.th, styles.thSm)}>위험</th>
                <th scope="col" className={cx(styles.th, styles.thSm)}>확인 상태</th>
              </tr>
            </thead>
            <tbody>
              {v.findings.map((f) => (
                <tr key={f.id}>
                  <td className={cx(styles.td, styles.tdSm, styles.mono)}>{f.id}</td>
                  <td className={cx(styles.td, styles.tdSm)}>{f.cat}</td>
                  <td className={cx(styles.td, styles.tdSm, styles.mono, f.falsePositive && styles.struck)}>{f.masked}</td>
                  <td className={cx(styles.td, styles.tdSm)}>{f.subject}</td>
                  <td className={cx(styles.td, styles.tdSm, styles.muted)}>{f.where}</td>
                  <td className={cx(styles.td, styles.tdSm, styles.heavy, styles.colored)} style={fgStyle(f.risk.fg)}>
                    {f.risk.label}
                  </td>
                  <td className={cx(styles.td, styles.tdSm, styles.bold, styles.colored)} style={fgStyle(f.status.fg)}>
                    {f.status.label}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </ReportSection>
  );
}

/** 08(실제 분석은 07) 안의 '최초 AI 결과와 담당자 수정' 표 — Main 679 */
export function ReportChangeTable({ v }: { v: ReportView }) {
  return (
    <div className={styles.scroll}>
      <table className={cx(styles.table, styles.changeTable)}>
        <caption>
          <VisuallyHidden>{CHANGE_TABLE_TITLE}</VisuallyHidden>
        </caption>
        <thead>
          <tr>
            <th scope="col" className={styles.th}>항목</th>
            <th scope="col" className={styles.th}>최초 AI 결과</th>
            <th scope="col" className={styles.th}>담당자 수정</th>
            <th scope="col" className={styles.th}>수정 사유</th>
            <th scope="col" className={cx(styles.th, styles.nowrap)}>수정 시각</th>
          </tr>
        </thead>
        <tbody>
          {v.changes.map((c) => (
            <tr key={c.id}>
              <td className={cx(styles.td, styles.tdCat, styles.top)}>
                <span className={styles.changeId}>{c.id}</span> <span className={styles.bold}>{c.item}</span>
              </td>
              <td className={cx(styles.td, styles.tdCat, styles.top, styles.aiWas)}>{c.ai}</td>
              <td className={cx(styles.td, styles.tdCat, styles.top, styles.bold)}>{c.now}</td>
              <td className={cx(styles.td, styles.tdCat, styles.top, styles.muted)}>{c.reason}</td>
              <td className={cx(styles.td, styles.tdCat, styles.top, styles.changeAt)}>{c.at}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
