import type { SeriesChapter } from '../../lib/api'
import { formatChapter } from '../../lib/format'

// Chapter state is a pipeline concept, not a ListStatus, so it gets its own
// small tone map rather than forcing StatusPill's typing to fit a different
// domain — the same reasoning JobRow's JobStateBadge already documents.
const TONE: Record<string, 'secondary' | 'tertiary' | 'error' | 'primary'> = {
  downloaded: 'secondary',
  downloading: 'tertiary',
  queued: 'tertiary',
  known: 'primary',
  failed: 'error',
  skipped: 'primary',
}

const LABEL: Record<string, string> = {
  downloaded: 'Downloaded',
  downloading: 'Downloading',
  queued: 'Queued',
  known: 'Known',
  failed: 'Failed',
  skipped: 'Skipped',
}

// The bracket form is load-bearing: 12 isn't on Tailwind's opacity scale, so a
// plain `/12` modifier compiles to no rule (see StatusPill.tsx).
const TINT: Record<string, string> = {
  secondary: 'bg-secondary/[0.12] text-secondary',
  tertiary: 'bg-tertiary/[0.12] text-tertiary',
  error: 'bg-error/[0.12] text-error',
  primary: 'bg-primary/[0.12] text-primary',
}

function ChapterStateBadge({ state }: { state: string }) {
  const tone = TONE[state] ?? 'primary'
  return (
    <span
      className={`inline-flex shrink-0 items-center gap-1.5 rounded-full px-space-sm py-0.5 font-mono text-label-sm ${TINT[tone]}`}
    >
      <span className="h-1.5 w-1.5 rounded-full bg-current" />
      {LABEL[state] ?? state}
    </span>
  )
}

// Markup reference: the "Capítulos & Histórico" list in
// .redesign/detalhes_do_mang_gest_o_de_pipeline_sincronia_multi_destino/code.html.
// The reference's columns are a release date and a reader action ("Ler
// Agora" / "Reler") — this pipeline has neither a release calendar nor a
// reader, so the columns it can honestly show are the ones the API returns:
// the chapter, its pipeline state, and the local file that state produced.
export function ChapterTable({ chapters }: { chapters: SeriesChapter[] }) {
  if (chapters.length === 0) {
    return (
      <p className="rounded-xl bg-surface-container-low px-space-md py-space-md text-body-sm text-on-surface-variant">
        No chapters discovered yet.
      </p>
    )
  }

  return (
    <div className="overflow-x-auto rounded-xl bg-surface-container-low shadow-card">
      <table className="w-full min-w-[480px] border-collapse">
        <thead>
          <tr className="border-b border-surface-container-highest/40 text-left font-mono text-label-sm text-outline">
            <th className="px-space-md py-space-sm font-normal">Chapter</th>
            <th className="px-space-md py-space-sm font-normal">State</th>
            <th className="px-space-md py-space-sm font-normal">Local file</th>
          </tr>
        </thead>
        <tbody>
          {chapters.map((chapter) => (
            <tr key={chapter.number} className="border-b border-surface-container-highest/20 last:border-0">
              <td className="px-space-md py-space-sm">
                <div className="flex flex-col">
                  <span className="text-body-sm font-semibold text-on-surface">
                    Ch {formatChapter(chapter.number)}
                  </span>
                  {chapter.title && (
                    <span className="truncate font-mono text-label-sm text-outline">{chapter.title}</span>
                  )}
                </div>
              </td>
              <td className="px-space-md py-space-sm">
                <ChapterStateBadge state={chapter.state} />
              </td>
              <td className="max-w-[1px] px-space-md py-space-sm">
                <span className="block truncate font-mono text-label-sm text-outline">
                  {chapter.file_path ?? '—'}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
