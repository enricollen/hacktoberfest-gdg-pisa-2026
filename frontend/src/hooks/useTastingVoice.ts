import { CommitStrategy, useScribe } from '@elevenlabs/react'
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
import { api, ApiError, type Conversation } from '../api'
import { errorText, logEvent } from '../log'

export type VoiceState = 'idle' | 'thinking' | 'speaking' | 'listening'

/** Extra silence after a VAD commit before the turn is sent: people pause mid-sentence. */
const GRACE_MS = 900
/** Holding the talk button longer than this makes it push-to-talk (release = end of turn). */
const HOLD_MS = 600
/** After Stop, wait this long for the final committed transcript before using the partial. */
const STOP_FLUSH_MS = 1500

const MIC = { echoCancellation: true, noiseSuppression: true, autoGainControl: true }

/**
 * Turn-based voice loop: the agent speaks (streamed ElevenLabs TTS), then the browser listens
 * (Scribe v2 Realtime with VAD, straight from the mic) and the transcript is sent to the backend.
 */
export function useTastingVoice(sessionId: string | null) {
  const [conversation, setConversation] = useState<Conversation | null>(null)
  const [voiceState, setVoiceState] = useState<VoiceState>('idle')
  const [partial, setPartial] = useState('')
  const [lastUserText, setLastUserText] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [autoListen, setAutoListen] = useState(true)

  /** Audio level 0..1 of whoever is talking, read by the orb animation loop. */
  const levelRef = useRef(0)

  const audioRef = useRef<HTMLAudioElement | null>(null)
  const audioCtxRef = useRef<AudioContext | null>(null)
  const ttsAnalyserRef = useRef<AnalyserNode | null>(null)
  const micAnalyserRef = useRef<AnalyserNode | null>(null)
  const micStreamRef = useRef<MediaStream | null>(null)

  const stateRef = useRef<VoiceState>('idle')
  const convRef = useRef<Conversation | null>(null)
  const autoListenRef = useRef(true)
  const bufferRef = useRef('')
  const partialRef = useRef('')
  const stopRequestedRef = useRef(false)
  const graceTimer = useRef<number | undefined>(undefined)
  const pressStart = useRef(0)
  // Handlers called from scribe callbacks, kept in a ref so callbacks never go stale.
  const handlers = useRef({
    onCommitted: (_t: string) => {},
    onPartial: (_t: string) => {},
    onError: (_e: unknown) => {},
  })
  /** Set by "Concludi": late answers of in-flight turns must not reopen the conversation. */
  const endedRef = useRef(false)
  /** Automatic reconnections left for the current turn after a transcription error. */
  const sttRetriesRef = useRef(1)

  // Read through a function: TS would otherwise keep a stale narrowing across awaits.
  const currentState = () => stateRef.current

  const setState = useCallback((s: VoiceState) => {
    stateRef.current = s
    setVoiceState(s)
  }, [])

  useEffect(() => {
    autoListenRef.current = autoListen
  }, [autoListen])

  const scribe = useScribe({
    modelId: 'scribe_v2_realtime',
    commitStrategy: CommitStrategy.VAD,
    languageCode: 'it',
    vadSilenceThresholdSecs: 1.1,
    noVerbatim: true,
    onPartialTranscript: (d) => handlers.current.onPartial(d.text),
    onCommittedTranscript: (d) => handlers.current.onCommitted(d.text),
    onError: (e) => handlers.current.onError(e),
  })
  const scribeRef = useRef(scribe)
  useLayoutEffect(() => {
    scribeRef.current = scribe
  })

  // --- audio graph ----------------------------------------------------------------------------

  /** Must run inside a user gesture the first time (autoplay policy). */
  const unlockAudio = useCallback(() => {
    if (!audioRef.current) {
      const audio = new Audio()
      audio.preload = 'auto'
      audioRef.current = audio
    }
    if (!audioCtxRef.current) {
      const ctx = new AudioContext()
      const source = ctx.createMediaElementSource(audioRef.current)
      const analyser = ctx.createAnalyser()
      analyser.fftSize = 512
      source.connect(analyser)
      analyser.connect(ctx.destination)
      audioCtxRef.current = ctx
      ttsAnalyserRef.current = analyser
    }
    void audioCtxRef.current.resume()
  }, [])

  useEffect(() => {
    const data = new Uint8Array(512)
    let frame = 0
    const tick = () => {
      const analyser =
        stateRef.current === 'speaking'
          ? ttsAnalyserRef.current
          : stateRef.current === 'listening'
            ? micAnalyserRef.current
            : null
      let level = 0
      if (analyser) {
        analyser.getByteTimeDomainData(data)
        let sum = 0
        for (let i = 0; i < analyser.fftSize; i++) {
          const v = (data[i] - 128) / 128
          sum += v * v
        }
        level = Math.min(1, Math.sqrt(sum / analyser.fftSize) * 4)
      }
      levelRef.current += (level - levelRef.current) * 0.25
      frame = requestAnimationFrame(tick)
    }
    frame = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(frame)
  }, [])

  // Separate lightweight mic tap, only to animate the orb while listening.
  const startMicMeter = useCallback(async () => {
    try {
      const ctx = audioCtxRef.current
      if (!ctx) return
      const stream = await navigator.mediaDevices.getUserMedia({ audio: MIC })
      const analyser = ctx.createAnalyser()
      analyser.fftSize = 512
      ctx.createMediaStreamSource(stream).connect(analyser)
      micStreamRef.current = stream
      micAnalyserRef.current = analyser
    } catch {
      /* the meter is cosmetic */
    }
  }, [])

  const stopMic = useCallback(() => {
    micStreamRef.current?.getTracks().forEach((t) => t.stop())
    micStreamRef.current = null
    micAnalyserRef.current = null
  }, [])

  // --- turn loop ------------------------------------------------------------------------------

  const clearGrace = () => window.clearTimeout(graceTimer.current)

  const startListening = useCallback(async () => {
    if (stateRef.current === 'listening' || !convRef.current || convRef.current.phase === 'done') {
      return
    }
    setError(null)
    bufferRef.current = ''
    partialRef.current = ''
    stopRequestedRef.current = false
    setPartial('')
    setState('listening')
    const started = performance.now()
    try {
      const { token } = await api.sttToken()
      if (currentState() !== 'listening') return // stopped while fetching the token
      await scribeRef.current.connect({
        token,
        keyterms: convRef.current.keyterms,
        microphone: MIC,
      })
      logEvent('info', 'stt.listening', { connect_ms: Math.round(performance.now() - started) })
      void startMicMeter()
    } catch (e) {
      logEvent('error', 'stt.connect_failed', { error: errorText(e) })
      setError('Non riesco ad attivare il microfono. Controlla i permessi oppure scrivi la risposta.')
      setState('idle')
    }
  }, [setState, startMicMeter])

  const speak = useCallback(
    async (conv: Conversation) => {
      const audio = audioRef.current
      const requested = performance.now()
      const afterSpeech = () => {
        if (stateRef.current !== 'speaking') return
        logEvent('info', 'tts.ended', { seconds: Math.round(audio?.currentTime ?? 0) })
        setState('idle')
        if (conv.phase !== 'done' && autoListenRef.current) void startListening()
      }
      if (!audio) return afterSpeech()
      setState('speaking')
      audio.onended = afterSpeech
      audio.onerror = () => {
        logEvent('error', 'tts.error', { code: audio.error?.code, message: audio.error?.message })
        afterSpeech()
      }
      audio.onplaying = () => {
        audio.onplaying = null
        logEvent('info', 'tts.playing', { latency_ms: Math.round(performance.now() - requested) })
      }
      audio.src = conv.speech_url
      try {
        await audio.play()
      } catch (e) {
        logEvent('error', 'tts.play_failed', { error: errorText(e) })
        afterSpeech()
      }
    },
    [setState, startListening],
  )

  const apply = useCallback(
    (conv: Conversation) => {
      convRef.current = conv
      setConversation(conv)
      void speak(conv)
    },
    [speak],
  )

  const send = useCallback(
    async (text: string) => {
      if (!sessionId) return
      setLastUserText(text)
      setPartial('')
      setState('thinking')
      sttRetriesRef.current = 1
      const started = performance.now()
      logEvent('info', 'turn.sent', { text })
      try {
        const conv = await api.sendTurn(sessionId, text)
        if (endedRef.current) return
        logEvent('info', 'turn.reply', {
          ms: Math.round(performance.now() - started),
          phase: conv.phase,
          profile_update: conv.profile_update?.name,
        })
        apply(conv)
      } catch (e) {
        if (endedRef.current) return
        logEvent('error', 'turn.failed', { error: errorText(e) })
        setError(e instanceof ApiError ? e.message : 'Connessione persa, riprova.')
        setState('idle')
        if (autoListenRef.current) void startListening()
      }
    },
    [apply, sessionId, setState, startListening],
  )

  const finishTurn = useCallback(() => {
    clearGrace()
    const text = (bufferRef.current || (stopRequestedRef.current ? partialRef.current : '')).trim()
    scribeRef.current.disconnect()
    stopMic()
    bufferRef.current = ''
    if (text) {
      void send(text)
    } else {
      logEvent('warning', 'stt.empty_turn', { stop: stopRequestedRef.current })
      setState('idle')
    }
  }, [send, setState, stopMic])

  useLayoutEffect(() => {
    handlers.current.onError = (e: unknown) => {
      logEvent('error', 'stt.error', { state: stateRef.current, error: errorText(e) })
      if (stateRef.current !== 'listening') return
      clearGrace()
      scribeRef.current.disconnect()
      stopMic()
      setState('idle')
      if (sttRetriesRef.current > 0) {
        sttRetriesRef.current -= 1 // a dropped connection should not end the experience
        logEvent('info', 'stt.retry')
        window.setTimeout(() => void startListening(), 800)
      } else {
        setError('Il microfono non risponde: premi Parla per riprovare oppure scrivi la risposta.')
      }
    }
    handlers.current.onPartial = (text: string) => {
      partialRef.current = text
      setPartial(text)
      if (text) clearGrace() // still talking: postpone the end of turn
    }
    handlers.current.onCommitted = (text: string) => {
      logEvent('info', 'stt.committed', { text })
      if (!text.trim()) return
      bufferRef.current = `${bufferRef.current} ${text}`.trim()
      partialRef.current = ''
      setPartial(bufferRef.current)
      clearGrace()
      graceTimer.current = window.setTimeout(finishTurn, stopRequestedRef.current ? 0 : GRACE_MS)
    }
  })

  // --- public controls ------------------------------------------------------------------------

  const start = useCallback(
    async (groupSize: number) => {
      if (!sessionId) return
      unlockAudio()
      setState('thinking')
      logEvent('info', 'conversation.start', { group_size: groupSize })
      try {
        apply(await api.startConversation(sessionId, groupSize))
      } catch (e) {
        logEvent('error', 'conversation.start_failed', { error: errorText(e) })
        setError(e instanceof ApiError ? e.message : 'Connessione persa, riprova.')
        setState('idle')
      }
    },
    [apply, sessionId, setState, unlockAudio],
  )

  /** Demo control: wrap up now; the summary shows what was gathered so far. */
  const endTasting = useCallback(async () => {
    if (!sessionId || endedRef.current) return
    endedRef.current = true
    logEvent('info', 'conversation.end_requested', { state: stateRef.current })
    clearGrace()
    scribeRef.current.disconnect()
    stopMic()
    audioRef.current?.pause()
    setPartial('')
    setError(null)
    setState('thinking')
    try {
      apply(await api.endConversation(sessionId))
    } catch (e) {
      endedRef.current = false // let the user try again
      logEvent('error', 'conversation.end_failed', { error: errorText(e) })
      setError(e instanceof ApiError ? e.message : 'Connessione persa, riprova.')
      setState('idle')
    }
  }, [apply, sessionId, setState, stopMic])

  /** Stop: silences the agent, or ends the current turn right now while listening. */
  const stop = useCallback(() => {
    logEvent('info', 'control.stop', { state: stateRef.current })
    if (stateRef.current === 'speaking') {
      audioRef.current?.pause()
      setState('idle')
      if (autoListenRef.current) void startListening()
    } else if (stateRef.current === 'listening') {
      stopRequestedRef.current = true
      if (!bufferRef.current && !partialRef.current) return finishTurn()
      scribeRef.current.commit()
      clearGrace()
      graceTimer.current = window.setTimeout(finishTurn, STOP_FLUSH_MS)
    }
  }, [finishTurn, setState, startListening])

  /** Talk button: tap = start listening (VAD ends the turn), hold = push-to-talk. */
  const talkPress = useCallback(() => {
    unlockAudio()
    sttRetriesRef.current = 1
    pressStart.current = performance.now()
    if (stateRef.current === 'speaking') {
      audioRef.current?.pause()
      setState('idle')
    }
    void startListening()
  }, [setState, startListening, unlockAudio])

  const talkRelease = useCallback(() => {
    if (performance.now() - pressStart.current > HOLD_MS) stop()
  }, [stop])

  const sendText = useCallback(
    (text: string) => {
      if (stateRef.current === 'listening') {
        clearGrace()
        scribeRef.current.disconnect()
        stopMic()
      }
      audioRef.current?.pause()
      void send(text)
    },
    [send, stopMic],
  )

  const replay = useCallback(() => {
    if (convRef.current && stateRef.current !== 'thinking') {
      if (stateRef.current === 'listening') {
        scribeRef.current.disconnect()
        stopMic()
      }
      void speak(convRef.current)
    }
  }, [speak, stopMic])

  useEffect(
    () => () => {
      clearGrace()
      scribeRef.current.disconnect()
      stopMic()
      audioRef.current?.pause()
      void audioCtxRef.current?.close()
    },
    [stopMic],
  )

  return {
    conversation,
    voiceState,
    partial,
    lastUserText,
    error,
    autoListen,
    setAutoListen,
    levelRef,
    start,
    stop,
    talkPress,
    talkRelease,
    sendText,
    replay,
    endTasting,
  }
}
