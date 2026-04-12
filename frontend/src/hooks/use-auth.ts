import { useMutation, useQueryClient } from '@tanstack/react-query'
import { apiClient } from '@/lib/api-client'
import {
  loginApiAuthLoginPost,
  logoutApiAuthLogoutPost,
  registerApiAuthRegisterPost,
} from '@/lib/api'

interface LoginParams {
  email: string
  password: string
}

interface RegisterParams {
  email: string
  password: string
  full_name?: string
}

function toErrorMessage(error: unknown, fallback: string) {
  if (typeof error === 'object' && error !== null && 'detail' in error) {
    const detail = (error as { detail?: unknown }).detail
    if (typeof detail === 'string') {
      return detail
    }
  }
  return fallback
}

export function useLogin() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (params: LoginParams) => {
      const result = await loginApiAuthLoginPost({
        body: params,
        client: apiClient,
      })

      if (result.error) {
        throw new Error(toErrorMessage(result.error, 'Login failed'))
      }

      return result.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['currentUser'] })
    },
  })
}

export function useRegister() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (params: RegisterParams) => {
      const result = await registerApiAuthRegisterPost({
        body: params,
        client: apiClient,
      })

      if (result.error) {
        throw new Error(toErrorMessage(result.error, 'Registration failed'))
      }

      return result.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['currentUser'] })
    },
  })
}

export function useLogout() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async () => {
      const result = await logoutApiAuthLogoutPost({ client: apiClient })
      if (result.error) {
        throw new Error('Logout failed')
      }
    },
    onSuccess: () => {
      queryClient.setQueryData(['currentUser'], null)
    },
  })
}
