import type { Config } from 'tailwindcss'

/**
 * The token map from .redesign/obsidian_vault/DESIGN.md front matter.
 *
 * That file also carries a prose palette naming #8b5cf6 over #0d1117. It
 * disagrees with this map and loses: every mockup in .redesign/ embeds these
 * values, and the screenshots were rendered from them.
 *
 * This is a deliberate subset: surface-tint and the *-fixed / *-fixed-dim /
 * on-*-fixed / on-*-fixed-variant roles are omitted because nothing uses them.
 */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        background: '#10141a',
        'on-background': '#dfe2eb',
        surface: '#10141a',
        'surface-dim': '#10141a',
        'surface-bright': '#353940',
        'surface-container-lowest': '#0a0e14',
        'surface-container-low': '#181c22',
        'surface-container': '#1c2026',
        'surface-container-high': '#262a31',
        'surface-container-highest': '#31353c',
        'surface-variant': '#31353c',
        'on-surface': '#dfe2eb',
        'on-surface-variant': '#cbc3d7',
        'inverse-surface': '#dfe2eb',
        'inverse-on-surface': '#2d3137',
        outline: '#958ea0',
        'outline-variant': '#494454',
        primary: '#d0bcff',
        'on-primary': '#3c0091',
        'primary-container': '#a078ff',
        'on-primary-container': '#340080',
        'inverse-primary': '#6d3bd7',
        secondary: '#4edea3',
        'on-secondary': '#003824',
        'secondary-container': '#00a572',
        'on-secondary-container': '#00311f',
        tertiary: '#7bd0ff',
        'on-tertiary': '#00354a',
        'tertiary-container': '#009bd1',
        'on-tertiary-container': '#002d40',
        error: '#ffb4ab',
        'on-error': '#690005',
        'error-container': '#93000a',
        'on-error-container': '#ffdad6',
        // Not in the source map. A fifth reading status needs a fifth role.
        warning: '#ffb877',
        'on-warning': '#4a2600',
        'warning-container': '#c2691a',
        'on-warning-container': '#3a1d00',
      },
      fontFamily: {
        sans: ['Plus Jakarta Sans', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'ui-monospace', 'monospace'],
      },
      fontSize: {
        'display-lg': ['3rem', { lineHeight: '3.5rem', letterSpacing: '-0.03em', fontWeight: '800' }],
        'display-sm': ['2.25rem', { lineHeight: '2.75rem', letterSpacing: '-0.02em', fontWeight: '700' }],
        'headline-lg': ['1.75rem', { lineHeight: '2.25rem', letterSpacing: '-0.02em', fontWeight: '700' }],
        'headline-md': ['1.375rem', { lineHeight: '1.875rem', letterSpacing: '-0.01em', fontWeight: '600' }],
        'headline-sm': ['1.125rem', { lineHeight: '1.5rem', fontWeight: '600' }],
        'title-md': ['1rem', { lineHeight: '1.375rem', fontWeight: '600' }],
        'body-lg': ['1rem', { lineHeight: '1.625rem', fontWeight: '400' }],
        'body-md': ['0.875rem', { lineHeight: '1.375rem', fontWeight: '400' }],
        'body-sm': ['0.75rem', { lineHeight: '1.125rem', fontWeight: '400' }],
        'label-md': ['0.8125rem', { lineHeight: '1.125rem', letterSpacing: '0.02em', fontWeight: '500' }],
        'label-sm': ['0.6875rem', { lineHeight: '0.9375rem', letterSpacing: '0.04em', fontWeight: '600' }],
      },
      borderRadius: {
        sm: '0.25rem',
        DEFAULT: '0.5rem',
        md: '0.75rem',
        lg: '1rem',
        xl: '1.5rem',
        full: '9999px',
      },
      spacing: {
        gutter: '1.25rem',
        // The bottom navigation's own height plus a gutter. Anything sticky or
        // fixed to the bottom below xl offsets by this: the settings save bar
        // and the nav were built by different tasks, neither knew about the
        // other, and the Save button ended up 26px behind it on a phone.
        'nav-clearance': '4.5rem',
        margin: '2rem',
        'space-xs': '0.25rem',
        'space-sm': '0.5rem',
        'space-md': '1rem',
        'space-lg': '1.5rem',
        'space-xl': '2.5rem',
      },
      maxWidth: { canvas: '1440px' },
      boxShadow: {
        card: '0 8px 24px -4px rgba(0, 0, 0, 0.45)',
        overlay: '0 20px 40px -12px rgba(208, 188, 255, 0.12)',
        glow: '0 8px 20px -2px rgba(208, 188, 255, 0.25)',
        // The batch bar floats over the list: a deep drop to lift it off the
        // page, and a violet halo tying it to the selection it acts on.
        'batch-bar': '0 20px 50px rgba(0, 0, 0, 0.8), 0 0 35px rgba(139, 92, 246, 0.25)',
      },
    },
  },
  plugins: [],
} satisfies Config
