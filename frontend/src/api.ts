export interface Shop {
  slug: string
  name: string
  tagline: string
  logo_url: string | null
}

export interface Product {
  code: string
  name: string
  description: string
  chocolate: string
  flavors: string[]
  allergens: string[]
  tasting_notes: string
  image_url: string | null
}

export interface RecognizedItem {
  item_id: number
  bbox: [number, number, number, number]
  det_conf: number
  match_score: number
  product: Product
}

export interface Recognition {
  count: number
  image_width: number
  image_height: number
  items: RecognizedItem[]
  elapsed_ms: number
}

export type Phase = 'intro' | 'feedback' | 'done'

export interface Tasting {
  item_id: number
  name: string
  rating: number | null
  comment: string | null
}

export interface Participant {
  name: string
  profile: string
  likes: string[]
  dislikes: string[]
  allergies: string[]
  pending_item: number | null
  tasted: number[]
  history: Tasting[]
}

export interface ProfileUpdate {
  name: string
  kind: 'created' | 'updated'
  profile: string
  likes: string[]
  rating: number | null
}

export interface ItemState {
  item_id: number
  code: string
  name: string
  status: 'available' | 'assigned' | 'eaten'
  assigned_to: string | null
}

export interface Conversation {
  reply: string
  speech_url: string
  phase: Phase
  speaking_to: string | null
  participants: Participant[]
  items: ItemState[]
  keyterms: string[]
  profile_update: ProfileUpdate | null
}

export class ApiError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

/** Conversation turns: the backend retries a slow LLM for up to ~35 s, never wait forever. */
const TURN_TIMEOUT_MS = 45_000

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response
  try {
    res = await fetch(path, init)
  } catch (e) {
    if (e instanceof DOMException && e.name === 'TimeoutError') {
      throw new ApiError(504, 'Il maître ci sta mettendo troppo: ripeti per favore.')
    }
    throw e
  }
  if (!res.ok) {
    let detail = res.statusText
    try {
      detail = (await res.json()).detail ?? detail
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, typeof detail === 'string' ? detail : 'Errore inatteso')
  }
  return res.json() as Promise<T>
}

const json = (body: unknown, timeoutMs?: number): RequestInit => ({
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
  signal: timeoutMs ? AbortSignal.timeout(timeoutMs) : undefined,
})

export const api = {
  shop: (slug: string) => request<Shop>(`/api/shops/${encodeURIComponent(slug)}`),

  createSession: (shopSlug: string) =>
    request<{ session_id: string; shop: Shop }>('/api/sessions', json({ shop_slug: shopSlug })),

  uploadPhoto: (sessionId: string, photo: Blob) => {
    const form = new FormData()
    form.append('photo', photo, 'scatola.jpg')
    return request<Recognition>(`/api/sessions/${sessionId}/photo`, { method: 'POST', body: form })
  },

  startConversation: (sessionId: string, groupSize: number) =>
    request<Conversation>(
      `/api/sessions/${sessionId}/conversation/start`,
      json({ group_size: groupSize }, TURN_TIMEOUT_MS),
    ),

  sendTurn: (sessionId: string, text: string) =>
    request<Conversation>(
      `/api/sessions/${sessionId}/conversation/turn`,
      json({ text }, TURN_TIMEOUT_MS),
    ),

  endConversation: (sessionId: string) =>
    request<Conversation>(`/api/sessions/${sessionId}/conversation/end`, json({}, TURN_TIMEOUT_MS)),

  sttToken: () => request<{ token: string }>('/api/voice/stt-token', { method: 'POST' }),
}
