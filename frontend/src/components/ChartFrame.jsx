import { cloneElement } from 'react'
import { ResponsiveContainer } from 'recharts'
import { usePrinting } from '../hooks.js'

// Wide enough to look good, narrow enough to fit inside the margins of both Letter and A4 paper.
export const PRINT_CHART_WIDTH = 620

// The box a chart is drawn in. Its height is in pixels (not rem units) on purpose: on paper the page's text size is
// reduced, and a box measured in rem would then shrink while the chart inside it stayed the same size.
//
// On screen the chart stretches to fill the box's width (ResponsiveContainer). That does not work reliably on paper:
// when the browser switches to the print layout it does not wait for the chart to measure itself again, so the chart
// can end up the wrong size or vanish. So while printing the chart gets a fixed width (and a shorter height, to fit
// more on a page), and goes back to stretching afterwards.
export default function ChartFrame({ height, printHeight = height, initialWidth, className = '', children }) {
  const printing = usePrinting()
  const shownHeight = printing ? printHeight : height
  return (
    <div className={`w-full ${className}`} style={{ height: shownHeight }}>
      {printing ? (
        cloneElement(children, { width: PRINT_CHART_WIDTH, height: shownHeight })
      ) : (
        <ResponsiveContainer width="100%" height="100%" initialDimension={{ width: initialWidth, height }}>
          {children}
        </ResponsiveContainer>
      )}
    </div>
  )
}
