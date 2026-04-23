import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { apiClient } from '@/lib/api-client'
import {
  deleteSettingApiAdminSettingsKeyDelete,
  getSettingsApiAdminSettingsGet,
  updateSettingsApiAdminSettingsPut,
} from '@/lib/api'

type SettingsRecord = Record<string, { value: unknown; source: 'env' | 'db' | string; is_set?: boolean }>

function normalizeError(error: unknown, fallback: string) {
  if (typeof error === 'object' && error !== null && 'detail' in error) {
    const detail = (error as { detail?: unknown }).detail
    if (typeof detail === 'string') return detail
  }
  return fallback
}

export function useSettings() {
  return useQuery({
    queryKey: ['settings'],
    queryFn: async () => {
      const result = await getSettingsApiAdminSettingsGet({ client: apiClient })
      if (result.error || !result.data) throw new Error('Failed to load settings')

      const payload = result.data as { settings?: SettingsRecord }
      return payload.settings ?? {}
    },
  })
}

export function useUpdateSettings() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (body: Record<string, unknown>) => {
      const result = await updateSettingsApiAdminSettingsPut({ client: apiClient, body })
      if (result.error) {
        throw new Error(normalizeError(result.error, 'Failed to update settings'))
      }
      return result.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings'] })
    },
  })
}

type ProviderModels = {
  available: boolean
  models?: string[]
  error?: string
}
type ModelsResponse = {
  providers: Record<string, ProviderModels>
}

export function useAvailableModels() {
  return useQuery({
    queryKey: ['settings-models'],
    queryFn: async () => {
      const resp = await fetch('/api/admin/settings/models', {
        credentials: 'include',
      })
      if (!resp.ok) throw new Error('Failed to load models')
      const data: ModelsResponse = await resp.json()
      return data.providers ?? {}
    },
    staleTime: 60_000,
  })
}

export function useResetSetting() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (key: string) => {
      const result = await deleteSettingApiAdminSettingsKeyDelete({
        client: apiClient,
        path: { key },
      })
      if (result.error) {
        throw new Error(normalizeError(result.error, 'Failed to reset setting'))
      }
      return result.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings'] })
    },
  })
}
