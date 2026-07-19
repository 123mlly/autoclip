import React from 'react'
import { Layout, Typography } from 'antd'
import { VideoCameraOutlined } from '@ant-design/icons'
import StoryboardStudio from '../components/StoryboardStudio'
import './StoryboardPage.css'

const { Content } = Layout
const { Title, Text } = Typography

const StoryboardPage: React.FC = () => {
  return (
    <Layout style={{ minHeight: 'calc(100vh - 72px)', background: 'transparent' }}>
      <Content className="storyboard-page">
        <div className="storyboard-page-inner">
          <div className="storyboard-page-hero">
            <div className="storyboard-page-hero-icon">
              <VideoCameraOutlined />
            </div>
            <div>
              <Title level={2} className="storyboard-page-title">
                AI 混剪
              </Title>
              <Text type="secondary">
                上传视频与字幕，AI 生成分镜表，编辑旁白后导出成片
              </Text>
            </div>
          </div>

          <div className="storyboard-page-studio studio-panel">
            <StoryboardStudio />
          </div>
        </div>
      </Content>
    </Layout>
  )
}

export default StoryboardPage
