// Demo data for the front-end-only build.
// Real figures come from the MVP 1 test data (data_profile.md, service_log.csv and the
// real data-quality run). Fault and loss figures are placeholders until those stages exist.

export const site = {
  city: 'Buffalo, NY',
  id: 'SS-TEST-001',
  name: 'Buffalo rooftop',
  period: 'Last 6 months · Mar 5 – Aug 31',
  made: '48,212 kWh made',
}

export const pid = (n: number) => 'P' + String(n).padStart(2, '0')
export const hubOf = (n: number) => Math.ceil(n / 3)

export type FaultId = 'P22' | 'P08' | 'P33'

export interface Fault {
  id: FaultId
  n: number
  kind: string
  icon: 'connector' | 'hotspot'
  hub: string
  row: number
  urgent: boolean
  kwhDay: string
  since: string
  order: string
  why: string
  todo: string[]
  plan: string
  history?: { date: string; ticket: string; note: string }[]
}

export const faults: Fault[] = [
  {
    id: 'P22', n: 22, kind: 'wiring problem', icon: 'connector', hub: 'H08', row: 2, urgent: true,
    kwhDay: '4.4', since: 'Aug 2', order: 'D001',
    why: 'Power drops to zero about once a day, 41 times in 30 days. It was fixed 3 times, but only one side of the connector was replaced.',
    todo: ['Replace both connector halves with a matched pair', 'Check the panel output the day after'],
    plan: 'Replace both connector halves with a matched pair from one maker.',
    history: [
      { date: 'Dec 18', ticket: 'SR-1006', note: 'Loose connector reseated' },
      { date: 'Feb 24', ticket: 'SR-1009', note: 'Loose again. Halves from two makers' },
      { date: 'May 1', ticket: 'SR-1013', note: 'Panel side replaced only' },
    ],
  },
  {
    id: 'P08', n: 8, kind: 'hot spot', icon: 'hotspot', hub: 'H03', row: 1, urgent: true,
    kwhDay: '3.5', since: 'Jun 30', order: 'D002',
    why: 'One spot on this panel runs hotter than the rest, so the panel makes less power. It has lost about 3.5 kWh a day since Jun 30.',
    todo: ['Look for the hot spot with a thermal camera.', 'Replace the panel if it is confirmed.'],
    plan: 'Look for the hot spot with a thermal camera. Replace the panel if it is confirmed.',
  },
  {
    id: 'P33', n: 33, kind: 'hot spot', icon: 'hotspot', hub: 'H11', row: 3, urgent: false,
    kwhDay: '1.3', since: 'Jul 10', order: 'D003',
    why: 'A smaller hot spot than P08. It has lost about 1.3 kWh a day since Jul 10, so it can wait for the same trip.',
    todo: ['Same check as P08 while you are on site.'],
    plan: 'Same check as P08 while you are on site.',
  },
]

export const weakening = [14, 29]

export const energy = {
  total: '1,286',
  weather: { kwh: 874, parts: [['Dirt', 402], ['Clouds', 256], ['Heat', 216]] as [string, number][] },
  panels: { kwh: 412, parts: [['Hot spots · P08, P33', 284], ['Wiring · P22', 128]] as [string, number][] },
}

export const quality = {
  usable: '99%',
  readings: '420,904',
  repeats: '1,424',
  hubs: [
    {
      hub: 'H09', panels: 'P25–P27', tone: 'sensor',
      happened: 'its light sensor reads too high since Jan 19.',
      did: 'left that sensor out, so it does not skew your results.',
      strip: ['H09 sensor left out', 'Reads too high since Jan 19'],
    },
    {
      hub: 'H02', panels: 'P04–P06', tone: 'ok',
      happened: 'its clock ran 4 hours early, Apr 1 – 15.',
      did: 'moved 1,351 readings back to the right time.',
      strip: ['H02 clock fixed', '4 h early, 1,351 readings moved back'],
    },
    {
      hub: 'H11', panels: 'P31–P33', tone: 'offline',
      happened: 'it was offline for 44.5 hours, May 3 – 5, during a phone network outage.',
      did: 'marked those hours as missing data, so no panel is blamed for them.',
      strip: ['H11 offline 44.5 h', 'May 3 – May 5'],
    },
  ],
}

export const files = [
  { name: 'readings.csv', meta: '33 MB · 420,904 readings from 12 hubs' },
  { name: 'weather.csv', meta: '34 KB · 365 days' },
  { name: 'service_log.csv', meta: '4 KB · 18 past visits' },
  { name: 'site.json', meta: '13 KB · 12 hubs, 36 panels' },
]

export const steps = [
  { title: 'Read the files', detail: '420,904 readings from 12 hubs' },
  { title: 'Clean up', detail: 'Counted 1,424 repeat readings once, fixed hub H02’s clock' },
  { title: 'Check data quality', detail: '99% usable · one sensor left out' },
  { title: 'Work out what each panel should make', detail: 'Using sunlight and weather for every hour' },
  { title: 'Find panels getting weaker', detail: 'P14 and P29 make a little less each month' },
  { title: 'Explain the losses and plan visits', detail: '1,286 kWh lost, one visit for 3 panels' },
  { title: 'Write the reports', detail: '2 PDF reports and 5 result files' },
]

export const pastVisits = [
  'In the last 6 months, 8 truck rolls cost $2,800. Three of them ($1,050) found nothing wrong. The drops were weather: overcast on Jun 16, heat on Jul 17, dust on Aug 12. No truck was needed.',
  'Over 12 months P22 was visited 3 times (Dec 18, Feb 24, May 1), $1,050 in all. Each time only one side of the connector was replaced, and the two halves come from different makers. A matched pair should stop the repeats.',
]

export const bring = [
  'Matched connector pair, both halves from one maker',
  'Thermal camera',
  'Spare panel, in case P08 needs replacing',
]
