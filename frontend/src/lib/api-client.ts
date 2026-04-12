import { createClient } from '@/lib/api/client'

export const apiClient = createClient({
  baseUrl: '',
  credentials: 'include',
})
