import { useMemo, useState } from 'react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Select } from '@/components/ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { useScans, useTriggerScan, useUploadScan } from '@/hooks/use-scans'
import type { ReviewRunRead } from '@/lib/api'
import { cn } from '@/lib/utils'
import { buttonVariants } from '@/components/ui/button'

interface ScansPageProps {
  isSuperuser: boolean
  onSelectScan: (id: string) => void
}

function formatDate(value: string | null) {
  if (!value) return '—'
  return new Date(value).toLocaleString()
}

function shortSha(sha: string) {
  return sha.slice(0, 8)
}

function stateBadgeClass(state: string) {
  if (state === 'completed') return 'bg-emerald-100 text-emerald-800 border-emerald-200'
  if (state === 'failed') return 'bg-red-100 text-red-800 border-red-200'
  if (state === 'pending') return 'bg-amber-100 text-amber-800 border-amber-200'
  if (state === 'superseded') return 'bg-zinc-100 text-zinc-700 border-zinc-200'
  return 'bg-blue-100 text-blue-800 border-blue-200'
}

function kindBadgeClass(kind: string) {
  return kind === 'pr' ? 'bg-indigo-100 text-indigo-800 border-indigo-200' : 'bg-sky-100 text-sky-800 border-sky-200'
}

function TriggerScanDialog() {
  const [open, setOpen] = useState(false)
  const [mode, setMode] = useState<'github' | 'upload'>('github')
  const [repo, setRepo] = useState('')
  const [installationId, setInstallationId] = useState('')
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [error, setError] = useState<string | null>(null)
  const triggerScan = useTriggerScan()
  const uploadScan = useUploadScan()

  const isSubmitting = triggerScan.isPending || uploadScan.isPending

  const resetForm = () => {
    setRepo('')
    setInstallationId('')
    setSelectedFile(null)
    setError(null)
  }

  const handleError = (mutationError: unknown) => {
    if (mutationError instanceof Error) {
      setError(mutationError.message)
    } else {
      setError('Failed to trigger scan')
    }
  }

  const handleSubmit: NonNullable<React.ComponentProps<'form'>['onSubmit']> = (event) => {
    event.preventDefault()
    setError(null)

    if (mode === 'github') {
      triggerScan.mutate(
        {
          repo: repo || undefined,
          installation_id: installationId ? Number(installationId) : undefined,
        },
        {
          onSuccess: () => {
            setOpen(false)
            resetForm()
          },
          onError: handleError,
        },
      )
    } else {
      if (!selectedFile) {
        setError('Please select a file to upload')
        return
      }
      uploadScan.mutate(selectedFile, {
        onSuccess: () => {
          setOpen(false)
          resetForm()
        },
        onError: handleError,
      })
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(value) => {
        setOpen(value)
        if (!value) resetForm()
      }}
    >
      <DialogTrigger className={cn(buttonVariants({ variant: 'default' }))}>
        Trigger Scan
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Trigger Scan</DialogTitle>
        </DialogHeader>
        <form className="space-y-4" onSubmit={handleSubmit}>
          <div className="flex gap-2">
            <button
              type="button"
              className={cn(
                'flex-1 rounded-md border px-3 py-2 text-sm font-medium transition-colors',
                mode === 'github'
                  ? 'border-zinc-900 bg-zinc-900 text-white'
                  : 'border-zinc-200 bg-white text-zinc-600 hover:bg-zinc-50',
              )}
              onClick={() => {
                setMode('github')
                setError(null)
              }}
            >
              GitHub Repository
            </button>
            <button
              type="button"
              className={cn(
                'flex-1 rounded-md border px-3 py-2 text-sm font-medium transition-colors',
                mode === 'upload'
                  ? 'border-zinc-900 bg-zinc-900 text-white'
                  : 'border-zinc-200 bg-white text-zinc-600 hover:bg-zinc-50',
              )}
              onClick={() => {
                setMode('upload')
                setError(null)
              }}
            >
              Upload Project
            </button>
          </div>

          {mode === 'github' ? (
            <>
              <p className="text-xs text-zinc-500">
                Scan a GitHub repository via the GitHub API. Requires the GitHub App to be installed on the target repo.
              </p>
              <div className="space-y-1">
                <label className="text-sm font-medium text-zinc-700">Repository</label>
                <Input value={repo} onChange={(event) => setRepo(event.target.value)} placeholder="owner/repo" />
                <p className="text-xs text-zinc-400">The full repository name, e.g. octocat/hello-world</p>
              </div>
              <div className="space-y-1">
                <label className="text-sm font-medium text-zinc-700">Installation ID <span className="font-normal text-zinc-400">(optional)</span></label>
                <Input
                  value={installationId}
                  onChange={(event) => setInstallationId(event.target.value)}
                  placeholder="Auto-discovered from repo"
                  type="number"
                />
                <p className="text-xs text-zinc-400">
                  Leave blank to auto-discover. Only needed if auto-discovery fails.
                </p>
              </div>
            </>
          ) : (
            <>
              <p className="text-xs text-zinc-500">
                Upload a project archive to scan. Supports .zip, .tar.gz, .tgz, .tar.bz2, and .tar.xz formats. Max 200 MB.
              </p>
              <div className="space-y-1">
                <label className="text-sm font-medium text-zinc-700">Project Archive</label>
                <Input
                  type="file"
                  accept=".zip,.tar,.tar.gz,.tgz,.tar.bz2,.tar.xz"
                  onChange={(event) => {
                    setSelectedFile(event.target.files?.[0] ?? null)
                    setError(null)
                  }}
                />
                {selectedFile ? (
                  <p className="text-xs text-zinc-400">
                    Selected: {selectedFile.name} ({(selectedFile.size / (1024 * 1024)).toFixed(1)} MB)
                  </p>
                ) : null}
              </div>
            </>
          )}

          {error ? <p className="text-sm text-red-600">{error}</p> : null}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={isSubmitting}>
              {isSubmitting
                ? (mode === 'upload' ? 'Uploading…' : 'Triggering…')
                : (mode === 'upload' ? 'Upload & Scan' : 'Trigger')}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

function TriggerButton() {
  return <TriggerScanDialog />
}

export function ScansPage({ isSuperuser, onSelectScan }: ScansPageProps) {
  const [page, setPage] = useState(1)
  const [repo, setRepo] = useState('')
  const [state, setState] = useState('')
  const [kind, setKind] = useState('')

  const query = useMemo(
    () => ({ page, repo: repo.trim(), state, kind }),
    [page, repo, state, kind],
  )

  const scans = useScans(query)
  const items: ReviewRunRead[] = scans.data?.items ?? []
  const pageSize = scans.data?.page_size ?? 20
  const total = scans.data?.total ?? 0
  const totalPages = Math.max(1, Math.ceil(total / pageSize))

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-semibold tracking-tight">Scan Management</h2>
        {isSuperuser ? <TriggerButton /> : null}
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Filters</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid gap-3 md:grid-cols-4">
            <Input
              placeholder="Repo (owner/repo)"
              value={repo}
              onChange={(event) => {
                setRepo(event.target.value)
                setPage(1)
              }}
            />
            <Select
              value={state}
              onChange={(event) => {
                setState(event.target.value)
                setPage(1)
              }}
            >
              <option value="">All states</option>
              <option value="pending">pending</option>
              <option value="classifying">classifying</option>
              <option value="collecting">collecting</option>
              <option value="normalizing">normalizing</option>
              <option value="reasoning">reasoning</option>
              <option value="deciding">deciding</option>
              <option value="publishing">publishing</option>
              <option value="completed">completed</option>
              <option value="failed">failed</option>
              <option value="superseded">superseded</option>
            </Select>
            <Select
              value={kind}
              onChange={(event) => {
                setKind(event.target.value)
                setPage(1)
              }}
            >
              <option value="">All kinds</option>
              <option value="pr">pr</option>
              <option value="baseline">baseline</option>
            </Select>
            <div className="flex items-center justify-end">
              <Button
                variant="outline"
                onClick={() => {
                  setRepo('')
                  setState('')
                  setKind('')
                  setPage(1)
                }}
              >
                Reset
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="pt-6">
          {scans.isLoading ? <p className="text-sm text-zinc-500">Loading scans…</p> : null}
          {scans.isError ? <p className="text-sm text-red-600">Failed to load scans.</p> : null}

          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Repo</TableHead>
                <TableHead>Kind</TableHead>
                <TableHead>State</TableHead>
                <TableHead>Created</TableHead>
                <TableHead>Head SHA</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {items.map((scan) => (
                <TableRow
                  key={scan.id}
                  className="cursor-pointer"
                  onClick={() => onSelectScan(scan.id)}
                >
                  <TableCell className="font-medium">{scan.repo}</TableCell>
                  <TableCell>
                    <Badge className={cn('capitalize', kindBadgeClass(scan.run_kind))}>{scan.run_kind}</Badge>
                  </TableCell>
                  <TableCell>
                    <Badge className={cn('capitalize', stateBadgeClass(scan.state))}>{scan.state}</Badge>
                  </TableCell>
                  <TableCell>{formatDate(scan.created_at)}</TableCell>
                  <TableCell className="font-mono text-xs">{shortSha(scan.head_sha)}</TableCell>
                </TableRow>
              ))}
              {items.length === 0 && !scans.isLoading ? (
                <TableRow>
                  <TableCell colSpan={5} className="py-6 text-center text-zinc-500">
                    No scans found.
                  </TableCell>
                </TableRow>
              ) : null}
            </TableBody>
          </Table>

          <div className="mt-4 flex items-center justify-between">
            <Button variant="outline" onClick={() => setPage((value) => Math.max(1, value - 1))} disabled={page <= 1}>
              Prev
            </Button>
            <p className="text-sm text-zinc-600">
              Page {page} of {totalPages}
            </p>
            <Button
              variant="outline"
              onClick={() => setPage((value) => Math.min(totalPages, value + 1))}
              disabled={page >= totalPages}
            >
              Next
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
