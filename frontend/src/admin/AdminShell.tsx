import type { ReactNode } from 'react'
import { shopSlug } from './shop'

type AdminTab = 'admin' | 'analytics'

/** Header, tabs and "demo only" banner shared by the shop owner pages. */
export function AdminShell({ tab, children }: { tab: AdminTab; children: ReactNode }) {
  const slug = shopSlug()
  return (
    <div className="admin">
      <header className="admin__top">
        <a className="admin__back" href={`/s/${slug}`}>
          ← Esperienza cliente
        </a>
        <img className="admin__logo" src={`/media/${slug}/logo.svg`} alt="Logo del negozio" />
        <span className="admin__badge">Area negozio</span>
      </header>

      <nav className="admin__tabs" aria-label="Sezioni area negozio">
        <a
          className={`admin__tab${tab === 'admin' ? ' admin__tab--active' : ''}`}
          href={`/s/${slug}/admin`}
          aria-current={tab === 'admin' ? 'page' : undefined}
        >
          Configurazione
        </a>
        <a
          className={`admin__tab${tab === 'analytics' ? ' admin__tab--active' : ''}`}
          href={`/s/${slug}/analytics`}
          aria-current={tab === 'analytics' ? 'page' : undefined}
        >
          Analytics
        </a>
      </nav>

      <div className="admin__banner" role="note">
        <strong>Anteprima dimostrativa.</strong>{' '}
        {tab === 'admin'
          ? 'Così un negozio configurerebbe GemmaCacao: i campi si possono compilare, ma non sono collegati.'
          : 'Dati di esempio: grafici e commenti sono fittizi.'}
      </div>

      {children}
    </div>
  )
}
