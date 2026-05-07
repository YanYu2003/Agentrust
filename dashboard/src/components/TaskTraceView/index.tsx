import React, { useEffect, useMemo, useState } from 'react'
import {
  Typography,
  Space,
  Input,
  Button,
  Steps,
  Card,
  Tag,
  Empty,
  Select,
  Drawer,
  Descriptions,
  Alert,
  Spin,
} from 'antd'
import {
  NodeIndexOutlined,
  SearchOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  WarningOutlined,
} from '@ant-design/icons'
import { useQuery } from '@tanstack/react-query'
import apiService from '../../services/api'
import type { TaskTraceStep } from '../../types'

const { Title, Text } = Typography

const resultConfig = {
  ALLOWED: { color: 'green', icon: <CheckCircleOutlined />, text: '允许' },
  DENIED: { color: 'red', icon: <CloseCircleOutlined />, text: '拒绝' },
  ERROR: { color: 'orange', icon: <WarningOutlined />, text: '错误' },
}

const TaskTraceView: React.FC = () => {
  const [taskIdInput, setTaskIdInput] = useState('')
  const [activeTaskId, setActiveTaskId] = useState<string | null>(null)
  const [selectedStep, setSelectedStep] = useState<TaskTraceStep | null>(null)
  const [drawerOpen, setDrawerOpen] = useState(false)

  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const q = params.get('task_id')
    if (q) {
      setTaskIdInput(q)
      setActiveTaskId(q)
    }
  }, [])

  const { data: recent } = useQuery({
    queryKey: ['recent-tasks'],
    queryFn: () => apiService.getRecentAuditTasks(30),
  })

  const { data: traceData, isLoading, error, isFetching } = useQuery({
    queryKey: ['task-trace', activeTaskId],
    queryFn: () => apiService.getTaskTrace(activeTaskId!),
    enabled: !!activeTaskId?.trim(),
  })

  const recentOptions = useMemo(
    () =>
      (recent?.tasks || []).map((t) => ({
        label: `${t.task_id} (${t.step_count} 步)`,
        value: t.task_id,
      })),
    [recent],
  )

  const loadTrace = () => {
    const t = taskIdInput.trim()
    if (!t) return
    setActiveTaskId(t)
    const url = new URL(window.location.href)
    url.searchParams.set('task_id', t)
    window.history.replaceState({}, '', url.toString())
  }

  const openStepDetail = (step: TaskTraceStep) => {
    setSelectedStep(step)
    setDrawerOpen(true)
  }

  const stepsItems =
    traceData?.trace.map((step) => ({
      title: (
        <Space wrap>
          <Text strong code>
            {step.agent_id}
          </Text>
          <Tag color={resultConfig[step.result].color}>
            {resultConfig[step.result].icon} {resultConfig[step.result].text}
          </Tag>
        </Space>
      ),
      description: (
        <div>
          <div>
            <Tag>{step.action}</Tag>
            <Text type="secondary">{step.resource}</Text>
          </div>
          <Button type="link" size="small" style={{ paddingLeft: 0 }} onClick={() => openStepDetail(step)}>
            查看上下文
          </Button>
        </div>
      ),
      status:
        step.result === 'ALLOWED' ? ('finish' as const) : step.result === 'DENIED' ? ('error' as const) : ('process' as const),
    })) || []

  return (
    <div>
      <Space direction="vertical" size="large" style={{ width: '100%' }}>
        <div>
          <Title level={4}>
            <NodeIndexOutlined /> 任务链路
          </Title>
          <Text type="secondary">
            按 task_id 聚合展示一次多 Agent 协作的审计步骤（用户 → Agent A → Agent B → 资源）。节点颜色区分允许 / 拦截 / 异常。
          </Text>
        </div>

        <Card size="small">
          <Space wrap align="start">
            <Select
              allowClear
              showSearch
              placeholder="选择近期任务"
              style={{ minWidth: 280 }}
              options={recentOptions}
              optionFilterProp="label"
              onChange={(v) => v && setTaskIdInput(v)}
            />
            <Input
              style={{ width: 320 }}
              placeholder="输入 task_id"
              value={taskIdInput}
              onChange={(e) => setTaskIdInput(e.target.value)}
              onPressEnter={loadTrace}
            />
            <Button type="primary" icon={<SearchOutlined />} onClick={loadTrace}>
              加载链路
            </Button>
          </Space>
        </Card>

        {!activeTaskId && <Alert type="info" message="请输入或选择 task_id 后加载链路。" />}

        {activeTaskId && isLoading && (
          <div style={{ textAlign: 'center', padding: 48 }}>
            <Spin />
          </div>
        )}

        {activeTaskId && error && (
          <Alert type="error" message="加载失败：该 task_id 无审计记录，或当前账号无权查看。" />
        )}

        {activeTaskId && traceData && traceData.trace.length === 0 && !isFetching && (
          <Empty description="暂无可见步骤（可能无权限查看该任务下的全部节点）" />
        )}

        {traceData && traceData.trace.length > 0 && (
          <Card title={`任务 ${traceData.task_id} · 共 ${traceData.total_steps} 步`}>
            <Steps direction="vertical" items={stepsItems} />
          </Card>
        )}
      </Space>

      <Drawer title="步骤详情" width={560} open={drawerOpen} onClose={() => setDrawerOpen(false)}>
        {selectedStep && (
          <>
            <Descriptions column={1} bordered size="small">
              <Descriptions.Item label="log_id">
                <Text code>{selectedStep.log_id}</Text>
              </Descriptions.Item>
              <Descriptions.Item label="agent_id">{selectedStep.agent_id}</Descriptions.Item>
              <Descriptions.Item label="parent_agent_id">
                {selectedStep.parent_agent_id || '-'}
              </Descriptions.Item>
              <Descriptions.Item label="task_id">{selectedStep.task_id || '-'}</Descriptions.Item>
              <Descriptions.Item label="操作">{selectedStep.action}</Descriptions.Item>
              <Descriptions.Item label="资源">{selectedStep.resource}</Descriptions.Item>
              <Descriptions.Item label="结果">
                <Tag color={resultConfig[selectedStep.result].color}>
                  {resultConfig[selectedStep.result].text}
                </Tag>
              </Descriptions.Item>
              <Descriptions.Item label="时间">
                {new Date(selectedStep.created_at).toLocaleString()}
              </Descriptions.Item>
              {selectedStep.error_detail && (
                <Descriptions.Item label="错误">
                  <Text type="danger">{selectedStep.error_detail}</Text>
                </Descriptions.Item>
              )}
            </Descriptions>
            <Title level={5} style={{ marginTop: 16 }}>
              task_context
            </Title>
            <pre
              style={{
                background: '#f5f5f5',
                padding: 12,
                borderRadius: 8,
                fontSize: 12,
                overflow: 'auto',
              }}
            >
              {JSON.stringify(selectedStep.task_context, null, 2)}
            </pre>
            <Title level={5}>request_context</Title>
            <pre
              style={{
                background: '#f5f5f5',
                padding: 12,
                borderRadius: 8,
                fontSize: 12,
                overflow: 'auto',
              }}
            >
              {JSON.stringify(selectedStep.request_context, null, 2)}
            </pre>
          </>
        )}
      </Drawer>
    </div>
  )
}

export default TaskTraceView
