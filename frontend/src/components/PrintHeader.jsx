import { describeRange, formatDate, formatDateTime } from '../format.js'
import { useGeneratedAt } from '../hooks.js'

// The title block of the printed report. It is hidden on screen and shown only on paper ("hidden print:block").
// It says what the report is, when it was made, and which dates it covers.
export default function PrintHeader({ coverage, range }) {
  const generatedAt = useGeneratedAt()
  return (
    <div className="hidden print:block" data-testid="print-header">
      <h2 className="text-2xl font-bold">Recall report</h2>
      <dl className="mt-2 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
        <dt className="font-semibold">Generated</dt>
        <dd>{formatDateTime(generatedAt)}</dd>
        <dt className="font-semibold">Data covers</dt>
        <dd>{coverage ? `${formatDate(coverage.oldest_report_date)} to ${formatDate(coverage.newest_report_date)}` : 'Not available'}</dd>
        <dt className="font-semibold">Reason categories</dt>
        <dd>{describeRange(range.from, range.to)}</dd>
      </dl>
    </div>
  )
}
