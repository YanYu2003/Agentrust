import React, { useState } from 'react'
import { Form, Input, Button, Card, message, Typography, Space, Divider } from 'antd'
import { SafetyCertificateOutlined, KeyOutlined } from '@ant-design/icons'
import apiService from '../../services/api'

const { Title, Text, Paragraph } = Typography

interface LoginFormValues {
  agentId: string
  certId?: string
  privateKey?: string
  sessionToken?: string
}

const LoginPage: React.FC = () => {
  const [loading, setLoading] = useState(false)
  const [form] = Form.useForm()

  const handleSubmit = async (values: LoginFormValues) => {
    const sessionFromScript = values.sessionToken?.trim()
    const agentId = values.agentId?.trim()

    if (sessionFromScript) {
      if (!agentId) {
        message.error('使用演示 Session 时请填写 Agent ID（与脚本打印的一致）')
        return
      }
      setLoading(true)
      try {
        apiService.setSessionToken(sessionFromScript)
        localStorage.setItem('agentrust_session_token', sessionFromScript)
        localStorage.setItem('agentrust_agent_id', agentId)
        const cid = values.certId?.trim()
        if (cid) localStorage.setItem('agentrust_cert_id', cid)
        else localStorage.removeItem('agentrust_cert_id')
        localStorage.removeItem('agentrust_demo_mode')
        message.success('已使用 IAM Session 登录（可调用审计与任务链路）')
        // App 与 Login 各自调用 useAuth() 时状态不同步；整页进入 /dashboard 才会从 localStorage 重新初始化认证态
        window.location.assign('/dashboard')
      } finally {
        setLoading(false)
      }
      return
    }

    if (!values.certId?.trim() || !values.privateKey?.trim()) {
      message.warning('请粘贴演示 Session Token；若不使用 Token，则需填写证书 ID 与私钥路径占位符')
      return
    }

    if (!agentId) {
      message.error('请输入 Agent ID')
      return
    }

    setLoading(true)
    try {
      const challenge = await apiService.requestChallenge(agentId, values.certId!.trim())

      message.info('占位登录：未使用脚本 JWT，审计接口将不可用')
      console.log('Challenge received:', challenge)

      const demoToken = `demo_token_${Date.now()}`
      apiService.setSessionToken(demoToken)
      localStorage.setItem('agentrust_session_token', demoToken)
      localStorage.setItem('agentrust_agent_id', agentId)
      localStorage.setItem('agentrust_cert_id', values.certId!.trim())
      localStorage.setItem('agentrust_demo_mode', 'true')

      message.success('登录成功（仅界面 Demo，请改用 Session Token 查看审计）')
      window.location.assign('/dashboard')
    } catch (error: unknown) {
      const err = error as { response?: { data?: { error?: { message?: string } } } }
      message.error(err.response?.data?.error?.message || '认证失败，请检查 Agent ID 和 Cert ID')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div
      style={{
        minHeight: '100vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
      }}
    >
      <Card
        style={{
          width: 460,
          borderRadius: 16,
          boxShadow: '0 10px 40px rgba(0,0,0,0.2)',
        }}
        styles={{ body: { padding: 40 } }}
      >
        <Space direction="vertical" size="large" style={{ width: '100%' }}>
          <div style={{ textAlign: 'center' }}>
            <div
              style={{
                width: 72,
                height: 72,
                borderRadius: '50%',
                background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                margin: '0 auto 16px',
              }}
            >
              <SafetyCertificateOutlined style={{ fontSize: 36, color: '#fff' }} />
            </div>
            <Title level={3} style={{ marginBottom: 4 }}>
              Agentrust
            </Title>
            <Text type="secondary">Agent 身份与权限管理系统</Text>
          </div>

          <Divider style={{ margin: '16px 0' }} />

          <Form
            form={form}
            layout="vertical"
            onFinish={handleSubmit}
            size="large"
          >
            <Form.Item name="sessionToken" label="演示 Session Token（推荐）">
              <Input.TextArea
                rows={4}
                placeholder="运行 backend/scripts/run_demo.bat 或 demo_cycle4_normal.py 后，控制台打印的整段 session_token（JWT）粘贴到这里"
              />
            </Form.Item>

            <Form.Item
              name="agentId"
              label="Agent ID"
              rules={[{ required: true, message: '请输入 Agent ID' }]}
            >
              <Input prefix={<KeyOutlined />} placeholder="与脚本打印的 agent_id 一致" />
            </Form.Item>

            <Form.Item name="certId" label="证书 ID（可选，占位登录时用）">
              <Input prefix={<SafetyCertificateOutlined />} placeholder="cert-xxxxxxxx" />
            </Form.Item>

            <Form.Item name="privateKey" label="私钥文件路径（可选占位）">
              <Input.Password placeholder="不使用 Session Token 时任意非空即可，例如 demo" />
            </Form.Item>

            <Paragraph type="secondary" style={{ fontSize: 12 }}>
              <Text type="warning">说明</Text>：优先使用上方 Session Token，与 IAM 网关签发的一致，
              才能加载审计日志与任务链路。仅填证书项且不粘贴 Token 时，会通过挑战接口占位登录，
              但不会调用真实 JWT，审计页将报错。
            </Paragraph>

            <Form.Item style={{ marginBottom: 0 }}>
              <Button
                type="primary"
                htmlType="submit"
                loading={loading}
                block
                style={{ height: 44 }}
              >
                登录
              </Button>
            </Form.Item>
          </Form>

          <Text type="secondary" style={{ fontSize: 12, textAlign: 'center', display: 'block' }}>
            基于 ECDSA P-256 证书链的身份与权限系统
          </Text>
        </Space>
      </Card>
    </div>
  )
}

export default LoginPage
