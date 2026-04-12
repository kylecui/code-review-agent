import { useEffect, useMemo, useState } from 'react'
import Editor from '@monaco-editor/react'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { useDeletePolicy, usePolicy, useSavePolicy } from '@/hooks/use-policies'

interface PolicyEditorPageProps {
  policyName: string
  onBack: () => void
}

export function PolicyEditorPage({ policyName, onBack }: PolicyEditorPageProps) {
  const policyQuery = usePolicy(policyName)
  const savePolicy = useSavePolicy()
  const deletePolicy = useDeletePolicy()

  const [content, setContent] = useState('')
  const [saveError, setSaveError] = useState<string | null>(null)
  const [validationError, setValidationError] = useState<string | null>(null)

  const etag = useMemo(() => policyQuery.data?.etag ?? '', [policyQuery.data?.etag])

  useEffect(() => {
    if (policyQuery.data) {
      setContent(policyQuery.data.content)
    }
  }, [policyQuery.data])

  if (policyQuery.isLoading) {
    return <p className="text-zinc-500">Loading policy…</p>
  }

  if (policyQuery.isError || !policyQuery.data) {
    return (
      <div className="space-y-3">
        <p className="text-red-600">Failed to load policy.</p>
        <Button variant="outline" onClick={onBack}>
          Back
        </Button>
      </div>
    )
  }

  const hasChanges = content !== policyQuery.data.content

  const onSave = () => {
    setSaveError(null)
    setValidationError(null)

    savePolicy.mutate(
      {
        name: policyName,
        content,
        etag,
      },
      {
        onError: (error) => {
          if (!(error instanceof Error)) {
            setSaveError('Failed to save policy')
            return
          }

          if (error.message.includes('modified by another user')) {
            setSaveError('Policy was modified by another user. Please refresh and try again.')
            return
          }

          if (error.message.toLowerCase().includes('yaml') || error.message.toLowerCase().includes('validation')) {
            setValidationError(error.message)
            return
          }

          setSaveError(error.message)
        },
      },
    )
  }

  const onDelete = () => {
    const confirmed = window.confirm(`Delete policy \"${policyName}\"? This cannot be undone.`)
    if (!confirmed) return

    deletePolicy.mutate(policyName, {
      onSuccess: onBack,
      onError: (error) => {
        if (error instanceof Error) {
          setSaveError(error.message)
        } else {
          setSaveError('Failed to delete policy')
        }
      },
    })
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-semibold tracking-tight">Policy Editor: {policyName}</h2>
        <div className="flex gap-2">
          <Button variant="outline" onClick={onBack}>
            Back
          </Button>
          <Button variant="destructive" onClick={onDelete} disabled={deletePolicy.isPending}>
            {deletePolicy.isPending ? 'Deleting…' : 'Delete'}
          </Button>
          <Button onClick={onSave} disabled={savePolicy.isPending || !hasChanges}>
            {savePolicy.isPending ? 'Saving…' : 'Save'}
          </Button>
        </div>
      </div>

      {saveError ? <p className="text-sm text-red-600">{saveError}</p> : null}

      <Card>
        <CardHeader>
          <CardTitle>YAML Policy</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <Editor
            height="68vh"
            defaultLanguage="yaml"
            language="yaml"
            value={content}
            onChange={(value) => setContent(value ?? '')}
            options={{
              minimap: { enabled: false },
              fontSize: 13,
              lineNumbers: 'on',
              wordWrap: 'on',
              automaticLayout: true,
            }}
          />

          {validationError ? <p className="text-sm text-red-600">{validationError}</p> : null}
        </CardContent>
      </Card>
    </div>
  )
}
