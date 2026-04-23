import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { apiClient } from '@/lib/api-client'
import {
  cancelScanApiAdminScansScanIdCancelPost,
  deleteScanApiAdminScansScanIdDelete,
  getScanApiAdminScansScanIdGet,
  listScansApiAdminScansGet,
  triggerScanApiAdminScansTriggerPost,
} from '@/lib/api'

function normalizeError(error: unknown, fallback: string) {
  if (typeof error === 'object' && error !== null && 'detail' in error) {
    const detail = (error as { detail?: unknown }).detail
    if (typeof detail === 'string') return detail
  }
  return fallback
}

export function useScans(params: { page?: number; repo?: string; state?: string; kind?: string }) {
  return useQuery({
    queryKey: ['scans', params],
    queryFn: async () => {
      const result = await listScansApiAdminScansGet({
        client: apiClient,
        query: {
          page: params.page,
          page_size: 20,
          repo: params.repo || undefined,
          state: params.state || undefined,
          kind: params.kind || undefined,
        },
      })
      if (result.error) throw new Error('Failed to load scans')
      return result.data
    },
  })
}

export function useScanDetail(scanId: string | null) {
  return useQuery({
    queryKey: ['scan', scanId],
    enabled: Boolean(scanId),
    queryFn: async () => {
      if (!scanId) return null
      const result = await getScanApiAdminScansScanIdGet({
        client: apiClient,
        path: { scan_id: scanId },
      })
      if (result.error) throw new Error('Failed to load scan details')
      return result.data
    },
  })
}

export function useTriggerScan() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (body: { repo?: string; installation_id?: number }) => {
      const result = await triggerScanApiAdminScansTriggerPost({
        client: apiClient,
        body,
      })
      if (result.error) {
        throw new Error(normalizeError(result.error, 'Failed to trigger scan'))
      }
      return result.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['scans'] })
    },
  })
}

export function useUploadScan() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (file: File) => {
      const formData = new FormData()
      formData.append('file', file)

      const response = await fetch('/api/admin/scans/upload', {
        method: 'POST',
        body: formData,
        credentials: 'include',
      })

      if (!response.ok) {
        const body = await response.json().catch(() => null)
        const detail = body?.detail
        throw new Error(typeof detail === 'string' ? detail : `Upload failed (${response.status})`)
      }

      return response.json()
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['scans'] })
    },
  })
}

export function useCancelScan() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (scanId: string) => {
      const result = await cancelScanApiAdminScansScanIdCancelPost({
        client: apiClient,
        path: { scan_id: scanId },
      })
      if (result.error) {
        throw new Error(normalizeError(result.error, 'Failed to cancel scan'))
      }
      return result.data
    },
    onSuccess: (_data, scanId) => {
      queryClient.invalidateQueries({ queryKey: ['scans'] })
      queryClient.invalidateQueries({ queryKey: ['scan', scanId] })
    },
  })
}

export function useDeleteScan() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (scanId: string) => {
      const result = await deleteScanApiAdminScansScanIdDelete({
        client: apiClient,
        path: { scan_id: scanId },
      })
      if (result.error) {
        throw new Error(normalizeError(result.error, 'Failed to delete scan'))
      }
      return result.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['scans'] })
    },
  })
}

export function useExportReport() {
  return useMutation({
    mutationFn: async ({ scanId, format }: { scanId: string; format: 'markdown' | 'json' }) => {
      const response = await fetch(`/api/admin/scans/${scanId}/report?format=${format}`, {
        credentials: 'include',
      })

      if (!response.ok) {
        const body = await response.json().catch(() => null)
        const detail = body?.detail
        throw new Error(typeof detail === 'string' ? detail : `Export failed (${response.status})`)
      }

      const disposition = response.headers.get('Content-Disposition') || ''
      const filenameMatch = disposition.match(/filename="?([^"]+)"?/)
      const filename = filenameMatch?.[1] || `report.${format === 'json' ? 'json' : 'md'}`

      const blob = await response.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = filename
      document.body.appendChild(a)
      a.click()
      a.remove()
      URL.revokeObjectURL(url)
    },
  })
}
