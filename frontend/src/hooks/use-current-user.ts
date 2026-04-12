import { useQuery } from '@tanstack/react-query'
import { apiClient } from '@/lib/api-client'
import { meApiAuthMeGet } from '@/lib/api'
import type { UserRead } from '@/lib/api'

export function useCurrentUser() {
  return useQuery<UserRead | null>({
    queryKey: ['currentUser'],
    queryFn: async () => {
      const result = await meApiAuthMeGet({ client: apiClient })
      if (result.error) {
        return null
      }
      return result.data ?? null
    },
    retry: false,
    staleTime: 5 * 60 * 1000,
  })
}
