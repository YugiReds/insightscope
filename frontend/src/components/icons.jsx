// Small inline icons. They are decoration only (aria-hidden): every icon is paired with words,
// so meaning never depends on a colour or a picture alone.
const base = {
  width: 18,
  height: 18,
  viewBox: '0 0 20 20',
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 2,
  strokeLinecap: 'round',
  strokeLinejoin: 'round',
  'aria-hidden': true,
  focusable: 'false',
}

export const CheckIcon = (props) => (
  <svg {...base} {...props}>
    <circle cx="10" cy="10" r="8" />
    <path d="M6.5 10.5l2.5 2.5 4.5-5" />
  </svg>
)

export const WarnIcon = (props) => (
  <svg {...base} {...props}>
    <path d="M10 3L18 17H2z" />
    <path d="M10 8.5v3.5M10 14.5v.01" />
  </svg>
)

export const CrossIcon = (props) => (
  <svg {...base} {...props}>
    <circle cx="10" cy="10" r="8" />
    <path d="M7 7l6 6M13 7l-6 6" />
  </svg>
)

export const InfoIcon = (props) => (
  <svg {...base} {...props}>
    <circle cx="10" cy="10" r="8" />
    <path d="M10 9.5V14M10 6.5v.01" />
  </svg>
)

// The spike marker: a diamond. Its SHAPE (not its colour) is what says "spike".
export const DiamondIcon = (props) => (
  <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true" focusable="false" {...props}>
    <path d="M7 1L13 7L7 13L1 7Z" fill="var(--ink)" stroke="var(--card)" strokeWidth="1.5" />
  </svg>
)
