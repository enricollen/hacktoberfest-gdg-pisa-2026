import { useState, type FormEvent } from 'react'
import { shopSlug } from './shop'

/** Simulated shop owner login: credentials are prefilled, "Accedi" just opens the console. */
export function LoginPage() {
  const slug = shopSlug()
  const [busy, setBusy] = useState(false)

  const login = (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    window.setTimeout(() => window.location.assign(`/s/${slug}/admin`), 700)
  }

  return (
    <div className="login">
      <a className="admin__back login__back" href={`/s/${slug}`}>
        ← Esperienza cliente
      </a>
      <form className="login__card" onSubmit={login}>
        <img className="login__logo" src={`/media/${slug}/logo.svg`} alt="Logo del negozio" />
        <h1 className="login__title">Area negozio</h1>
        <p className="login__hint">Accedi per configurare l'esperienza e vedere le analytics.</p>
        <label className="field">
          <span>Email</span>
          <input type="email" defaultValue="titolare@gemmacacao.it" autoComplete="username" />
        </label>
        <label className="field">
          <span>Password</span>
          <input type="password" defaultValue="cioccolato2026" autoComplete="current-password" />
        </label>
        <label className="login__remember">
          <input type="checkbox" defaultChecked /> Ricordami su questo dispositivo
        </label>
        <button className="btn btn--primary login__submit" type="submit" disabled={busy}>
          {busy ? 'Accesso in corso…' : 'Accedi'}
        </button>
        <p className="login__demo">Accesso simulato per la demo: le credenziali sono già compilate.</p>
      </form>
    </div>
  )
}
