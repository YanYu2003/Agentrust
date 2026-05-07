import React, { useState } from 'react'
import {
  Table,
  Tag,
  Button,
  Space,
  Typography,
  Select,
  DatePicker,
  Form,
  Row,
  Col,
  Empty,
  Drawer,
  Descriptions,
  Input,
} from 'antd'
import {
  AuditOutlined,
  EyeOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  WarningOutlined,
  BranchesOutlined,
} from '@ant-design/icons'
import { useQuery } from '@tanstack/react-query'
import dayjs from 'dayjs'
import apiService from '../../services/api'
import type { AuditLog, AuditLogDetail } from '../../types'

const { Title, Text, Paragraph } = Typography
const { RangePicker } = DatePicker

const resultConfig = {
  ALLOWED: { color: 'green', icon: <CheckCircleOutlined />, text: '允许' },
  DENIED: { color: 'red', icon: <CloseCircleOutlined />, text: '拒绝' },
  ERROR: { color: 'orange', icon: <WarningOutlined />, text: '错误' },
}

interface LogDetailDrawerProps {
  log: AuditLogDetail | null
  open: boolean
  onClose: () => void
}

const LogDetailDrawer: React.FC<LogDetailDrawerProps> = ({ log, open, onClose }) => {
  if (!log) return null

  return (
    <Drawer
      title={
        <Space>
          <EyeOutlined />
          审计日志详情
        </Space>
      }
      placement="right"
      width={600}
      onClose={onClose}
      open={open}
    >
      <Descriptions column={1} bordered size="small">
        <Descriptions.Item label="日志 ID">
          <Text code>{log.log_id}</Text>
        </Descriptions.Item>
        <Descriptions.Item label="Agent ID">
          <Text code>{log.agent_id}</Text>
        </Descriptions.Item>
        {log.parent_agent_id ? (
          <Descriptions.Item label="上游 Agent">
            <Text code>{log.parent_agent_id}</Text>
          </Descriptions.Item>
        ) : null}
        {log.task_id ? (
          <Descriptions.Item label="task_id">
            <Text code>{log.task_id}</Text>
          </Descriptions.Item>
        ) : null}
        <Descriptions.Item label="操作">
          <Tag color="blue">{log.action}</Tag>
        </Descriptions.Item>
        <Descriptions.Item label="资源">{log.resource}</Descriptions.Item>
        <Descriptions.Item label="结果">
          <Tag color={resultConfig[log.result].color}>
            {resultConfig[log.result].icon} {resultConfig[log.result].text}
          </Tag>
        </Descriptions.Item>
        <Descriptions.Item label="委托链">
          {log.delegation_chain_summary || '-'}
        </Descriptions.Item>
        <Descriptions.Item label="时间">
          {new Date(log.created_at).toLocaleString()}
        </Descriptions.Item>
        {log.error_detail && (
          <Descriptions.Item label="错误详情">
            <Text type="danger">{log.error_detail}</Text>
          </Descriptions.Item>
        )}
      </Descriptions>

      <Title level={5} style={{ marginTop: 24 }}>
        完整令牌链
      </Title>
      <pre
        style={{
          background: '#f5f5f5',
          padding: 16,
          borderRadius: 8,
          overflow: 'auto',
          maxHeight: 400,
          fontSize: 12,
        }}
      >
        {JSON.stringify(log.token_chain, null, 2)}
      </pre>

      <Title level={5} style={{ marginTop: 24 }}>
        请求上下文
      </Title>
      <pre
        style={{
          background: '#f5f5f5',
          padding: 16,
          borderRadius: 8,
          overflow: 'auto',
          fontSize: 12,
        }}
      >
        {JSON.stringify(log.request_context, null, 2)}
      </pre>

      {log.task_context != null && Object.keys(log.task_context).length > 0 ? (
        <>
          <Title level={5} style={{ marginTop: 24 }}>
            任务上下文（task_context）
          </Title>
          <pre
            style={{
              background: '#f5f5f5',
              padding: 16,
              borderRadius: 8,
              overflow: 'auto',
              fontSize: 12,
            }}
          >
            {JSON.stringify(log.task_context, null, 2)}
          </pre>
        </>
      ) : null}
    </Drawer>
  )
}

const AuditView: React.FC = () => {
  const [filters, setFilters] = useState({
    agent_id: '',
    task_id: '',
    action: '',
    result: '',
    start_time: dayjs().subtract(7, 'day').toISOString(),
    end_time: dayjs().toISOString(),
    page: 1,
    page_size: 20,
  })
  const [selectedLog, setSelectedLog] = useState<AuditLogDetail | null>(null)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [form] = Form.useForm()

  const { data: logsData, isLoading } = useQuery({
    queryKey: ['audit-logs', filters],
    queryFn: () => apiService.getAuditLogs(filters),
  })

  const { data: graphData } = useQuery({
    queryKey: ['delegation-graph'],
    queryFn: apiService.getDelegationGraph,
  })

  // Get unique agent IDs for filter
  const agentOptions = graphData?.nodes.map((n) => ({ label: n.name, value: n.id })) || []

  // Get unique actions for filter
  const actionOptions = [
    { label: '全部', value: '' },
    { label: 'read_database', value: 'read_database' },
    { label: 'write_database', value: 'write_database' },
    { label: 'delete_database', value: 'delete_database' },
    { label: 'read_bitable', value: 'read_bitable' },
    { label: 'write_bitable', value: 'write_bitable' },
    { label: 'send_message', value: 'send_message' },
    { label: 'delegate', value: 'delegate' },
    { label: 'read_document', value: 'read_document' },
    { label: 'write_document', value: 'write_document' },
  ]

  const resultOptions = [
    { label: '全部', value: '' },
    { label: '允许 (ALLOWED)', value: 'ALLOWED' },
    { label: '拒绝 (DENIED)', value: 'DENIED' },
    { label: '错误 (ERROR)', value: 'ERROR' },
  ]

  const handleViewDetail = async (log: AuditLog) => {
    try {
      const detail = await apiService.getAuditLogDetail(log.log_id)
      setSelectedLog(detail)
      setDrawerOpen(true)
    } catch (error) {
      console.error('Failed to fetch log detail:', error)
    }
  }

  const handleFilterChange = (changedValues: Record<string, unknown>) => {
    if ('agent_id' in changedValues) setFilters((f) => ({ ...f, agent_id: changedValues.agent_id as string }))
    if ('task_id' in changedValues) setFilters((f) => ({ ...f, task_id: changedValues.task_id as string }))
    if ('action' in changedValues) setFilters((f) => ({ ...f, action: changedValues.action as string }))
    if ('result' in changedValues) setFilters((f) => ({ ...f, result: changedValues.result as string }))
  }

  const handleTimeChange = (dates: unknown) => {
    if (dates && Array.isArray(dates) && dates[0] && dates[1]) {
      setFilters((f) => ({
        ...f,
        start_time: (dates[0] as dayjs.Dayjs).toISOString(),
        end_time: (dates[1] as dayjs.Dayjs).toISOString(),
      }))
    }
  }

  const columns = [
    {
      title: '时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 180,
      render: (time: string) => new Date(time).toLocaleString(),
    },
    {
      title: 'Agent',
      dataIndex: 'agent_id',
      key: 'agent_id',
      width: 150,
      render: (id: string) => <Text code>{id.substring(0, 16)}...</Text>,
    },
    {
      title: '上游',
      dataIndex: 'parent_agent_id',
      key: 'parent_agent_id',
      width: 120,
      ellipsis: true,
      render: (v: string | null | undefined) =>
        v ? <Text code>{v.length > 12 ? `${v.slice(0, 12)}…` : v}</Text> : '-',
    },
    {
      title: 'task_id',
      dataIndex: 'task_id',
      key: 'task_id',
      width: 140,
      ellipsis: true,
      render: (v: string | null | undefined) => (v ? <Text code>{v}</Text> : '-'),
    },
    {
      title: '操作',
      dataIndex: 'action',
      key: 'action',
      width: 130,
      render: (action: string) => <Tag color="blue">{action}</Tag>,
    },
    {
      title: '资源',
      dataIndex: 'resource',
      key: 'resource',
      ellipsis: true,
    },
    {
      title: '结果',
      dataIndex: 'result',
      key: 'result',
      width: 100,
      render: (result: 'ALLOWED' | 'DENIED' | 'ERROR') => (
        <Tag color={resultConfig[result].color}>
          {resultConfig[result].icon} {resultConfig[result].text}
        </Tag>
      ),
    },
    {
      title: '委托链',
      dataIndex: 'delegation_chain_summary',
      key: 'delegation_chain_summary',
      width: 150,
      render: (chain: string | null) => chain || '-',
    },
    {
      title: '操作',
      key: 'actions',
      width: 160,
      render: (_: unknown, log: AuditLog) => (
        <Space size="small">
          {log.task_id ? (
            <Button
              size="small"
              icon={<BranchesOutlined />}
              onClick={() => {
                window.location.href = `/dashboard/trace?task_id=${encodeURIComponent(log.task_id!)}`
              }}
            >
              链路
            </Button>
          ) : null}
          <Button size="small" icon={<EyeOutlined />} onClick={() => handleViewDetail(log)}>
            详情
          </Button>
        </Space>
      ),
    },
  ]

  const getRowClassName = (record: AuditLog) => {
    if (record.result === 'DENIED') {
      return 'audit-row-denied'
    }
    if (record.result === 'ERROR') {
      return 'audit-row-error'
    }
    return ''
  }

  return (
    <div>
      <Space direction="vertical" size="large" style={{ width: '100%' }}>
        <div>
          <Title level={4} style={{ marginBottom: 16 }}>
            <AuditOutlined /> 审计日志
          </Title>
        </div>

        <Form
          form={form}
          layout="vertical"
          onValuesChange={handleFilterChange}
          initialValues={{
            agent_id: filters.agent_id,
            task_id: filters.task_id,
            action: filters.action,
            result: filters.result,
            time: [dayjs().subtract(7, 'day'), dayjs()],
          }}
        >
          <Row gutter={16}>
            <Col xs={24} md={8}>
              <Form.Item name="task_id" label="task_id" style={{ marginBottom: 12 }}>
                <Input allowClear placeholder="精确匹配 task_id" />
              </Form.Item>
            </Col>
            <Col xs={24} md={8}>
              <Form.Item name="agent_id" label="Agent" style={{ marginBottom: 12 }}>
                <Select
                  allowClear
                  showSearch
                  placeholder="选择 Agent"
                  options={agentOptions}
                  optionFilterProp="label"
                />
              </Form.Item>
            </Col>
            <Col xs={24} md={8}>
              <Form.Item name="action" label="操作类型" style={{ marginBottom: 12 }}>
                <Select allowClear placeholder="选择操作" options={actionOptions} />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={16}>
            <Col xs={24} md={8}>
              <Form.Item name="result" label="结果" style={{ marginBottom: 12 }}>
                <Select allowClear placeholder="选择结果" options={resultOptions} />
              </Form.Item>
            </Col>
            <Col xs={24} md={16}>
              <Form.Item name="time" label="时间范围" style={{ marginBottom: 12 }}>
                <RangePicker style={{ width: '100%' }} onChange={handleTimeChange} />
              </Form.Item>
            </Col>
          </Row>
        </Form>

        <Table
          columns={columns}
          dataSource={logsData?.logs || []}
          rowKey="log_id"
          loading={isLoading}
          pagination={{
            current: filters.page,
            pageSize: filters.page_size,
            total: logsData?.total || 0,
            showSizeChanger: true,
            showTotal: (total) => `共 ${total} 条记录`,
            onChange: (page, pageSize) => {
              setFilters((f) => ({ ...f, page, page_size: pageSize }))
            },
          }}
          rowClassName={getRowClassName}
          locale={{
            emptyText: <Empty description="暂无审计日志" />,
          }}
        />

        <Paragraph type="secondary" style={{ fontSize: 12 }}>
          <Text type="secondary">说明：</Text>
          <Text type="secondary">
            红色行表示被拒绝的操作，橙色行表示错误。点击"详情"查看完整的令牌链和请求上下文。
          </Text>
        </Paragraph>
      </Space>

      <LogDetailDrawer log={selectedLog} open={drawerOpen} onClose={() => setDrawerOpen(false)} />

      <style>{`
        .audit-row-denied {
          background-color: #fff2f0 !important;
        }
        .audit-row-error {
          background-color: #fffbe6 !important;
        }
        .audit-row-denied:hover > td {
          background-color: #ffebe8 !important;
        }
        .audit-row-error:hover > td {
          background-color: #fffbd6 !important;
        }
      `}</style>
    </div>
  )
}

export default AuditView
