import styles from './IconSprite.module.css';

/**
 * 아이콘 스프라이트 — Main.dc.html 45–97줄의 `<symbol>` 50개를 그대로 옮겼다(순서·경로 같음).
 * AppShell 이 한 번만 렌더한다. `<Icon name="dg-i-…" />` 이 `<use href="#…">` 로 가져다 쓴다.
 * - 선 아이콘(`dg-i-*`, 24×24)은 쓰는 쪽 svg 의 stroke(currentColor)를 물려받는다.
 * - 위험 막대(`dg-r0~3`, 12×12)와 로고(`dg-logo`, 28×32)는 채움 도형이다.
 *   로고 안쪽 흰 도형은 원본 `fill="#fff"` 를 토큰(--on-solid) 클래스로 바꿨다.
 */
export function IconSprite() {
  return (
    <svg className={styles.sprite} width="0" height="0" aria-hidden="true" focusable="false">
      <defs>
      <symbol id="dg-i-brand" viewBox="0 0 24 24"><path d="M12 3 5 6v5c0 4.4 3 8.3 7 9.5 4-1.2 7-5.1 7-9.5V6z" /><path d="M9 10.5h6M9 14h4" /></symbol>
      <symbol id="dg-i-file" viewBox="0 0 24 24"><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" /><path d="M14 3v5h5M9 13h6M9 17h4" /></symbol>
      <symbol id="dg-i-report" viewBox="0 0 24 24"><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" /><path d="M14 3v5h5M9 17v-3M12 17v-5M15 17v-2" /></symbol>
      <symbol id="dg-i-layers" viewBox="0 0 24 24"><path d="m12 3.5 8.5 4.5-8.5 4.5L3.5 8z" /><path d="m3.5 12.5 8.5 4.5 8.5-4.5" /><path d="m3.5 16.5 8.5 4.5 8.5-4.5" /></symbol>
      <symbol id="dg-i-search" viewBox="0 0 24 24"><circle cx="11" cy="11" r="6.5" /><path d="m20 20-4.2-4.2" /></symbol>
      <symbol id="dg-i-plus" viewBox="0 0 24 24"><path d="M12 5v14M5 12h14" /></symbol>
      <symbol id="dg-i-upload" viewBox="0 0 24 24"><path d="M12 15V4M7.5 8.5 12 4l4.5 4.5" /><path d="M5 14v4a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-4" /></symbol>
      <symbol id="dg-i-download" viewBox="0 0 24 24"><path d="M12 4v11M7.5 10.5 12 15l4.5-4.5" /><path d="M5 19.5h14" /></symbol>
      <symbol id="dg-i-folder" viewBox="0 0 24 24"><path d="M3.5 7a2 2 0 0 1 2-2h4l2 2.5h7a2 2 0 0 1 2 2V17a2 2 0 0 1-2 2h-13a2 2 0 0 1-2-2z" /></symbol>
      <symbol id="dg-i-chev-left" viewBox="0 0 24 24"><path d="m14.5 6-6 6 6 6" /></symbol>
      <symbol id="dg-i-chev-right" viewBox="0 0 24 24"><path d="m9.5 6 6 6-6 6" /></symbol>
      <symbol id="dg-i-chev-down" viewBox="0 0 24 24"><path d="m6 9.5 6 6 6-6" /></symbol>
      <symbol id="dg-i-arrow-left" viewBox="0 0 24 24"><path d="M19 12H5M11 6l-6 6 6 6" /></symbol>
      <symbol id="dg-i-x" viewBox="0 0 24 24"><path d="M6 6l12 12M18 6 6 18" /></symbol>
      <symbol id="dg-i-check" viewBox="0 0 24 24"><path d="m5 12.5 4.5 4.5L19 7.5" /></symbol>
      <symbol id="dg-i-check-circle" viewBox="0 0 24 24"><circle cx="12" cy="12" r="8.5" /><path d="m8.5 12.2 2.4 2.4 4.6-4.8" /></symbol>
      <symbol id="dg-i-alert" viewBox="0 0 24 24"><path d="M10.3 4.3 2.9 17.5a2 2 0 0 0 1.7 3h14.8a2 2 0 0 0 1.7-3L13.7 4.3a2 2 0 0 0-3.4 0z" /><path d="M12 9.5v4.5M12 17.3v.2" /></symbol>
      <symbol id="dg-i-x-circle" viewBox="0 0 24 24"><circle cx="12" cy="12" r="8.5" /><path d="m9.2 9.2 5.6 5.6m0-5.6-5.6 5.6" /></symbol>
      <symbol id="dg-i-clock" viewBox="0 0 24 24"><circle cx="12" cy="12" r="8.5" /><path d="M12 7.5V12l3 2" /></symbol>
      <symbol id="dg-i-flag" viewBox="0 0 24 24"><path d="M5.5 21V4.5" /><path d="M5.5 4.5h11l-2.2 4 2.2 4h-11" /></symbol>
      <symbol id="dg-i-circle" viewBox="0 0 24 24"><circle cx="12" cy="12" r="7.5" /></symbol>
      <symbol id="dg-i-circle-dashed" viewBox="0 0 24 24"><circle cx="12" cy="12" r="7.5" strokeDasharray="2.6 3" /></symbol>
      <symbol id="dg-i-check-badge" viewBox="0 0 24 24"><path d="M12 3 5 6v5c0 4.4 3 8.3 7 9.5 4-1.2 7-5.1 7-9.5V6z" /><path d="m9 12 2.2 2.2L15.5 10" /></symbol>
      <symbol id="dg-i-ban" viewBox="0 0 24 24"><circle cx="12" cy="12" r="8.5" /><path d="m6 6 12 12" /></symbol>
      <symbol id="dg-i-pencil" viewBox="0 0 24 24"><path d="M4.5 19.5h4l10-10-4-4-10 10z" /><path d="m13 7 4 4" /></symbol>
      <symbol id="dg-i-memo" viewBox="0 0 24 24"><path d="M5 5h14v10H10l-5 4z" /><path d="M8.5 9h7M8.5 12h4.5" /></symbol>
      <symbol id="dg-i-eye" viewBox="0 0 24 24"><path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12z" /><circle cx="12" cy="12" r="3" /></symbol>
      <symbol id="dg-i-eye-off" viewBox="0 0 24 24"><path d="M3.5 3.5l17 17" /><path d="M10.6 5.6c.5-.1.9-.1 1.4-.1 6 0 9.5 6.5 9.5 6.5a16.7 16.7 0 0 1-2.9 3.6M6.4 6.9C3.9 8.6 2.5 12 2.5 12S6 18.5 12 18.5c1.5 0 2.9-.4 4.1-1" /><path d="M9.9 9.9a3 3 0 0 0 4.2 4.2" /></symbol>
      <symbol id="dg-i-eye-half" viewBox="0 0 24 24"><path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12z" /><path d="M12 9a3 3 0 0 0 0 6z" fill="currentColor" /><circle cx="12" cy="12" r="3" /></symbol>
      <symbol id="dg-i-zoom-in" viewBox="0 0 24 24"><circle cx="11" cy="11" r="6.5" /><path d="m20 20-4.2-4.2M11 8.5v5M8.5 11h5" /></symbol>
      <symbol id="dg-i-zoom-out" viewBox="0 0 24 24"><circle cx="11" cy="11" r="6.5" /><path d="m20 20-4.2-4.2M8.5 11h5" /></symbol>
      <symbol id="dg-i-fit" viewBox="0 0 24 24"><path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5" /></symbol>
      <symbol id="dg-i-link" viewBox="0 0 24 24"><path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1" /><path d="M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1" /></symbol>
      <symbol id="dg-i-link-off" viewBox="0 0 24 24"><path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1" /><path d="M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1" /><path d="M3.5 3.5l17 17" /></symbol>
      <symbol id="dg-i-help" viewBox="0 0 24 24"><circle cx="12" cy="12" r="8.5" /><path d="M9.7 9.6a2.4 2.4 0 0 1 4.6.9c0 1.6-2.3 2-2.3 3.5M12 17.2v.2" /></symbol>
      <symbol id="dg-i-history" viewBox="0 0 24 24"><path d="M4.5 12a7.5 7.5 0 1 0 2.2-5.3" /><path d="M4.5 4.5v3.5H8" /><path d="M12 8.5V12l2.6 1.7" /></symbol>
      <symbol id="dg-i-refresh" viewBox="0 0 24 24"><path d="M19.5 12a7.5 7.5 0 1 1-2.2-5.3" /><path d="M19.5 4.5V8H16" /></symbol>
      <symbol id="dg-i-trash" viewBox="0 0 24 24"><path d="M5 7h14M10 7V5h4v2M7 7l.9 12.1a1 1 0 0 0 1 .9h6.2a1 1 0 0 0 1-.9L17 7" /></symbol>
      <symbol id="dg-i-info" viewBox="0 0 24 24"><circle cx="12" cy="12" r="8.5" /><path d="M12 11v5M12 7.8v.2" /></symbol>
      <symbol id="dg-i-pin-q" viewBox="0 0 24 24"><path d="M12 21s-6.5-5.6-6.5-11a6.5 6.5 0 0 1 13 0C18.5 15.4 12 21 12 21z" /><path d="M10.3 8.6a1.8 1.8 0 0 1 3.4.8c0 1.2-1.7 1.4-1.7 2.5M12 14.1v.2" /></symbol>
      <symbol id="dg-i-scissors" viewBox="0 0 24 24"><circle cx="6" cy="7" r="2.5" /><circle cx="6" cy="17" r="2.5" /><path d="M8.2 8.3 20 18M8.2 15.7 20 6" /></symbol>
      <symbol id="dg-i-neq" viewBox="0 0 24 24"><path d="M5 9.5h14M5 14.5h14M15.5 5l-7 14" /></symbol>
      <symbol id="dg-i-panel" viewBox="0 0 24 24"><rect x="3.5" y="4.5" width="17" height="15" rx="2" /><path d="M9 4.5v15" /></symbol>
      <symbol id="dg-i-play" viewBox="0 0 24 24"><path d="M8 5.5v13l10.5-6.5z" /></symbol>
      <symbol id="dg-i-copy" viewBox="0 0 24 24"><rect x="8.5" y="8.5" width="11" height="11" rx="2" /><path d="M15.5 8.5V6.5a2 2 0 0 0-2-2h-7a2 2 0 0 0-2 2v7a2 2 0 0 0 2 2h2" /></symbol>
      <symbol id="dg-r3" viewBox="0 0 12 12"><rect x="0.8" y="7" width="2.6" height="4.2" rx="0.6" fill="currentColor" /><rect x="4.7" y="4.2" width="2.6" height="7" rx="0.6" fill="currentColor" /><rect x="8.6" y="1.2" width="2.6" height="10" rx="0.6" fill="currentColor" /></symbol>
      <symbol id="dg-r2" viewBox="0 0 12 12"><rect x="0.8" y="7" width="2.6" height="4.2" rx="0.6" fill="currentColor" /><rect x="4.7" y="4.2" width="2.6" height="7" rx="0.6" fill="currentColor" /><rect x="8.6" y="1.2" width="2.6" height="10" rx="0.6" fill="currentColor" opacity=".25" /></symbol>
      <symbol id="dg-r1" viewBox="0 0 12 12"><rect x="0.8" y="7" width="2.6" height="4.2" rx="0.6" fill="currentColor" /><rect x="4.7" y="4.2" width="2.6" height="7" rx="0.6" fill="currentColor" opacity=".25" /><rect x="8.6" y="1.2" width="2.6" height="10" rx="0.6" fill="currentColor" opacity=".25" /></symbol>
      <symbol id="dg-r0" viewBox="0 0 12 12"><rect x="0.8" y="7" width="2.6" height="4.2" rx="0.6" fill="currentColor" opacity=".3" /><rect x="4.7" y="4.2" width="2.6" height="7" rx="0.6" fill="currentColor" opacity=".3" /><rect x="8.6" y="1.2" width="2.6" height="10" rx="0.6" fill="currentColor" opacity=".3" /></symbol>
      <symbol id="dg-logo" viewBox="0 0 28 32"><path d="M7 2H18L25 9V17C25 23.2 20.6 27.6 14 30C7.4 27.6 3 23.2 3 17V6C3 3.8 4.8 2 7 2Z" fill="currentColor" /><path d="M18 2V6.6C18 7.9 19.1 9 20.4 9H25Z" className={styles.logoInk} fillOpacity=".45" /><rect x="7.5" y="11.6" width="9" height="2.4" rx="1.2" className={styles.logoInk} fillOpacity=".62" /><rect x="7.5" y="15.9" width="13" height="4.2" rx="2.1" className={styles.logoInk} /><rect x="7.5" y="22" width="6" height="2.4" rx="1.2" className={styles.logoInk} fillOpacity=".62" /></symbol>
      </defs>
    </svg>
  );
}
