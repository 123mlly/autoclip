import React, { useState, useEffect, useCallback, useMemo } from 'react'
import {
  Layout,
  Typography,
  Select,
  Spin,
  Empty,
  message,
  Pagination,
} from 'antd'
import { useNavigate } from 'react-router-dom'
import ProjectCard from '../components/ProjectCard'
import FileUpload from '../components/FileUpload'
import BilibiliDownload from '../components/BilibiliDownload'

import { GetProjectsParams, ProjectPagination, projectApi } from '../services/api'
import { Project, useProjectStore } from '../store/useProjectStore'
import { useProjectPolling } from '../hooks/useProjectPolling'
import './HomePage.css'

const { Content } = Layout
const { Title, Text } = Typography
const { Option } = Select

const DEFAULT_PAGE_SIZE = 20

function isActiveProjectStatus(status: string | undefined): boolean {
  const s = String(status || '').toLowerCase()
  return s === 'pending' || s === 'processing'
}

const HomePage: React.FC = () => {
  const navigate = useNavigate()
  const { projects, setProjects, deleteProject, loading, setLoading } = useProjectStore()
  const [statusFilter, setStatusFilter] = useState<string>('all')
  const [activeTab, setActiveTab] = useState<'upload' | 'bilibili'>('upload')
  const [currentPage, setCurrentPage] = useState(1)
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE)
  const [pagination, setPagination] = useState<ProjectPagination>({
    page: 1,
    size: DEFAULT_PAGE_SIZE,
    total: 0,
    pages: 0,
    has_next: false,
    has_prev: false,
  })

  const listQuery = useMemo<GetProjectsParams>(
    () => ({
      page: currentPage,
      size: pageSize,
      status: statusFilter,
    }),
    [currentPage, pageSize, statusFilter]
  )

  const hasActiveProjects = projects.some((p) => isActiveProjectStatus(p.status))

  const handleProjectsUpdate = useCallback(
    (updatedProjects: Project[]) => {
      setProjects(updatedProjects || [])
    },
    [setProjects]
  )

  const handlePaginationUpdate = useCallback((next: ProjectPagination) => {
    setPagination(next)
  }, [])

  useProjectPolling({
    query: listQuery,
    onProjectsUpdate: handleProjectsUpdate,
    onPaginationUpdate: handlePaginationUpdate,
    enabled: hasActiveProjects,
    interval: 2500,
  })

  const loadProjects = useCallback(
    async (
      withSpinner = true,
      overrides?: Partial<GetProjectsParams>
    ) => {
      if (withSpinner) setLoading(true)
      try {
        const result = await projectApi.getProjects({
          page: overrides?.page ?? currentPage,
          size: overrides?.size ?? pageSize,
          status: overrides?.status ?? statusFilter,
        })
        setProjects(result.items || [])
        setPagination(result.pagination)
        if (overrides?.page !== undefined) {
          setCurrentPage(overrides.page)
        }
      } catch (error) {
        if (withSpinner) message.error('加载项目失败')
        console.error('Load projects error:', error)
        if (withSpinner) setProjects([])
      } finally {
        if (withSpinner) setLoading(false)
      }
    },
    [currentPage, pageSize, statusFilter, setProjects, setLoading]
  )

  useEffect(() => {
    void loadProjects()
  }, [currentPage, pageSize, statusFilter])

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
      const remainingOnPage = projects.filter((p) => p.id !== id).length
      if (remainingOnPage === 0 && currentPage > 1) {
        setCurrentPage(currentPage - 1)
      } else {
        await loadProjects(false)
      }
    } catch (error) {
      message.error('删除项目失败')
      console.error('Delete project error:', error)
    }
  }

  const handleRetryProject = async (projectId: string) => {
    try {
      const project = projects.find((p) => p.id === projectId)
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

  const handleProjectCardClick = (project: Project) => {
    if (String(project.status || '').toLowerCase() === 'pending') {
      message.warning('项目正在导入中，请稍后再查看详情')
      return
    }

    navigate(`/project/${project.id}`)
  }

  const handleImportSuccess = async () => {
    setCurrentPage(1)
    await loadProjects(false, { page: 1 })
  }

  const handleStatusFilterChange = (value: string) => {
    setStatusFilter(value)
    setCurrentPage(1)
  }

  return (
    <Layout style={{ minHeight: '100vh', background: 'transparent' }}>
      <Content style={{ padding: '40px 24px', position: 'relative' }}>
        <div style={{ maxWidth: 1600, margin: '0 auto', position: 'relative', zIndex: 1 }}>
          <div
            style={{
              marginBottom: 48,
              marginTop: 8,
              display: 'flex',
              justifyContent: 'center',
            }}
          >
            <div
              className="studio-panel"
              style={{
                width: '100%',
                maxWidth: 800,
                padding: 24,
              }}
            >
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

              <div style={{ minHeight: 168 }}>
                {activeTab === 'bilibili' && (
                  <BilibiliDownload onDownloadSuccess={handleImportSuccess} />
                )}
                {activeTab === 'upload' && (
                  <FileUpload
                    onUploadSuccess={async () => {
                      await handleImportSuccess()
                      message.success('项目创建成功，正在处理中...')
                    }}
                  />
                )}
              </div>
            </div>
          </div>

          <div className="studio-panel" style={{ padding: 32, marginBottom: 32 }}>
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                marginBottom: 24,
                paddingBottom: 16,
                borderBottom: '1px solid var(--border)',
              }}
            >
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
                <span className="count-chip">共 {pagination.total} 个项目</span>
                {hasActiveProjects && (
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    处理中，自动刷新中…
                  </Text>
                )}
              </div>

              <Select
                placeholder="选择状态"
                value={statusFilter}
                onChange={handleStatusFilterChange}
                style={{ minWidth: 140 }}
                allowClear
              >
                <Option value="all">全部状态</Option>
                <Option value="completed">已完成</Option>
                <Option value="processing">处理中</Option>
                <Option value="pending">等待中</Option>
                <Option value="failed">处理失败</Option>
              </Select>
            </div>

            <div>
              {loading ? (
                <div
                  style={{
                    textAlign: 'center',
                    padding: '60px 0',
                    background: 'var(--surface-2)',
                    borderRadius: 12,
                    border: '1px solid var(--border)',
                  }}
                >
                  <Spin size="large" />
                  <div
                    style={{
                      marginTop: 20,
                      color: 'var(--muted)',
                      fontSize: 16,
                    }}
                  >
                    正在加载项目列表...
                  </div>
                </div>
              ) : projects.length === 0 ? (
                <div
                  style={{
                    textAlign: 'center',
                    padding: '60px 0',
                    background: 'var(--surface-2)',
                    borderRadius: 12,
                    border: '1px solid var(--border)',
                  }}
                >
                  <Empty
                    image={Empty.PRESENTED_IMAGE_SIMPLE}
                    description={
                      <div>
                        <Text type="secondary">
                          {pagination.total === 0
                            ? '还没有项目，请使用上方的导入区域创建第一个项目'
                            : '当前页没有项目，试试其他页或筛选条件'}
                        </Text>
                      </div>
                    }
                  />
                </div>
              ) : (
                <>
                  <div className="project-grid">
                    {projects.map((project: Project) => (
                      <div key={project.id} className="project-grid-item">
                        <ProjectCard
                          project={project}
                          onDelete={handleDeleteProject}
                          onRetry={() => handleRetryProject(project.id)}
                          onClick={() => handleProjectCardClick(project)}
                        />
                      </div>
                    ))}
                  </div>

                  {pagination.total > 0 && (
                    <div
                      style={{
                        display: 'flex',
                        justifyContent: 'center',
                        marginTop: 28,
                        paddingTop: 8,
                      }}
                    >
                      <Pagination
                        current={currentPage}
                        pageSize={pageSize}
                        total={pagination.total}
                        showSizeChanger
                        showQuickJumper
                        pageSizeOptions={[10, 15, 20, 25, 50]}
                        showTotal={(total, range) =>
                          `第 ${range[0]}-${range[1]} 条，共 ${total} 个项目`
                        }
                        onChange={(page, size) => {
                          const nextSize = size ?? pageSize
                          if (nextSize !== pageSize) {
                            setPageSize(nextSize)
                            setCurrentPage(1)
                          } else {
                            setCurrentPage(page)
                          }
                        }}
                      />
                    </div>
                  )}
                </>
              )}
            </div>
          </div>
        </div>
      </Content>
    </Layout>
  )
}

export default HomePage
