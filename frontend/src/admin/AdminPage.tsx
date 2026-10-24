import { useState, type FormEvent } from 'react'
import { AdminShell } from './AdminShell'
import { shopSlug } from './shop'

/**
 * Shop owner console: a STATIC mock-up for the demo. Fields can be typed into but nothing is
 * saved (customer insights live in AnalyticsPage). It shows that the same recognize → profile → recommend loop fits any food & drink
 * business (wine bars, cheese shops, roasters...) by swapping vocabulary and catalog.
 */

interface Vertical {
  id: string
  label: string
  icon: string
  guide: string
  item: string
  items: string
  box: string
  attributes: string[]
  questions: string[]
  products: { name: string; description: string; tags: string[]; allergens: string; image?: string }[]
}

const VERTICALS: Vertical[] = [
  {
    id: 'cioccolateria',
    label: 'Cioccolateria',
    icon: '🍫',
    guide: 'maître chocolatier',
    item: 'pralina',
    items: 'praline',
    box: 'Scatola degustazione 16 praline',
    attributes: ['Tipo di cioccolato', 'Ripieno', 'Frutta secca', 'Note di degustazione'],
    questions: ['Fondente, al latte o bianco?', 'Ti piace la frutta secca?', 'Hai allergie o intolleranze?'],
    products: [
      { name: 'Cupola Fondente', description: 'Guscio lucido, ganache fondente 70%.', tags: ['fondente', 'ganache'], allergens: 'soia, latte (tracce)', image: '/media/demo/products/P01.jpg' },
      { name: 'Pralina alla Nocciola', description: 'Gianduia e nocciola Piemonte IGP tostata.', tags: ['latte', 'nocciola'], allergens: 'latte, frutta a guscio', image: '/media/demo/products/P05.jpg' },
      { name: 'Sfera Ruby', description: 'Cioccolato ruby, fruttato e acidulo.', tags: ['ruby', 'frutti rossi'], allergens: 'latte, soia', image: '/media/demo/products/P08.jpg' },
      { name: 'Coppetta al Pistacchio', description: 'Crema di pistacchio di Bronte DOP.', tags: ['fondente', 'pistacchio'], allergens: 'frutta a guscio', image: '/media/demo/products/P12.jpg' },
    ],
  },
  {
    id: 'enoteca',
    label: 'Enoteca / vineria',
    icon: '🍷',
    guide: 'sommelier',
    item: 'vino',
    items: 'vini',
    box: 'Kit degustazione 6 calici',
    attributes: ['Vitigno', 'Annata', 'Regione', 'Gradazione', 'Abbinamenti'],
    questions: ['Rossi, bianchi o bollicine?', 'Preferisci vini strutturati o freschi?', 'Che cosa mangerai?'],
    products: [
      { name: 'Chianti Classico 2021', description: 'Sangiovese, ciliegia e viola, tannino morbido.', tags: ['rosso', 'sangiovese'], allergens: 'solfiti' },
      { name: 'Vermentino di Bolgheri', description: 'Fresco e sapido, note di agrumi e macchia.', tags: ['bianco', 'vermentino'], allergens: 'solfiti' },
      { name: 'Brunello di Montalcino 2018', description: 'Strutturato, frutti scuri e spezie dolci.', tags: ['rosso', 'invecchiato'], allergens: 'solfiti' },
      { name: 'Franciacorta Brut', description: 'Bollicine fini, crosta di pane e mela.', tags: ['bollicine', 'chardonnay'], allergens: 'solfiti' },
    ],
  },
  {
    id: 'caseificio',
    label: 'Caseificio / formaggi',
    icon: '🧀',
    guide: 'affinatore',
    item: 'formaggio',
    items: 'formaggi',
    box: 'Tagliere degustazione 8 formaggi',
    attributes: ['Latte', 'Stagionatura', 'Pasta', 'Abbinamenti'],
    questions: ['Formaggi freschi o stagionati?', 'Vaccino, ovino o caprino?', 'Ami gli erborinati?'],
    products: [
      { name: 'Pecorino Toscano DOP', description: 'Stagionato 6 mesi, note di nocciola.', tags: ['ovino', 'stagionato'], allergens: 'latte' },
      { name: 'Gorgonzola dolce', description: 'Cremoso, erborinato delicato.', tags: ['vaccino', 'erborinato'], allergens: 'latte' },
      { name: 'Parmigiano Reggiano 30 mesi', description: 'Cristalli croccanti, brodo e frutta secca.', tags: ['vaccino', 'stagionato'], allergens: 'latte' },
      { name: 'Caprino fresco alle erbe', description: 'Morbido e acidulo, erbe aromatiche.', tags: ['caprino', 'fresco'], allergens: 'latte' },
    ],
  },
  {
    id: 'torrefazione',
    label: 'Torrefazione / caffè',
    icon: '☕',
    guide: 'barista',
    item: 'caffè',
    items: 'caffè',
    box: 'Box assaggio 5 monorigine',
    attributes: ['Origine', 'Tostatura', 'Processo', 'Note aromatiche'],
    questions: ['Espresso o filtro?', 'Lo preferisci intenso o fruttato?', 'Lo bevi con il latte?'],
    products: [
      { name: 'Etiopia Yirgacheffe', description: 'Lavato, floreale con note di bergamotto.', tags: ['chiaro', 'floreale'], allergens: '-' },
      { name: 'Brasile Cerrado', description: 'Naturale, cioccolato e nocciola.', tags: ['medio', 'cioccolato'], allergens: '-' },
      { name: 'Colombia Huila', description: 'Equilibrato, caramello e frutti rossi.', tags: ['medio', 'fruttato'], allergens: '-' },
      { name: 'Miscela Napoli', description: 'Tostatura scura, corposa e cremosa.', tags: ['scuro', 'intenso'], allergens: '-' },
    ],
  },
  {
    id: 'birrificio',
    label: 'Birrificio artigianale',
    icon: '🍺',
    guide: 'mastro birraio',
    item: 'birra',
    items: 'birre',
    box: 'Cassetta degustazione 6 birre',
    attributes: ['Stile', 'Gradazione', 'IBU', 'Luppoli', 'Abbinamenti'],
    questions: ['Chiare, ambrate o scure?', 'Ti piace l\'amaro del luppolo?', 'Preferisci birre leggere o corpose?'],
    products: [
      { name: 'Blanche al coriandolo', description: 'Frumento, agrumi e spezie, beverina.', tags: ['chiara', 'leggera'], allergens: 'glutine' },
      { name: 'IPA Toscana', description: 'Luppoli americani, resina e pompelmo.', tags: ['ambrata', 'luppolata'], allergens: 'glutine' },
      { name: 'Stout al caffè', description: 'Tostata, cacao e caffè, cremosa.', tags: ['scura', 'tostata'], allergens: 'glutine' },
      { name: 'Saison', description: 'Secca e speziata, finale pepato.', tags: ['chiara', 'speziata'], allergens: 'glutine' },
    ],
  },
]

/** Decorative QR-like pattern (not a real QR code). */
function FakeQr({ seed }: { seed: string }) {
  const cells: boolean[] = []
  let h = 0
  for (const ch of seed) h = (h * 31 + ch.charCodeAt(0)) >>> 0
  for (let i = 0; i < 21 * 21; i++) {
    h = (h * 1103515245 + 12345) >>> 0
    cells.push(((h >>> 16) & 1) === 1)
  }
  const finder = (x: number, y: number) =>
    (x < 7 && y < 7) || (x > 13 && y < 7) || (x < 7 && y > 13)
  return (
    <svg viewBox="0 0 21 21" className="fake-qr" role="img" aria-label="QR code dimostrativo">
      <rect width="21" height="21" fill="var(--bg-raised)" />
      {cells.map((on, i) => {
        const x = i % 21
        const y = Math.floor(i / 21)
        if (finder(x, y)) return null
        return on ? <rect key={i} x={x} y={y} width="1" height="1" fill="var(--text)" /> : null
      })}
      {[
        [0, 0],
        [14, 0],
        [0, 14],
      ].map(([x, y]) => (
        <g key={`${x}-${y}`}>
          <rect x={x} y={y} width="7" height="7" fill="var(--text)" />
          <rect x={x + 1} y={y + 1} width="5" height="5" fill="var(--bg-raised)" />
          <rect x={x + 2} y={y + 2} width="3" height="3" fill="var(--text)" />
        </g>
      ))}
    </svg>
  )
}

const withArticle = (noun: string) => (/^[aeiouàèéìòù]/i.test(noun) ? `L'${noun}` : `Il ${noun}`)

export function AdminPage() {
  const [verticalId, setVerticalId] = useState('cioccolateria')
  const [notice, setNotice] = useState<string | null>(null)
  const v = VERTICALS.find((x) => x.id === verticalId) ?? VERTICALS[0]
  const slug = shopSlug()

  const demoOnly = (e?: FormEvent) => {
    e?.preventDefault()
    setNotice('Anteprima dimostrativa: in questa versione nulla viene salvato.')
    window.setTimeout(() => setNotice(null), 3500)
  }

  return (
    <AdminShell tab="admin">
      <form className="admin__grid" onSubmit={demoOnly}>
        {/* 1. Business type */}
        <section className="panel panel--wide" aria-labelledby="vertical-title">
          <h2 id="vertical-title" className="panel__title">
            1 · Tipo di attività
          </h2>
          <p className="panel__hint">
            La stessa base (foto della confezione → riconoscimento → profili di gusto →
            consigli a voce) funziona per qualsiasi prodotto alimentare.
          </p>
          <div className="verticals" role="radiogroup" aria-label="Tipo di attività">
            {VERTICALS.map((x) => (
              <button
                key={x.id}
                type="button"
                role="radio"
                aria-checked={x.id === v.id}
                className={`vertical${x.id === v.id ? ' vertical--active' : ''}`}
                onClick={() => setVerticalId(x.id)}
              >
                <span className="vertical__icon" aria-hidden="true">
                  {x.icon}
                </span>
                <span className="vertical__label">{x.label}</span>
                <span className="vertical__guide">guida: {x.guide}</span>
              </button>
            ))}
          </div>
        </section>

        {/* 2. Shop identity */}
        <section className="panel" aria-labelledby="identity-title">
          <h2 id="identity-title" className="panel__title">
            2 · Identità del negozio
          </h2>
          <label className="field">
            <span>Nome del negozio</span>
            <input defaultValue="GemmaCacao" />
          </label>
          <label className="field">
            <span>Sottotitolo</span>
            <input key={v.id} defaultValue={`${v.label} artigianale`} />
          </label>
          <label className="field">
            <span>Indirizzo web (dal QR code)</span>
            <input defaultValue={`gemmacacao.app/s/${slug}`} />
          </label>
          <div className="field">
            <span>Logo</span>
            <div className="upload">Trascina qui il logo (SVG o PNG)</div>
          </div>
          <div className="field">
            <span>Colori</span>
            <div className="swatches">
              {['#f7f0e3', '#6d3b1e', '#4a2c1d', '#c58a4d'].map((c) => (
                <span key={c} className="swatch" style={{ background: c }} title={c} />
              ))}
            </div>
          </div>
        </section>

        {/* 3. Voice guide */}
        <section className="panel" aria-labelledby="guide-title">
          <h2 id="guide-title" className="panel__title">
            3 · La guida vocale
          </h2>
          <label className="field">
            <span>Nome della guida</span>
            <input key={v.id} defaultValue={`${withArticle(v.guide)} di GemmaCacao`} />
          </label>
          <label className="field">
            <span>Tono</span>
            <select defaultValue="gioviale">
              <option value="gioviale">Gioviale e simpatico</option>
              <option value="elegante">Elegante e raffinato</option>
              <option value="tecnico">Esperto e tecnico</option>
            </select>
          </label>
          <label className="field">
            <span>Voce</span>
            <select defaultValue="marco">
              <option value="marco">Marco · italiano, caldo</option>
              <option value="sami">Sami · italiana, avvolgente</option>
              <option value="valentina">Valentina · italiana, solare</option>
            </select>
          </label>
          <label className="field">
            <span>Lingue</span>
            <select defaultValue="it">
              <option value="it">Italiano</option>
              <option value="it-en">Italiano + inglese</option>
            </select>
          </label>
          <div className="field">
            <span>Domande per conoscere i gusti</span>
            <ul className="questions" key={v.id}>
              {v.questions.map((q) => (
                <li key={q}>
                  <input defaultValue={q} aria-label="Domanda" />
                </li>
              ))}
            </ul>
          </div>
        </section>

        {/* 4. Catalog */}
        <section className="panel panel--wide" aria-labelledby="catalog-title">
          <div className="panel__head">
            <h2 id="catalog-title" className="panel__title">
              4 · Catalogo {v.items}
            </h2>
            <button type="button" className="btn btn--primary btn--small" onClick={() => demoOnly()}>
              + Aggiungi {v.item}
            </button>
          </div>
          <p className="panel__hint">
            Per ogni {v.item}: una foto singola (per il riconoscimento con CLIP) e le
            caratteristiche che la guida usa per consigliare. Caratteristiche per questo tipo di
            attività: <em>{v.attributes.join(', ')}</em>.
          </p>
          <div className="catalog">
            {v.products.map((p) => (
              <article key={p.name} className="product">
                <div className="product__img" aria-hidden="true">
                  {p.image ? <img src={p.image} alt="" /> : <span>{v.icon}</span>}
                </div>
                <div className="product__body">
                  <input className="product__name" defaultValue={p.name} aria-label="Nome" />
                  <textarea
                    className="product__desc"
                    defaultValue={p.description}
                    rows={2}
                    aria-label="Descrizione"
                  />
                  <ul className="tags">
                    {p.tags.map((t) => (
                      <li key={t} className="tag">
                        {t}
                      </li>
                    ))}
                  </ul>
                  <p className="product__allergens">Allergeni: {p.allergens}</p>
                </div>
              </article>
            ))}
          </div>
          <div className="upload upload--wide">
            Oppure carica la foto della confezione aperta: i prodotti vengono ritagliati e
            riconosciuti in automatico.
          </div>
        </section>

        {/* 5. Boxes & QR */}
        <section className="panel panel--wide" aria-labelledby="box-title">
          <h2 id="box-title" className="panel__title">
            5 · Box e QR code
          </h2>
          <div className="box-row">
            <FakeQr seed={v.id + slug} />
            <div>
              <label className="field">
                <span>Nome della confezione</span>
                <input key={v.id} defaultValue={v.box} />
              </label>
              <label className="field">
                <span>Copie da stampare</span>
                <input type="number" defaultValue={200} min={1} />
              </label>
            </div>
          </div>
          <button type="button" className="btn btn--ghost btn--small" onClick={() => demoOnly()}>
            Scarica QR in PDF
          </button>
        </section>

        <div className="admin__actions">
          <button type="submit" className="btn btn--primary">
            Salva configurazione
          </button>
        </div>
      </form>

      {notice && (
        <div className="admin__toast" role="status">
          {notice}
        </div>
      )}
    </AdminShell>
  )
}
