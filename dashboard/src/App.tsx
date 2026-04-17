import React from 'react'
import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom'
import { Layout, Menu, Typography, Space, Button, Avatar, Dropdown, theme } from 'antd'
import {
  DashboardOutlined,
  SafetyCertificateOutlined,
  ShareAltOutlined,
  AuditOutlined,
  LogoutOutlined,
  UserOutlined,
} from '@ant-design/icons'
import type { MenuProps } from 'antd'
import LoginPage from './components/Login'
import CertView from './components/CertView'
import DelegationGraph from './components/DelegationGraph'
import AuditView from './components/AuditView'
import { useAuth } from './hooks/useAuth'

const { Header, Content, Sider } = Layout
const { Title, Text } = Typography

const DashboardLayout: React.FC = () => {
  const { agentId, logout } = useAuth()
  const location = useLocation()
  const { token } = theme.useToken()

  const selectedKey = location.pathname.replace('/dashboard/', '') || 'overview'

  const menuItems: MenuProps['items'] = [
    {
      key: 'overview',
      icon: <DashboardOutlined />,
      label: '概览',
    },
    {
      key: 'certs',
      icon: <SafetyCertificateOutlined />,
      label: '证书管理',
    },
    {
      key: 'delegation',
      icon: <ShareAltOutlined />,
      label: '委托链',
    },
    {
      key: 'audit',
      icon: <AuditOutlined />,
      label: '审计日志',
    },
  ]

  const userMenuItems: MenuProps['items'] = [
    {
      key: 'logout',
      icon: <LogoutOutlined />,
      label: '退出登录',
      danger: true,
    },
  ]

  const handleMenuClick: MenuProps['onClick'] = (e) => {
    if (e.key === 'logout') {
      logout()
    }
  }

  // Dynamic content based on selected menu
  const renderContent = () => {
    switch (selectedKey) {
      case 'certs':
        return <CertView />
      case 'delegation':
        return <DelegationGraph />
      case 'audit':
        return <AuditView />
      default:
        return <OverviewPanel />
    }
  }

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Header
        style={{
          background: token.colorPrimary,
          padding: '0 24px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
        }}
      >
        <Space>
          <SafetyCertificateOutlined style={{ fontSize: 24, color: '#fff' }} />
          <Title level={4} style={{ color: '#fff', margin: 0 }}>
            Agentrust
          </Title>
          <Text style={{ color: 'rgba(255,255,255,0.8)', marginLeft: 8 }}>
            Agent 身份与权限管理系统
          </Text>
        </Space>
        <Dropdown menu={{ items: userMenuItems, onClick: handleMenuClick }} placement="bottomRight">
          <Space style={{ cursor: 'pointer' }}>
            <Avatar icon={<UserOutlined />} />
            <Text style={{ color: '#fff' }}>{agentId || 'User'}</Text>
          </Space>
        </Dropdown>
      </Header>
      <Layout>
        <Sider width={200} style={{ background: token.colorBgContainer }}>
          <Menu
            mode="inline"
            selectedKeys={[selectedKey]}
            items={menuItems}
            style={{ height: '100%', borderRight: 0 }}
            onClick={(e) => {
              if (e.key === 'overview') {
                window.location.href = '/dashboard'
              } else {
                window.location.href = `/dashboard/${e.key}`
              }
            }}
          />
        </Sider>
        <Layout style={{ padding: '24px' }}>
          <Content
            style={{
              background: token.colorBgContainer,
              borderRadius: token.borderRadiusLG,
              padding: 24,
              minHeight: 280,
              overflow: 'auto',
            }}
          >
            {renderContent()}
          </Content>
        </Layout>
      </Layout>
    </Layout>
  )
}

const OverviewPanel: React.FC = () => {
  const { token } = theme.useToken()

  return (
    <div>
      <Title level={4}>系统概览</Title>
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(250px, 1fr))',
          gap: 16,
          marginTop: 24,
        }}
      >
        <div
          style={{
            padding: 24,
            borderRadius: 8,
            background: `linear-gradient(135deg, ${token.colorPrimary} 0%, ${token.colorPrimaryBg} 100%)`,
            color: '#fff',
          }}
        >
          <SafetyCertificateOutlined style={{ fontSize: 32 }} />
          <Title level={2} style={{ color: '#fff', marginTop: 16 }}>
            证书管理
          </Title>
          <Text style={{ color: 'rgba(255,255,255,0.8)' }}>
            查看和管理所有 Agent 的证书
          </Text>
          <div style={{ marginTop: 16 }}>
            <Button
              type="primary"
              ghost
              onClick={() => (window.location.href = '/dashboard/certs')}
            >
              前往管理
            </Button>
          </div>
        </div>

        <div
          style={{
            padding: 24,
            borderRadius: 8,
            background: 'linear-gradient(135deg, #722ed1 0%, #eb8fff 100%)',
            color: '#fff',
          }}
        >
          <ShareAltOutlined style={{ fontSize: 32 }} />
          <Title level={2} style={{ color: '#fff', marginTop: 16 }}>
            委托链
          </Title>
          <Text style={{ color: 'rgba(255,255,255,0.8)' }}>
            可视化查看 Agent 之间的委托关系
          </Text>
          <div style={{ marginTop: 16 }}>
            <Button
              type="primary"
              ghost
              onClick={() => (window.location.href = '/dashboard/delegation')}
            >
              查看关系图
            </Button>
          </div>
        </div>

        <div
          style={{
            padding: 24,
            borderRadius: 8,
            background: 'linear-gradient(135deg, #52c41a 0%, #d9f7be 100%)',
            color: '#fff',
          }}
        >
          <AuditOutlined style={{ fontSize: 32 }} />
          <Title level={2} style={{ color: '#fff', marginTop: 16 }}>
            审计日志
          </Title>
          <Text style={{ color: 'rgba(255,255,255,0.8)' }}>
            查看所有操作的审计记录和拒绝日志
          </Text>
          <div style={{ marginTop: 16 }}>
            <Button
              type="primary"
              ghost
              onClick={() => (window.location.href = '/dashboard/audit')}
            >
              查看日志
            </Button>
          </div>
        </div>
      </div>
    </div>
  )
}

const App: React.FC = () => {
  const { isAuthenticated } = useAuth()

  return (
    <BrowserRouter>
      <Routes>
        <Route
          path="/login"
          element={isAuthenticated ? <Navigate to="/dashboard" replace /> : <LoginPage />}
        />
        <Route
          path="/dashboard"
          element={
            isAuthenticated ? (
              <DashboardLayout />
            ) : (
              <Navigate to="/login" replace />
            )
          }
        />
        <Route
          path="/dashboard/:view"
          element={
            isAuthenticated ? (
              <DashboardLayout />
            ) : (
              <Navigate to="/login" replace />
            )
          }
        />
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Routes>
    </BrowserRouter>
  )
}

export default App
