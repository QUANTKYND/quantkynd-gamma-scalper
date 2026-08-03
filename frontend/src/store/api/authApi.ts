import { createApi, fetchBaseQuery } from '@reduxjs/toolkit/query/react'
import { API_BASE } from './base'

export type AuthConnectionStatus = {
  broker: string
  status: 'connected' | 'disconnected' | 'error'
  connected: boolean
  profile?: Record<string, unknown> | null
  error?: string | null
}

export const getUpstoxLoginUrl = (): string => `${API_BASE}/auth/upstox/login`

export const authApi = createApi({
  reducerPath: 'authApi',
  baseQuery: fetchBaseQuery({ baseUrl: API_BASE }),
  tagTypes: ['AuthStatus'],
  endpoints: (builder) => ({
    getAuthStatus: builder.query<AuthConnectionStatus, void>({
      query: () => '/auth/status',
      providesTags: ['AuthStatus'],
    }),
    disconnectAuth: builder.mutation<AuthConnectionStatus, void>({
      query: () => ({
        url: '/auth/disconnect',
        method: 'POST',
      }),
      invalidatesTags: ['AuthStatus'],
    }),
  }),
})

export const { useGetAuthStatusQuery, useDisconnectAuthMutation } = authApi
