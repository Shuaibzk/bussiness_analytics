import { useEffect, useRef } from 'react'
import { fluidSimulation } from '../lib/fluid'
import { prefersReducedMotion } from './Reveal'

/**
 * Full-bleed WebGL fluid + soft radial scrim.
 *  variant="hero": the full-strength landing look (login screen)
 *  variant="app":  calmer - lower resolution, 30fps cap, smaller burst and a stronger scrim so data stays legible
 * A fresh <canvas> is created per mount so React StrictMode / route changes can safely create and lose GL contexts.
 * With "reduce motion" enabled in the OS (or without WebGL) a static gradient is shown instead of the animation.
 */
const SCRIMS = {
  hero: 'radial-gradient(115% 95% at 50% 46%, var(--scrim-strong) 0%, var(--scrim-strong) 24%, var(--scrim) 52%, var(--scrim-soft) 100%)',
  app: 'radial-gradient(130% 110% at 50% 35%, rgba(4,5,12,0.86) 0%, rgba(4,5,12,0.78) 45%, rgba(4,5,12,0.6) 100%)',
}
const STATIC = 'radial-gradient(60% 50% at 20% 20%, rgba(94,225,255,0.16), transparent 70%), radial-gradient(55% 50% at 80% 70%, rgba(167,139,250,0.18), transparent 70%)'

export default function FluidBackground({ variant = 'hero' }) {
  const host = useRef(null)
  const reduced = prefersReducedMotion()
  useEffect(() => {
    if (reduced) return undefined
    const canvas = document.createElement('canvas')
    canvas.setAttribute('aria-hidden', 'true')
    canvas.style.cssText = 'position:absolute;inset:0;width:100%;height:100%;z-index:0;pointer-events:none'
    host.current.prepend(canvas)
    let destroy = () => {}
    try {
      destroy = fluidSimulation(canvas, variant === 'app'
        ? { simRes: 128, dyeRes: 384, fps: 30, burst: 18, waves: 3, speed: 0.5 }
        : { speed: 0.5 })
    } catch (e) {
      console.warn('WebGL fluid unavailable, using static background', e)
      canvas.style.background = STATIC
    }
    return () => { destroy(); canvas.remove() }
  }, [variant, reduced])

  return (
    <div ref={host} className="no-print pointer-events-none fixed inset-0 z-0 overflow-hidden bg-[var(--hero-base)]" aria-hidden="true"
      style={reduced ? { backgroundImage: STATIC } : undefined}>
      <div className="absolute inset-0 z-[1]" style={{ background: SCRIMS[variant] }} />
    </div>
  )
}
