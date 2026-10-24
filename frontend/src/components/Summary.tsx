import type { Conversation, Recognition, Tasting } from '../api'

interface Props {
  conversation: Conversation
  recognition: Recognition
}

const Stars = ({ rating }: { rating: number | null }) =>
  rating ? (
    <span className="stars" aria-label={`${rating} su 5`}>
      {'★'.repeat(rating)}
      <span className="stars__empty">{'★'.repeat(5 - rating)}</span>
    </span>
  ) : null

function favorite(history: Tasting[]): Tasting | null {
  return history.reduce<Tasting | null>(
    (best, t) => ((t.rating ?? 0) > (best?.rating ?? 0) ? t : best),
    null,
  )
}

/** End of the experience: one card per person with what they ate and what was understood. */
export function Summary({ conversation, recognition }: Props) {
  const images = new Map(recognition.items.map((i) => [i.item_id, i.product.image_url]))
  const names = new Map(recognition.items.map((i) => [i.item_id, i.product.name]))
  const tasted = conversation.participants.reduce((n, p) => n + p.history.length, 0)
  const eaten = conversation.items.filter((i) => i.status === 'eaten').length
  const endedEarly = eaten < conversation.items.length

  return (
    <section className="summary" aria-labelledby="summary-title">
      <h2 id="summary-title" className="summary__title">
        Il vostro riepilogo
      </h2>
      <p className="summary__subtitle">
        {conversation.participants.length} {conversation.participants.length === 1 ? 'persona' : 'persone'} ·{' '}
        {tasted} dolcetti assaggiati
        {endedEarly && ` · degustazione conclusa in anticipo (${eaten}/${conversation.items.length})`}
      </p>
      {conversation.participants.length === 0 && (
        <p className="summary__subtitle">Nessun partecipante presentato: alla prossima!</p>
      )}

      <div className="cards">
        {conversation.participants.map((p, idx) => {
          const best = favorite(p.history)
          return (
            <article className="card" key={p.name} style={{ animationDelay: `${idx * 120}ms` }}>
              <header className="card__header">
                <span className="card__avatar" aria-hidden="true">
                  {p.name.slice(0, 1).toUpperCase()}
                </span>
                <div>
                  <h3 className="card__name">{p.name}</h3>
                  {best && <p className="card__fav">Preferito: {best.name}</p>}
                </div>
              </header>

              <div className="card__section">
                <h4 className="card__label">Cosa ho capito dei tuoi gusti</h4>
                <p className="card__profile">{p.profile}</p>
                {p.likes.length > 0 && (
                  <ul className="tags">
                    {p.likes.map((l) => (
                      <li key={l} className="tag">
                        {l}
                      </li>
                    ))}
                  </ul>
                )}
                {(p.dislikes.length > 0 || p.allergies.length > 0) && (
                  <ul className="tags">
                    {p.dislikes.map((d) => (
                      <li key={d} className="tag tag--muted">
                        no {d}
                      </li>
                    ))}
                    {p.allergies.map((a) => (
                      <li key={a} className="tag tag--warn">
                        allergia: {a}
                      </li>
                    ))}
                  </ul>
                )}
              </div>

              <div className="card__section">
                <h4 className="card__label">Ha assaggiato</h4>
                <ul className="tasted">
                  {p.history.map((t) => (
                    <li key={t.item_id} className={`tasted__item${t === best ? ' tasted__item--best' : ''}`}>
                      {images.get(t.item_id) && (
                        <img className="tasted__img" src={images.get(t.item_id)!} alt="" loading="lazy" />
                      )}
                      <div className="tasted__body">
                        <div className="tasted__row">
                          <span className="tasted__name">{t.name}</span>
                          <Stars rating={t.rating} />
                        </div>
                        {t.comment && <p className="tasted__comment">{t.comment}</p>}
                      </div>
                    </li>
                  ))}
                  {p.pending_item !== null && (
                    <li className="tasted__item tasted__item--pending">
                      {images.get(p.pending_item) && (
                        <img className="tasted__img" src={images.get(p.pending_item)!} alt="" loading="lazy" />
                      )}
                      <div className="tasted__body">
                        <span className="tasted__name">{names.get(p.pending_item)}</span>
                        <p className="tasted__comment">stava assaggiando, senza commento</p>
                      </div>
                    </li>
                  )}
                  {p.history.length === 0 && p.pending_item === null && (
                    <li className="tasted__empty">Nessun assaggio registrato</li>
                  )}
                </ul>
              </div>
            </article>
          )
        })}
      </div>
    </section>
  )
}
