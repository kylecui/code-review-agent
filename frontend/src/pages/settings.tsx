import { useMemo, useState } from 'react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { useResetSetting, useSettings, useUpdateSettings } from '@/hooks/use-settings'

type SettingItem = {
  key: string
  label: string
}

const sections: Array<{ title: string; items: SettingItem[] }> = [
  {
    title: 'LLM Configuration',
    items: [
      { key: 'llm_classify_model', label: 'Classify Model' },
      { key: 'llm_synthesize_model', label: 'Synthesize Model' },
      { key: 'llm_fallback_model', label: 'Fallback Model' },
      { key: 'llm_max_tokens', label: 'Max Tokens' },
      { key: 'llm_temperature', label: 'Temperature' },
      { key: 'llm_cost_budget_per_run_cents', label: 'Cost Budget per Run (cents)' },
    ],
  },
  {
    title: 'Collectors',
    items: [
      { key: 'semgrep_mode', label: 'Semgrep Mode' },
      { key: 'semgrep_severity_filter', label: 'Semgrep Severity Filter' },
    ],
  },
  {
    title: 'Limits',
    items: [
      { key: 'max_inline_comments', label: 'Max Inline Comments' },
      { key: 'max_diff_lines', label: 'Max Diff Lines' },
    ],
  },
  {
    title: 'Observability',
    items: [{ key: 'log_level', label: 'Log Level' }],
  },
]

function sourceBadgeClass(source: string) {
  return source === 'env'
    ? 'bg-blue-100 text-blue-800 border-blue-200'
    : 'bg-emerald-100 text-emerald-800 border-emerald-200'
}

export function SettingsPage() {
  const settingsQuery = useSettings()
  const updateSettings = useUpdateSettings()
  const resetSetting = useResetSetting()
  const [draftValues, setDraftValues] = useState<Record<string, string>>({})
  const [errorMessage, setErrorMessage] = useState<string | null>(null)

  const settings = settingsQuery.data ?? {}

  const hasChanges = useMemo(() => {
    return Object.entries(draftValues).some(([key, value]) => {
      const current = settings[key]?.value
      return String(current ?? '') !== value
    })
  }, [draftValues, settings])

  const setDraft = (key: string, value: string) => {
    setDraftValues((prev) => ({ ...prev, [key]: value }))
  }

  const saveAll = () => {
    setErrorMessage(null)

    const payload: Record<string, unknown> = {}
    Object.entries(draftValues).forEach(([key, value]) => {
      const original = settings[key]?.value
      if (String(original ?? '') !== value) {
        if (typeof original === 'number') {
          const asNumber = Number(value)
          payload[key] = Number.isNaN(asNumber) ? value : asNumber
        } else if (typeof original === 'boolean') {
          payload[key] = value === 'true'
        } else {
          payload[key] = value
        }
      }
    })

    if (Object.keys(payload).length === 0) return

    updateSettings.mutate(payload, {
      onSuccess: () => {
        setDraftValues({})
      },
      onError: (error) => {
        if (error instanceof Error) {
          setErrorMessage(error.message)
        } else {
          setErrorMessage('Failed to save settings')
        }
      },
    })
  }

  if (settingsQuery.isLoading) {
    return <p className="text-zinc-500">Loading settings…</p>
  }

  if (settingsQuery.isError) {
    return <p className="text-red-600">Failed to load settings.</p>
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-semibold tracking-tight">Settings</h2>
        <Button onClick={saveAll} disabled={!hasChanges || updateSettings.isPending}>
          {updateSettings.isPending ? 'Saving…' : 'Save All'}
        </Button>
      </div>

      {errorMessage ? <p className="text-sm text-red-600">{errorMessage}</p> : null}

      {sections.map((section) => (
        <Card key={section.title}>
          <CardHeader>
            <CardTitle>{section.title}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {section.items.map((item) => {
              const setting = settings[item.key]
              const value = draftValues[item.key] ?? String(setting?.value ?? '')
              const source = setting?.source ?? 'env'

              return (
                <div key={item.key} className="grid gap-2 rounded-md border border-zinc-200 p-3 md:grid-cols-[260px_1fr_auto_auto] md:items-center">
                  <div>
                    <p className="text-sm font-medium">{item.label}</p>
                    <p className="text-xs text-zinc-500">{item.key}</p>
                  </div>

                  <Input value={value} onChange={(event) => setDraft(item.key, event.target.value)} />

                  <Badge className={sourceBadgeClass(source)}>{source}</Badge>

                  <Button
                    variant="outline"
                    disabled={resetSetting.isPending || source !== 'db'}
                    onClick={() => {
                      setErrorMessage(null)
                      resetSetting.mutate(item.key, {
                        onError: (error) => {
                          if (error instanceof Error) {
                            setErrorMessage(error.message)
                          } else {
                            setErrorMessage('Failed to reset setting')
                          }
                        },
                      })
                    }}
                  >
                    Reset to Default
                  </Button>
                </div>
              )
            })}
          </CardContent>
        </Card>
      ))}
    </div>
  )
}
