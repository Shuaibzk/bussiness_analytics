import { motion } from 'framer-motion'
import { AlertTriangle } from 'lucide-react'
import { cx } from '../lib/format'

/** two interleaving flow lines, echoing the fluid background */
export function FlowGlyph({ size = 24, className }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true" className={className}>
      <path d="M2.5 9c2.5 0 2.5 4.2 5 4.2S10 9 12 9s2.5 4.2 5 4.2S19.5 9 21.5 9" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
      <path d="M2.5 15c2.5 0 2.5 4.2 5 4.2S10 15 12 15s2.5 4.2 5 4.2S19.5 15 21.5 15" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" opacity="0.5" />
    </svg>
  )
}

export function Logo({ size = 24, text = true }) {
  return (
    <div className="flex items-center gap-[0.6rem] font-medium tracking-[-0.01em] text-white">
      <FlowGlyph size={size} />
      {text && <span className="text-[1.15rem] sm:text-[1.375rem]">Panorama</span>}
    </div>
  )
}

export function Card({ className, children, delay = 0, ...rest }) {
  return (
    <motion.section
      initial={{ opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.7, delay, ease: [0.2, 0, 0, 1] }}
      className={cx('panel rounded-[1.5rem]', className)}
      {...rest}
    >
      {children}
    </motion.section>
  )
}

export function CardHeader({ title, subtitle, right }) {
  return (
    <div className="flex items-start justify-between gap-3 px-6 pt-5">
      <div className="min-w-0">
        <h3 className="text-[1.05rem] font-medium tracking-[-0.01em] text-[var(--heading)]">{title}</h3>
        {subtitle && <p className="mt-1 text-[0.8rem] text-[var(--body-muted)]">{subtitle}</p>}
      </div>
      {right}
    </div>
  )
}

export function Segmented({ value, onChange, options, size = 'sm', label }) {
  return (
    <div className="glass inline-flex rounded-full p-[0.2rem]" role="group" aria-label={label}>
      {options.map((o) => {
        const v = typeof o === 'string' ? o : o.value
        const label = typeof o === 'string' ? o : o.label
        const active = v === value
        return (
          <button
            key={v}
            onClick={() => onChange(v)}
            aria-pressed={active}
            className={cx(
              'rounded-full px-3 font-medium transition-colors',
              size === 'sm' ? 'py-1 text-[0.75rem]' : 'py-1.5 text-[0.85rem]',
              active ? 'bg-white text-[var(--action-inverse-fg)]' : 'text-[var(--body-muted)] hover:text-white',
            )}
          >
            {label}
          </button>
        )
      })}
    </div>
  )
}

export function Badge({ children, tone = 'neutral', className }) {
  const tones = {
    neutral: 'text-[var(--body-muted)]',
    good: 'text-emerald-300',
    warn: 'text-amber-300',
    bad: 'text-rose-300',
    brand: 'text-sky-200',
    cyan: 'text-cyan-200',
  }
  return (
    <span className={cx('glass inline-flex items-center gap-1 rounded-full px-[0.7rem] py-[0.2rem] text-[0.7rem] font-medium', tones[tone], className)}>
      {children}
    </span>
  )
}

export const Skeleton = ({ className, style }) => <div className={cx('skeleton', className)} style={style} />

export function ErrorBox({ error }) {
  return (
    <div className="flex items-center gap-2 rounded-2xl border border-rose-400/25 bg-rose-400/5 p-4 text-sm text-rose-300">
      <AlertTriangle size={16} /> {error?.message || 'Something went wrong'}
    </div>
  )
}

export function Empty({ children = 'No data for the current filters' }) {
  return <div className="flex h-full min-h-32 items-center justify-center text-sm text-[var(--body-muted)]">{children}</div>
}

export const statusTone = { Delivered: 'good', Processing: 'cyan', Returned: 'warn', Cancelled: 'bad' }
