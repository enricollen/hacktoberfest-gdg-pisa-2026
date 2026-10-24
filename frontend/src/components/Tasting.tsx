import { useState, type FormEvent } from 'react'
import type { Recognition } from '../api'
import type { useTastingVoice } from '../hooks/useTastingVoice'
import { BoxView } from './BoxView'
import { Orb } from './Orb'
import { ProfileToast } from './ProfileToast'
import { Summary } from './Summary'

type Voice = ReturnType<typeof useTastingVoice>

interface Props {
  voice: Voice
  recognition: Recognition
  photoUrl: string
}

const STATUS_TEXT = {
  idle: 'Premi Parla per rispondere',
  thinking: 'Il maître ci sta pensando…',
  speaking: 'Il maître sta parlando',
  listening: 'Ti ascolto…',
} as const

const MicIcon = () => (
  <svg viewBox="0 0 24 24" aria-hidden="true" className="icon">
    <path d="M12 15a3 3 0 0 0 3-3V6a3 3 0 1 0-6 0v6a3 3 0 0 0 3 3Zm5-3a5 5 0 0 1-10 0H5a7 7 0 0 0 6 6.92V21h2v-2.08A7 7 0 0 0 19 12h-2Z" />
  </svg>
)
const StopIcon = () => (
  <svg viewBox="0 0 24 24" aria-hidden="true" className="icon">
    <rect x="6" y="6" width="12" height="12" rx="2" />
  </svg>
)
const ReplayIcon = () => (
  <svg viewBox="0 0 24 24" aria-hidden="true" className="icon">
    <path d="M12 5V2L7 6l5 4V7a5 5 0 1 1-5 5H5a7 7 0 1 0 7-7Z" />
  </svg>
)
const KeyboardIcon = () => (
  <svg viewBox="0 0 24 24" aria-hidden="true" className="icon">
    <path d="M20 6H4a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2ZM8 9h2v2H8V9Zm0 3h2v2H8v-2ZM5 9h2v2H5V9Zm0 3h2v2H5v-2Zm11 4H8v-1h8v1Zm0-4h-2v-2h2v2Zm0-3h-2V9h2v2Zm3 3h-2v-2h2v2Zm0-3h-2V9h2v2Z" />
  </svg>
)

export function Tasting({ voice, recognition, photoUrl }: Props) {
  const [typing, setTyping] = useState(false)
  const [draft, setDraft] = useState('')
  const [confirmEnd, setConfirmEnd] = useState(false)
  const { conversation: conv, voiceState } = voice
  const done = conv?.phase === 'done'
  const eaten = conv?.items.filter((i) => i.status === 'eaten').length ?? 0

  const submit = (e: FormEvent) => {
    e.preventDefault()
    const text = draft.trim()
    if (!text) return
    voice.sendText(text)
    setDraft('')
  }

  return (
    <section className="tasting" aria-label="Degustazione">
      <div className="tasting__box">
        <BoxView
          photoUrl={photoUrl}
          recognition={recognition}
          items={conv?.items}
          highlight={conv?.speaking_to}
        />
        {conv && (
          <p className="tasting__progress">
            {eaten}/{conv.items.length} dolcetti assaggiati
          </p>
        )}
      </div>

      <Orb state={done ? 'idle' : voiceState} levelRef={voice.levelRef} size={done ? 120 : 170} />

      <div className="subtitles" aria-live="polite">
        {conv && <p className="subtitles__agent">{conv.reply}</p>}
        {voiceState === 'listening' && <p className="subtitles__user">{voice.partial || '…'}</p>}
        {voiceState === 'thinking' && voice.lastUserText && (
          <p className="subtitles__user subtitles__user--sent">«{voice.lastUserText}»</p>
        )}
      </div>

      {!done && <ProfileToast conversation={conv} voiceState={voiceState} />}

      {voice.error && (
        <p className="notice" role="alert">
          {voice.error}
        </p>
      )}

      {!done && (
        <>
          <p className="status-line">{STATUS_TEXT[voiceState]}</p>
          <div className="controls">
            <button
              className="icon-btn"
              onClick={voice.replay}
              disabled={!conv || voiceState === 'thinking'}
              aria-label="Riascolta"
              title="Riascolta"
            >
              <ReplayIcon />
            </button>
            <button
              className={`talk-btn${voiceState === 'listening' ? ' talk-btn--active' : ''}`}
              onPointerDown={voice.talkPress}
              onPointerUp={voice.talkRelease}
              onPointerLeave={(e) => e.buttons && voice.talkRelease()}
              onContextMenu={(e) => e.preventDefault()}
              disabled={!conv || voiceState === 'thinking'}
              aria-label="Parla (tieni premuto per parlare)"
            >
              <MicIcon />
              <span>Parla</span>
            </button>
            <button
              className="icon-btn icon-btn--stop"
              onClick={voice.stop}
              disabled={voiceState !== 'speaking' && voiceState !== 'listening'}
              aria-label="Stop"
              title="Stop"
            >
              <StopIcon />
            </button>
          </div>

          <div className="options">
            <label className="switch">
              <input
                type="checkbox"
                checked={voice.autoListen}
                onChange={(e) => voice.setAutoListen(e.target.checked)}
              />
              <span>Ascolto automatico</span>
            </label>
            <button className="link-btn" onClick={() => setTyping((t) => !t)} aria-expanded={typing}>
              <KeyboardIcon /> Scrivi
            </button>
          </div>

          {typing && (
            <form className="type-form" onSubmit={submit}>
              <input
                className="type-form__input"
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                placeholder="Scrivi la tua risposta…"
                aria-label="Risposta scritta"
                disabled={voiceState === 'thinking'}
              />
              <button className="btn btn--primary" type="submit" disabled={voiceState === 'thinking'}>
                Invia
              </button>
            </form>
          )}

          {conv && conv.participants.length > 0 && (
            <ul className="people" aria-label="Partecipanti">
              {conv.participants.map((p) => (
                <li
                  key={p.name}
                  className={`person${conv.speaking_to === p.name ? ' person--active' : ''}`}
                  title={p.profile}
                >
                  <span className="person__name">{p.name}</span>
                  <span className="person__count">{p.tasted.length} 🍫</span>
                </li>
              ))}
            </ul>
          )}
        </>
      )}

      {!done && conv && (
        <div className="end-bar">
          {confirmEnd ? (
            <>
              <span className="end-bar__ask">Concludere adesso la degustazione?</span>
              <button className="btn btn--primary btn--small" onClick={() => void voice.endTasting()}>
                Sì, concludi
              </button>
              <button className="btn btn--ghost btn--small" onClick={() => setConfirmEnd(false)}>
                Continua
              </button>
            </>
          ) : (
            <button className="link-btn" onClick={() => setConfirmEnd(true)}>
              Concludi degustazione
            </button>
          )}
        </div>
      )}

      {done && conv && <Summary conversation={conv} recognition={recognition} />}
    </section>
  )
}
