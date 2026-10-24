import { useEffect, useState } from 'react'
import type { Conversation, ProfileUpdate } from '../api'
import type { VoiceState } from '../hooks/useTastingVoice'

interface Props {
  conversation: Conversation | null
  voiceState: VoiceState
}

const SHOW_MS = 4500

/**
 * Makes profile bookkeeping visible: a "taking notes" card while the agent processes an answer,
 * then a "profile saved" card with what was understood.
 */
export function ProfileToast({ conversation, voiceState }: Props) {
  // The card belongs to the latest reply; the timer only dismisses it.
  const [dismissed, setDismissed] = useState<Conversation | null>(null)
  const saved: ProfileUpdate | null =
    conversation && dismissed !== conversation ? conversation.profile_update : null

  useEffect(() => {
    if (!conversation?.profile_update) return
    const timer = window.setTimeout(() => setDismissed(conversation), SHOW_MS)
    return () => window.clearTimeout(timer)
  }, [conversation])

  if (voiceState === 'thinking' && conversation) {
    const who = conversation.phase === 'feedback' ? conversation.speaking_to : null
    return (
      <div className="profile-toast profile-toast--saving" role="status">
        <span className="quill" aria-hidden="true">
          <svg viewBox="0 0 24 24" className="icon">
            <path d="M20.7 3.3c-3.9-.6-8.6 1.6-11 5.2L7.4 12l2.6 2.6 3.5-2.3c3.6-2.4 5.8-7.1 5.2-11ZM6 13.4l-2.7 5.5 1.8 1.8 5.5-2.7L6 13.4Z" />
          </svg>
        </span>
        <span>
          {who ? `Aggiorno il profilo di gusto di ${who}` : 'Sto annotando i tuoi gusti'}
          <span className="dots" aria-hidden="true">
            <span>.</span>
            <span>.</span>
            <span>.</span>
          </span>
        </span>
      </div>
    )
  }

  if (!saved) return null
  return (
    <div className="profile-toast profile-toast--saved" role="status" key={`${saved.name}-${saved.profile}`}>
      <span className="check" aria-hidden="true">
        <svg viewBox="0 0 24 24">
          <path d="M5 12.5l4.5 4.5L19 7.5" />
        </svg>
      </span>
      <div className="profile-toast__body">
        <strong>
          {saved.kind === 'created' ? `Profilo di ${saved.name} creato` : `Profilo di ${saved.name} aggiornato`}
          {saved.rating ? ` · ${'★'.repeat(saved.rating)}` : ''}
        </strong>
        <p className="profile-toast__text">{saved.profile}</p>
        {saved.kind === 'created' && saved.likes.length > 0 && (
          <ul className="tags">
            {saved.likes.slice(0, 6).map((like, i) => (
              <li key={like} className="tag" style={{ animationDelay: `${200 + i * 90}ms` }}>
                {like}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}
