import React, { useState, useEffect, useCallback } from 'react'
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

const { Content } = Layout
const { Title, Text } = Typography
const { Option } = Select

function isActiveProjectStatus(status: string | undefined): boolean {
  const s = String(status || '').toLowerCase()
  return s === 'pending' || s === 'processing'
}

const HomePage: React.FC = () => {
  const navigate = useNavigate()
  const { projects, setProjects, deleteProject, loading, setLoading } = useProjectStore()
  const [statusFilter, setStatusFilter] = useState<string>('all')
  const [activeTab, setActiveTab] = useState<'upload' | 'bilibili'>('upload')

  const hasActiveProjects = projects.some((p) => isActiveProjectStatus(p.status))

  const handleProjectsUpdate = useCallback((updatedProjects: Project[]) => {
    setProjects(updatedProjects || [])
  }, [setProjects])

  // 仅有下载/处理中的项目时轮询；全部完成后停止
  const { refreshNow } = useProjectPolling({
    onProjectsUpdate: handleProjectsUpdate,
    enabled: hasActiveProjects,
    interval: 2500
  })

  const loadProjects = useCallback(async (withSpinner = true) => {
    if (withSpinner) setLoading(true)
    try {
      const list = await projectApi.getProjects()
      setProjects(list || [])
    } catch (error) {
      if (withSpinner) message.error('加载项目失败')
      console.error('Load projects error:', error)
      if (withSpinner) setProjects([])
    } finally {
      if (withSpinner) setLoading(false)
    }
  }, [setProjects, setLoading])

  useEffect(() => {
    void loadProjects()
  }, [loadProjects])

  // 回到页面时补一次，避免闲时停轮询后状态过旧
  useEffect(() => {
    const onFocus = () => {
      void loadProjects(false)
    }
    const onVisibility = () => {
      if (document.visibilityState === 'visible') onFocus()
    }
    window.addEventListener('focus', onFocus)
    document.addEventListener('visibilitychange', onVisibility)
    return () => {
      window.removeEventListener('focus', onFocus)
      document.removeEventListener('visibilitychange', onVisibility)
    }
  }, [loadProjects])

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
      const project = projects.find(p => p.id === projectId)
      if (!project) {
        message.error('项目不存在')
        return
      }
      
      await projectApi.retryProcessing(projectId)
      message.success('已开始重试处理项目')
      
      await loadProjects(false)
    } catch (error) {
      message.error('重试失败，请稍后再试')
      console.error('Retry project error:', error)
    }
  }

  const handleStartProcessing = async (projectId: string) => {
    try {
      await projectApi.startProcessing(projectId)
      message.success('项目已开始处理，请稍等片刻查看进度')
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
      
      if ((error as { code?: string; message?: string })?.code === 'ECONNABORTED' || (error as { code?: string; message?: string })?.message?.includes('timeout')) {
        message.info('请求超时，但项目可能已开始处理，请查看项目状态', 5)
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
    if (String(project.status || '').toLowerCase() === 'pending') {
      message.warning('项目正在导入中，请稍后再查看详情')
      return
    }
    
    navigate(`/project/${project.id}`)
  }

  const filteredProjects = projects
    .filter(project => {
      const matchesStatus = statusFilter === 'all' || project.status === statusFilter
      return matchesStatus
    })
    .sort((a, b) => {
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
                    await loadProjects(false)
                  }} />
                )}
                {activeTab === 'upload' && (
                  <FileUpload onUploadSuccess={async () => {
                    await loadProjects(false)
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
                {hasActiveProjects && (
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    处理中，自动刷新中…
                  </Text>
                )}
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
