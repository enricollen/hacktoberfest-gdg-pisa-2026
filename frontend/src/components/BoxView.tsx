import type { ItemState, Recognition } from '../api'

interface Props {
  photoUrl: string
  recognition: Recognition
  /** Live tasting state; when absent, boxes are drawn as freshly recognized. */
  items?: ItemState[]
  highlight?: string | null
}

const initials = (name: string) => name.slice(0, 2).toUpperCase()

/** The box photo with one frame per recognized sweet (and who is tasting what). */
export function BoxView({ photoUrl, recognition, items, highlight }: Props) {
  const { image_width: w, image_height: h } = recognition
  const byId = new Map(items?.map((i) => [i.item_id, i]))

  return (
    <figure className="box-view">
      <div className="box-view__frame" style={{ aspectRatio: `${w} / ${h}` }}>
        <img src={photoUrl} alt="La tua scatola aperta" className="box-view__img" />
        {recognition.items.map((it, n) => {
          const [x1, y1, x2, y2] = it.bbox
          const state = byId.get(it.item_id)
          const status = state?.status ?? 'recognized'
          const mine = !!highlight && state?.assigned_to === highlight && status === 'assigned'
          return (
            <div
              key={it.item_id}
              className={`sweet sweet--${status}${mine ? ' sweet--highlight' : ''}`}
              style={{
                left: `${(x1 / w) * 100}%`,
                top: `${(y1 / h) * 100}%`,
                width: `${((x2 - x1) / w) * 100}%`,
                height: `${((y2 - y1) / h) * 100}%`,
                animationDelay: items ? undefined : `${n * 70}ms`,
              }}
              title={`${it.product.name}${state?.assigned_to ? ` · ${state.assigned_to}` : ''}`}
            >
              {state?.assigned_to && status !== 'available' && (
                <span className="sweet__tag" aria-label={state.assigned_to}>
                  {initials(state.assigned_to)}
                </span>
              )}
            </div>
          )
        })}
      </div>
    </figure>
  )
}
