import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { apiClient } from '@/lib/api-client'
import {
  createUserApiAdminUsersPost,
  deactivateUserApiAdminUsersUserIdDelete,
  listUsersApiAdminUsersGet,
  updateUserApiAdminUsersUserIdPatch,
  type UserCreate,
  type UserUpdate,
} from '@/lib/api'

function normalizeError(error: unknown, fallback: string) {
  if (typeof error === 'object' && error !== null && 'detail' in error) {
    const detail = (error as { detail?: unknown }).detail
    if (typeof detail === 'string') return detail
  }
  return fallback
}

export function useUsers() {
  return useQuery({
    queryKey: ['users'],
    queryFn: async () => {
      const result = await listUsersApiAdminUsersGet({
        client: apiClient,
        query: { skip: 0, limit: 100 },
      })
      if (result.error) throw new Error('Failed to load users')
      return result.data ?? []
    },
  })
}

export function useCreateUser() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (body: UserCreate) => {
      const result = await createUserApiAdminUsersPost({ client: apiClient, body })
      if (result.error) {
        throw new Error(normalizeError(result.error, 'Failed to create user'))
      }
      return result.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['users'] })
    },
  })
}

export function useUpdateUser() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({ userId, body }: { userId: string; body: UserUpdate }) => {
      const result = await updateUserApiAdminUsersUserIdPatch({
        client: apiClient,
        path: { user_id: userId },
        body,
      })
      if (result.error) {
        throw new Error(normalizeError(result.error, 'Failed to update user'))
      }
      return result.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['users'] })
    },
  })
}

export function useDeactivateUser() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (userId: string) => {
      const result = await deactivateUserApiAdminUsersUserIdDelete({
        client: apiClient,
        path: { user_id: userId },
      })
      if (result.error) {
        throw new Error(normalizeError(result.error, 'Failed to deactivate user'))
      }
      return result.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['users'] })
    },
  })
}
