import { useEffect, useState } from 'react'

const ENTRANCE = 'cubic-bezier(0.2, 0, 0, 1)'
const EASE_OUT_CUBIC = 'cubic-bezier(0.215, 0.61, 0.355, 1)' // 1-(1-t)^3

/** true when the user asked the OS for reduced motion */
export const prefersReducedMotion = () => typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches

/** flips to true `delay` ms after mount (the staggered page-load entrance) */
function useShown(delay) {
  const [shown, setShown] = useState(prefersReducedMotion())
  useEffect(() => {
    const t = setTimeout(() => setShown(true), prefersReducedMotion() ? 0 : delay)
    return () => clearTimeout(t)
  }, [delay])
  return shown
}

/** whole block fades + slides in together */
export function Reveal({ delay = 0, from = '1.25rem', as: Tag = 'div', className, style, children, ...rest }) {
  const shown = useShown(delay)
  return (
    <Tag
      className={className}
      style={{
        opacity: shown ? 1 : 0,
        transform: shown ? 'translateY(0)' : `translateY(${from})`,
        transition: `opacity 700ms ${ENTRANCE}, transform 700ms ${ENTRANCE}`,
        ...style,
      }}
      {...rest}
    >
      {children}
    </Tag>
  )
}

/** word-by-word reveal: each word is an inline-block span with its own transition delay */
export function Words({ text, delay = 0, stagger = 85, duration = 720, y = 26, as: Tag = 'span', className, style }) {
  const shown = useShown(10)
  return (
    <Tag className={className} style={style}>
      {text.split(' ').map((w, i, all) => (
        <span key={i}>
          <span
            style={{
              display: 'inline-block',
              opacity: shown ? 1 : 0,
              transform: shown ? 'translateY(0)' : `translateY(${y}px)`,
              transition: `opacity ${duration}ms ${EASE_OUT_CUBIC} ${delay + i * stagger}ms, transform ${duration}ms ${EASE_OUT_CUBIC} ${delay + i * stagger}ms`,
            }}
          >
            {w}
          </span>
          {i < all.length - 1 ? ' ' : ''}
        </span>
      ))}
    </Tag>
  )
}
