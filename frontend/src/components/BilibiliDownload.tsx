import React, { useState, useEffect } from 'react'
import { Button, message, Progress, Input, Card, Typography, Space, Spin, Select, Upload, Tag } from 'antd'
import { DownloadOutlined, UploadOutlined, DeleteOutlined } from '@ant-design/icons'
import { projectApi, bilibiliApi, VideoCategory, BilibiliDownloadTask, DownloadTaskCreateResponse } from '../services/api'
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
  const [selectedBrowser, setSelectedBrowser] = useState<string>('chrome')
  const [categories, setCategories] = useState<VideoCategory[]>([])
  const [loadingCategories, setLoadingCategories] = useState(false)
  const [downloading, setDownloading] = useState(false)
  const [currentTask, setCurrentTask] = useState<BilibiliDownloadTask | null>(null)
  const [pollingInterval, setPollingInterval] = useState<number | null>(null)
  const [videoInfo, setVideoInfo] = useState<any>(null)
  const [parsing, setParsing] = useState(false)
  const [error, setError] = useState('')
  const [youtubeCookieStatus, setYoutubeCookieStatus] = useState<{
    configured: boolean
    path: string
    size?: number
    updated_at?: string
    in_docker?: boolean
    hint?: string
  } | null>(null)
  const [douyinCookieStatus, setDouyinCookieStatus] = useState<{
    configured: boolean
    path: string
    size?: number
    updated_at?: string
    in_docker?: boolean
    hint?: string
  } | null>(null)
  const [cookieUploading, setCookieUploading] = useState(false)
  
  const { addProject } = useProjectStore()

  const refreshCookieStatus = async () => {
    try {
      const [yt, dy] = await Promise.all([
        bilibiliApi.getYouTubeCookiesStatus(),
        bilibiliApi.getDouyinCookiesStatus(),
      ])
      setYoutubeCookieStatus(yt)
      setDouyinCookieStatus(dy)
    } catch (e) {
      console.error('Failed to load cookie status:', e)
    }
  }

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
    refreshCookieStatus()
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

  const douyinPatterns = [
    /^https?:\/\/(www\.|m\.)?douyin\.com\/video\/\d+/,
    /^https?:\/\/(www\.)?douyin\.com\/(?:jingxuan|discover|note)\/?\?.*modal_id=\d+/,
    /^https?:\/\/v\.douyin\.com\/[0-9A-Za-z]+\/?/,
    /^https?:\/\/(www\.)?iesdouyin\.com\/(?:share\/)?video\/\d+/,
  ]

  const isDouyinUserPage = (url: string) => /douyin\.com\/user\//i.test(url)

  const validateVideoUrl = (url: string): boolean => {
    return bilibiliPatterns.some(pattern => pattern.test(url)) ||
           youtubePatterns.some(pattern => pattern.test(url)) ||
           douyinPatterns.some(pattern => pattern.test(url))
  }
  
  const getVideoType = (url: string): 'bilibili' | 'youtube' | 'douyin' | null => {
    if (bilibiliPatterns.some(pattern => pattern.test(url))) {
      return 'bilibili'
    }
    if (youtubePatterns.some(pattern => pattern.test(url))) {
      return 'youtube'
    }
    if (douyinPatterns.some(pattern => pattern.test(url))) {
      return 'douyin'
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
      if (isDouyinUserPage(url.trim())) {
        setError('这是抖音用户主页，请粘贴单条视频链接（www.douyin.com/video/... 或 App 分享短链）')
      } else {
        setError('请输入正确的 B站 / YouTube / 抖音 视频链接')
      }
      return
    }

    setParsing(true)
    setError('') // 清除之前的错误信息
    
    try {
      let response: { video_info?: any; used_browser?: string | null } | undefined
      if (videoType === 'bilibili') {
        response = await bilibiliApi.parseVideoInfo(url.trim(), selectedBrowser)
      } else if (videoType === 'youtube') {
        response = await bilibiliApi.parseYouTubeVideoInfo(url.trim(), selectedBrowser || undefined)
        if (response?.used_browser && !selectedBrowser) {
          setSelectedBrowser(response.used_browser)
        }
      } else {
        response = await bilibiliApi.parseDouyinVideoInfo(url.trim(), selectedBrowser || undefined)
        if (response?.used_browser && !selectedBrowser) {
          setSelectedBrowser(response.used_browser)
        }
      }
      
      const parsedVideoInfo = response?.video_info
      if (!parsedVideoInfo) {
        setError('未获取到视频信息')
        return
      }
      
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
      if (tip.includes('用户主页')) {
        setError(tip)
      } else if (tip.includes('bot') || tip.includes('登录') || tip.includes('Cookie') || tip.includes('浏览器') || tip.includes('cookie') || tip.includes('Fresh cookies')) {
        const platform = getVideoType(url.trim()) === 'douyin' ? '抖音' : 'YouTube'
        if (platform === '抖音') {
          setError(`解析失败：${tip}\n公开视频一般无需 Cookie；可换 App 分享短链，或上传 douyin.com 的 cookies.txt 后重试。`)
        } else {
          setError(`${platform} 需要登录态。请上传 cookies.txt（Docker 推荐）或选择已登录浏览器后重试。`)
        }
      } else {
        setError(`解析失败：${tip}`)
      }
      setVideoInfo(null)
    } finally {
      setParsing(false)
    }
  }

  const formatDownloadError = (raw?: string) => {
    const tip = String(raw || '未知错误')
    if (/bot|sign in|登录|cookie|cookies\.txt|认证|fresh cookies/i.test(tip)) {
      const platform = getVideoType(url.trim()) === 'douyin' ? '抖音' : 'YouTube'
      return `${tip}\n请重新上传有效的 ${platform} cookies.txt 后再试。`
    }
    return tip
  }

  const startPolling = (taskId: string, videoType: 'bilibili' | 'youtube' | 'douyin', projectId?: string) => {
    const interval = setInterval(async () => {
      try {
        let task
        if (videoType === 'bilibili') {
          task = await bilibiliApi.getTaskStatus(taskId)
        } else if (videoType === 'youtube') {
          task = await bilibiliApi.getYouTubeTaskStatus(taskId)
        } else {
          task = await bilibiliApi.getDouyinTaskStatus(taskId)
        }
        setCurrentTask(task)
        
        if (task.status === 'completed') {
          clearInterval(interval)
          setPollingInterval(null)
          setDownloading(false)
          message.success('视频下载完成，已提交后台处理')
          refreshCookieStatus()
          
          const pid = task.project_id || projectId
          if (pid && onDownloadSuccess) {
            onDownloadSuccess(pid)
          }
          
          resetForm()
        } else if (task.status === 'failed') {
          clearInterval(interval)
          setPollingInterval(null)
          setDownloading(false)
          const errText = formatDownloadError(task.error_message)
          setError(errText)
          message.error({
            content: errText,
            duration: 8,
          })
          if (videoType === 'youtube' || videoType === 'douyin') {
            refreshCookieStatus()
          }
          if (projectId && onDownloadSuccess) {
            // 刷新列表，让失败项目状态可见
            onDownloadSuccess(projectId)
          }
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
      message.error('请输入有效的 B站 / YouTube / 抖音 视频链接')
      return
    }

    setDownloading(true)
    setError('')
    
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

      let response: DownloadTaskCreateResponse & Partial<BilibiliDownloadTask>
      if (videoType === 'bilibili') {
        response = await bilibiliApi.createDownloadTask(requestBody)
      } else if (videoType === 'youtube') {
        response = await bilibiliApi.createYouTubeDownloadTask(requestBody)
      } else {
        response = await bilibiliApi.createDouyinDownloadTask(requestBody)
      }
      
      const platformName =
        videoType === 'bilibili' ? 'B站' : videoType === 'youtube' ? 'YouTube' : '抖音'

      // 新格式：先建项目，再轮询后台下载任务（失败时要提示，尤其是 Cookie/bot）
      if (response.project_id) {
        message.info(`${platformName}项目已创建，正在后台下载…`)
        if (onDownloadSuccess) {
          onDownloadSuccess(response.project_id)
        }
        if (response.task_id) {
          setCurrentTask({
            id: response.task_id,
            status: 'processing',
            progress: 0,
            project_id: response.project_id,
          } as any)
          startPolling(response.task_id, videoType, response.project_id)
        } else {
          setDownloading(false)
          resetForm()
          message.success(`${platformName}项目创建成功`)
        }
      } else if (response.id) {
        const legacyTask = {
          ...response,
          id: response.id,
          status: (response.status as BilibiliDownloadTask['status']) || 'processing',
          progress: response.progress ?? 0,
          url: response.url || url.trim(),
          project_name: response.project_name || projectName || '',
          created_at: response.created_at || new Date().toISOString(),
          updated_at: response.updated_at || new Date().toISOString(),
        } satisfies BilibiliDownloadTask
        setCurrentTask(legacyTask)
        startPolling(response.id, videoType, response.project_id)
      } else {
        setDownloading(false)
        message.warning('未返回任务 ID，请到项目列表查看下载状态')
      }
      
    } catch (error: any) {
      setDownloading(false)
      const errorMessage = formatDownloadError(
        error.response?.data?.detail || error.message || '创建下载任务失败'
      )
      setError(errorMessage)
      message.error({ content: errorMessage, duration: 8 })
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
      <div style={{ marginBottom: videoInfo || error || parsing ? '16px' : 0 }}>
        <Space direction="vertical" style={{ width: '100%' }} size={16}>
          <div>
            <Input.TextArea
              placeholder="请粘贴 B站 / YouTube / 抖音 链接。例：B站 BV… · YouTube watch/shorts · 抖音 https://v.douyin.com/… 或 www.douyin.com/video/…"
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
                borderRadius: '16px',
                color: '#14181f',
                fontSize: '15px',
                lineHeight: 1.6,
                minHeight: 160,
                height: 160,
                padding: '18px 16px',
                resize: 'none',
                boxSizing: 'border-box',
              }}
              rows={6}
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

            {(getVideoType(url.trim()) === 'youtube' || getVideoType(url.trim()) === 'douyin') && (() => {
              const isDouyin = getVideoType(url.trim()) === 'douyin'
              const cookieStatus = isDouyin ? douyinCookieStatus : youtubeCookieStatus
              const platformLabel = isDouyin ? '抖音' : 'YouTube'
              const cookieDomain = isDouyin ? 'douyin.com' : 'youtube.com'
              return (
              <div style={{ marginTop: '12px' }}>
                <Text style={{ color: '#14181f', marginBottom: '8px', display: 'block', fontSize: '14px', fontWeight: 500 }}>
                  {isDouyin
                    ? '抖音 Cookie（可选，公开视频一般不需要）'
                    : 'YouTube 登录态（Docker 推荐上传 cookies.txt）'}
                </Text>
                <div style={{
                  display: 'flex',
                  flexWrap: 'wrap',
                  gap: '8px',
                  alignItems: 'center',
                  marginBottom: '8px'
                }}>
                  {cookieStatus?.configured ? (
                    <Tag color="success">已配置 cookies.txt</Tag>
                  ) : isDouyin ? (
                    <Tag color="default">未配置（公开视频可跳过）</Tag>
                  ) : (
                    <Tag color="warning">未配置 cookies.txt</Tag>
                  )}
                  {cookieStatus?.in_docker && (
                    <Tag>Docker 环境</Tag>
                  )}
                  {cookieStatus?.updated_at && (
                    <Text style={{ color: '#6b7585', fontSize: '12px' }}>
                      更新于 {new Date(cookieStatus.updated_at).toLocaleString()}
                    </Text>
                  )}
                </div>
                <Space wrap style={{ marginBottom: '8px' }}>
                  <Upload
                    accept=".txt,.cookies,text/plain"
                    showUploadList={false}
                    disabled={downloading || parsing || cookieUploading}
                    beforeUpload={async (file) => {
                      setCookieUploading(true)
                      try {
                        if (isDouyin) {
                          await bilibiliApi.uploadDouyinCookies(file)
                        } else {
                          await bilibiliApi.uploadYouTubeCookies(file)
                        }
                        message.success('cookies.txt 已上传，可重新解析')
                        await refreshCookieStatus()
                      } catch (e: any) {
                        message.error(e?.response?.data?.detail || e?.message || '上传失败')
                      } finally {
                        setCookieUploading(false)
                      }
                      return false
                    }}
                  >
                    <Button icon={<UploadOutlined />} loading={cookieUploading} disabled={downloading || parsing}>
                      上传 cookies.txt
                    </Button>
                  </Upload>
                  {cookieStatus?.configured && (
                    <Button
                      icon={<DeleteOutlined />}
                      disabled={downloading || parsing || cookieUploading}
                      onClick={async () => {
                        try {
                          if (isDouyin) {
                            await bilibiliApi.deleteDouyinCookies()
                          } else {
                            await bilibiliApi.deleteYouTubeCookies()
                          }
                          message.success('已删除 cookies.txt')
                          await refreshCookieStatus()
                        } catch (e: any) {
                          message.error(e?.response?.data?.detail || e?.message || '删除失败')
                        }
                      }}
                    >
                      清除
                    </Button>
                  )}
                </Space>
                <Text style={{ color: '#6b7585', fontSize: '12px', display: 'block', lineHeight: 1.5, marginBottom: '12px' }}>
                  {isDouyin
                    ? '多数公开视频可直接解析。若失败，请用扩展从 douyin.com 导出 cookies.txt 上传；勿粘贴用户主页。'
                    : cookieStatus?.in_docker
                      ? `Docker 内无法读取本机浏览器。请用扩展「Get cookies.txt LOCALLY」从已登录的 ${cookieDomain} 导出后上传。`
                      : '也可上传 cookies.txt；本机还可直接选择已登录的浏览器。'}
                </Text>
                {!cookieStatus?.in_docker && (
                  <>
                    <Text style={{ color: '#14181f', marginBottom: '8px', display: 'block', fontSize: '14px', fontWeight: 500 }}>
                      或选择本机浏览器 Cookie
                    </Text>
                    <Select
                      placeholder={`选择已登录 ${platformLabel} 的浏览器`}
                      value={selectedBrowser || undefined}
                      onChange={(value) => setSelectedBrowser(value || '')}
                      allowClear
                      style={{ width: '100%' }}
                      disabled={downloading || parsing || !!cookieStatus?.configured}
                    >
                      <Select.Option value="chrome">Chrome</Select.Option>
                      <Select.Option value="safari">Safari</Select.Option>
                      <Select.Option value="edge">Edge</Select.Option>
                      <Select.Option value="firefox">Firefox</Select.Option>
                    </Select>
                    <Text style={{ color: '#6b7585', fontSize: '12px', marginTop: '8px', display: 'block', lineHeight: 1.5 }}>
                      已上传 cookies.txt 时将优先使用文件，无需再选浏览器。
                    </Text>
                  </>
                )}
              </div>
              )
            })()}
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
                {getVideoType(url) === 'bilibili' ? 'UP主' : getVideoType(url) === 'douyin' ? '作者' : '频道'}: {videoInfo.uploader || '未知'} • 时长: {videoInfo.duration ? `${Math.floor(videoInfo.duration / 60)}:${String(Math.floor(videoInfo.duration % 60)).padStart(2, '0')}` : '未知'}
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
              
              {getVideoType(url.trim()) === 'bilibili' && (
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