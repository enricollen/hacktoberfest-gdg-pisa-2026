import { useEffect, useRef, useState, type PointerEvent } from 'react'
import { AdminShell } from './AdminShell'
import { shopSlug } from './shop'

/** Shop analytics: STATIC demo with made-up numbers (single-series charts, hover tooltips). */

const STATS = [
  { label: 'Degustazioni questo mese', value: '128', delta: '+18% sul mese scorso' },
  { label: 'Valutazione media', value: '4,4', delta: 'su 5 · 1.024 voti' },
  { label: 'Profili di gusto raccolti', value: '342', delta: '+56 questo mese' },
  { label: 'Clienti tornati ad acquistare', value: '37%', delta: 'entro 30 giorni' },
]

const WEEKS = [
  { label: '3 ago', value: 42 },
  { label: '10 ago', value: 51 },
  { label: '17 ago', value: 48 },
  { label: '24 ago', value: 63 },
  { label: '31 ago', value: 70 },
  { label: '7 set', value: 66 },
  { label: '14 set', value: 81 },
  { label: '21 set', value: 94 },
  { label: '28 set', value: 88 },
  { label: '5 ott', value: 102 },
  { label: '12 ott', value: 117 },
  { label: '19 ott', value: 128 },
]

const RANKING = [
  { code: 'P12', name: 'Coppetta Fondente al Pistacchio', rating: 4.8, tastings: 96 },
  { code: 'P05', name: 'Pralina alla Nocciola', rating: 4.7, tastings: 112 },
  { code: 'P09', name: 'Pralina Fondente al Caramello', rating: 4.6, tastings: 88 },
  { code: 'P04', name: 'Tartufo al Cacao', rating: 4.5, tastings: 101 },
  { code: 'P08', name: 'Sfera Ruby', rating: 4.4, tastings: 74 },
  { code: 'P16', name: 'Pralina Caramello e Noci Pecan', rating: 4.3, tastings: 69 },
  { code: 'P07', name: "Rettangolo Fondente all'Arancia", rating: 4.2, tastings: 77 },
  { code: 'P10', name: 'Quadrotto al Latte e Caffè', rating: 4.0, tastings: 81 },
  { code: 'P06', name: 'Sfera Bianca al Cocco', rating: 3.8, tastings: 63 },
  { code: 'P15', name: 'Quadrotto Bianco Rigato', rating: 3.6, tastings: 58 },
]

const TASTES = [
  { label: 'Fondente', share: 46 },
  { label: 'Nocciola', share: 38 },
  { label: 'Pistacchio', share: 34 },
  { label: 'Al latte', share: 31 },
  { label: 'Frutti rossi', share: 22 },
  { label: 'Caramello', share: 21 },
  { label: 'Bianco', share: 18 },
  { label: 'Caffè', share: 12 },
]

const FEEDBACK = [
  { who: 'Giulia', when: '19 ott', code: 'P12', sweet: 'Coppetta Fondente al Pistacchio', rating: 5, text: 'Mi ha consigliato esattamente quello che avrei scelto io!' },
  { who: 'Marco', when: '18 ott', code: 'P05', sweet: 'Pralina alla Nocciola', rating: 5, text: 'Esperienza divertente, la rifaremo con gli amici.' },
  { who: 'Sara', when: '17 ott', code: 'P11', sweet: 'Cupola Bianca al Lampone', rating: 3, text: "Un po' troppo dolce per me, ma il consiglio successivo era perfetto." },
  { who: 'Luca', when: '15 ott', code: 'P04', sweet: 'Tartufo al Cacao', rating: 5, text: 'Intenso come piace a me, il maître ci ha preso in pieno.' },
  { who: 'Anna', when: '14 ott', code: 'P15', sweet: 'Quadrotto Bianco Rigato', rating: 2, text: 'Troppo dolce, preferisco il fondente.' },
  { who: 'Paolo', when: '12 ott', code: 'P08', sweet: 'Sfera Ruby', rating: 4, text: 'Non conoscevo il cioccolato ruby: sorprendente!' },
]

const fmt = (n: number) => n.toLocaleString('it-IT', { maximumFractionDigits: 1, minimumFractionDigits: 1 })

/* ---------------------------------------------------------------------------------------------- */

const M = { top: 16, right: 12, bottom: 32, left: 40 }

/** Drawn at the container's real pixel width, so labels stay 12 px on phones and desktops. */
function WeeklyLine() {
  const [hover, setHover] = useState<number | null>(null)
  const plotRef = useRef<HTMLDivElement>(null)
  const [W, setW] = useState(640)
  useEffect(() => {
    const el = plotRef.current
    if (!el) return
    const observer = new ResizeObserver(([entry]) => setW(Math.max(280, entry.contentRect.width)))
    observer.observe(el)
    return () => observer.disconnect()
  }, [])
  const H = W < 500 ? 220 : 280
  // Fewer date labels when narrow, so they never collide.
  const every = W < 500 ? 5 : 3
  const max = 140
  const x = (i: number) => M.left + (i / (WEEKS.length - 1)) * (W - M.left - M.right)
  const y = (v: number) => M.top + (1 - v / max) * (H - M.top - M.bottom)
  const path = WEEKS.map((d, i) => `${i ? 'L' : 'M'}${x(i)},${y(d.value)}`).join(' ')
  const area = `${path} L${x(WEEKS.length - 1)},${y(0)} L${x(0)},${y(0)} Z`

  const onMove = (e: PointerEvent<SVGSVGElement>) => {
    const box = e.currentTarget.getBoundingClientRect()
    const px = ((e.clientX - box.left) / box.width) * W
    const i = Math.round(((px - M.left) / (W - M.left - M.right)) * (WEEKS.length - 1))
    setHover(Math.max(0, Math.min(WEEKS.length - 1, i)))
  }

  const h = hover === null ? null : WEEKS[hover]
  return (
    <figure className="chart">
      <div className="chart__plot" ref={plotRef}>
        <svg
          viewBox={`0 0 ${W} ${H}`}
          width={W}
          height={H}
          className="chart__svg"
          role="img"
          aria-label="Degustazioni per settimana, da 42 a 128 nelle ultime 12 settimane"
          onPointerMove={onMove}
          onPointerLeave={() => setHover(null)}
        >
          {[0, 40, 80, 120].map((t) => (
            <g key={t}>
              <line x1={M.left} x2={W - M.right} y1={y(t)} y2={y(t)} className="chart__grid" />
              <text x={M.left - 8} y={y(t)} className="chart__tick" textAnchor="end" dominantBaseline="middle">
                {t}
              </text>
            </g>
          ))}
          {WEEKS.map((d, i) =>
            // Every `every` weeks, plus the latest one (skipping labels that would touch it).
            (i % every === 0 && WEEKS.length - 1 - i >= every / 2) || i === WEEKS.length - 1 ? (
              <text
                key={d.label}
                x={x(i)}
                y={H - 8}
                className="chart__tick"
                textAnchor={i === 0 ? 'start' : i === WEEKS.length - 1 ? 'end' : 'middle'}
              >
                {d.label}
              </text>
            ) : null,
          )}
          <path d={area} className="chart__area" />
          <path d={path} className="chart__line" />
          {/* Direct label on the latest value only. */}
          <circle cx={x(WEEKS.length - 1)} cy={y(WEEKS[WEEKS.length - 1].value)} r={4} className="chart__dot" />
          {hover !== null && h && (
            <g>
              <line x1={x(hover)} x2={x(hover)} y1={M.top} y2={y(0)} className="chart__crosshair" />
              <circle cx={x(hover)} cy={y(h.value)} r={5} className="chart__dot chart__dot--hover" />
            </g>
          )}
        </svg>
        {hover !== null && h && (
          <div
            className="chart__tooltip"
            style={{ left: `${(x(hover) / W) * 100}%`, top: `${(y(h.value) / H) * 100}%` }}
          >
            <strong>{h.value} degustazioni</strong>
            <span>settimana del {h.label}</span>
          </div>
        )}
      </div>
      <figcaption className="chart__caption">Ultimo dato: {WEEKS[WEEKS.length - 1].value} nella settimana del 19 ott</figcaption>
    </figure>
  )
}

function Ranking() {
  const slug = shopSlug()
  const [hover, setHover] = useState<string | null>(null)
  return (
    <ol className="ranking">
      {RANKING.map((r, i) => (
        <li
          key={r.code}
          className={`ranking__row${hover === r.code ? ' ranking__row--hover' : ''}`}
          onPointerEnter={() => setHover(r.code)}
          onPointerLeave={() => setHover(null)}
          title={`${r.name}: ${fmt(r.rating)} su 5, ${r.tastings} assaggi`}
        >
          <span className="ranking__pos">{i + 1}</span>
          <img className="ranking__img" src={`/media/${slug}/products/${r.code}.jpg`} alt="" loading="lazy" />
          <div className="ranking__body">
            <div className="ranking__head">
              <span className="ranking__name">{r.name}</span>
              <span className="ranking__value">
                {fmt(r.rating)} <span className="stars">★</span>
              </span>
            </div>
            {/* Bars start at 0: length is the average rating on a 0–5 scale. */}
            <div className="hbar" aria-hidden="true">
              <div className="hbar__fill" style={{ width: `${(r.rating / 5) * 100}%` }} />
            </div>
            <span className="ranking__meta">{r.tastings} assaggi</span>
          </div>
        </li>
      ))}
    </ol>
  )
}

function Tastes() {
  return (
    <ul className="tastes">
      {TASTES.map((t) => (
        <li key={t.label} className="tastes__row" title={`${t.label}: ${t.share}% dei profili`}>
          <span className="tastes__label">{t.label}</span>
          <div className="hbar" aria-hidden="true">
            <div className="hbar__fill" style={{ width: `${t.share * 2}%` }} />
          </div>
          <span className="tastes__value">{t.share}%</span>
        </li>
      ))}
    </ul>
  )
}

type Filter = 'all' | 'positive' | 'improve'

function Feedback() {
  const slug = shopSlug()
  const [filter, setFilter] = useState<Filter>('all')
  const shown = FEEDBACK.filter((f) =>
    filter === 'all' ? true : filter === 'positive' ? f.rating >= 4 : f.rating <= 3,
  )
  const chips: { id: Filter; label: string }[] = [
    { id: 'all', label: `Tutti (${FEEDBACK.length})` },
    { id: 'positive', label: 'Positivi' },
    { id: 'improve', label: 'Da migliorare' },
  ]
  return (
    <>
      <div className="filters" role="group" aria-label="Filtra i commenti">
        {chips.map((c) => (
          <button
            key={c.id}
            type="button"
            className={`filter${filter === c.id ? ' filter--active' : ''}`}
            aria-pressed={filter === c.id}
            onClick={() => setFilter(c.id)}
          >
            {c.label}
          </button>
        ))}
      </div>
      <ul className="feedback">
        {shown.map((f) => (
          <li key={f.who + f.when} className="feedback__item">
            <img className="feedback__img" src={`/media/${slug}/products/${f.code}.jpg`} alt="" loading="lazy" />
            <div className="feedback__body">
              <div className="feedback__head">
                <strong>{f.who}</strong>
                <span className="stars" aria-label={`${f.rating} su 5`}>
                  {'★'.repeat(f.rating)}
                  <span className="stars__empty">{'★'.repeat(5 - f.rating)}</span>
                </span>
              </div>
              <p className="feedback__text">«{f.text}»</p>
              <span className="feedback__meta">
                {f.sweet} · {f.when}
              </span>
            </div>
          </li>
        ))}
      </ul>
    </>
  )
}

export function AnalyticsPage() {
  return (
    <AdminShell tab="analytics">
      <div className="admin__grid">
        <section className="panel panel--wide" aria-label="Numeri chiave">
          <div className="stats stats--wide">
            {STATS.map((s) => (
              <div key={s.label} className="stat">
                <span className="stat__value">{s.value}</span>
                <span className="stat__label">{s.label}</span>
                <span className="stat__delta">{s.delta}</span>
              </div>
            ))}
          </div>
        </section>

        <section className="panel panel--wide" aria-labelledby="trend-title">
          <h2 id="trend-title" className="panel__title">
            Degustazioni per settimana
          </h2>
          <WeeklyLine />
        </section>

        <section className="panel" aria-labelledby="ranking-title">
          <h2 id="ranking-title" className="panel__title">
            Le praline più apprezzate
          </h2>
          <p className="panel__hint">Voto medio dato dai clienti a fine assaggio.</p>
          <Ranking />
        </section>

        <div className="admin__col">
          <section className="panel" aria-labelledby="tastes-title">
            <h2 id="tastes-title" className="panel__title">
              Gusti più richiesti
            </h2>
            <p className="panel__hint">Quota di profili di gusto che li citano.</p>
            <Tastes />
          </section>

          <section className="panel" aria-labelledby="feedback-title">
            <h2 id="feedback-title" className="panel__title">
              Feedback dei clienti
            </h2>
            <Feedback />
          </section>
        </div>
      </div>
    </AdminShell>
  )
}
