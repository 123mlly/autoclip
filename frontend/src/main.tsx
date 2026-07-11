import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { ConfigProvider } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import dayjs from 'dayjs'
import 'dayjs/locale/zh-cn'
import relativeTime from 'dayjs/plugin/relativeTime'
import timezone from 'dayjs/plugin/timezone'
import utc from 'dayjs/plugin/utc'
import App from './App.tsx'
import './index.css'

dayjs.extend(relativeTime)
dayjs.extend(timezone)
dayjs.extend(utc)
dayjs.locale('zh-cn')
dayjs.tz.setDefault('Asia/Shanghai')

const theme = {
  token: {
    colorPrimary: '#0e7c66',
    colorInfo: '#0e7c66',
    colorSuccess: '#1f8a5b',
    colorWarning: '#c9851a',
    colorError: '#d64545',
    colorText: '#14181f',
    colorTextSecondary: '#6b7585',
    colorBgBase: '#eef2f5',
    colorBgContainer: '#ffffff',
    colorBorder: '#d5dde6',
    borderRadius: 10,
    fontFamily: "'Plus Jakarta Sans', 'PingFang SC', 'Helvetica Neue', sans-serif",
    fontFamilyCode: "'SF Mono', 'Menlo', 'Consolas', monospace",
  },
  components: {
    Layout: {
      headerBg: 'rgba(255,255,255,0.84)',
      bodyBg: 'transparent',
    },
    Button: {
      primaryShadow: 'none',
      defaultShadow: 'none',
    },
    Card: {
      colorBgContainer: '#ffffff',
    },
    Modal: {
      contentBg: '#ffffff',
      headerBg: '#ffffff',
    },
  },
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <ConfigProvider locale={zhCN} theme={theme}>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </ConfigProvider>,
)
