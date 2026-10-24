import { useState } from 'react'

interface Props {
  max: number
  onConfirm: (groupSize: number) => void
}

/** Step 3: how many people take part, chosen by hand before the voice conversation starts. */
export function PeopleStep({ max, onConfirm }: Props) {
  const [count, setCount] = useState(Math.min(2, max))
  const change = (delta: number) => setCount((c) => Math.min(max, Math.max(1, c + delta)))

  return (
    <section className="step" aria-labelledby="people-title">
      <h1 id="people-title" className="step__title">
        Quanti siete?
      </h1>
      <p className="step__text">
        Il maître vi conoscerà uno alla volta e consiglierà a ciascuno il dolcetto giusto.
      </p>

      <div className="counter" role="group" aria-label="Numero di partecipanti">
        <button
          className="counter__btn"
          onClick={() => change(-1)}
          disabled={count <= 1}
          aria-label="Una persona in meno"
        >
          −
        </button>
        <output className="counter__value" aria-live="polite" data-testid="people-count">
          <span key={count} className="counter__number">
            {count}
          </span>
          <span className="counter__label">{count === 1 ? 'persona' : 'persone'}</span>
        </output>
        <button
          className="counter__btn"
          onClick={() => change(1)}
          disabled={count >= max}
          aria-label="Una persona in più"
        >
          +
        </button>
      </div>
      <div className="avatars" aria-hidden="true">
        {Array.from({ length: count }, (_, i) => (
          <span key={i} className="avatars__dot" style={{ animationDelay: `${i * 40}ms` }} />
        ))}
      </div>

      <div className="actions">
        <button className="btn btn--primary" onClick={() => onConfirm(count)}>
          Inizia la degustazione
        </button>
      </div>
    </section>
  )
}
