import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { useCancelScan, useDeleteScan, useExportReport, useScanDetail, useScanLogs } from '@/hooks/use-scans'
import type { LogEntry } from '@/hooks/use-scans'
import type { FindingRead } from '@/lib/api'
import { cn } from '@/lib/utils'
import { useState } from 'react'

interface ScanDetailPageProps {
  scanId: string
  isSuperuser: boolean
  onBack: () => void
}

function formatDate(value: string | null) {
  if (!value) return '—'
  return new Date(value).toLocaleString()
}

function stateBadgeClass(state: string) {
  if (state === 'completed') return 'bg-emerald-100 text-emerald-800 border-emerald-200'
  if (state === 'failed') return 'bg-red-100 text-red-800 border-red-200'
  if (state === 'pending') return 'bg-amber-100 text-amber-800 border-amber-200'
  if (state === 'superseded') return 'bg-zinc-100 text-zinc-700 border-zinc-200'
  return 'bg-blue-100 text-blue-800 border-blue-200'
}

function severityBadgeClass(severity: string) {
  if (severity === 'critical' || severity === 'high') return 'bg-red-100 text-red-800 border-red-200'
  if (severity === 'medium') return 'bg-amber-100 text-amber-800 border-amber-200'
  if (severity === 'low') return 'bg-blue-100 text-blue-800 border-blue-200'
  return 'bg-zinc-100 text-zinc-700 border-zinc-200'
}

function buildGitHubUrl(repo: string, headSha: string, filePath: string, lineStart: number): string | null {
  // Only build links for GitHub-hosted repos (owner/repo format, not local paths)
  if (!repo.includes('/') || repo.startsWith('/')) return null
  const lineFragment = lineStart > 0 ? `#L${lineStart}` : ''
  return `https://github.com/${repo}/blob/${headSha}/${filePath}${lineFragment}`
}

interface FindingCardProps {
  finding: FindingRead
  repo: string
  headSha: string
}

function FindingCard({ finding, repo, headSha }: FindingCardProps) {
  const githubUrl = buildGitHubUrl(repo, headSha, finding.file_path, finding.line_start)
  const locationText = finding.line_end
    ? `${finding.file_path}:${finding.line_start}-${finding.line_end}`
    : `${finding.file_path}:${finding.line_start}`

  return (
    <Card>
      <CardHeader>
        <div className="flex items-start justify-between gap-3">
          <CardTitle className="text-base">{finding.title}</CardTitle>
          <Badge className={cn('capitalize', severityBadgeClass(finding.severity))}>{finding.severity}</Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-2 text-sm">
        <p>
          <span className="font-medium">Category:</span> {finding.category}
        </p>
        <p>
          <span className="font-medium">Location:</span>{' '}
          {githubUrl ? (
            <a
              href={githubUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="font-mono text-blue-600 underline underline-offset-2 hover:text-blue-800"
            >
              {locationText}
            </a>
          ) : (
            <span className="font-mono">{locationText}</span>
          )}
        </p>
        <p>
          <span className="font-medium">Source Tools:</span> {finding.source_tools.join(', ') || '—'}
        </p>
        <p>
          <span className="font-medium">Impact:</span> {finding.impact}
        </p>
        <p>
          <span className="font-medium">Fix Recommendation:</span> {finding.fix_recommendation}
        </p>
      </CardContent>
    </Card>
  )
}

const LOG_LEVELS = ['ALL', 'INFO', 'WARN', 'ERROR', 'DEBUG'] as const

function logLevelClass(level: string) {
  if (level === 'ERROR') return 'text-red-600'
  if (level === 'WARN') return 'text-amber-600'
  if (level === 'DEBUG') return 'text-zinc-400'
  return 'text-zinc-700'
}

function LogViewer({ scanId }: { scanId: string }) {
  const [levelFilter, setLevelFilter] = useState<string>('ALL')
  const logsQuery = useScanLogs(scanId, levelFilter === 'ALL' ? undefined : levelFilter)

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle>Pipeline Logs</CardTitle>
          <div className="flex gap-1">
            {LOG_LEVELS.map((lvl) => (
              <button
                key={lvl}
                type="button"
                className={cn(
                  'rounded-md px-2 py-1 text-xs font-medium transition-colors',
                  levelFilter === lvl ? 'bg-zinc-900 text-white' : 'bg-zinc-100 text-zinc-600 hover:bg-zinc-200',
                )}
                onClick={() => setLevelFilter(lvl)}
              >
                {lvl}
              </button>
            ))}
          </div>
        </div>
      </CardHeader>
      <CardContent>
        {logsQuery.isLoading ? (
          <p className="text-sm text-zinc-500">Loading logs…</p>
        ) : logsQuery.isError ? (
          <p className="text-sm text-red-600">Failed to load logs.</p>
        ) : !logsQuery.data || logsQuery.data.length === 0 ? (
          <p className="text-sm text-zinc-500">No logs available for this scan.</p>
        ) : (
          <div className="max-h-96 overflow-auto rounded-md bg-zinc-950 p-3 font-mono text-xs">
            {logsQuery.data.map((entry: LogEntry, idx: number) => (
              <div key={idx} className="flex gap-2 leading-relaxed">
                <span className="shrink-0 text-zinc-500">{formatLogTime(entry.ts)}</span>
                <span className={cn('shrink-0 w-12', logLevelClass(entry.level))}>[{entry.level}]</span>
                <span className="shrink-0 text-blue-400">{entry.stage}</span>
                <span className="text-zinc-300">{entry.msg}</span>
                {entry.details ? (
                  <span className="text-zinc-500">{JSON.stringify(entry.details)}</span>
                ) : null}
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  )
}

function formatLogTime(iso: string) {
  try {
    const d = new Date(iso)
    const hh = String(d.getHours()).padStart(2, '0')
    const mm = String(d.getMinutes()).padStart(2, '0')
    const ss = String(d.getSeconds()).padStart(2, '0')
    const ms = String(d.getMilliseconds()).padStart(3, '0')
    return `${hh}:${mm}:${ss}.${ms}`
  } catch {
    return iso
  }
}

export function ScanDetailPage({ scanId, isSuperuser, onBack }: ScanDetailPageProps) {
  const query = useScanDetail(scanId)
  const cancelScan = useCancelScan()
  const deleteScan = useDeleteScan()
  const exportReport = useExportReport()
  const [showExportMenu, setShowExportMenu] = useState(false)

  if (query.isLoading) {
    return <p className="text-zinc-500">Loading scan detail…</p>
  }

  if (query.isError || !query.data) {
    return (
      <div className="space-y-3">
        <p className="text-red-600">Failed to load scan detail.</p>
        <Button variant="outline" onClick={onBack}>
          Back
        </Button>
      </div>
    )
  }

  const { scan, findings } = query.data
  const blocking = findings.filter((finding) => finding.blocking)
  const advisory = findings.filter((finding) => !finding.blocking)
  const canCancel = ['pending', 'classifying', 'collecting', 'normalizing', 'reasoning', 'deciding', 'publishing'].includes(
    scan.state,
  )

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <Button variant="outline" onClick={onBack}>
          Back to Scans
        </Button>

        <div className="flex items-center gap-2">
          {scan.state === 'completed' ? (
            <div className="relative">
              <Button
                variant="outline"
                disabled={exportReport.isPending}
                onClick={() => setShowExportMenu((prev) => !prev)}
              >
                {exportReport.isPending ? 'Exporting…' : 'Export Report'}
              </Button>
              {showExportMenu ? (
                <div className="absolute right-0 top-full z-10 mt-1 w-40 rounded-md border bg-white py-1 shadow-lg">
                  <button
                    type="button"
                    className="w-full px-3 py-2 text-left text-sm hover:bg-zinc-100"
                    onClick={() => {
                      exportReport.mutate({ scanId: scan.id, format: 'markdown' })
                      setShowExportMenu(false)
                    }}
                  >
                    Markdown (.md)
                  </button>
                  <button
                    type="button"
                    className="w-full px-3 py-2 text-left text-sm hover:bg-zinc-100"
                    onClick={() => {
                      exportReport.mutate({ scanId: scan.id, format: 'json' })
                      setShowExportMenu(false)
                    }}
                  >
                    JSON (.json)
                  </button>
                </div>
              ) : null}
            </div>
          ) : null}

          {isSuperuser ? (
            <>
              <Button
                variant="outline"
                disabled={!canCancel || cancelScan.isPending}
                onClick={() => cancelScan.mutate(scan.id)}
              >
                {cancelScan.isPending ? 'Cancelling…' : 'Cancel'}
              </Button>
              <Button
                variant="destructive"
                disabled={deleteScan.isPending}
                onClick={() => {
                  deleteScan.mutate(scan.id, { onSuccess: onBack })
                }}
              >
                {deleteScan.isPending ? 'Deleting…' : 'Delete'}
              </Button>
            </>
          ) : null}
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Scan Overview</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-3 text-sm md:grid-cols-2">
          <p>
            <span className="font-medium">Repo:</span> {scan.repo}
          </p>
          <p>
            <span className="font-medium">Kind:</span> {scan.run_kind}
          </p>
          <p className="flex items-center gap-2">
            <span className="font-medium">State:</span>
            <Badge className={cn('capitalize', stateBadgeClass(scan.state))}>{scan.state}</Badge>
          </p>
          <p>
            <span className="font-medium">Head SHA:</span> <span className="font-mono text-xs">{scan.head_sha}</span>
          </p>
          <p>
            <span className="font-medium">Created:</span> {formatDate(scan.created_at)}
          </p>
          <p>
            <span className="font-medium">Completed:</span> {formatDate(scan.completed_at)}
          </p>
          <p className="md:col-span-2">
            <span className="font-medium">Error:</span> {scan.error || '—'}
          </p>
        </CardContent>
      </Card>

      {scan.decision ? (
        <Card>
          <CardHeader>
            <CardTitle>Decision</CardTitle>
          </CardHeader>
          <CardContent>
            <pre className="overflow-auto rounded-md bg-zinc-50 p-3 text-xs">{JSON.stringify(scan.decision, null, 2)}</pre>
          </CardContent>
        </Card>
      ) : null}

      <section className="space-y-3">
        <h3 className="text-lg font-semibold">Blocking Findings ({blocking.length})</h3>
        <div className="space-y-3">
          {blocking.map((finding) => (
            <FindingCard key={finding.id} finding={finding} repo={scan.repo} headSha={scan.head_sha} />
          ))}
          {blocking.length === 0 ? <p className="text-sm text-zinc-500">No blocking findings.</p> : null}
        </div>
      </section>

      <section className="space-y-3">
        <h3 className="text-lg font-semibold">Advisory Findings ({advisory.length})</h3>
        <div className="space-y-3">
          {advisory.map((finding) => (
            <FindingCard key={finding.id} finding={finding} repo={scan.repo} headSha={scan.head_sha} />
          ))}
          {advisory.length === 0 ? <p className="text-sm text-zinc-500">No advisory findings.</p> : null}
        </div>
      </section>

      <LogViewer scanId={scan.id} />
    </div>
  )
}
