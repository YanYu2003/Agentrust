import React, { useState } from 'react'
import {
  Table,
  Tag,
  Button,
  Modal,
  Descriptions,
  Space,
  Typography,
  Popconfirm,
  message,
  Alert,
  Empty,
} from 'antd'
import {
  SafetyCertificateOutlined,
  ExclamationCircleOutlined,
  CheckCircleOutlined,
  ClockCircleOutlined,
  StopOutlined,
} from '@ant-design/icons'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import apiService from '../../services/api'
import type { Agent, Certificate } from '../../types'

const { Title, Text } = Typography

const statusConfig = {
  valid: { color: 'green', icon: <CheckCircleOutlined />, text: '有效' },
  expired: { color: 'orange', icon: <ClockCircleOutlined />, text: '已过期' },
  revoked: { color: 'red', icon: <StopOutlined />, text: '已吊销' },
}

const trustLevelColors: Record<number, string> = {
  1: 'orange',
  2: 'blue',
  3: 'cyan',
  4: 'green',
  5: 'purple',
}

interface CertDetailModalProps {
  agent: Agent | null
  cert: Certificate | null
  open: boolean
  onClose: () => void
}

const CertDetailModal: React.FC<CertDetailModalProps> = ({ agent, cert, open, onClose }) => {
  if (!agent || !cert) return null

  return (
    <Modal
      title={
        <Space>
          <SafetyCertificateOutlined />
          证书详情
        </Space>
      }
      open={open}
      onCancel={onClose}
      footer={null}
      width={600}
    >
      <Descriptions column={2} bordered size="small">
        <Descriptions.Item label="Agent ID" span={2}>
          <Text code>{agent.agent_id}</Text>
        </Descriptions.Item>
        <Descriptions.Item label="Agent 名称">{agent.name}</Descriptions.Item>
        <Descriptions.Item label="信任等级">
          <Tag color={trustLevelColors[agent.trust_level]}>Level {agent.trust_level}</Tag>
        </Descriptions.Item>
        <Descriptions.Item label="证书 ID" span={2}>
          <Text code>{cert.cert_id}</Text>
        </Descriptions.Item>
        <Descriptions.Item label="证书状态">
          <Tag color={statusConfig[cert.status].color}>
            {statusConfig[cert.status].icon} {statusConfig[cert.status].text}
          </Tag>
        </Descriptions.Item>
        <Descriptions.Item label="签发时间">
          {cert.issued_at ? new Date(cert.issued_at).toLocaleString() : '-'}
        </Descriptions.Item>
        <Descriptions.Item label="过期时间" span={2}>
          {new Date(cert.expires_at).toLocaleString()}
        </Descriptions.Item>
        <Descriptions.Item label="持有者">{agent.owner}</Descriptions.Item>
        <Descriptions.Item label="描述">{agent.description || '-'}</Descriptions.Item>
        <Descriptions.Item label="拥有能力" span={2}>
          <Space wrap>
            {cert.capabilities.map((cap) => (
              <Tag key={cap} color="blue">
                {cap}
              </Tag>
            ))}
          </Space>
        </Descriptions.Item>
        {cert.public_key && (
          <Descriptions.Item label="公钥" span={2}>
            <Text code style={{ fontSize: 10, wordBreak: 'break-all' }}>
              {cert.public_key.substring(0, 64)}...
            </Text>
          </Descriptions.Item>
        )}
      </Descriptions>
    </Modal>
  )
}

const CertView: React.FC = () => {
  const [selectedCert, setSelectedCert] = useState<Certificate | null>(null)
  const [selectedAgent, setSelectedAgent] = useState<Agent | null>(null)
  const [detailModalOpen, setDetailModalOpen] = useState(false)

  const queryClient = useQueryClient()

  // Fetch delegation graph to get all agents
  const { data: graphData, isLoading: graphLoading } = useQuery({
    queryKey: ['delegation-graph'],
    queryFn: apiService.getDelegationGraph,
  })

  // Fetch CRL to get revoked certificates
  const { data: crlData } = useQuery({
    queryKey: ['crl'],
    queryFn: apiService.getCRL,
  })

  // Fetch agent details
  const { data: agentsData, isLoading: agentsLoading } = useQuery({
    queryKey: ['agents'],
    queryFn: apiService.getAllAgents,
    enabled: !!graphData,
  })

  // Revoke mutation
  const revokeMutation = useMutation({
    mutationFn: (certId: string) =>
      apiService.revokeCertificate({ cert_id: certId, reason: 'Manual revocation from Dashboard' }),
    onSuccess: () => {
      message.success('证书已吊销')
      queryClient.invalidateQueries({ queryKey: ['agents'] })
      queryClient.invalidateQueries({ queryKey: ['crl'] })
    },
    onError: (error: unknown) => {
      const err = error as { response?: { data?: { error?: { message?: string } } } }
      message.error(err.response?.data?.error?.message || '吊销失败')
    },
  })

  const revokedCertIds = new Set(crlData?.entries.map((e) => e.cert_id) || [])

  // Flatten certificates from all agents
  const allCertificates: Array<{ agent: Agent; cert: Certificate }> = []
  agentsData?.forEach((agent) => {
    agent.certificates?.forEach((cert) => {
      allCertificates.push({ agent, cert })
    })
  })

  const handleViewDetail = (agent: Agent, cert: Certificate) => {
    setSelectedAgent(agent)
    setSelectedCert(cert)
    setDetailModalOpen(true)
  }

  const handleRevoke = (certId: string) => {
    revokeMutation.mutate(certId)
  }

  const columns = [
    {
      title: 'Agent',
      key: 'agent',
      render: (_: unknown, record: { agent: Agent; cert: Certificate }) => (
        <Space direction="vertical" size={0}>
          <Text strong>{record.agent.name}</Text>
          <Text type="secondary" style={{ fontSize: 12 }}>
            {record.agent.agent_id}
          </Text>
        </Space>
      ),
    },
    {
      title: '证书 ID',
      dataIndex: ['cert', 'cert_id'],
      key: 'cert_id',
      render: (certId: string) => <Text code>{certId.substring(0, 16)}...</Text>,
    },
    {
      title: '信任等级',
      key: 'trust_level',
      render: (_: unknown, record: { agent: Agent }) => (
        <Tag color={trustLevelColors[record.agent.trust_level]}>
          Level {record.agent.trust_level}
        </Tag>
      ),
    },
    {
      title: '状态',
      key: 'status',
      render: (_: unknown, record: { cert: Certificate }) => {
        const status = revokedCertIds.has(record.cert.cert_id) ? 'revoked' : record.cert.status
        return (
          <Tag color={statusConfig[status].color}>
            {statusConfig[status].icon} {statusConfig[status].text}
          </Tag>
        )
      },
    },
    {
      title: '过期时间',
      dataIndex: ['cert', 'expires_at'],
      key: 'expires_at',
      render: (expiresAt: string) => {
        const isExpired = new Date(expiresAt) < new Date()
        return (
          <Text type={isExpired ? 'danger' : undefined}>
            {new Date(expiresAt).toLocaleString()}
          </Text>
        )
      },
    },
    {
      title: '能力',
      key: 'capabilities',
      render: (_: unknown, record: { cert: Certificate }) => (
        <Space wrap>
          {record.cert.capabilities.slice(0, 3).map((cap) => (
            <Tag key={cap}>{cap}</Tag>
          ))}
          {record.cert.capabilities.length > 3 && (
            <Tag>+{record.cert.capabilities.length - 3}</Tag>
          )}
        </Space>
      ),
    },
    {
      title: '操作',
      key: 'actions',
      render: (_: unknown, record: { agent: Agent; cert: Certificate }) => {
        const isRevoked = revokedCertIds.has(record.cert.cert_id) || record.cert.status === 'revoked'
        const isExpired = new Date(record.cert.expires_at) < new Date()

        return (
          <Space>
            <Button size="small" onClick={() => handleViewDetail(record.agent, record.cert)}>
              详情
            </Button>
            {!isRevoked && !isExpired && (
              <Popconfirm
                title="确认吊销此证书？"
                description="吊销后该证书将立即失效，所有依赖该证书的操作都会被拒绝。"
                icon={<ExclamationCircleOutlined style={{ color: 'red' }} />}
                onConfirm={() => handleRevoke(record.cert.cert_id)}
                okText="确认吊销"
                cancelText="取消"
                okButtonProps={{ danger: true }}
              >
                <Button size="small" danger>
                  吊销
                </Button>
              </Popconfirm>
            )}
          </Space>
        )
      },
    },
  ]

  if (agentsLoading || graphLoading) {
    return <div>加载中...</div>
  }

  if (!agentsData || agentsData.length === 0) {
    return (
      <div>
        <Title level={4}>证书管理</Title>
        <Empty description="暂无证书数据，请先注册 Agent" />
      </div>
    )
  }

  return (
    <div>
      <Space direction="vertical" size="large" style={{ width: '100%' }}>
        <div>
          <Title level={4} style={{ marginBottom: 16 }}>
            <SafetyCertificateOutlined /> 证书管理
          </Title>
          {revokedCertIds.size > 0 && (
            <Alert
              type="warning"
              message={`${revokedCertIds.size} 个证书已被吊销`}
              showIcon
              style={{ marginBottom: 16 }}
            />
          )}
        </div>

        <Table
          columns={columns}
          dataSource={allCertificates}
          rowKey={(_, index) => `${allCertificates[index ?? 0]?.cert.cert_id}-${index}`}
          pagination={{ pageSize: 10, showSizeChanger: true }}
          loading={agentsLoading || graphLoading}
        />
      </Space>

      <CertDetailModal
        agent={selectedAgent}
        cert={selectedCert}
        open={detailModalOpen}
        onClose={() => setDetailModalOpen(false)}
      />
    </div>
  )
}

export default CertView
