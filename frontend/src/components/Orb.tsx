import { useEffect, useLayoutEffect, useRef, type RefObject } from 'react'
import type { VoiceState } from '../hooks/useTastingVoice'

interface Props {
  state: VoiceState
  levelRef: RefObject<number>
  size?: number
}

const LABELS: Record<VoiceState, string> = {
  idle: 'In attesa',
  thinking: 'Sta pensando',
  speaking: 'Sta parlando',
  listening: 'Ti sta ascoltando',
}

/** The agent: a molten-chocolate blob that breathes, swirls while thinking and reacts to voice. */
export function Orb({ state, levelRef, size = 260 }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const stateRef = useRef(state)
  useLayoutEffect(() => {
    stateRef.current = state
  }, [state])

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return
    const dpr = Math.min(window.devicePixelRatio || 1, 2)
    canvas.width = size * dpr
    canvas.height = size * dpr
    ctx.scale(dpr, dpr)

    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    let frame = 0
    let t = 0
    const c = size / 2

    const draw = () => {
      const s = stateRef.current
      const level = levelRef.current ?? 0
      t += reduceMotion ? 0.004 : s === 'thinking' ? 0.05 : 0.018
      ctx.clearRect(0, 0, size, size)

      const base = size * 0.3
      const breathe = Math.sin(t * 1.6) * size * 0.01
      const radius = base + breathe + level * size * 0.07

      // Halo
      const halo = ctx.createRadialGradient(c, c, radius * 0.6, c, c, radius * 1.65)
      const haloColor = s === 'listening' ? '232, 196, 140' : '200, 162, 122'
      halo.addColorStop(0, `rgba(${haloColor}, ${0.28 + level * 0.35})`)
      halo.addColorStop(1, `rgba(${haloColor}, 0)`)
      ctx.fillStyle = halo
      ctx.beginPath()
      ctx.arc(c, c, radius * 1.65, 0, Math.PI * 2)
      ctx.fill()

      // Wobbly blob
      ctx.beginPath()
      const points = 96
      const wobble = (s === 'speaking' || s === 'listening' ? 0.05 + level * 0.1 : 0.03) * radius
      for (let i = 0; i <= points; i++) {
        const a = (i / points) * Math.PI * 2
        const r =
          radius +
          Math.sin(a * 3 + t * 2) * wobble +
          Math.sin(a * 5 - t * 1.3) * wobble * 0.6 +
          Math.cos(a * 2 + t * 0.7) * wobble * 0.4
        const x = c + Math.cos(a) * r
        const y = c + Math.sin(a) * r
        if (i === 0) ctx.moveTo(x, y)
        else ctx.lineTo(x, y)
      }
      ctx.closePath()
      const body = ctx.createRadialGradient(
        c - radius * 0.35, c - radius * 0.4, radius * 0.1, c, c, radius * 1.1,
      )
      body.addColorStop(0, '#9a6a45')
      body.addColorStop(0.45, '#5b3520')
      body.addColorStop(1, '#2a160c')
      ctx.fillStyle = body
      ctx.fill()

      // Swirl of gold while thinking, rim light otherwise
      ctx.save()
      ctx.clip()
      ctx.strokeStyle = `rgba(232, 196, 140, ${s === 'thinking' ? 0.55 : 0.18 + level * 0.4})`
      ctx.lineWidth = size * 0.012
      for (let k = 0; k < 3; k++) {
        ctx.beginPath()
        const phase = t * (s === 'thinking' ? 2.2 : 0.8) + (k * Math.PI * 2) / 3
        for (let i = 0; i <= 60; i++) {
          const u = i / 60
          const a = phase + u * Math.PI * 1.4
          const r = radius * (0.25 + u * 0.75)
          const x = c + Math.cos(a) * r
          const y = c + Math.sin(a) * r * 0.85
          if (i === 0) ctx.moveTo(x, y)
          else ctx.lineTo(x, y)
        }
        ctx.stroke()
      }
      ctx.restore()

      // Glossy highlight
      const gloss = ctx.createRadialGradient(
        c - radius * 0.38, c - radius * 0.45, 0, c - radius * 0.38, c - radius * 0.45, radius * 0.5,
      )
      gloss.addColorStop(0, 'rgba(255, 240, 220, 0.35)')
      gloss.addColorStop(1, 'rgba(255, 240, 220, 0)')
      ctx.fillStyle = gloss
      ctx.beginPath()
      ctx.arc(c, c, radius, 0, Math.PI * 2)
      ctx.fill()

      frame = requestAnimationFrame(draw)
    }
    frame = requestAnimationFrame(draw)
    return () => cancelAnimationFrame(frame)
  }, [levelRef, size])

  return (
    <div className={`orb orb--${state}`} style={{ width: size, height: size }}>
      <canvas ref={canvasRef} style={{ width: size, height: size }} aria-hidden="true" />
      <span className="visually-hidden" role="status">
        {LABELS[state]}
      </span>
    </div>
  )
}
