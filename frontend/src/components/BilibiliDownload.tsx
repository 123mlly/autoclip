import React, { useState, useEffect } from 'react'
import { Button, message, Progress, Input, Card, Typography, Space, Spin, Select } from 'antd'
import { DownloadOutlined } from '@ant-design/icons'
import { projectApi, bilibiliApi, VideoCategory, BilibiliDownloadTask } from '../services/api'
import { useProjectStore } from '../store/useProjectStore'

const { Text } = Typography

interface BilibiliDownloadProps {
  onDownloadSuccess?: (projectId: string) => void
}

// 使用从API导入的BilibiliDownloadTask类型

const BilibiliDownload: React.FC<BilibiliDownloadProps> = ({ onDownloadSuccess }) => {
  const [url, setUrl] = useState('')
  const [projectName, setProjectName] = useState('')
  const [selectedCategory, setSelectedCategory] = useState<string>('')
  const [selectedBrowser, setSelectedBrowser] = useState<string>('')
  const [categories, setCategories] = useState<VideoCategory[]>([])
  const [loadingCategories, setLoadingCategories] = useState(false)
  const [downloading, setDownloading] = useState(false)
  const [currentTask, setCurrentTask] = useState<BilibiliDownloadTask | null>(null)
  const [pollingInterval, setPollingInterval] = useState<number | null>(null)
  const [videoInfo, setVideoInfo] = useState<any>(null)
  const [parsing, setParsing] = useState(false)
  const [error, setError] = useState('')
  
  const { addProject } = useProjectStore()

  // 加载视频分类配置
  useEffect(() => {
    const loadCategories = async () => {
      setLoadingCategories(true)
      try {
        const response = await projectApi.getVideoCategories()
        setCategories(response.categories)
        if (response.default_category) {
          setSelectedCategory(response.default_category)
        } else if (response.categories.length > 0) {
          setSelectedCategory(response.categories[0].value)
        }
      } catch (error) {
        console.error('Failed to load video categories:', error)
        message.error('加载视频分类失败')
      } finally {
        setLoadingCategories(false)
      }
    }

    loadCategories()
  }, [])

  // 清理轮询
  useEffect(() => {
    return () => {
      if (pollingInterval) {
        clearInterval(pollingInterval)
      }
    }
  }, [pollingInterval])

  const bilibiliPatterns = [
    /^https?:\/\/(www\.)?bilibili\.com\/video\/[Bb][Vv][0-9A-Za-z]+/,
    /^https?:\/\/b23\.tv\/[0-9A-Za-z]+/,
    /^https?:\/\/(www\.)?bilibili\.com\/video\/av\d+/
  ]

  const youtubePatterns = [
    /^https?:\/\/(www\.|m\.)?youtube\.com\/watch\?v=[a-zA-Z0-9_-]+/,
    /^https?:\/\/(www\.|m\.)?youtube\.com\/shorts\/[a-zA-Z0-9_-]+/,
    /^https?:\/\/youtu\.be\/[a-zA-Z0-9_-]+/,
    /^https?:\/\/(www\.|m\.)?youtube\.com\/embed\/[a-zA-Z0-9_-]+/,
    /^https?:\/\/(www\.|m\.)?youtube\.com\/v\/[a-zA-Z0-9_-]+/
  ]

  const validateVideoUrl = (url: string): boolean => {
    return bilibiliPatterns.some(pattern => pattern.test(url)) ||
           youtubePatterns.some(pattern => pattern.test(url))
  }
  
  const getVideoType = (url: string): 'bilibili' | 'youtube' | null => {
    if (bilibiliPatterns.some(pattern => pattern.test(url))) {
      return 'bilibili'
    }
    if (youtubePatterns.some(pattern => pattern.test(url))) {
      return 'youtube'
    }
    return null
  }

  const parseVideoInfo = async () => {
    if (!url.trim()) {
      setError('请输入视频链接')
      return
    }

    const videoType = getVideoType(url.trim())
    if (!videoType) {
      setError('请输入正确的B站或YouTube视频链接')
      return
    }

    setParsing(true)
    setError('') // 清除之前的错误信息
    
    try {
      let response
      if (videoType === 'bilibili') {
        response = await bilibiliApi.parseVideoInfo(url.trim(), selectedBrowser)
      } else if (videoType === 'youtube') {
        response = await bilibiliApi.parseYouTubeVideoInfo(url.trim(), selectedBrowser || undefined)
        // 后端自动检测到浏览器时，同步到前端选择
        if (response?.used_browser && !selectedBrowser) {
          setSelectedBrowser(response.used_browser)
        }
      }
      
      const parsedVideoInfo = response.video_info
      
      setVideoInfo(parsedVideoInfo)
      setError('') // 解析成功，清除错误信息
      
      // 自动填充项目名称
      if (!projectName && parsedVideoInfo.title) {
        setProjectName(parsedVideoInfo.title)
      }
      
      return parsedVideoInfo
    } catch (error: any) {
      const detail =
        error?.response?.data?.detail ||
        error?.message ||
        '解析失败'
      const tip = String(detail)
      if (tip.includes('bot') || tip.includes('登录') || tip.includes('Cookie') || tip.includes('浏览器')) {
        setError('YouTube 需要浏览器登录态。请选择已登录 YouTube 的浏览器（Chrome/Safari）后重试。')
      } else {
        setError(`解析失败：${tip}`)
      }
      setVideoInfo(null)
    } finally {
      setParsing(false)
    }
  }

  const startPolling = (taskId: string, videoType: 'bilibili' | 'youtube') => {
    const interval = setInterval(async () => {
      try {
        let task
        if (videoType === 'bilibili') {
          task = await bilibiliApi.getTaskStatus(taskId)
        } else {
          task = await bilibiliApi.getYouTubeTaskStatus(taskId)
        }
        setCurrentTask(task)
        
        if (task.status === 'completed') {
          clearInterval(interval)
          setPollingInterval(null)
          setDownloading(false)
          message.success('视频下载完成！')
          
          if (task.project_id && onDownloadSuccess) {
            onDownloadSuccess(task.project_id)
          }
          
          // 重置状态
          resetForm()
        } else if (task.status === 'failed') {
          clearInterval(interval)
          setPollingInterval(null)
          setDownloading(false)
          message.error(`下载失败: ${task.error_message || '未知错误'}`)
          resetForm()
        }
      } catch (error) {
        console.error('轮询任务状态失败:', error)
      }
    }, 2000)
    
    setPollingInterval(interval)
  }

  const handleDownload = async () => {
    if (!url.trim()) {
      message.error('请输入视频链接')
      return
    }

    const videoType = getVideoType(url.trim())
    if (!videoType) {
      message.error('请输入有效的B站或YouTube视频链接')
      return
    }

    setDownloading(true)
    
    try {
      const requestBody: any = {
        url: url.trim(),
        video_category: selectedCategory
      }
      
      if (projectName.trim()) {
        requestBody.project_name = projectName.trim()
      }
      
      if (selectedBrowser) {
        requestBody.browser = selectedBrowser
      }

      let response
      if (videoType === 'bilibili') {
        response = await bilibiliApi.createDownloadTask(requestBody)
      } else {
        response = await bilibiliApi.createYouTubeDownloadTask(requestBody)
      }
      
      // 检查响应是否包含项目ID（新的优化后的响应格式）
      if (response.project_id) {
        // 新格式：项目已创建，立即重置表单
        setCurrentTask(null)
        setDownloading(false)
        resetForm()
        
        // 显示统一的成功提示
        const platformName = videoType === 'bilibili' ? 'B站' : 'YouTube'
        message.success(`${platformName}项目创建成功，正在后台下载中，您可以继续添加其他项目`)
        
        if (onDownloadSuccess) {
          onDownloadSuccess(response.project_id)
        }
      } else {
        // 旧格式：继续轮询任务状态
        setCurrentTask(response)
        startPolling(response.id, videoType)
      }
      
    } catch (error: any) {
      setDownloading(false)
      const errorMessage = error.response?.data?.detail || error.message || '创建下载任务失败'
      message.error(errorMessage)
    }
  }

  const resetForm = () => {
    setUrl('')
    setProjectName('')
    setCurrentTask(null)
    setVideoInfo(null)
    setError('')
    // 保持分类和浏览器选择，方便用户继续添加项目
    // setSelectedCategory(categories[0].value)
    // setSelectedBrowser('')
  }

  const stopDownload = () => {
    if (pollingInterval) {
      clearInterval(pollingInterval)
      setPollingInterval(null)
    }
    setDownloading(false)
    setCurrentTask(null)
    message.info('已停止监控下载任务')
  }

  return (
    <div style={{
      width: '100%',
      margin: '0 auto'
    }}>

      {/* 输入表单 */}
      <div style={{ marginBottom: '16px' }}>
        <Space direction="vertical" style={{ width: '100%' }} size={16}>
          <div>
            <Input.TextArea
              placeholder="请粘贴B站或YouTube视频链接，支持：• B站：https://www.bilibili.com/video/BV1xx411c7mu • YouTube：https://www.youtube.com/watch?v=xxxxx 或 Shorts：https://www.youtube.com/shorts/xxxxx"
              value={url}
              onChange={(e) => {
                setUrl(e.target.value)
                // 清除之前的解析结果和错误信息
                if (videoInfo) {
                  setVideoInfo(null)
                  setProjectName('')
                }
                if (error) {
                  setError('')
                }
              }}
              onBlur={() => {
                // 失去焦点时自动解析
                if (url.trim() && !videoInfo && validateVideoUrl(url.trim())) {
                  parseVideoInfo();
                }
              }}
              style={{
                background: '#ffffff',
                border: '1px solid #d5dde6',
                borderRadius: '8px',
                color: '#14181f',
                fontSize: '14px',
                resize: 'none'
              }}
              rows={2}
              disabled={downloading || parsing}
            />
            {parsing && (
               <div style={{
                 marginTop: '8px',
                 color: '#0e7c66',
                 fontSize: '14px',
                 display: 'flex',
                 alignItems: 'center',
                 gap: '8px'
               }}>
                 <span>正在解析视频信息...</span>
               </div>
             )}
             {error && !parsing && (
               <div style={{
                 marginTop: '8px',
                 color: '#ff6b6b',
                 fontSize: '14px',
                 display: 'flex',
                 alignItems: 'center',
                 gap: '8px'
               }}>
                 <span>{error}</span>
               </div>
             )}

            {getVideoType(url.trim()) === 'youtube' && (
              <div style={{ marginTop: '12px' }}>
                <Text style={{ color: '#14181f', marginBottom: '8px', display: 'block', fontSize: '14px', fontWeight: 500 }}>
                  浏览器 Cookie（YouTube 推荐）
                </Text>
                <Select
                  placeholder="选择已登录 YouTube 的浏览器"
                  value={selectedBrowser || undefined}
                  onChange={(value) => setSelectedBrowser(value || '')}
                  allowClear
                  style={{ width: '100%' }}
                  disabled={downloading || parsing}
                >
                  <Select.Option value="chrome">Chrome</Select.Option>
                  <Select.Option value="safari">Safari</Select.Option>
                  <Select.Option value="edge">Edge</Select.Option>
                  <Select.Option value="firefox">Firefox</Select.Option>
                </Select>
                <Text style={{ color: '#6b7585', fontSize: '12px', marginTop: '8px', display: 'block', lineHeight: 1.5 }}>
                  YouTube 常需登录态。请先在该浏览器打开 youtube.com 并登录，再选择对应浏览器后重新解析。
                </Text>
              </div>
            )}
          </div>
          
          {/* 显示解析成功的视频信息 */}
          {videoInfo && (
            <div style={{
              background: 'rgba(14, 124, 102, 0.08)',
              border: '1px solid rgba(14, 124, 102, 0.2)',
              borderRadius: '8px',
              padding: '12px',
              marginBottom: '12px'
            }}>
              <Text style={{ color: '#0e7c66', fontWeight: 600, fontSize: '16px', display: 'block', marginBottom: '8px' }}>
                视频信息解析成功
              </Text>
              <Text style={{ color: '#14181f', fontSize: '14px', display: 'block' }}>
                {videoInfo.title}
              </Text>
              <Text style={{ color: '#6b7585', fontSize: '12px' }}>
                {getVideoType(url) === 'bilibili' ? 'UP主' : '频道'}: {videoInfo.uploader || '未知'} • 时长: {videoInfo.duration ? `${Math.floor(videoInfo.duration / 60)}:${String(Math.floor(videoInfo.duration % 60)).padStart(2, '0')}` : '未知'}
              </Text>
            </div>
          )}
          
          {/* 只有解析成功后才显示项目名称和分类 */}
          {videoInfo && (
            <>
              <div>
                <Text style={{ color: '#14181f', marginBottom: '12px', display: 'block', fontSize: '16px', fontWeight: 500 }}>项目名称（可选）</Text>
                <Input
                  placeholder="留空将使用视频标题作为项目名称"
                  value={projectName}
                  onChange={(e) => setProjectName(e.target.value)}
                  style={{
                    background: '#ffffff',
                    border: '1px solid #d5dde6',
                    borderRadius: '12px',
                    color: '#14181f',
                    height: '48px',
                    fontSize: '14px'
                  }}
                  disabled={downloading}
                />
              </div>
              
              {getVideoType(url.trim()) !== 'youtube' && (
              <div>
                <Text style={{ color: '#14181f', marginBottom: '12px', display: 'block', fontSize: '16px', fontWeight: 500 }}>浏览器选择（获取AI字幕需要）</Text>
                <Select
                  placeholder="选择浏览器以获取cookie（可选）"
                  value={selectedBrowser || undefined}
                  onChange={(value) => setSelectedBrowser(value || '')}
                  allowClear
                  style={{
                    width: '100%',
                    height: '48px'
                  }}
                  dropdownStyle={{
                    background: '#ffffff',
                    border: '1px solid #d5dde6',
                    borderRadius: '12px'
                  }}
                  disabled={downloading}
                >
                  <Select.Option value="chrome">Chrome</Select.Option>
                  <Select.Option value="firefox">Firefox</Select.Option>
                  <Select.Option value="safari">Safari</Select.Option>
                  <Select.Option value="edge">Edge</Select.Option>
                </Select>
                <Text style={{ color: '#6b7585', fontSize: '12px', marginTop: '8px', display: 'block' }}>
                  选择浏览器可获取登录状态，用于下载AI字幕。如不选择将只能下载公开字幕。
                </Text>
              </div>
              )}
              
              <div>
                <Text style={{ color: '#14181f', marginBottom: '12px', display: 'block', fontSize: '16px', fontWeight: 500 }}>视频分类</Text>
                {loadingCategories ? (
                  <Spin size="small" />
                ) : (
                  <div style={{
                    display: 'flex',
                    flexWrap: 'wrap',
                    gap: '8px'
                  }}>
                    {categories.map(category => {
                      const isSelected = selectedCategory === category.value
                      return (
                        <div
                          key={category.value}
                          onClick={() => setSelectedCategory(category.value)}
                          style={{
                            display: 'flex',
                            alignItems: 'center',
                            gap: '6px',
                            padding: '8px 12px',
                            borderRadius: '6px',
                            border: isSelected 
                              ? `2px solid ${category.color}` 
                              : '2px solid #d5dde6',
                            background: isSelected 
                              ? `${category.color}15` 
                              : '#f7f9fb',
                            color: isSelected ? '#14181f' : '#6b7585',
                            boxShadow: isSelected 
                              ? 'var(--shadow-sm)' 
                              : 'none',
                            cursor: 'pointer',
                            transition: 'all 0.2s ease',
                            fontSize: '13px',
                            fontWeight: isSelected ? 600 : 400,
                            userSelect: 'none'
                          }}
                          onMouseEnter={(e) => {
                            if (!isSelected) {
                              e.currentTarget.style.background = '#eef2f5'
                              e.currentTarget.style.borderColor = '#b8c4d1'
                            }
                          }}
                          onMouseLeave={(e) => {
                            if (!isSelected) {
                              e.currentTarget.style.background = '#f7f9fb'
                              e.currentTarget.style.borderColor = '#d5dde6'
                            }
                          }}
                        >
                          <span style={{ fontSize: '14px' }}>{category.icon}</span>
                          <span>{category.name}</span>
                        </div>
                      )
                    })}
                  </div>
                )}
              </div>
            </>
          )}
        </Space>
      </div>

      {/* 操作按钮 - 只有解析成功后才显示 */}
      {videoInfo && (
        <div style={{ marginBottom: '16px', display: 'flex', justifyContent: 'center', gap: '12px' }}>
          <Button
            type="primary"
            icon={<DownloadOutlined />}
            onClick={handleDownload}
            loading={downloading}
            disabled={!url.trim()}
            size="large"
            style={{
              background: '#0e7c66',
              border: 'none',
              borderRadius: '12px',
              height: '48px',
              padding: '0 32px',
              fontSize: '16px',
              fontWeight: 600,
              boxShadow: 'var(--shadow-sm)',
              minWidth: '160px'
            }}
          >
            {downloading ? '导入中...' : '开始导入'}
          </Button>
          
          {downloading && (
            <Button
              onClick={stopDownload}
              size="large"
              style={{
                background: '#f7f9fb',
                border: '1px solid #d5dde6',
                color: '#14181f',
                borderRadius: '12px',
                height: '48px',
                padding: '0 24px',
                fontSize: '14px'
              }}
            >
              停止监控
            </Button>
          )}
        </div>
      )}

      {/* 下载进度 */}
      {currentTask && (
        <Card
          style={{
            background: '#ffffff',
            border: '1px solid #d5dde6',
            borderRadius: '12px',
            marginTop: '16px',
            backdropFilter: 'blur(10px)'
          }}
          styles={{
            body: { padding: '16px' }
          }}
        >
          <div style={{ marginBottom: '16px' }}>
            <Text style={{ color: '#14181f', fontWeight: 600, fontSize: '18px' }}>导入进度</Text>
          </div>
          
          {currentTask.video_info && (
            <div style={{ marginBottom: '16px' }}>
              <Text style={{ color: '#0e7c66', fontWeight: 600, fontSize: '16px' }}>{currentTask.video_info.title}</Text>
            </div>
          )}
          
          <div style={{ marginBottom: '16px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
              <Text style={{ color: '#6b7585', fontSize: '14px' }}>状态: {currentTask.status}</Text>
              <Text style={{ color: '#6b7585', fontSize: '14px' }}>{Math.round(currentTask.progress)}%</Text>
            </div>
            
            <Progress
              percent={Math.round(currentTask.progress)}
              status={currentTask.status === 'failed' ? 'exception' : 'active'}
              strokeColor="#0e7c66"
              trailColor="#eef2f5"
              strokeWidth={8}
              showInfo={false}
            />
          </div>
          
          {currentTask.error_message && (
            <div style={{ 
              marginTop: '16px',
              padding: '12px',
              background: 'rgba(255, 77, 79, 0.1)',
              border: '1px solid rgba(255, 77, 79, 0.3)',
              borderRadius: '8px'
            }}>
              <Text style={{ color: '#ff4d4f', fontSize: '14px' }}>错误: {currentTask.error_message}</Text>
            </div>
          )}
        </Card>
      )}
    </div>
  )
}

export default BilibiliDownload