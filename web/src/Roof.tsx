import { useId } from 'react'
import { pid, weakening } from './data'

/*
 * The roof is drawn in the same 1440 × 960 coordinate space as the Figma frames
 * (scale 1, origin top-left), using the isometric projection from the build spec:
 * 50 px per unit, panels 1 × 1.6 tilted 30°, hubs of 3, rows 4 units apart.
 */
const S = 50
const OX = 453.4
const OY = 492.9
const ZF = 0.25
const ZB = 1.05
const DY = 1.386
const RS = 4

type Pt = [number, number]
const P = (x: number, y: number, z = 0): Pt => [OX + (x * 0.8 + y * 0.5) * S, OY + (x * -0.36 + y * 0.42) * S - z * S]
const add = (a: Pt, b: Pt): Pt => [a[0] + b[0], a[1] + b[1]]
const lerp = (a: Pt, b: Pt, t: number): Pt => [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t]
const poly = (pts: Pt[]) => 'M' + pts.map(p => p[0].toFixed(1) + ' ' + p[1].toFixed(1)).join('L') + 'Z'
const seg = (a: Pt, b: Pt) => `M${a[0].toFixed(1)} ${a[1].toFixed(1)}L${b[0].toFixed(1)} ${b[1].toFixed(1)}`

function panel(n: number) {
  const row = Math.ceil(n / 12) - 1
  const i = (n - 1) % 12
  const x0 = Math.floor(i / 3) * 3.5 + (i % 3) * 1.05
  const y0 = row * RS
  const b0 = P(x0, y0, ZB), b1 = P(x0 + 1, y0, ZB)
  const f1 = P(x0 + 1, y0 + DY, ZF), f0 = P(x0, y0 + DY, ZF)
  const quad: Pt[] = [b0, b1, f1, f0]
  const cells: string[] = []
  for (let k = 1; k < 4; k++) cells.push(seg(lerp(b0, b1, k / 4), lerp(f0, f1, k / 4)))
  for (let k = 1; k < 6; k++) cells.push(seg(lerp(b0, f0, k / 6), lerp(b1, f1, k / 6)))
  const centre = lerp(lerp(b0, f1, 0.5), lerp(b1, f0, 0.5), 0.5)
  const origin: Pt = [b0[0], b1[1]] // top-left of the quad's bounding box, as in Figma
  return { row, x0, y0, quad, cells: cells.join(''), centre, origin }
}

const PANELS = Array.from({ length: 36 }, (_, i) => i + 1)
const geo = PANELS.map(panel)
const G = (n: number) => geo[n - 1]

// Sun from the south: hub shadows fall north, behind the racks.
function hubShadow(h: number) {
  const a = G(h * 3 - 2).origin, c = G(h * 3).origin
  return poly([add(a, [27.6, 88.8]), add(c, [67.6, 70.8]), add(c, [4.5, 17.8]), add(a, [-35.5, 35.8])])
}

function racks(h: number) {
  const { x0, y0 } = G(h * 3 - 2)
  const x1 = x0 + 3.1
  const legs: string[] = []
  for (const x of [x0 + 0.1, x1 - 0.1]) {
    legs.push(seg(P(x, y0 + 0.1), P(x, y0 + 0.1, ZB - 0.05)))
    legs.push(seg(P(x, y0 + DY - 0.1), P(x, y0 + DY - 0.1, ZF + 0.02)))
    legs.push(seg(P(x, y0 + 0.1), P(x, y0 + DY - 0.1)))
  }
  return legs.join('')
}

// 1.2 m parapet south of row 3.
const WA: Pt = [716.9, 735.1]
const WB: Pt = [1301.1, 472.5]
const WH = 55
const up = (p: Pt, h = WH): Pt => [p[0], p[1] - h]
const back: Pt = [-6, -5]

function grid() {
  const lines: string[] = []
  for (let i = -14; i <= 30; i++) lines.push(seg(P(i * 1.75, -14), P(i * 1.75, 26)))
  for (let j = -14; j <= 26; j++) lines.push(seg(P(-14 * 1.75, j), P(30 * 1.75, j)))
  return lines.join('')
}
const GRID = grid()

export type Overlay = 'urgent' | 'later' | 'weaker' | 'sensor' | 'clock' | 'offline'
export type RoofView = 'plain' | 'pipeline' | 'problems' | 'energy' | 'quality' | 'dispatch'

function overlaysFor(view: RoofView, step: number): Map<number, Overlay> {
  const m = new Map<number, Overlay>()
  if (view === 'plain') return m
  if (view === 'pipeline') {
    if (step >= 2) [25, 26, 27].forEach(n => m.set(n, 'sensor'))
    return m
  }
  if (view === 'quality') {
    [25, 26, 27].forEach(n => m.set(n, 'sensor'));
    [4, 5, 6].forEach(n => m.set(n, 'clock'));
    [31, 32, 33].forEach(n => m.set(n, 'offline'))
    return m
  }
  m.set(22, 'urgent'); m.set(8, 'urgent'); m.set(33, 'later')
  if (view === 'problems') {
    weakening.forEach(n => m.set(n, 'weaker'));
    [25, 26, 27].forEach(n => m.set(n, 'sensor'))
  }
  if (view === 'dispatch') [25, 26, 27].forEach(n => m.set(n, 'sensor'))
  return m
}

export interface RoofProps {
  view: RoofView
  /** pipeline progress, 0..7 */
  step?: number
  selected?: string
  onPanel?: (id: string) => void
  dim?: boolean
  labels?: boolean
  pins?: boolean
}

export function Roof({ view, step = 7, selected, onPanel, dim, labels = true, pins = true }: RoofProps) {
  const uid = useId().replace(/:/g, '')
  const ov = overlaysFor(view, step)
  const showBlooms = view === 'problems' || view === 'energy' || view === 'dispatch' || (view === 'pipeline' && step >= 7)
  const wallLabel = view === 'energy' || view === 'quality' || view === 'dispatch' ? '1.2 m wall' : '1.2 m wall · row 3 is shaded first'
  const scanRow = view === 'pipeline' && step < 7 ? Math.min(2, Math.max(0, step - 3)) : -1

  const panelEl = (n: number) => {
    const g = G(n)
    const o = ov.get(n)
    const id = pid(n)
    const faded = view === 'pipeline' && step < 6 && g.row === 2 && o !== 'sensor'
    const clickable = !!onPanel && (o === 'urgent' || o === 'later')
    return (
      <g key={n} className={'panel' + (clickable ? ' clickable' : '') + (selected === id ? ' selected' : '')}
        opacity={faded ? 0.55 : 1}
        onClick={clickable ? () => onPanel!(id) : undefined}
        role={clickable ? 'button' : undefined}
        tabIndex={clickable ? 0 : undefined}
        aria-label={clickable ? `${id}, show details` : undefined}
        onKeyDown={clickable ? e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onPanel!(id) } } : undefined}>
        <path d={poly(g.quad)} fill={`url(#pf${uid})`} className="pf" />
        <path d={g.cells} className="pc" />
        {o === 'urgent' && <path d={poly(g.quad)} className="ov urgent" />}
        {o === 'weaker' && <path d={poly(g.quad)} className="ov weaker" />}
        {o === 'sensor' && <path d={poly(g.quad)} className="ov sensor" />}
        {o && <path d={poly(g.quad)} className={'edge ' + o} />}
      </g>
    )
  }

  const rowGroup = (r: number) => (
    <g key={r}>
      {[1, 2, 3, 4].map(k => <path key={k} className="rack" d={racks(r * 4 + k)} />)}
      {PANELS.filter(n => G(n).row === r).map(panelEl)}
    </g>
  )

  // Low-sun shadow of the wall (Energy lost only)
  const A2 = add(WA, back), B2 = add(WB, back)
  const shadowPoly = poly([A2, B2, add(B2, [-100, -84]), add(A2, [-100, -84])])

  const scan = scanRow >= 0 ? (() => {
    const a = G(scanRow * 12 + 1).origin, b = G(scanRow * 12 + 12).origin
    const lowA = add(a, [34.6, 87.1]), lowB = add(b, [74.6, 69.1])
    return { band: poly([add(a, [0, 18]), add(b, [40, 0]), lowB, lowA]), edge: seg(lowA, lowB), row: scanRow }
  })() : null

  const hubBox = (h: number) => {
    const O = add(G(h * 3 - 1).origin, [17, 13])
    const a: Pt = [15, -6.5], b: Pt = [-8.4, -6.9]
    const Oa = add(O, a), Oab = add(Oa, b), Ob = add(O, b)
    const t = (p: Pt) => up(p, 12)
    const special = h === 2 ? 'clock' : h === 9 ? 'sensor' : h === 11 ? 'offline' : ''
    const c = lerp(O, Oab, 0.5)
    return (
      <g key={h} className={'hubbox ' + special}>
        {special && <ellipse cx={c[0]} cy={c[1] - 2} rx={21} ry={10.5} className={'ring ' + special} />}
        <path d={poly([O, Oa, t(Oa), t(O)])} className="hb-front" />
        <path d={poly([Oa, Oab, t(Oab), t(Oa)])} className="hb-side" />
        <path d={poly([t(O), t(Oa), t(Oab), t(Ob)])} className="hb-top" />
        <path d={poly([lerp(t(O), t(Oab), 0.25), lerp(t(Oa), t(Ob), 0.25), lerp(t(O), t(Oab), 0.75), lerp(t(Oa), t(Ob), 0.75)])} className={'hb-plate ' + (h === 9 ? 'sensor' : '')} />
        {special && (
          <g transform={`translate(${c[0]} ${c[1] - 30})`} className={'hubchip ' + special}>
            <rect x={-17} y={-10} width={34} height={20} rx={5} />
            <text y={4} textAnchor="middle">{'H' + String(h).padStart(2, '0')}</text>
          </g>
        )}
      </g>
    )
  }

  const pinFor = (id: string) => G(Number(id.slice(1))).centre
  const dispatchPins = [['P22', '1', true], ['P08', '2', true], ['P33', '3', false]] as const

  return (
    <svg className={'roof' + (dim ? ' dim' : '')} viewBox="0 0 1440 960" width="1440" height="960" role="img"
      aria-label="Rooftop with 36 panels in 3 rows, 12 hubs, and a 1.2 m wall south of row 3">
      <defs>
        <linearGradient id={`pf${uid}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#405280" />
          <stop offset="1" stopColor="#1C2645" />
        </linearGradient>
        <radialGradient id={`bloom${uid}`}>
          <stop offset="0" stopColor="var(--status-fault)" stopOpacity="1" />
          <stop offset=".3" stopColor="var(--status-fault)" stopOpacity=".6" />
          <stop offset="1" stopColor="var(--status-fault)" stopOpacity="0" />
        </radialGradient>
        <linearGradient id={`ws${uid}`} gradientUnits="userSpaceOnUse" x1={A2[0]} y1={A2[1]} x2={A2[0] - 100} y2={A2[1] - 84}>
          <stop offset="0" stopColor="#03050D" stopOpacity=".92" />
          <stop offset=".6" stopColor="#03050D" stopOpacity=".7" />
          <stop offset="1" stopColor="#03050D" stopOpacity="0" />
        </linearGradient>
      </defs>

      <path className="grid" d={GRID} />
      <g className="scene-body">
        {[1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12].map(h => <path key={h} className="hub-shadow" d={hubShadow(h)} />)}
        {rowGroup(0)}
        {rowGroup(1)}
        {rowGroup(2)}

        {view === 'energy' && <path className="wall-shadow" d={shadowPoly} fill={`url(#ws${uid})`} />}

        {scan && (
          <g className="scan" key={scan.row}>
            <path d={scan.band} className="scan-band" />
            <path d={scan.edge} className="scan-edge" />
          </g>
        )}

        {showBlooms && [8, 33].map(n => {
          const c = add(G(n).origin, [42, 70])
          return (
            <g key={n} className={'bloom' + (view === 'problems' ? ' live' : '')} pointerEvents="none">
              <ellipse cx={c[0]} cy={c[1]} rx={22} ry={15} fill={`url(#bloom${uid})`} />
              <ellipse cx={c[0]} cy={c[1]} rx={4} ry={3} className="bloom-core" />
            </g>
          )
        })}

        {(view === 'problems' || view === 'energy' || view === 'dispatch') && (() => {
          const o = add(G(22).origin, [50, 78])
          return (
            <g className="connector-break" transform={`translate(${o[0] - 8} ${o[1] - 6}) scale(1.6)`} pointerEvents="none">
              <path d="M0 0L9 7" className="cb-a" />
              <rect x={8} y={6} width={6} height={5} rx={1} className="cb-a-fill" />
              <rect x={17} y={13} width={6} height={5} rx={2.5} className="cb-b-fill" />
              <path d="M22 17L30 24" className="cb-b" />
            </g>
          )
        })()}

        {/* wall */}
        <g className="wall">
          <path d={poly([WA, WB, up(WB), up(WA)])} className="wall-face" />
          <path d={poly([up(WA), up(WB), add(up(WB), back), add(up(WA), back)])} className="wall-top" />
          <path d={poly([WB, add(WB, back), add(up(WB), back), up(WB)])} className="wall-end" />
          <text className="wall-label" transform={`translate(${WA[0] + 36.6} ${WA[1] - 38.1}) rotate(-23.8)`}>{wallLabel}</text>
        </g>

        {view === 'quality' && Array.from({ length: 12 }, (_, i) => hubBox(i + 1))}

        {labels && PANELS.map(n => {
          const g = G(n)
          const o = ov.get(n)
          const flagged = o && o !== 'clock' && o !== 'offline'
          return (
            <g key={n} className={'chip' + (flagged ? ' flagged ' + o : '')} transform={`translate(${g.centre[0].toFixed(1)} ${(g.centre[1] + 3).toFixed(1)})`} pointerEvents="none">
              <rect x={-15} y={-10} width={30} height={20} rx={5} />
              <text y={4} textAnchor="middle">{pid(n)}</text>
            </g>
          )
        })}

        {(view === 'problems' || (view === 'pipeline' && step >= 2)) && (() => {
          const c = G(25).origin
          return <text className="roof-note sensor" x={c[0] - 128} y={c[1] + 82}>H09 · sensor left out</text>
        })()}

        {pins && view === 'problems' && selected && (() => {
          const c = pinFor(selected)
          return (
            <g className="pin" key={selected} transform={`translate(${c[0]} ${c[1] - 10})`} pointerEvents="none">
              <path d="M0 0V-28" className="pin-stem" />
              <circle cy={-46} r={18} className="pin-head" />
              <g transform="translate(-10 -56)" className="pin-icon">
                <circle cx="10" cy="10" r="7.5" />
                <path d="M10 6.5v4M10 13.5h.01" />
              </g>
            </g>
          )
        })()}

        {pins && view === 'dispatch' && dispatchPins.map(([id, label, urgent]) => {
          const c = pinFor(id)
          return (
            <g key={id} className={'npin' + (urgent ? '' : ' later')} transform={`translate(${c[0]} ${c[1] - 10})`} pointerEvents="none">
              <path d="M0 0V-26" className="pin-stem" />
              <circle cy={-39} r={13} className="npin-head" />
              <text y={-34.5} textAnchor="middle">{label}</text>
            </g>
          )
        })}
      </g>
    </svg>
  )
}
