import React, { useEffect, useRef, useState } from 'react'
import { Card, Typography, Space, Spin, Empty, Modal, Descriptions, Tag } from 'antd'
import { ShareAltOutlined } from '@ant-design/icons'
import { useQuery } from '@tanstack/react-query'
import * as echarts from 'echarts'
import type { ECharts } from 'echarts'
import apiService from '../../services/api'
import type { DelegationGraphResponse, GraphEdge } from '../../types'

const { Title, Text } = Typography

const capabilityColors: Record<string, string> = {
  read_database: '#52c41a',
  write_database: '#faad14',
  delete_database: '#ff4d4f',
  read_document: '#1890ff',
  write_document: '#13c2c2',
  delete_document: '#f5222d',
  send_message: '#722ed1',
  read_bitable: '#001629',
  write_bitable: '#fa8c16',
  read_doc: '#2fabee',
  write_doc: '#eb2f96',
  read_calendar: '#fa541c',
  create_meeting: '#0e639d',
  manage_agents: '#595959',
}

const trustLevelSizes: Record<number, number> = {
  1: 30,
  2: 40,
  3: 50,
  4: 60,
  5: 70,
}

interface EdgeDetailModalProps {
  edge: GraphEdge | null
  open: boolean
  onClose: () => void
}

const EdgeDetailModal: React.FC<EdgeDetailModalProps> = ({ edge, open, onClose }) => {
  if (!edge) return null

  return (
    <Modal title="委托详情" open={open} onCancel={onClose} footer={null} width={500}>
      <Descriptions column={1} bordered size="small">
        <Descriptions.Item label="委托 ID">
          <Text code>{edge.delegation_id}</Text>
        </Descriptions.Item>
        <Descriptions.Item label="委托能力">
          <Tag color={capabilityColors[edge.capability] || 'default'}>{edge.capability}</Tag>
        </Descriptions.Item>
        <Descriptions.Item label="过期时间">
          {new Date(edge.expires_at).toLocaleString()}
        </Descriptions.Item>
        <Descriptions.Item label="状态">
          <Tag color={edge.status === 'active' ? 'green' : 'red'}>{edge.status}</Tag>
        </Descriptions.Item>
        <Descriptions.Item label="衰减参数" span={2}>
          <pre style={{ margin: 0, fontSize: 12 }}>
            {JSON.stringify(edge.attenuations, null, 2)}
          </pre>
        </Descriptions.Item>
      </Descriptions>
    </Modal>
  )
}

const DelegationGraph: React.FC = () => {
  const chartRef = useRef<HTMLDivElement>(null)
  const chartInstanceRef = useRef<ECharts | null>(null)
  const [selectedEdge, setSelectedEdge] = useState<GraphEdge | null>(null)
  const [modalOpen, setModalOpen] = useState(false)

  const { data: graphData, isLoading } = useQuery<DelegationGraphResponse>({
    queryKey: ['delegation-graph'],
    queryFn: apiService.getDelegationGraph,
  })

  useEffect(() => {
    if (!chartRef.current || !graphData) return

    // Initialize chart
    if (chartInstanceRef.current) {
      chartInstanceRef.current.dispose()
    }

    const chart = echarts.init(chartRef.current)
    chartInstanceRef.current = chart

    // Prepare nodes
    const nodes = graphData.nodes.map((node) => ({
      id: node.id,
      name: node.name,
      symbolSize: trustLevelSizes[node.trust_level] || 40,
      itemStyle: {
        color:
          node.trust_level === 5
            ? '#52c41a'
            : node.trust_level === 4
              ? '#1890ff'
              : node.trust_level === 3
                ? '#722ed1'
                : node.trust_level <= 2
                  ? '#faad14'
                  : '#d9d9d9',
      },
      label: {
        show: true,
        formatter: `{b}`,
        fontSize: 12,
      },
    }))

    // Prepare edges
    const edges = graphData.edges.map((edge) => ({
      source: edge.from_agent,
      target: edge.to_agent,
      lineStyle: {
        color: capabilityColors[edge.capability] || '#999',
        width: 2,
        curveness: 0.2,
      },
      edgeData: edge, // Store full edge data for click handler
    }))

    // Set chart options
    chart.setOption({
      animation: true,
      animationDuration: 1000,
      tooltip: {
        trigger: 'item',
        formatter: (params: unknown) => {
          const p = params as { dataType?: string; data?: { name?: string; edgeData?: GraphEdge } }
          if (p.dataType === 'edge' && p.data?.edgeData) {
            const e = p.data.edgeData
            return `${e.from_agent} → ${e.to_agent}<br/>能力: ${e.capability}<br/>衰减: ${JSON.stringify(e.attenuations)}`
          }
          if (p.dataType === 'node') {
            return p.data?.name || ''
          }
          return ''
        },
      },
      series: [
        {
          type: 'graph',
          layout: 'force',
          force: {
            repulsion: 300,
            edgeLength: 150,
            layoutAnimation: true,
          },
          symbol: 'circle',
          roam: true,
          draggable: true,
          label: {
            show: true,
            position: 'right',
            formatter: '{b}',
          },
          nodes,
          edges,
          lineStyle: {
            width: 2,
            curveness: 0.2,
          },
          emphasis: {
            focus: 'adjacency',
            lineStyle: {
              width: 4,
            },
          },
        },
      ],
    })

    // Handle click on edge
    chart.on('click', (params: unknown) => {
      const p = params as { dataType?: string; data?: { edgeData?: GraphEdge } }
      if (p.dataType === 'edge' && p.data?.edgeData) {
        setSelectedEdge(p.data.edgeData)
        setModalOpen(true)
      }
    })

    // Handle resize
    const handleResize = () => {
      chart.resize()
    }
    window.addEventListener('resize', handleResize)

    return () => {
      window.removeEventListener('resize', handleResize)
      chart.dispose()
    }
  }, [graphData])

  if (isLoading) {
    return (
      <div style={{ textAlign: 'center', padding: 50 }}>
        <Spin size="large" />
        <div style={{ marginTop: 16 }}>加载委托关系图中...</div>
      </div>
    )
  }

  if (!graphData || graphData.nodes.length === 0) {
    return (
      <div>
        <Title level={4}>
          <ShareAltOutlined /> 委托链可视化
        </Title>
        <Empty description="暂无委托关系数据" />
      </div>
    )
  }

  return (
    <div>
      <Space direction="vertical" size="large" style={{ width: '100%' }}>
        <div>
          <Title level={4} style={{ marginBottom: 16 }}>
            <ShareAltOutlined /> 委托链可视化
          </Title>
          <Text type="secondary" style={{ display: 'block', marginBottom: 16 }}>
            节点大小表示 trust_level，边的颜色表示委托的能力类型。点击边查看详细衰减参数。
          </Text>
        </div>

        <Card
          style={{ background: '#fafafa' }}
          styles={{ body: { padding: 0 } }}
        >
          <div ref={chartRef} style={{ height: 500 }} />
        </Card>

        <Card title="图例说明" size="small">
          <Space wrap>
            <Text strong>节点大小：</Text>
            {[1, 2, 3, 4, 5].map((level) => (
              <Space key={level}>
                <div
                  style={{
                    width: trustLevelSizes[level] / 2,
                    height: trustLevelSizes[level] / 2,
                    borderRadius: '50%',
                    background: '#1890ff',
                  }}
                />
                <Text style={{ fontSize: 12 }}>Level {level}</Text>
              </Space>
            ))}
          </Space>
          <div style={{ marginTop: 16 }}>
            <Text strong>能力类型：</Text>
            <Space wrap style={{ marginTop: 8 }}>
              {Object.entries(capabilityColors)
                .slice(0, 8)
                .map(([cap, color]) => (
                  <Tag key={cap} color={color}>
                    {cap}
                  </Tag>
                ))}
            </Space>
          </div>
        </Card>
      </Space>

      <EdgeDetailModal edge={selectedEdge} open={modalOpen} onClose={() => setModalOpen(false)} />
    </div>
  )
}

export default DelegationGraph
