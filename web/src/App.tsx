import { useCallback, useEffect, useLayoutEffect, useRef, useState, type ReactNode } from 'react'
import { Icon, Logo, type IconName } from './Icon'
import { Roof, type RoofView } from './Roof'
import { bring, energy, faults, files, pastVisits, quality, site, steps, type FaultId } from './data'
import './App.css'

type Route = 'files' | 'check' | 'site' | 'energy' | 'quality' | 'visit' | 'reports'
const ROUTES: Route[] = ['files', 'check', 'site', 'energy', 'quality', 'visit', 'reports']
const SITE: Route[] = ['site', 'energy', 'quality']

function readRoute(): Route {
  const h = window.location.hash.replace(/^#\/?/, '') as Route
  return ROUTES.includes(h) ? h : 'files'
}

function useRoute(): [Route, (r: Route) => void] {
  const [route, set] = useState<Route>(readRoute)
  useEffect(() => {
    const on = () => set(readRoute())
    window.addEventListener('hashchange', on)
    return () => window.removeEventListener('hashchange', on)
  }, [])
  return [route, useCallback((r: Route) => { window.location.hash = '/' + r }, [])]
}

type Theme = 'night' | 'day'
function useTheme(): [Theme, (t: Theme) => void] {
  const [theme, setTheme] = useState<Theme>(() => {
    try {
      const saved = localStorage.getItem('ss-theme')
      if (saved === 'day' || saved === 'night') return saved
    } catch { /* storage unavailable */ }
    return window.matchMedia?.('(prefers-color-scheme: light)').matches ? 'day' : 'night'
  })
  useEffect(() => {
    document.documentElement.dataset.theme = theme
    try { localStorage.setItem('ss-theme', theme) } catch { /* storage unavailable */ }
  }, [theme])
  return [theme, setTheme]
}

/** Fit the 1440 × 960 design canvas to the window; below 900 px the layout reflows instead. */
function useStage() {
  const calc = () => {
    const w = window.innerWidth, h = window.innerHeight
    return { flow: w < 900, scale: Math.min(w / 1440, h / 960) }
  }
  const [s, set] = useState(calc)
  useLayoutEffect(() => {
    const on = () => set(calc())
    window.addEventListener('resize', on)
    return () => window.removeEventListener('resize', on)
  }, [])
  return s
}

function download(name: string, text: string) {
  const url = URL.createObjectURL(new Blob([text], { type: 'text/csv' }))
  const a = document.createElement('a')
  a.href = url
  a.download = name
  a.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

const workOrdersCsv = () => [
  'work_order,stop,panel,hub,row,problem,urgency,kwh_lost_per_day,what_to_do',
  ...faults.map((f, i) => [f.order, i + 1, f.id, f.hub, f.row, f.kind, f.urgent ? 'urgent' : 'not urgent', f.kwhDay, `"${f.plan}"`].join(',')),
  ',4,P25-P27,H09,3,light sensor reads high,not urgent,,"Reads too high since Jan 19. Clean or replace it."',
].join('\n')

/* ------------------------------------------------------------- primitives */

function Btn({ kind = 'primary', size = 'm', icon, children, onClick, disabled, className = '' }: {
  kind?: 'primary' | 'secondary' | 'ghost'; size?: 'm' | 's'; icon?: IconName; children: ReactNode
  onClick?: () => void; disabled?: boolean; className?: string
}) {
  return (
    <button type="button" className={`btn ${kind} ${size} ${className}`} onClick={onClick} disabled={disabled}>
      <span>{children}</span>
      {icon && <Icon name={icon} size={size === 's' ? 16 : 18} />}
    </button>
  )
}

const NAV: { route: Route; icon: IconName; label: string; match: Route[] }[] = [
  { route: 'site', icon: 'panel', label: 'Site', match: SITE },
  { route: 'files', icon: 'upload', label: 'Files', match: ['files'] },
  { route: 'check', icon: 'scope', label: 'Check', match: ['check'] },
  { route: 'visit', icon: 'dispatch', label: 'Visit', match: ['visit'] },
  { route: 'reports', icon: 'report', label: 'Reports', match: ['reports'] },
]

function Rail({ route, go, theme, setTheme }: { route: Route; go: (r: Route) => void; theme: Theme; setTheme: (t: Theme) => void }) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!open) return
    const onDown = (e: MouseEvent) => { if (!ref.current?.contains(e.target as Node)) setOpen(false) }
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false) }
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onKey)
    return () => { document.removeEventListener('mousedown', onDown); document.removeEventListener('keydown', onKey) }
  }, [open])
  return (
    <nav className="rail" aria-label="Main">
      <div className="rail-logo"><Logo size={30} /></div>
      <ul>
        {NAV.map(n => {
          const on = n.match.includes(route)
          return (
            <li key={n.route}>
              <button type="button" className={on ? 'on' : ''} aria-current={on ? 'page' : undefined} onClick={() => go(n.route)}>
                <Icon name={n.icon} />
                <span>{n.label}</span>
              </button>
            </li>
          )
        })}
      </ul>
      <div className="rail-foot" ref={ref}>
        <button type="button" className="rail-icon" aria-label="Settings" aria-expanded={open} onClick={() => setOpen(o => !o)}>
          <Icon name="settings" />
        </button>
        {open && (
          <div className="menu" role="menu" aria-label="Appearance">
            <p>Appearance</p>
            {(['night', 'day'] as Theme[]).map(t => (
              <button key={t} type="button" role="menuitemradio" aria-checked={theme === t} onClick={() => { setTheme(t); setOpen(false) }}>
                <Icon name={t === 'night' ? 'cloud' : 'sun'} size={16} />
                <span>{t === 'night' ? 'Night' : 'Day'}</span>
                {theme === t && <Icon name="check" size={16} className="tick" />}
              </button>
            ))}
          </div>
        )}
        <span className="avatar" title="Signed in as DT">DT</span>
      </div>
    </nav>
  )
}

function Header({ period }: { period: string }) {
  return (
    <header className="head">
      <nav aria-label="Breadcrumb" className="crumb">{site.city}<span aria-hidden="true">/</span>{site.id}</nav>
      <h1>{site.name}</h1>
      <p className="period"><Icon name="calendar" size={14} />{period}</p>
    </header>
  )
}

type Key = 'urgent' | 'later' | 'weaker' | 'sensor' | 'fine' | 'shade' | 'clock' | 'offline'
const KEY_LABEL: Record<Key, string> = {
  urgent: 'Urgent visit', later: 'Visit, not urgent', weaker: 'Getting weaker', sensor: 'Sensor left out',
  fine: 'Working fine', shade: 'Shaded first by the wall', clock: 'Clock fixed', offline: 'Went offline',
}
function Legend({ keys }: { keys: Key[] }) {
  return (
    <ul className="legend" aria-label="Map key">
      {keys.map(k => <li key={k}><i className={'key ' + k} />{KEY_LABEL[k]}</li>)}
    </ul>
  )
}

function SiteTabs({ route, go }: { route: Route; go: (r: Route) => void }) {
  const tabs: [Route, string][] = [['site', 'Problems'], ['energy', 'Energy lost'], ['quality', 'Data quality']]
  return (
    <div className="tabs" role="tablist" aria-label="Site view">
      {tabs.map(([r, l]) => (
        <button key={r} type="button" role="tab" aria-selected={route === r} onClick={() => go(r)}>{l}</button>
      ))}
    </div>
  )
}

/* ------------------------------------------------------------- screens */

type ImportState = 'empty' | 'adding' | 'ready'

function FilesScreen({ state, added, onAdd, onReset, onCheck }: {
  state: ImportState; added: number; onAdd: () => void; onReset: () => void; onCheck: () => void
}) {
  const [over, setOver] = useState(false)
  if (state === 'ready') {
    return (
      <section className="card col" aria-labelledby="files-h">
        <h2 id="files-h" className="h3">Add this site’s files</h2>
        <p className="sub">All four are here. We check each one before anything runs.</p>
        <ul className="files">
          {files.map(f => (
            <li key={f.name}><Icon name="check" size={20} className="t-ok" /><span><b>{f.name}</b><small>{f.meta}</small></span></li>
          ))}
        </ul>
        <button type="button" className="link-btn" onClick={onReset}>Replace files</button>
        <Btn onClick={onCheck} className="wide">Check my data</Btn>
        <p className="hint">Usually done in under 10 seconds</p>
      </section>
    )
  }
  return (
    <section className="card col" aria-labelledby="files-h">
      <h2 id="files-h" className="h3">Add this site’s files</h2>
      <p className="sub">Drop all four at once. We check each file before anything runs.</p>
      <div className={'drop' + (over ? ' over' : '')}
        onDragOver={e => { e.preventDefault(); setOver(true) }}
        onDragLeave={() => setOver(false)}
        onDrop={e => { e.preventDefault(); setOver(false); if (state === 'empty') onAdd() }}>
        <Icon name="upload" size={24} className="t-accent" />
        <b>Drop files here</b>
        <Btn kind="secondary" size="s" onClick={onAdd} disabled={state === 'adding'}>Choose files</Btn>
      </div>
      <ul className="files">
        {files.map((f, i) => {
          const s = i < added ? 'done' : state === 'adding' && i === added ? 'checking' : 'waiting'
          return (
            <li key={f.name} className={s}>
              {s === 'done' ? <Icon name="check" size={20} className="t-ok" /> : s === 'checking' ? <span className="spin" /> : <span className="ring" />}
              <span><b>{f.name}</b><small>{s === 'done' ? f.meta : s === 'checking' ? 'Checking…' : 'Waiting'}</small></span>
            </li>
          )
        })}
      </ul>
      <Btn disabled className="wide">Check my data</Btn>
      <p className="hint">Add all four files to start</p>
    </section>
  )
}

function CheckScreen({ step, go }: { step: number; go: (r: Route) => void }) {
  const done = step >= 7
  return (
    <>
      <section className="card col" aria-labelledby="check-h">
        <h2 id="check-h" className="h3">{done ? 'Your data is checked' : 'Checking your data'}</h2>
        <p className="sub">{done
          ? '3 panels need a visit and 1,286 kWh was lost in the last 6 months. Here is the full picture.'
          : 'This takes a few seconds. You can leave this page, we will keep going.'}</p>
        {!done && (
          <div className="progress" role="progressbar" aria-label="Progress" aria-valuemin={0} aria-valuemax={7} aria-valuenow={step}>
            <i style={{ width: `${(step / 7) * 100}%` }} />
          </div>
        )}
        <p className="sub sm" aria-live="polite">{done ? 'All 7 steps done' : `Step ${step + 1} of 7`}</p>
        <ol className="steps">
          {steps.map((s, i) => {
            const st = i < step ? 'done' : i === step ? 'now' : 'wait'
            return (
              <li key={s.title} className={st}>
                {st === 'done' ? <Icon name="check" size={20} className="t-ok" /> : st === 'now' ? <span className="spin" /> : <span className="ring" />}
                <span><b>{s.title}</b>{st !== 'wait' && <small>{s.detail}</small>}</span>
              </li>
            )
          })}
        </ol>
        {done && <Btn onClick={() => go('site')} className="wide">See what we found</Btn>}
      </section>
      {!done && step >= 3 && (
        <section className="card toast-card" role="status">
          <Icon name="sensor-drift" className="t-sensor" />
          <div>
            <b className="h4">Found one thing so far</b>
            <p className="body-s">Hub H09’s light sensor has read too high since Jan 19. We will leave it out so it does not skew your results.</p>
          </div>
          <Btn kind="ghost" size="s" onClick={() => go('quality')}>Show me</Btn>
        </section>
      )}
    </>
  )
}

function KwhRow({ label, value, max, tone }: { label: string; value: number; max: number; tone: string }) {
  return (
    <div className="kwh-row">
      <div className="kwh-line"><span>{label}</span><b className="num">{value} kWh</b></div>
      <div className="bar"><i className={tone} style={{ width: `${(value / max) * 100}%` }} /></div>
    </div>
  )
}

function ProblemsScreen({ go, selected, setSelected }: { go: (r: Route) => void; selected: FaultId | null; setSelected: (f: FaultId | null) => void }) {
  const f = faults.find(x => x.id === selected)
  const [history, setHistory] = useState(false)
  useEffect(() => setHistory(false), [selected])
  return (
    <>
      <section className="card col" aria-labelledby="need-h">
        <h2 id="need-h" className="h3">3 panels need a visit</h2>
        <p className="sub">Together they lose about 9 kWh a day. 2 more are getting weaker. The rest work normally.</p>
        <ul className="faults">
          {faults.map(x => (
            <li key={x.id}>
              <button type="button" aria-pressed={selected === x.id} onClick={() => setSelected(x.id)}>
                <Icon name={x.icon} className={x.urgent ? 't-fault' : 't-2'} />
                <span><b>{x.id} · {x.kind}</b><small>{x.urgent ? 'Urgent' : 'Not urgent'} · {x.kwhDay} kWh a day since {x.since}</small></span>
              </button>
            </li>
          ))}
        </ul>
        <div className="divided">
          <p className="h4 keyed"><i className="key weaker" />Keep an eye on P14 and P29</p>
          <p className="sub">They make a little less each month. No visit needed yet.</p>
        </div>
        <Btn onClick={() => go('visit')} className="wide">Plan one visit for all 3</Btn>
      </section>

      <section className="card col-bottom" aria-labelledby="lost-h">
        <h2 id="lost-h" className="h4">1,286 kWh lost</h2>
        <small>compared with a clean, healthy roof</small>
        <div className="loss">
          <KwhRow label="Weather" value={energy.weather.kwh} max={1286} tone="weather" />
          <small>Dirt 402 · clouds 256 · heat 216</small>
          <KwhRow label="Panel problems" value={energy.panels.kwh} max={1286} tone="fault" />
          <small>Hot spots 284 · wiring 128</small>
        </div>
      </section>

      {f && (
        <section className="card popover" key={f.id} aria-labelledby="pop-h">
          <div className="pop-head">
            <div><h3 id="pop-h" className="h4">{f.id} · {f.kind}</h3><small>Hub {f.hub} · row {f.row}</small></div>
            <button type="button" className="icon-btn" aria-label="Close details" onClick={() => setSelected(null)}><Icon name="close" size={18} /></button>
          </div>
          {history && f.history ? (
            <ol className="history">
              {f.history.map(h => <li key={h.ticket}><b className="num">{h.date}</b><span>{h.note}<small>{h.ticket} · $350 truck roll</small></span></li>)}
            </ol>
          ) : (
            <>
              <p className="body-s">{f.why}</p>
              <p className="label">What to do</p>
              <ol className="todo">{f.todo.map(t => <li key={t}>{t}</li>)}</ol>
            </>
          )}
          <div className="row">
            <Btn kind="secondary" size="s" onClick={() => go('visit')}>See visit plan</Btn>
            {f.history && <Btn kind="ghost" size="s" onClick={() => setHistory(h => !h)}>{history ? 'What to do' : 'Repair history'}</Btn>}
          </div>
        </section>
      )}

      <button type="button" className="card dq-strip" onClick={() => go('quality')}>
        <span className="dq-score"><Icon name="check" className="t-ok" /><span><b className="h4">99% of readings usable</b><small>420,904 readings · 12 months</small></span></span>
        {quality.hubs.map(h => (
          <span key={h.hub} className="dq-item"><b><i className={'dot ' + h.tone} />{h.strip[0]}</b><small>{h.strip[1]}</small></span>
        ))}
      </button>
    </>
  )
}

function EnergyScreen({ go }: { go: (r: Route) => void }) {
  const max = 402
  const wPct = (energy.weather.kwh / 1286) * 100
  return (
    <>
      <section className="card col" aria-labelledby="en-h">
        <h2 id="en-h" className="h3">1,286 kWh lost</h2>
        <p className="sub">In the last 6 months, compared with a clean, healthy roof.</p>
        <div className="split" aria-hidden="true"><i className="weather" style={{ width: `${wPct}%` }} /><i className="fault" /></div>
        <div className="group">
          <div className="group-head"><span className="h4 keyed"><i className="key weatherkey" />Weather</span><b className="num big">874 kWh</b></div>
          <small>No repair needed. Dirt can be washed off; clouds and heat cannot be fixed.</small>
          {energy.weather.parts.map(([l, v]) => <KwhRow key={l} label={l} value={v} max={max} tone="weather" />)}
        </div>
        <div className="group divided">
          <div className="group-head"><span className="h4 keyed"><i className="key urgent" />Panel problems</span><b className="num big">412 kWh</b></div>
          <small>Fixable. All three panels are on one visit plan.</small>
          {energy.panels.parts.map(([l, v]) => <KwhRow key={l} label={l} value={v} max={max} tone="fault" />)}
        </div>
      </section>
      <section className="card side" aria-labelledby="stop-h">
        <h2 id="stop-h" className="h4">Stop the panel losses</h2>
        <p className="body-s">P22, P08 and P33 still lose about 9 kWh a day together. One visit can fix all three.</p>
        <div className="row">
          <Btn size="s" onClick={() => go('visit')}>Plan the visit</Btn>
          <Btn kind="ghost" size="s" onClick={() => go('site')}>See problems</Btn>
        </div>
      </section>
    </>
  )
}

function QualityScreen({ go }: { go: (r: Route) => void }) {
  return (
    <>
      <div className="col stack">
        <section className="card" aria-labelledby="dq-h">
          <h2 id="dq-h" className="h3">99% of readings usable</h2>
          <p className="sub">We checked all 420,904 readings in the file: 12 months, 12 hubs.</p>
          <div className="bar thick"><i className="ok" style={{ width: '99%' }} /></div>
          <div className="divided">
            <p className="h4">1,424 repeat readings counted once</p>
            <p className="sub">Some readings arrived twice. Nothing was deleted.</p>
          </div>
        </section>
        <section className="card" aria-labelledby="hubs-h">
          <h2 id="hubs-h" className="h3">3 hubs needed a fix</h2>
          <p className="sub">Two are sorted. H09’s light sensor still reads high, so it is on the visit plan.</p>
          <ul className="hubfix">
            {quality.hubs.map(h => (
              <li key={h.hub}>
                <h3 className="h4"><i className={'dot ' + h.tone} />{h.hub} · panels {h.panels}</h3>
                <p className="body-s"><b>What happened:</b> {h.happened}</p>
                <p className="body-s"><b>What we did:</b> {h.did}</p>
              </li>
            ))}
          </ul>
        </section>
      </div>
      <section className="card side" aria-labelledby="method-h">
        <h2 id="method-h" className="h4">Want the full method?</h2>
        <p className="body-s">Page 6 of each report lists usable data for every hub and the rules we used.</p>
        <div className="row"><Btn kind="secondary" size="s" onClick={() => go('reports')}>Go to reports</Btn></div>
      </section>
    </>
  )
}

function Ticket({ stub, n, urgent, sent, title, meta, body, sensor }: {
  stub: string; n?: string; urgent?: boolean; sent?: boolean; title: string; meta: string; body: string; sensor?: boolean
}) {
  return (
    <li className="ticket-wrap">
      <article className="ticket">
        <div className="stub">
          {sensor ? <Icon name="sensor" size={22} className="t-2" /> : <span className={'badge' + (urgent ? '' : ' later')}>{n}</span>}
          <span className={'wo' + (sensor ? '' : ' num')}>{stub}</span>
          {sent && !sensor && <span className="sent-tag">Sent</span>}
        </div>
        <div className="ticket-body">
          <h3 className="h4">{title}</h3>
          <small>{meta}</small>
          <p className="body-s strong">{body}</p>
        </div>
      </article>
    </li>
  )
}

function VisitScreen({ go, sent, setSent, toast }: { go: (r: Route) => void; sent: boolean; setSent: (s: boolean) => void; toast: (m: string) => void }) {
  const [packed, setPacked] = useState<string[]>([])
  const dl = () => { download('work_orders_D001-D003.csv', workOrdersCsv()); toast('Work orders saved as a CSV file') }
  return (
    <>
      <section className="plan" aria-labelledby="plan-h">
        <h2 id="plan-h" className="h3">Visit plan</h2>
        <p className="sub">One trip covers all 3 panels. Go in this order, the most urgent first.</p>
        <ol className="tickets">
          {faults.map((f, i) => (
            <Ticket key={f.id} stub={f.order} n={String(i + 1)} urgent={f.urgent} sent={sent}
              title={`${f.id} · ${f.kind}`} meta={`Hub ${f.hub} · row ${f.row} · ${f.urgent ? 'Urgent' : 'Not urgent'} · ${f.kwhDay} kWh a day`} body={f.plan} />
          ))}
          <Ticket stub="Check" sensor title="Also: H09 light sensor" meta="Hub H09 · row 3, by P25–P27" body="Reads too high since Jan 19. Clean or replace it." />
        </ol>
      </section>

      <section className="card col-bottom" aria-labelledby="past-h">
        <h2 id="past-h" className="h4">What past visits tell us</h2>
        {pastVisits.map(p => <p key={p.slice(0, 16)} className="body-s">{p}</p>)}
      </section>

      <section className="card before" aria-labelledby="bring-h">
        <h2 id="bring-h" className="h4">Bring with you</h2>
        <ul className="bring">
          {bring.map(b => (
            <li key={b}><label><input type="checkbox" checked={packed.includes(b)}
              onChange={() => setPacked(p => p.includes(b) ? p.filter(x => x !== b) : [...p, b])} /><span>{b}</span></label></li>
          ))}
        </ul>
        {sent ? (
          <div className="sent" role="status">
            <div className="sent-row">
              <Icon name="check" size={22} className="t-ok" />
              <div><b className="h4">Sent to the technician</b><small>3 work orders, D001 to D003</small></div>
              <Btn kind="ghost" size="s" onClick={() => setSent(false)}>Undo</Btn>
            </div>
            <div className="row">
              <Btn kind="ghost" size="s" icon="download" onClick={dl}>Download work orders</Btn>
              <Btn kind="ghost" size="s" onClick={() => go('reports')}>Get the reports</Btn>
            </div>
          </div>
        ) : (
          <div className="actions">
            <Btn onClick={() => setSent(true)} className="wide">Send to technician</Btn>
            <Btn kind="ghost" icon="download" onClick={dl}>Download work orders</Btn>
          </div>
        )}
      </section>
    </>
  )
}

function ReportsScreen({ toast }: { toast: (m: string) => void }) {
  const pdf = () => toast('This demo has no back-end, so the PDF is not generated here.')
  const csv = () => {
    download('panel_results_demo.csv', [
      'panel,hub,row,status,kwh_lost_per_day,since',
      ...faults.map(f => [f.id, f.hub, f.row, f.urgent ? 'urgent visit' : 'visit, not urgent', f.kwhDay, f.since].join(',')),
      'P14,H05,2,getting weaker,,',
      'P29,H10,3,getting weaker,,',
    ].join('\n'))
    toast('Result file saved as a CSV file')
  }
  return (
    <section className="card col" aria-labelledby="rep-h">
      <h2 id="rep-h" className="h3">Your reports are ready</h2>
      <p className="sub">Two reports, one for each time window. Share them with your team or the site owner.</p>
      <div className="rep divided">
        <h3 className="h4">Last 6 months</h3>
        <small>Mar 5 – Aug 31, 2026 · PDF</small>
        <p className="body-s muted">Six pages: losses and why, the 3 panels to visit, repeat repairs, panels getting weaker, and data quality.</p>
        <Btn size="s" icon="download" onClick={pdf}>Download PDF</Btn>
      </div>
      <div className="rep divided">
        <h3 className="h4">Last 12 months</h3>
        <small>Sep 1, 2025 – Aug 31, 2026 · PDF</small>
        <p className="body-s muted">The same six pages over a full year. Better for slow trends like P14 and P29.</p>
        <Btn kind="secondary" size="s" icon="download" onClick={pdf}>Download PDF</Btn>
      </div>
      <div className="rep raw divided">
        <span><b>Want the numbers?</b><small>5 result files, CSV</small></span>
        <Btn kind="ghost" size="s" icon="download" onClick={csv}>Download files</Btn>
      </div>
      <p className="made">Made Sep 1 at 6:12 AM</p>
    </section>
  )
}

/* ------------------------------------------------------------- app */

const TITLES: Record<Route, string> = { files: 'Files', check: 'Check', site: 'Problems', energy: 'Energy lost', quality: 'Data quality', visit: 'Visit plan', reports: 'Reports' }

export default function App() {
  const [route, go] = useRoute()
  const [theme, setTheme] = useTheme()
  const { flow, scale } = useStage()

  const [imp, setImp] = useState<ImportState>('empty')
  const [added, setAdded] = useState(0)
  const [step, setStep] = useState(7)
  const [running, setRunning] = useState(false)
  const [selected, setSelected] = useState<FaultId | null>('P22')
  const [sent, setSent] = useState(false)
  const [msg, setMsg] = useState<string | null>(null)

  const toast = useCallback((m: string) => setMsg(m), [])
  useEffect(() => {
    if (!msg) return
    const t = setTimeout(() => setMsg(null), 3200)
    return () => clearTimeout(t)
  }, [msg])

  // Files: the four demo files arrive one after another.
  useEffect(() => {
    if (imp !== 'adding') return
    if (added >= files.length) { setImp('ready'); return }
    const t = setTimeout(() => setAdded(a => a + 1), 420)
    return () => clearTimeout(t)
  }, [imp, added])

  // Check: advance the pipeline while it runs.
  useEffect(() => {
    if (!running) return
    if (step >= 7) { setRunning(false); return }
    const t = setTimeout(() => setStep(s => s + 1), step === 3 ? 1800 : 1000)
    return () => clearTimeout(t)
  }, [running, step])

  useEffect(() => { document.title = `SolarScope · ${TITLES[route]}` }, [route])

  const startCheck = () => { setStep(0); setRunning(true); go('check') }
  const newData = () => { setImp('empty'); setAdded(0); go('files') }

  const period = route === 'files' && imp !== 'ready' ? 'No data yet'
    : route === 'files' || (route === 'check' && step < 7) ? site.period
      : `${site.period} · ${site.made}`

  const roofView: RoofView = route === 'files' ? 'plain'
    : route === 'check' ? (step >= 7 ? 'problems' : 'pipeline')
      : route === 'site' || route === 'reports' ? 'problems'
        : route === 'visit' ? 'dispatch' : route

  const legend: Key[] | null = route === 'site' || route === 'reports' || (route === 'check' && step >= 7)
    ? ['urgent', 'later', 'weaker', 'sensor', 'fine']
    : route === 'energy' ? ['urgent', 'later', 'fine', 'shade']
      : route === 'quality' ? ['sensor', 'clock', 'offline', 'fine'] : null

  const stageStyle = flow ? undefined : { transform: `translate(-50%, -50%) scale(${scale})` }

  return (
    <div className={'viewport' + (flow ? ' flow' : '')}>
      <div className={'stage r-' + route} style={stageStyle}>
        <div className={'roof-layer' + (route === 'visit' ? ' shifted' : '')}>
          <Roof view={roofView} step={route === 'check' ? step : 7} dim={route === 'files'} labels={route !== 'files'}
            selected={route === 'site' ? selected ?? undefined : undefined}
            onPanel={route === 'site' ? id => setSelected(id as FaultId) : undefined} />
        </div>
        <Rail route={route} go={go} theme={theme} setTheme={setTheme} />
        <Header period={period} />
        {SITE.includes(route) && <SiteTabs route={route} go={go} />}
        {SITE.includes(route) && <div className="top-right"><Btn kind="secondary" icon="upload" onClick={newData}>Check new data</Btn></div>}
        {legend && <Legend keys={legend} />}

        <main className="layer">
          {route === 'files' && <FilesScreen state={imp} added={added}
            onAdd={() => { setAdded(0); setImp('adding') }} onReset={() => { setImp('empty'); setAdded(0) }} onCheck={startCheck} />}
          {route === 'check' && <CheckScreen step={step} go={go} />}
          {route === 'site' && <ProblemsScreen go={go} selected={selected} setSelected={setSelected} />}
          {route === 'energy' && <EnergyScreen go={go} />}
          {route === 'quality' && <QualityScreen go={go} />}
          {route === 'visit' && <VisitScreen go={go} sent={sent} setSent={setSent} toast={toast} />}
          {route === 'reports' && <ReportsScreen toast={toast} />}
          {route === 'files' && <p className="roof-hint"><Icon name="panel" size={16} />Your 36 panels light up here as we check them</p>}
        </main>
      </div>
      <div className="toast" role="status" aria-live="polite">{msg && <span key={msg}>{msg}</span>}</div>
    </div>
  )
}
