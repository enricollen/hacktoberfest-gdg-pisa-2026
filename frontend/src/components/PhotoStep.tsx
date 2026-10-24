import { useRef } from 'react'

interface Props {
  onPhoto: (photo: Blob) => void
  busy: boolean
}

/**
 * Step 1: top-down photo of the open box. A file input with `capture` opens the camera on
 * phones and the file picker on desktop (the demo uploads the photo from the PC).
 */
export function PhotoStep({ onPhoto, busy }: Props) {
  const fileRef = useRef<HTMLInputElement>(null)

  return (
    <section className="step" aria-labelledby="photo-title">
      <h1 id="photo-title" className="step__title">
        Apri la scatola
      </h1>
      <p className="step__text">
        Scatta una foto dall'alto alla scatola aperta, con tutti i dolcetti ben visibili.
      </p>
      <div className="actions">
        <button className="btn btn--primary" onClick={() => fileRef.current?.click()} disabled={busy}>
          Scatta una foto
        </button>
      </div>
      <input
        ref={fileRef}
        type="file"
        accept="image/*"
        capture="environment"
        hidden
        data-testid="photo-input"
        onChange={(e) => {
          const file = e.target.files?.[0]
          if (file) onPhoto(file)
          e.target.value = ''
        }}
      />
    </section>
  )
}
