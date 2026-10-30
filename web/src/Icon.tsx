// Paths exported from the Brand Kit icon components (24px grid, 1.75 stroke).
const paths: Record<string, string[]> = {
  sun: ['M12 16a4 4 0 1 0 0-8 4 4 0 0 0 0 8Z', 'M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41'],
  panel: ['M5 3H19L21 15H3L5 3Z', 'M4 9H20M9.67 3L9 15M14.33 3L15 15M12 15V20M8 21H16'],
  connector: ['M9 2V7M15 2V7M12 17a6 6 0 0 0 6-6V7H6v4a6 6 0 0 0 6 6Zm0 0v5'],
  hotspot: ['M12 19a7 7 0 1 0 0-14 7 7 0 0 0 0 14Z', 'M12 14.5a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5Z', 'M12 2V5M12 19V22M2 12H5M19 12H22'],
  'sensor-drift': ['M3 18H21', 'M3 18C7 18 9 16.5 12 13C15 9.5 17 7 21 6'],
  decline: ['M22 17L13.5 8.5L8.5 13.5L2 7', 'M16 17H22V11'],
  alert: ['M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20Z', 'M12 8V12M12 16H12.01'],
  check: ['M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20Z', 'M8 12L11 15L16 9'],
  dispatch: ['M14 18V6a2 2 0 0 0-2-2H4a2 2 0 0 0-2 2v11a1 1 0 0 0 1 1h2M15 18H9M19 18h2a1 1 0 0 0 1-1v-3.65a1 1 0 0 0-.22-.62l-3.48-4.35a1 1 0 0 0-.78-.38H14', 'M17 20a2 2 0 1 0 0-4 2 2 0 0 0 0 4Z', 'M7 20a2 2 0 1 0 0-4 2 2 0 0 0 0 4Z'],
  repair: ['M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76Z'],
  report: ['M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6Z', 'M14 2V8H20M8 13H16M8 17H13'],
  upload: ['M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4', 'M7 8L12 3L17 8M12 3V15'],
  download: ['M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4', 'M17 10L12 15L7 10M12 15V3'],
  calendar: ['M19 4H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6a2 2 0 0 0-2-2Z', 'M16 2V6M8 2V6M3 10H21'],
  scope: ['M3 8V5a2 2 0 0 1 2-2h3M16 3h3a2 2 0 0 1 2 2v3M21 16v3a2 2 0 0 1-2 2h-3M8 21H5a2 2 0 0 1-2-2v-3', 'M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z'],
  settings: ['M4 21V14M4 10V3M12 21V12M12 8V3M20 21V16M20 12V3M1 14H7M9 8H15M17 16H23'],
  'arrow-right': ['M5 12H19M13 18L19 12L13 6'],
  close: ['M18 6L6 18M6 6L18 18'],
  cloud: ['M17.5 19H9a7 7 0 1 1 6.71-9h1.79a4.5 4.5 0 1 1 0 9Z'],
  sensor: ['M12 14a2 2 0 1 0 0-4 2 2 0 0 0 0 4Z', 'M8.5 8.5a5 5 0 0 0 0 7M15.5 8.5a5 5 0 0 1 0 7M5.6 5.6a9 9 0 0 0 0 12.8M18.4 5.6a9 9 0 0 1 0 12.8'],
}

export type IconName = keyof typeof paths

export function Icon({ name, size = 20, className }: { name: IconName; size?: number; className?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.75}
      strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden="true">
      {paths[name].map((d, i) => <path key={i} d={d} />)}
    </svg>
  )
}

export function Logo({ size = 32 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 48 48" fill="none" aria-label="SolarScope">
      <path d="M5 15V8a3 3 0 0 1 3-3h7M33 5h7a3 3 0 0 1 3 3v7M43 33v7a3 3 0 0 1-3 3h-7M15 43H8a3 3 0 0 1-3-3v-7" stroke="currentColor" strokeWidth={3.5} strokeLinecap="round" strokeLinejoin="round" />
      <path d="M24 11V15M13.4 15.4L16 18M34.6 15.4L32 18" stroke="var(--accent)" strokeWidth={3} strokeLinecap="round" />
      <path d="M14 28a10 10 0 0 1 20 0H14Z" fill="var(--accent)" />
      <rect x={11} y={31} width={26} height={3.5} rx={1.75} fill="currentColor" />
      <rect x={15} y={37} width={18} height={3.5} rx={1.75} fill="currentColor" />
    </svg>
  )
}
