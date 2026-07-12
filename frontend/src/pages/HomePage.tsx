import React, { useState, useEffect } from 'react'
import { 
  Layout, 
  Typography, 
  Select, 
  Spin, 
  Empty,
  message 
} from 'antd'
import { useNavigate } from 'react-router-dom'
import ProjectCard from '../components/ProjectCard'
import FileUpload from '../components/FileUpload'
import BilibiliDownload from '../components/BilibiliDownload'

import { projectApi } from '../services/api'
import { Project, useProjectStore } from '../store/useProjectStore'
import { useProjectPolling } from '../hooks/useProjectPolling'
// import { useWebSocket, WebSocketEventMessage } from '../hooks/useWebSocket'  // 已禁用WebSocket系统

const { Content } = Layout
const { Title, Text } = Typography
const { Option } = Select

const HomePage: React.FC = () => {
  const navigate = useNavigate()
  const { projects, setProjects, deleteProject, loading, setLoading } = useProjectStore()
  const [statusFilter, setStatusFilter] = useState<string>('all')
  const [activeTab, setActiveTab] = useState<'upload' | 'bilibili'>('upload')

  const hasActiveProjects = projects.some(
    (p) => p.status === 'pending' || p.status === 'processing'
  )

  // 使用项目轮询Hook（下载/字幕阶段加快刷新）
  const { refreshNow } = useProjectPolling({
    onProjectsUpdate: (updatedProjects) => {
      setProjects(updatedProjects || [])
    },
    enabled: true,
    interval: hasActiveProjects ? 2500 : 15000
  })

  useEffect(() => {
    loadProjects()
  }, [])

  const loadProjects = async () => {
    setLoading(true)
    try {
      // 从后端API获取真实项目数据
      const projects = await projectApi.getProjects()
      setProjects(projects || [])
    } catch (error) {
      message.error('加载项目失败')
      console.error('Load projects error:', error)
      // 如果API调用失败，设置空数组
      setProjects([])
    } finally {
      setLoading(false)
    }
  }

  // 使用集合差异对齐订阅项目WebSocket主题
  // WebSocket订阅已禁用，使用新的简化进度系统
  // useEffect(() => {
  //   if (isConnected && projects.length > 0) {
  //     const desiredChannels = projects.map(project => `project_${project.id}`)
  //     console.log('同步订阅项目频道:', desiredChannels)
  //     syncSubscriptions(desiredChannels)
  //   } else if (isConnected && projects.length === 0) {
  //     // 如果没有项目，清空所有订阅
  //     console.log('清空所有项目订阅')
  //     syncSubscriptions([])
  //   }
  // }, [isConnected, projects, syncSubscriptions])

  const handleDeleteProject = async (id: string) => {
    try {
      await projectApi.deleteProject(id)
      deleteProject(id)
      message.success('项目删除成功')
    } catch (error) {
      message.error('删除项目失败')
      console.error('Delete project error:', error)
    }
  }

  const handleRetryProject = async (projectId: string) => {
    try {
      // 查找项目状态
      const project = projects.find(p => p.id === projectId)
      if (!project) {
        message.error('项目不存在')
        return
      }
      
      // 统一使用retryProcessing API，它会自动处理视频文件不存在的情况
      await projectApi.retryProcessing(projectId)
      message.success('已开始重试处理项目')
      
      await loadProjects()
    } catch (error) {
      message.error('重试失败，请稍后再试')
      console.error('Retry project error:', error)
    }
  }

  const handleStartProcessing = async (projectId: string) => {
    try {
      await projectApi.startProcessing(projectId)
      message.success('项目已开始处理，请稍等片刻查看进度')
      // 立即刷新项目列表以显示最新状态
      setTimeout(async () => {
        try {
          await refreshNow()
        } catch (refreshError) {
          console.error('Failed to refresh after starting processing:', refreshError)
        }
      }, 1000)
    } catch (error: unknown) {
      const errorMessage = (error as { userMessage?: string })?.userMessage || '启动处理失败'
      message.error(errorMessage)
      console.error('Start processing error:', error)
      
      // 如果是超时错误，提示用户项目可能仍在处理
      if ((error as { code?: string; message?: string })?.code === 'ECONNABORTED' || (error as { code?: string; message?: string })?.message?.includes('timeout')) {
        message.info('请求超时，但项目可能已开始处理，请查看项目状态', 5)
        // 延迟刷新项目列表
        setTimeout(async () => {
          try {
            await refreshNow()
          } catch (refreshError) {
            console.error('Failed to refresh after timeout:', refreshError)
          }
        }, 3000)
      }
    }
  }

  const handleProjectCardClick = (project: Project) => {
    // 导入中状态的项目不能点击进入详情页
    if (project.status === 'pending') {
      message.warning('项目正在导入中，请稍后再查看详情')
      return
    }
    
    // 其他状态可以正常进入详情页
    navigate(`/project/${project.id}`)
  }

  const filteredProjects = projects
    .filter(project => {
      const matchesStatus = statusFilter === 'all' || project.status === statusFilter
      return matchesStatus
    })
    .sort((a, b) => {
      // 按创建时间倒序排列，最新的在前面
      return new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
    })

  return (
    <Layout style={{ minHeight: '100vh', background: 'transparent' }}>
      <Content style={{ padding: '40px 24px', position: 'relative' }}>
        <div style={{ maxWidth: 1600, margin: '0 auto', position: 'relative', zIndex: 1 }}>
          <div style={{
            marginBottom: 48,
            marginTop: 8,
            display: 'flex',
            justifyContent: 'center'
          }}>
            <div className="studio-panel" style={{
              width: '100%',
              maxWidth: 800,
              padding: 24,
            }}>
              <div className="tab-switch" style={{ marginBottom: 20 }}>
                <button
                  className={activeTab === 'bilibili' ? 'active' : ''}
                  onClick={() => setActiveTab('bilibili')}
                >
                  链接导入
                </button>
                <button
                  className={activeTab === 'upload' ? 'active' : ''}
                  onClick={() => setActiveTab('upload')}
                >
                  文件导入
                </button>
              </div>

              <div>
                {activeTab === 'bilibili' && (
                  <BilibiliDownload onDownloadSuccess={async () => {
                    await loadProjects()
                  }} />
                )}
                {activeTab === 'upload' && (
                  <FileUpload onUploadSuccess={async () => {
                    await loadProjects()
                    message.success('项目创建成功，正在处理中...')
                  }} />
                )}
              </div>
            </div>
          </div>

          <div className="studio-panel" style={{ padding: 32, marginBottom: 32 }}>
            <div style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              marginBottom: 24,
              paddingBottom: 16,
              borderBottom: '1px solid var(--border)'
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
                <Title
                  level={2}
                  className="section-title"
                  style={{
                    margin: 0,
                    fontSize: 28,
                    fontWeight: 700,
                  }}
                >
                  我的项目
                </Title>
                <span className="count-chip">
                  共 {filteredProjects.length} 个项目
                </span>
              </div>

              <Select
                placeholder="选择状态"
                value={statusFilter}
                onChange={setStatusFilter}
                style={{ minWidth: 140 }}
                allowClear
              >
                  <Option value="all">全部状态</Option>
                  <Option value="completed">已完成</Option>
                  <Option value="processing">处理中</Option>
                  <Option value="error">处理失败</Option>
                </Select>
            </div>

            <div>
              {loading ? (
                <div style={{
                  textAlign: 'center',
                  padding: '60px 0',
                  background: 'var(--surface-2)',
                  borderRadius: 12,
                  border: '1px solid var(--border)'
                }}>
                  <Spin size="large" />
                  <div style={{
                    marginTop: 20,
                    color: 'var(--muted)',
                    fontSize: 16
                  }}>
                    正在加载项目列表...
                  </div>
                </div>
              ) : filteredProjects.length === 0 ? (
                <div style={{
                  textAlign: 'center',
                  padding: '60px 0',
                  background: 'var(--surface-2)',
                  borderRadius: 12,
                  border: '1px solid var(--border)'
                }}>
                  <Empty
                    image={Empty.PRESENTED_IMAGE_SIMPLE}
                    description={
                      <div>
                        <Text type="secondary">
                          {projects.length === 0 ? '还没有项目，请使用上方的导入区域创建第一个项目' : '没有找到匹配的项目'}
                        </Text>
                      </div>
                    }
                  />
                </div>
              ) : (
                <div style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))',
                  gap: 16,
                  justifyContent: 'start',
                  padding: '6px 0'
                }}>
                  {filteredProjects.map((project: Project) => (
                    <div key={project.id} style={{ position: 'relative', zIndex: 1 }}>
                      <ProjectCard
                        project={project}
                        onDelete={handleDeleteProject}
                        onRetry={() => handleRetryProject(project.id)}
                        onClick={() => handleProjectCardClick(project)}
                      />
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      </Content>
    </Layout>
  )
}

export default HomePage