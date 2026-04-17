import { useState, useCallback, useEffect } from 'react'
import { message } from 'antd'
import apiService from '../services/api'
// AuthVerifyResponse - imported for type documentation

const AUTH_STORAGE_KEY = 'agentrust_session_token'
const AGENT_ID_KEY = 'agentrust_agent_id'
const CERT_ID_KEY = 'agentrust_cert_id'

export interface AuthState {
  isAuthenticated: boolean
  agentId: string | null
  certId: string | null
  sessionToken: string | null
  expiresAt: string | null
}

export function useAuth() {
  const [authState, setAuthState] = useState<AuthState>(() => {
    const token = localStorage.getItem(AUTH_STORAGE_KEY)
    const agentId = localStorage.getItem(AGENT_ID_KEY)
    const certId = localStorage.getItem(CERT_ID_KEY)
    return {
      isAuthenticated: !!token,
      agentId,
      certId,
      sessionToken: token,
      expiresAt: null,
    }
  })

  useEffect(() => {
    if (authState.sessionToken) {
      apiService.setSessionToken(authState.sessionToken)
    }
  }, [authState.sessionToken])

  const login = useCallback(
    async (agentId: string, certId: string, signedNonce: string, _expiresAt: string) => {
      try {
        const result = await apiService.verifyChallenge({
          challenge_id: '', // Will be set by challenge-response
          agent_id: agentId,
          signed_nonce: signedNonce,
        })

        const newState: AuthState = {
          isAuthenticated: true,
          agentId,
          certId,
          sessionToken: result.session_token,
          expiresAt: result.expires_at,
        }

        setAuthState(newState)
        localStorage.setItem(AUTH_STORAGE_KEY, result.session_token)
        localStorage.setItem(AGENT_ID_KEY, agentId)
        localStorage.setItem(CERT_ID_KEY, certId)

        message.success('登录成功')
        return result
      } catch (error: unknown) {
        const err = error as { response?: { data?: { error?: { message?: string } } } }
        message.error(err.response?.data?.error?.message || '认证失败')
        throw error
      }
    },
    []
  )

  const logout = useCallback(() => {
    setAuthState({
      isAuthenticated: false,
      agentId: null,
      certId: null,
      sessionToken: null,
      expiresAt: null,
    })
    apiService.clearSession()
    localStorage.removeItem(AUTH_STORAGE_KEY)
    localStorage.removeItem(AGENT_ID_KEY)
    localStorage.removeItem(CERT_ID_KEY)
    message.info('已退出登录')
  }, [])

  const refreshSession = useCallback(
    async (agentId: string, certId: string) => {
      try {
        // Step 1: Get challenge
        const challenge = await apiService.requestChallenge(agentId, certId)

        // Step 2: For demo purposes, we'll skip actual signing
        // In production, the wallet would sign the nonce
        message.warning('请使用 Agent SDK 进行实际签名认证')
        return challenge
      } catch (error: unknown) {
        const err = error as { response?: { data?: { error?: { message?: string } } } }
        message.error(err.response?.data?.error?.message || '会话刷新失败')
        throw error
      }
    },
    []
  )

  return {
    ...authState,
    login,
    logout,
    refreshSession,
  }
}
