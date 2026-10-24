import { useEffect, useState } from 'react'
import { api, ApiError, type Recognition, type Shop } from './api'
import { BoxView } from './components/BoxView'
import { Orb } from './components/Orb'
import { PeopleStep } from './components/PeopleStep'
import { PhotoStep } from './components/PhotoStep'
import { Tasting } from './components/Tasting'
import { useTastingVoice } from './hooks/useTastingVoice'
import { errorText, logEvent, setLogSession } from './log'

type Step = 'photo' | 'analyzing' | 'recognized' | 'people' | 'tasting'

const MAX_PEOPLE = 10

/** The QR code on the box opens /s/<shop-slug>; the bare root falls back to the demo shop. */
function shopSlugFromUrl(): string {
  const match = window.location.pathname.match(/^\/s\/([\w-]+)/)
  if (match) return match[1]
  window.history.replaceState(null, '', '/s/demo')
  return 'demo'
}

export default function App() {
  const [shop, setShop] = useState<Shop | null>(null)
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [step, setStep] = useState<Step>('photo')
  const [photoUrl, setPhotoUrl] = useState<string | null>(null)
  const [recognition, setRecognition] = useState<Recognition | null>(null)
  const [error, setError] = useState<string | null>(null)
  const voice = useTastingVoice(sessionId)

  useEffect(() => {
    let cancelled = false
    const slug = shopSlugFromUrl()
    api
      .createSession(slug)
      .then(({ session_id, shop }) => {
        if (cancelled) return
        setShop(shop)
        setSessionId(session_id)
        setLogSession(session_id)
        logEvent('info', 'session.created', { shop: shop.slug, ua: navigator.userAgent })
        document.title = 'GemmaCacao'
      })
      .catch((e) =>
        setError(e instanceof ApiError && e.status === 404 ? 'Negozio non trovato.' : 'Servizio non raggiungibile.'),
      )
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => () => {
    if (photoUrl) URL.revokeObjectURL(photoUrl)
  }, [photoUrl])

  const handlePhoto = async (photo: Blob) => {
    if (!sessionId) return
    setError(null)
    setPhotoUrl(URL.createObjectURL(photo))
    setStep('analyzing')
    try {
      const started = performance.now()
      const result = await api.uploadPhoto(sessionId, photo)
      logEvent('info', 'photo.recognized', {
        count: result.count,
        server_ms: result.elapsed_ms,
        total_ms: Math.round(performance.now() - started),
        bytes: photo.size,
      })
      if (result.count === 0) {
        setError('Non vedo dolcetti nella foto: riprova inquadrando la scatola aperta dall\'alto.')
        setStep('photo')
        return
      }
      setRecognition(result)
      setStep('recognized')
    } catch (e) {
      logEvent('error', 'photo.failed', { error: errorText(e) })
      setError(e instanceof ApiError ? e.message : 'Analisi non riuscita, riprova.')
      setStep('photo')
    }
  }

  const startTasting = (groupSize: number) => {
    setStep('tasting')
    void voice.start(groupSize)
  }

  const orbState = step === 'analyzing' ? 'thinking' : step === 'tasting' ? voice.voiceState : 'idle'

  return (
    <div className="app">
      {step === 'photo' && (
        <a className="admin-link" href={`/s/${shop?.slug ?? 'demo'}/login`}>
          <svg viewBox="0 0 24 24" aria-hidden="true" className="icon">
            <path d="M4 10h16v10H4V10Zm2-6h12l2 4H4l2-4Zm4 9v5h4v-5h-4Z" />
          </svg>
          Area negozio
        </a>
      )}
      <header className={`header${step === 'photo' || step === 'analyzing' ? ' header--home' : ''}`}>
        {shop?.logo_url ? (
          <img className="header__logo" src={shop.logo_url} alt={shop.name} />
        ) : (
          <span className="header__name">{shop?.name ?? ''}</span>
        )}
      </header>

      <main className={`main main--${step}`}>
        {step !== 'tasting' && (
          <Orb state={orbState} levelRef={voice.levelRef} size={step === 'recognized' ? 150 : 240} />
        )}

        {error && <p className="notice" role="alert">{error}</p>}

        {step === 'photo' && <PhotoStep onPhoto={handlePhoto} busy={!sessionId} />}

        {step === 'analyzing' && (
          <section className="step" aria-live="polite">
            <h1 className="step__title">Sto contando i dolcetti…</h1>
            {photoUrl && <img className="preview" src={photoUrl} alt="Foto della scatola" />}
          </section>
        )}

        {step === 'recognized' && recognition && photoUrl && (
          <section className="step" aria-labelledby="found-title">
            <h1 id="found-title" className="step__title">
              Ho trovato {recognition.count} dolcetti
            </h1>
            <BoxView photoUrl={photoUrl} recognition={recognition} />
            <h2 className="section-title">I cioccolatini della tua scatola</h2>
            <ul className="sweets" aria-label="Dolcetti riconosciuti">
              {recognition.items.map((it, n) => (
                <li key={it.item_id} className="sweet-card" style={{ animationDelay: `${n * 60}ms` }}>
                  {it.product.image_url && (
                    <img className="sweet-card__img" src={it.product.image_url} alt="" loading="lazy" />
                  )}
                  <div className="sweet-card__body">
                    <h3 className="sweet-card__name">{it.product.name}</h3>
                    <p className="sweet-card__desc">{it.product.description}</p>
                  </div>
                </li>
              ))}
            </ul>
            <div className="actions actions--sticky">
              <button className="btn btn--primary" onClick={() => setStep('people')}>
                Avanti
              </button>
              <button className="btn btn--ghost" onClick={() => setStep('photo')}>
                Rifai la foto
              </button>
            </div>
          </section>
        )}

        {step === 'people' && recognition && (
          <PeopleStep max={Math.min(MAX_PEOPLE, recognition.count)} onConfirm={startTasting} />
        )}

        {step === 'tasting' && recognition && photoUrl && (
          <Tasting voice={voice} recognition={recognition} photoUrl={photoUrl} />
        )}
      </main>
    </div>
  )
}
