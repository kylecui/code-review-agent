import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { useCancelScan, useDeleteScan, useScanDetail } from '@/hooks/use-scans'
import type { FindingRead } from '@/lib/api'
import { cn } from '@/lib/utils'

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

function FindingCard({ finding }: { finding: FindingRead }) {
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
          <span className="font-medium">Location:</span> {finding.file_path}:{finding.line_start}
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

export function ScanDetailPage({ scanId, isSuperuser, onBack }: ScanDetailPageProps) {
  const query = useScanDetail(scanId)
  const cancelScan = useCancelScan()
  const deleteScan = useDeleteScan()

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

        {isSuperuser ? (
          <div className="flex items-center gap-2">
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
          </div>
        ) : null}
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
            <FindingCard key={finding.id} finding={finding} />
          ))}
          {blocking.length === 0 ? <p className="text-sm text-zinc-500">No blocking findings.</p> : null}
        </div>
      </section>

      <section className="space-y-3">
        <h3 className="text-lg font-semibold">Advisory Findings ({advisory.length})</h3>
        <div className="space-y-3">
          {advisory.map((finding) => (
            <FindingCard key={finding.id} finding={finding} />
          ))}
          {advisory.length === 0 ? <p className="text-sm text-zinc-500">No advisory findings.</p> : null}
        </div>
      </section>
    </div>
  )
}
