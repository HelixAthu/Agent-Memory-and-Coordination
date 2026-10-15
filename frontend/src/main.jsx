import React, { useState } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'

const Icon = ({ name, size = 16, strokeWidth = 1.8 }) => {
  const paths = {
    activity: <><path d="M3 12h3l2-8 4 16 2-8h4" /></>,
    chevron: <path d="m6 9 6 6 6-6" />,
    database: <><ellipse cx="12" cy="5" rx="7.5" ry="3" /><path d="M4.5 5v7c0 1.7 3.4 3 7.5 3s7.5-1.3 7.5-3V5" /><path d="M4.5 12v7c0 1.7 3.4 3 7.5 3s7.5-1.3 7.5-3v-7" /></>,
    git: <><circle cx="6" cy="6" r="2.5" /><circle cx="18" cy="6" r="2.5" /><circle cx="12" cy="18" r="2.5" /><path d="M8.3 7.3 10 9a2.8 2.8 0 0 1 .8 2V15M15.7 7.3 14 9a2.8 2.8 0 0 0-.8 2V15" /></>,
    grid: <><rect x="4" y="4" width="6" height="6" rx="1" /><rect x="14" y="4" width="6" height="6" rx="1" /><rect x="4" y="14" width="6" height="6" rx="1" /><rect x="14" y="14" width="6" height="6" rx="1" /></>,
    layers: <><path d="m12 3 8 4-8 4-8-4 8-4Z" /><path d="m4 12 8 4 8-4M4 17l8 4 8-4" /></>,
    minus: <path d="M5 12h14" />,
    plus: <><path d="M12 5v14M5 12h14" /></>,
    refresh: <><path d="M20 11a8.1 8.1 0 0 0-14.8-3L3 11" /><path d="M3 5v6h6M4 13a8.1 8.1 0 0 0 14.8 3L21 13" /><path d="M21 19v-6h-6" /></>,
    send: <><path d="m21 3-7.5 18-3.7-7.8L2 9.5 21 3Z" /><path d="M9.8 13.2 21 3" /></>,
    settings: <><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1-1.8 1.8-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.6v.2h-2.6V20a1.7 1.7 0 0 0-1-1.6 1.7 1.7 0 0 0-1.9.3l-.1.1-1.8-1.8.1-.1a1.7 1.7 0 0 0 .3-1.9 1.7 1.7 0 0 0-1.6-1H6v-2.6h.4a1.7 1.7 0 0 0 1.6-1 1.7 1.7 0 0 0-.3-1.9l-.1-.1 1.8-1.8.1.1a1.7 1.7 0 0 0 1.9.3 1.7 1.7 0 0 0 1-1.6V5H15v.4a1.7 1.7 0 0 0 1 1.6 1.7 1.7 0 0 0 1.9-.3l.1-.1 1.8 1.8-.1.1a1.7 1.7 0 0 0-.3 1.9 1.7 1.7 0 0 0 1.6 1h.4V14H21a1.7 1.7 0 0 0-1.6 1Z" /></>,
    spark: <><path d="m12 2 1.4 6.6L20 10l-6.6 1.4L12 18l-1.4-6.6L4 10l6.6-1.4L12 2ZM19 16l.6 2.4L22 19l-2.4.6L19 22l-.6-2.4L16 19l2.4-.6L19 16Z" /></>,
  }
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round">{paths[name]}</svg>
}

const agents = [
  { name: 'DevOps-Agent', role: 'Incident response', color: 'blue', initials: 'DO' },
  { name: 'DB-Agent', role: 'Data integrity', color: 'violet', initials: 'DB' },
  { name: 'Security-Agent', role: 'Threat analysis', color: 'rose', initials: 'SA' },
]

const initialLogs = [
  { time: '14:32:08', tone: 'blue', text: 'Incident received — beginning triage' },
  { time: '14:32:09', tone: 'slate', text: 'DevOps-Agent indexed 4 related memories' },
  { time: '14:32:11', tone: 'amber', text: 'Handoff queued to DB-Agent' },
  { time: '14:32:14', tone: 'emerald', text: 'Runbook match found: database-connection-pool' },
]

function App() {
  const [role, setRole] = useState('DevOps-Agent')
  const [incident, setIncident] = useState('ERROR: connection pool exhausted\\nservice=checkout-api  latency=842ms\\nactive_connections=100/100')
  const [logs, setLogs] = useState(initialLogs)
  const [processing, setProcessing] = useState(false)
  const [showLogs, setShowLogs] = useState(true)
  const [showMemory, setShowMemory] = useState(true)
  const [showHandoffs, setShowHandoffs] = useState(true)
  const [zoom, setZoom] = useState(1)

  const dispatch = () => {
    if (processing || !incident.trim()) return
    setProcessing(true)
    setLogs((current) => [...current, { time: '14:32:18', tone: 'blue', text: `${role} dispatched with incident context` }])
    window.setTimeout(() => {
      setProcessing(false)
      setLogs((current) => [...current, { time: '14:32:21', tone: 'emerald', text: 'Swarm context assembled — awaiting next action' }])
    }, 1200)
  }

  return (
    <div className="min-h-screen bg-[#090b10] text-slate-100">
      <header className="border-b border-slate-800/90 bg-[#0b0e14]/95">
        <div className="mx-auto flex max-w-[1600px] items-center justify-between gap-6 px-5 py-4 lg:px-8">
          <div className="flex items-center gap-7">
            <div className="flex items-center gap-3">
              <div className="brand-mark"><Icon name="git" size={20} /></div>
              <div><h1 className="text-[15px] font-semibold tracking-tight text-slate-100">SwarmGraph <span className="text-blue-400">AI</span></h1><p className="font-mono text-[9px] uppercase tracking-[0.19em] text-slate-500">Command center</p></div>
            </div>
            <div className="hidden h-7 w-px bg-slate-800 md:block" />
            <div className="hidden items-center gap-2 text-xs text-slate-400 sm:flex"><span className="status-dot" /> FalkorDB Connected <span className="ml-1 text-slate-600">·</span> <span className="font-mono text-[10px] text-slate-500">us-east-1</span></div>
          </div>
          <div className="hidden items-center gap-8 md:flex">
            <Metric label="Active agents" value="08" tone="blue" />
            <Metric label="Memory nodes" value="12,847" />
            <Metric label="Active handoffs" value="03" tone="amber" />
            <button className="icon-button" aria-label="Settings"><Icon name="settings" /></button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-[1600px] px-5 py-6 lg:px-8">
        <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
          <div><p className="eyebrow">Operations / Live topology</p><h2 className="mt-1 text-2xl font-semibold tracking-tight">Agent memory graph</h2><p className="mt-1 text-sm text-slate-500">Observe, coordinate, and dispatch autonomous agent workflows.</p></div>
          <div className="flex items-center gap-2 rounded-md border border-slate-800 bg-slate-900/40 px-3 py-2 text-xs text-slate-400"><span className="status-dot bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,.45)]" /> All systems operational <span className="ml-2 font-mono text-[10px] text-slate-600">Updated just now</span></div>
        </div>
        <div className="grid gap-5 xl:grid-cols-[360px_minmax(0,1fr)]">
          <aside className="space-y-5">
            <section className="panel overflow-hidden">
              <div className="border-b border-slate-800 px-5 py-4"><div className="flex items-center gap-2"><span className="text-blue-400"><Icon name="spark" size={17} /></span><h3 className="text-sm font-semibold">Incident simulator</h3></div><p className="mt-1 text-xs text-slate-500">Inject a production signal into the swarm.</p></div>
              <div className="space-y-4 p-5">
                <label className="field-label">Production error log<textarea value={incident} onChange={(event) => setIncident(event.target.value)} className="input mt-2 min-h-[118px] resize-none font-mono text-[11px] leading-5" /></label>
                <label className="field-label">Primary agent role<select value={role} onChange={(event) => setRole(event.target.value)} className="input mt-2 appearance-none"><option>DevOps-Agent</option><option>DB-Agent</option><option>Security-Agent</option></select></label>
                <button onClick={dispatch} className="primary-button w-full">{processing ? <><span className="spinner" /> Building swarm context...</> : <><Icon name="send" size={15} /> Dispatch Agent Swarm</>}</button>
                <p className="text-center font-mono text-[10px] text-slate-600">Estimated response time · 1.2s</p>
              </div>
            </section>
            <section className="panel">
              <button onClick={() => setShowLogs(!showLogs)} className="flex w-full items-center justify-between px-5 py-4 text-left"><div className="flex items-center gap-2"><span className="text-emerald-400"><Icon name="activity" size={16} /></span><h3 className="text-sm font-semibold">Live reasoning stream</h3><span className="rounded bg-emerald-400/10 px-1.5 py-0.5 font-mono text-[9px] text-emerald-400">LIVE</span></div><span className={`text-slate-500 transition-transform ${showLogs ? 'rotate-180' : ''}`}><Icon name="chevron" size={15} /></span></button>
              {showLogs && <div className="border-t border-slate-800 px-5 py-3">{logs.map((log, index) => <div className="log-row" key={`${log.time}-${index}`}><span className="font-mono text-[10px] text-slate-600">{log.time}</span><span className={`log-dot log-tone-${log.tone}`} /><span className="text-[11px] text-slate-400">{log.text}</span></div>)}<div className="mt-2 flex items-center gap-2 font-mono text-[10px] text-slate-600"><span className="pulse-line" /> stream connected</div></div>}
            </section>
          </aside>

          <section className="panel flex min-h-[650px] flex-col overflow-hidden">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800 px-5 py-3">
              <div className="flex items-center gap-2"><span className="eyebrow !text-slate-500">Topology</span><span className="text-slate-700">/</span><span className="font-mono text-[11px] text-slate-400">swarm-production</span></div>
              <div className="flex items-center gap-1">
                <button className="toolbar-button" onClick={() => setZoom((value) => Math.max(.7, value - .1))}><Icon name="minus" size={14} /></button><span className="w-10 text-center font-mono text-[10px] text-slate-500">{Math.round(zoom * 100)}%</span><button className="toolbar-button" onClick={() => setZoom((value) => Math.min(1.4, value + .1))}><Icon name="plus" size={14} /></button>
                <span className="mx-2 h-4 w-px bg-slate-800" /><button className="toolbar-button gap-1.5 px-2.5" onClick={() => setZoom(1)}><Icon name="refresh" size={13} /> Reset</button>
                <span className="mx-2 h-4 w-px bg-slate-800" />
                <button className={`toggle-button ${showMemory ? 'active' : ''}`} onClick={() => setShowMemory(!showMemory)}><span className="legend-dot bg-blue-400" /> Memory</button>
                <button className={`toggle-button ${showHandoffs ? 'active' : ''}`} onClick={() => setShowHandoffs(!showHandoffs)}><span className="legend-dot bg-amber-400" /> Handoffs</button>
              </div>
            </div>
            <div className="graph-stage relative flex-1 overflow-hidden">
              <div className="graph-grid absolute inset-0" />
              <div className="absolute left-5 top-5 z-10 rounded border border-slate-800 bg-[#0d1119]/90 px-3 py-2 shadow-xl"><p className="font-mono text-[9px] uppercase tracking-widest text-slate-600">Graph namespace</p><p className="mt-1 text-xs text-slate-300">production / shared-memory</p></div>
              <div className="absolute bottom-5 left-5 z-10 flex items-center gap-4 rounded border border-slate-800 bg-[#0d1119]/90 px-3 py-2 font-mono text-[9px] text-slate-500"><span className="flex items-center gap-1.5"><span className="legend-dot bg-blue-400" /> Memory node</span><span className="flex items-center gap-1.5"><span className="legend-line bg-amber-400" /> Handoff</span><span className="flex items-center gap-1.5"><span className="legend-dot bg-emerald-400" /> Active agent</span></div>
              <Graph zoom={zoom} showMemory={showMemory} showHandoffs={showHandoffs} />
            </div>
            <div className="flex items-center justify-between border-t border-slate-800 px-5 py-3"><div className="flex items-center gap-5 font-mono text-[10px] text-slate-500"><span>Nodes <b className="font-medium text-slate-300">{showMemory ? '24' : '8'}</b></span><span>Edges <b className="font-medium text-slate-300">{showHandoffs ? '31' : '19'}</b></span><span>Last sync <b className="font-medium text-slate-300">2s ago</b></span></div><span className="font-mono text-[10px] text-slate-600">drag to pan · scroll to zoom</span></div>
          </section>
        </div>
      </main>
    </div>
  )
}

function Metric({ label, value, tone }) { return <div><p className="mb-1 text-[10px] uppercase tracking-wider text-slate-600">{label}</p><p className={`font-mono text-sm ${tone === 'blue' ? 'text-blue-400' : tone === 'amber' ? 'text-amber-400' : 'text-slate-200'}`}>{value}</p></div> }

function Graph({ zoom, showMemory, showHandoffs }) {
  const nodes = [
    { id: 'core', x: 50, y: 48, label: 'Swarm Orchestrator', type: 'core' },
    { id: 'dev', x: 25, y: 28, label: 'DevOps-Agent', type: 'agent', color: 'emerald' },
    { id: 'db', x: 74, y: 26, label: 'DB-Agent', type: 'agent', color: 'blue' },
    { id: 'sec', x: 76, y: 70, label: 'Security-Agent', type: 'agent', color: 'violet' },
    { id: 'incident', x: 27, y: 72, label: 'INC-2847', type: 'incident', color: 'rose' },
    { id: 'memory1', x: 13, y: 47, label: 'checkout-api', type: 'memory' },
    { id: 'memory2', x: 48, y: 20, label: 'pool exhaustion', type: 'memory' },
    { id: 'memory3', x: 91, y: 47, label: 'runbook v2.4', type: 'memory' },
    { id: 'memory4', x: 49, y: 80, label: 'postgres-primary', type: 'memory' },
  ]
  const edges = [['core', 'dev'], ['core', 'db'], ['core', 'sec'], ['core', 'incident'], ['dev', 'memory1'], ['db', 'memory2'], ['sec', 'memory3'], ['incident', 'memory4']]
  const byId = Object.fromEntries(nodes.map((node) => [node.id, node]))
  return <div className="absolute inset-0 flex items-center justify-center" style={{ transform: `scale(${zoom})`, transition: 'transform .2s ease' }}><div className="relative h-[78%] w-[86%] min-w-[560px]">
    <svg className="absolute inset-0 h-full w-full overflow-visible">{edges.map(([from, to]) => {
      const isHandoff = from === 'core' || from === 'incident'
      if (isHandoff && !showHandoffs) return null
      return <line key={`${from}-${to}`} x1={`${byId[from].x}%`} y1={`${byId[from].y}%`} x2={`${byId[to].x}%`} y2={`${byId[to].y}%`} className={isHandoff ? 'edge handoff-edge' : 'edge'} />
    })}</svg>
    {nodes.map((node) => (node.type === 'memory' && !showMemory ? null : <div key={node.id} className={`graph-node node-${node.type} node-${node.color || ''}`} style={{ left: `${node.x}%`, top: `${node.y}%` }}><div className="node-dot" /><span>{node.label}</span>{node.type === 'agent' && <small>online</small>}</div>))}
  </div></div>
}

createRoot(document.getElementById('root')).render(<App />)
