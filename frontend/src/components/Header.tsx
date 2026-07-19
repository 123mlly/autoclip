import React from 'react'
import { Layout, Button } from 'antd'
import {
  SettingOutlined,
  HomeOutlined,
  VideoCameraOutlined,
} from '@ant-design/icons'
import { useNavigate, useLocation } from 'react-router-dom'
import logoUrl from '../assets/logo.svg'

const { Header: AntHeader } = Layout

const Header: React.FC = () => {
  const navigate = useNavigate()
  const location = useLocation()
  const pathname = location.pathname
  const isHomePage = pathname === '/'
  const isStoryboardPage = pathname === '/storyboard'
  const showBackHome = !isHomePage && !isStoryboardPage

  return (
    <AntHeader
      className="glass-effect site-header"
      style={{
        padding: '0 32px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        height: 72,
        position: 'sticky',
        top: 0,
        zIndex: 1000,
        backdropFilter: 'blur(16px)',
        background: 'rgba(255, 255, 255, 0.84)',
        borderBottom: '1px solid var(--border)',
      }}
    >
      <div
        className="brand-mark"
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 12,
          cursor: 'pointer',
          fontSize: 24,
        }}
        onClick={() => navigate('/')}
      >
        <img
          src={logoUrl}
          alt="AutoClip"
          width={36}
          height={36}
          style={{ display: 'block', borderRadius: 9 }}
        />
        <span className="brand-wordmark">
          Auto<span>Clip</span>
        </span>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <Button
          type={isHomePage ? 'primary' : 'text'}
          icon={<HomeOutlined />}
          onClick={() => navigate('/')}
          style={{ height: 40, padding: '0 16px' }}
        >
          首页
        </Button>
        <Button
          type={isStoryboardPage ? 'primary' : 'text'}
          icon={<VideoCameraOutlined />}
          onClick={() => navigate('/storyboard')}
          style={{ height: 40, padding: '0 16px' }}
        >
          AI 混剪
        </Button>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        {showBackHome && (
          <Button
            type="primary"
            icon={<HomeOutlined />}
            onClick={() => navigate('/')}
            style={{ height: 40, padding: '0 18px' }}
          >
            返回首页
          </Button>
        )}

        <Button
          type="text"
          icon={<SettingOutlined />}
          onClick={() => navigate('/settings')}
          style={{ height: 40, padding: '0 14px', color: 'var(--ink-soft)' }}
        >
          设置
        </Button>
      </div>
    </AntHeader>
  )
}

export default Header
