import React, { useState } from 'react'
import { Form, Input, Button, Card, message, Typography, Space, Divider } from 'antd'
import { SafetyCertificateOutlined, KeyOutlined } from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import apiService from '../../services/api'

const { Title, Text, Paragraph } = Typography

interface LoginFormValues {
  agentId: string
  certId: string
  privateKey: string
}

const LoginPage: React.FC = () => {
  const [loading, setLoading] = useState(false)
  const [form] = Form.useForm()
  const navigate = useNavigate()

  const handleSubmit = async (values: LoginFormValues) => {
    setLoading(true)
    try {
      // Step 1: Request challenge
      const challenge = await apiService.requestChallenge(values.agentId, values.certId)

      // Step 2: In a real scenario, the wallet would sign the nonce with the private key
      // For demo purposes, we simulate by storing the challenge for later use
      // In production, the SDK handles signing

      message.info('Demo 模式：跳过实际签名验证')
      console.log('Challenge received:', challenge)

      // For demo, we'll use a simplified flow where we just navigate
      // In production, proper signature verification would happen here
      const demoToken = `demo_token_${Date.now()}`
      apiService.setSessionToken(demoToken)
      localStorage.setItem('agentrust_session_token', demoToken)
      localStorage.setItem('agentrust_agent_id', values.agentId)
      localStorage.setItem('agentrust_cert_id', values.certId)
      localStorage.setItem('agentrust_demo_mode', 'true')

      message.success('登录成功（Demo 模式）')
      navigate('/dashboard')
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
          width: 420,
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
            <Form.Item
              name="agentId"
              label="Agent ID"
              rules={[{ required: true, message: '请输入 Agent ID' }]}
            >
              <Input prefix={<KeyOutlined />} placeholder="agent-xxxxxxxx" />
            </Form.Item>

            <Form.Item
              name="certId"
              label="证书 ID"
              rules={[{ required: true, message: '请输入证书 ID' }]}
            >
              <Input prefix={<SafetyCertificateOutlined />} placeholder="cert-xxxxxxxx" />
            </Form.Item>

            <Form.Item
              name="privateKey"
              label="私钥文件路径"
              rules={[{ required: true, message: '请输入私钥文件路径' }]}
            >
              <Input.Password placeholder="./keys/agent_private.pem" />
            </Form.Item>

            <Paragraph type="secondary" style={{ fontSize: 12 }}>
              <Text type="warning">注意</Text>：Demo 模式下跳过实际签名验证。
              实际使用请通过 Agent SDK 进行认证。
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
