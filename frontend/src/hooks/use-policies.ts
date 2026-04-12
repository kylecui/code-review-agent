import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { apiClient } from '@/lib/api-client'
import {
  deletePolicyApiAdminPoliciesNameDelete,
  getPolicyApiAdminPoliciesNameGet,
  listPoliciesApiAdminPoliciesGet,
  putPolicyApiAdminPoliciesNamePut,
  seedPoliciesApiAdminPoliciesSeedPost,
} from '@/lib/api'

type PolicyListItem = {
  name: string
  updated_at?: string
}

type PolicyRead = {
  name: string
  content: string
  etag: string
}

function normalizeError(error: unknown, fallback: string) {
  if (typeof error === 'object' && error !== null && 'detail' in error) {
    const detail = (error as { detail?: unknown }).detail
    if (typeof detail === 'string') return detail
    if (typeof detail === 'object' && detail !== null && 'message' in detail) {
      const message = (detail as { message?: unknown }).message
      if (typeof message === 'string') return message
    }
  }
  return fallback
}

export function usePolicies() {
  return useQuery({
    queryKey: ['policies'],
    queryFn: async () => {
      const result = await listPoliciesApiAdminPoliciesGet({ client: apiClient })
      if (result.error) throw new Error('Failed to load policies')
      return (result.data ?? []) as PolicyListItem[]
    },
  })
}

export function usePolicy(name: string | null) {
  return useQuery({
    queryKey: ['policy', name],
    enabled: Boolean(name),
    queryFn: async () => {
      if (!name) return null

      const result = await getPolicyApiAdminPoliciesNameGet({
        client: apiClient,
        path: { name },
      })

      if (result.error) {
        throw new Error(normalizeError(result.error, 'Failed to load policy'))
      }

      const data = (result.data ?? {}) as Record<string, unknown>
      const etagHeader = result.response.headers.get('etag')
      const etag = typeof data.etag === 'string' ? data.etag : etagHeader?.replace(/"/g, '')

      return {
        name: String(data.name ?? name),
        content: String(data.content ?? ''),
        etag: etag ?? '',
      } as PolicyRead
    },
  })
}

export function useSavePolicy() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({ name, content, etag }: { name: string; content: string; etag?: string }) => {
      const result = await putPolicyApiAdminPoliciesNamePut({
        client: apiClient,
        path: { name },
        body: { content },
        headers: {
          'If-Match': etag ? `"${etag}"` : undefined,
        },
      })
      if (result.error) {
        const error = result.error as { detail?: unknown }
        if (typeof error.detail === 'object' && error.detail !== null && 'message' in error.detail) {
          const message = (error.detail as { message?: unknown }).message
          if (message === 'ETag mismatch') {
            throw new Error('Policy was modified by another user. Please refresh and try again.')
          }
        }
        throw new Error(normalizeError(result.error, 'Failed to save policy'))
      }
      return result.data as PolicyRead
    },
    onSuccess: (data, variables) => {
      queryClient.invalidateQueries({ queryKey: ['policies'] })
      queryClient.invalidateQueries({ queryKey: ['policy', variables.name] })
      if (data) {
        queryClient.setQueryData(['policy', variables.name], data)
      }
    },
  })
}

export function useDeletePolicy() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (name: string) => {
      const result = await deletePolicyApiAdminPoliciesNameDelete({
        client: apiClient,
        path: { name },
      })
      if (result.error) {
        throw new Error(normalizeError(result.error, 'Failed to delete policy'))
      }
      return result.data
    },
    onSuccess: (_data, name) => {
      queryClient.invalidateQueries({ queryKey: ['policies'] })
      queryClient.removeQueries({ queryKey: ['policy', name] })
    },
  })
}

export function useSeedPolicies() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async () => {
      const result = await seedPoliciesApiAdminPoliciesSeedPost({ client: apiClient })
      if (result.error) {
        throw new Error(normalizeError(result.error, 'Failed to seed policies'))
      }
      return result.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['policies'] })
    },
  })
}

export type { PolicyListItem, PolicyRead }
