import { useState } from 'react'

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
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { useDeletePolicy, usePolicies, useSavePolicy, useSeedPolicies } from '@/hooks/use-policies'
import { buttonVariants } from '@/components/ui/button'
import { cn } from '@/lib/utils'

interface PoliciesPageProps {
  onEditPolicy: (name: string) => void
}

function formatDate(value?: string) {
  if (!value) return '—'
  return new Date(value).toLocaleString()
}

function CreatePolicyDialog({ onCreate }: { onCreate: (name: string) => void }) {
  const [open, setOpen] = useState(false)
  const [name, setName] = useState('')
  const savePolicy = useSavePolicy()
  const [errorMessage, setErrorMessage] = useState<string | null>(null)

  const handleCreate = () => {
    if (!name.trim()) return
    setErrorMessage(null)

    savePolicy.mutate(
      {
        name: name.trim(),
        content: 'version: 1\nprofiles:\n  default:\n    blocking_categories:\n      - "security.*"\n',
      },
      {
        onSuccess: () => {
          setOpen(false)
          onCreate(name.trim())
          setName('')
        },
        onError: (error) => {
          if (error instanceof Error) {
            setErrorMessage(error.message)
          } else {
            setErrorMessage('Failed to create policy')
          }
        },
      },
    )
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger className={cn(buttonVariants({ variant: 'default' }))}>Create Policy</DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Create Policy</DialogTitle>
        </DialogHeader>

        <div className="space-y-3">
          <Input value={name} onChange={(event) => setName(event.target.value)} placeholder="default.policy" />
          {errorMessage ? <p className="text-sm text-red-600">{errorMessage}</p> : null}
        </div>

        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => setOpen(false)}>
            Cancel
          </Button>
          <Button type="button" onClick={handleCreate} disabled={savePolicy.isPending || !name.trim()}>
            {savePolicy.isPending ? 'Creating…' : 'Create'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export function PoliciesPage({ onEditPolicy }: PoliciesPageProps) {
  const policiesQuery = usePolicies()
  const deletePolicy = useDeletePolicy()
  const seedPolicies = useSeedPolicies()
  const [errorMessage, setErrorMessage] = useState<string | null>(null)

  const policies = policiesQuery.data ?? []

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-semibold tracking-tight">Policies</h2>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            onClick={() => seedPolicies.mutate()}
            disabled={seedPolicies.isPending}
          >
            {seedPolicies.isPending ? 'Seeding…' : 'Seed from Disk'}
          </Button>
          <CreatePolicyDialog onCreate={onEditPolicy} />
        </div>
      </div>

      {errorMessage ? <p className="text-sm text-red-600">{errorMessage}</p> : null}

      <Card>
        <CardHeader>
          <CardTitle>Policy Files</CardTitle>
        </CardHeader>
        <CardContent>
          {policiesQuery.isLoading ? <p className="text-sm text-zinc-500">Loading policies…</p> : null}
          {policiesQuery.isError ? <p className="text-sm text-red-600">Failed to load policies.</p> : null}

          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Updated At</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {policies.map((policy) => (
                <TableRow key={policy.name}>
                  <TableCell className="font-medium">{policy.name}</TableCell>
                  <TableCell>{formatDate(policy.updated_at)}</TableCell>
                  <TableCell>
                    <div className="flex justify-end gap-2">
                      <Button variant="outline" onClick={() => onEditPolicy(policy.name)}>
                        Edit
                      </Button>
                      <Button
                        variant="destructive"
                        onClick={() => {
                          setErrorMessage(null)
                          deletePolicy.mutate(policy.name, {
                            onError: (error) => {
                              if (error instanceof Error) {
                                setErrorMessage(error.message)
                              } else {
                                setErrorMessage('Failed to delete policy')
                              }
                            },
                          })
                        }}
                        disabled={deletePolicy.isPending}
                      >
                        Delete
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
              {policies.length === 0 && !policiesQuery.isLoading ? (
                <TableRow>
                  <TableCell colSpan={3} className="py-6 text-center text-zinc-500">
                    No policies yet.
                  </TableCell>
                </TableRow>
              ) : null}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  )
}
