import axios, { AxiosInstance, AxiosError } from 'axios'
import type {
  ChallengeResponse,
  AuthVerifyRequest,
  AuthVerifyResponse,
  Agent,
  AgentTokens,
  AuditLogDetail,
  AuditLogsResponse,
  DelegationGraphResponse,
  RevokeRequest,
  RevokeResponse,
} from '../types'

const BASE_URL = '/api/v1'

class ApiService {
  private client: AxiosInstance
  private sessionToken: string | null = null

  constructor() {
    this.client = axios.create({
      baseURL: BASE_URL,
      headers: {
        'Content-Type': 'application/json',
      },
    })

    this.client.interceptors.request.use((config) => {
      if (this.sessionToken) {
        config.headers.Authorization = `Bearer ${this.sessionToken}`
      }
      return config
    })

    this.client.interceptors.response.use(
      (response) => response,
      (error: AxiosError) => {
        if (error.response?.status === 401) {
          this.clearSession()
          window.location.href = '/login'
        }
        return Promise.reject(error)
      }
    )
  }

  setSessionToken(token: string) {
    this.sessionToken = token
  }

  clearSession() {
    this.sessionToken = null
  }

  hasSession(): boolean {
    return this.sessionToken !== null
  }

  // ============ Auth APIs ============
  async requestChallenge(agentId: string, certId: string): Promise<ChallengeResponse> {
    const response = await this.client.post<ChallengeResponse>('/ca/auth/challenge', {
      agent_id: agentId,
      cert_id: certId,
    })
    return response.data
  }

  async verifyChallenge(request: AuthVerifyRequest): Promise<AuthVerifyResponse> {
    const response = await this.client.post<AuthVerifyResponse>('/ca/auth/verify', request)
    this.sessionToken = response.data.session_token
    return response.data
  }

  // ============ Agent APIs ============
  async getAgent(agentId: string): Promise<Agent> {
    const response = await this.client.get<Agent>(`/agents/${agentId}`)
    return response.data
  }

  async getAgentTokens(agentId: string): Promise<AgentTokens> {
    const response = await this.client.get<AgentTokens>(`/agents/${agentId}/tokens`)
    return response.data
  }

  async getAllAgents(): Promise<Agent[]> {
    // Get agents from audit logs and delegation graph
    // Since there's no direct "list all agents" API, we gather from multiple sources
    const graph = await this.getDelegationGraph()
    const agentIds = new Set<string>()
    graph.nodes.forEach((node) => agentIds.add(node.id))

    const agents: Agent[] = []
    for (const id of Array.from(agentIds)) {
      try {
        const agent = await this.getAgent(id)
        agents.push(agent)
      } catch {
        // Agent might not be accessible
      }
    }
    return agents
  }

  // ============ Certificate APIs ============
  async revokeCertificate(request: RevokeRequest): Promise<RevokeResponse> {
    const response = await this.client.post<RevokeResponse>('/ca/revoke', request)
    return response.data
  }

  async getCRL(): Promise<{ entries: Array<{ cert_id: string; revoked_at: string; reason: string }> }> {
    const response = await this.client.get('/ca/crl')
    return response.data
  }

  // ============ Audit APIs ============
  async getAuditLogs(params: {
    agent_id?: string
    action?: string
    result?: string
    start_time?: string
    end_time?: string
    page?: number
    page_size?: number
  }): Promise<AuditLogsResponse> {
    const response = await this.client.get<AuditLogsResponse>('/audit/logs', { params })
    return response.data
  }

  async getAuditLogDetail(logId: string): Promise<AuditLogDetail> {
    const response = await this.client.get<AuditLogDetail>(`/audit/logs/${logId}`)
    return response.data
  }

  async getDelegationGraph(): Promise<DelegationGraphResponse> {
    const response = await this.client.get<DelegationGraphResponse>('/audit/delegation-graph')
    return response.data
  }

  async getAlertStatus(): Promise<{ denied_count: number; threshold: number; alerting: boolean }> {
    const response = await this.client.get('/audit/alert-status')
    return response.data
  }
}

export const apiService = new ApiService()
export default apiService
