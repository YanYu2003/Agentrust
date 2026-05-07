// API Types for Agentrust Dashboard

// ============ Auth Types ============
export interface ChallengeResponse {
  challenge_id: string
  nonce: string
  expires_at: string
}

export interface AuthVerifyRequest {
  challenge_id: string
  agent_id: string
  signed_nonce: string
}

export interface AuthVerifyResponse {
  session_token: string
  expires_at: string
  agent_id: string
}

// ============ Agent Types ============
export interface Agent {
  agent_id: string
  name: string
  description: string
  owner: string
  trust_level: number
  status: 'active' | 'suspended' | 'revoked'
  registered_at: string
  certificates: Certificate[]
  active_capability_tokens: number
  active_delegations_from: number
  active_delegations_to: number
}

export interface Certificate {
  cert_id: string
  status: 'valid' | 'expired' | 'revoked'
  capabilities: string[]
  expires_at: string
  public_key?: string
  issued_at?: string
  trust_level?: number
}

// ============ Token Types ============
export interface CapabilityToken {
  token_id: string
  capability: string
  resource_scope: string
  attenuations: Record<string, unknown>
  expires_at: string
  status: 'active'
}

export interface DelegationToken {
  delegation_id: string
  from_agent_id: string
  to_agent_id: string
  capability: string
  resource_scope: string
  attenuations: Record<string, unknown>
  max_depth: number
  current_depth: number
  issued_at: string
  expires_at: string
  from_signature: string
  status: 'active'
}

export interface AgentTokens {
  agent_id: string
  capability_tokens: CapabilityToken[]
  delegation_tokens_received: DelegationToken[]
  delegation_tokens_issued: DelegationToken[]
}

// ============ Audit Types ============
export interface AuditLog {
  log_id: string
  agent_id: string
  parent_agent_id?: string | null
  task_id?: string | null
  action: string
  resource: string
  result: 'ALLOWED' | 'DENIED' | 'ERROR'
  delegation_chain_summary: string | null
  created_at: string
  token_chain?: TokenChainItem[]
  request_context?: Record<string, unknown>
  error_detail?: string | null
}

export interface TokenChainItem {
  type: 'certificate' | 'capability' | 'delegation'
  cert_id?: string
  agent?: string
  token_id?: string
  capability?: string
  delegation_id?: string
  from?: string
  to?: string
  attenuations?: Record<string, unknown>
}

export interface AuditLogDetail extends AuditLog {
  token_chain: TokenChainItem[]
  request_context: Record<string, unknown>
  task_context?: Record<string, unknown>
}

export interface AuditLogsResponse {
  total: number
  page: number
  page_size: number
  logs: AuditLog[]
}

// ============ Delegation Graph Types ============
export interface GraphNode {
  id: string
  name: string
  trust_level: number
  status: 'active'
}

export interface GraphEdge {
  from_agent: string
  to_agent: string
  delegation_id: string
  capability: string
  attenuations: Record<string, unknown>
  status: 'active'
  expires_at: string
}

export interface DelegationGraphResponse {
  nodes: GraphNode[]
  edges: GraphEdge[]
}

export interface TaskTraceStep {
  log_id: string
  agent_id: string
  parent_agent_id: string | null
  task_id: string | null
  action: string
  resource: string
  result: 'ALLOWED' | 'DENIED' | 'ERROR'
  request_context: Record<string, unknown>
  task_context: Record<string, unknown>
  error_detail: string | null
  created_at: string
}

export interface TaskTraceResponse {
  task_id: string
  total_steps: number
  trace: TaskTraceStep[]
}

export interface RecentTaskSummary {
  task_id: string
  step_count: number
  last_at: string
}

export interface RecentTasksResponse {
  tasks: RecentTaskSummary[]
}

// ============ Revoke Types ============
export interface RevokeRequest {
  cert_id: string
  reason: string
}

export interface RevokeResponse {
  cert_id: string
  status: 'revoked'
  revoked_at: string
}

// ============ API Error Types ============
export interface ApiError {
  error: {
    code: string
    message: string
    details?: Record<string, unknown>
    request_id?: string
    timestamp?: string
  }
}
