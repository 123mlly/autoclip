import React, { useState, useEffect, useRef } from 'react'
import { Card, Button, Tooltip, Modal, message } from 'antd'
import { PlayCircleOutlined, DownloadOutlined, ClockCircleOutlined, StarFilled, EditOutlined, UploadOutlined } from '@ant-design/icons'
import ReactPlayer from 'react-player'
import { Clip } from '../store/useProjectStore'
import SubtitleEditor from './SubtitleEditor'
import { subtitleEditorApi } from '../services/subtitleEditorApi'
import { SubtitleSegment, VideoEditOperation } from '../types/subtitle'
import UploadModal from './UploadModal'
import EditableTitle from './EditableTitle'
import './ClipCard.css'

interface ClipCardProps {
  clip: Clip
  videoUrl?: string
  onDownload: (clipId: string) => void
  projectId?: string
  onClipUpdate?: (clipId: string, updates: Partial<Clip>) => void
}

const ClipCard: React.FC<ClipCardProps> = ({ 
  clip, 
  videoUrl, 
  onDownload,
  projectId,
  onClipUpdate
}) => {
  const [coverStatus, setCoverStatus] = useState<'loading' | 'ready' | 'failed'>('loading')
  const [showPlayer, setShowPlayer] = useState(false)
  const [showSubtitleEditor, setShowSubtitleEditor] = useState(false)
  const [subtitleData, setSubtitleData] = useState<SubtitleSegment[]>([])
  const [loadingSubtitles, setLoadingSubtitles] = useState(false)
  const [showUploadModal, setShowUploadModal] = useState(false)
  const playerRef = useRef<ReactPlayer>(null)
  const coverVideoRef = useRef<HTMLVideoElement>(null)

  // 用 video 元素直接显示首帧作封面（避免 canvas CORS / 大文件截帧卡住）
  useEffect(() => {
    if (!videoUrl) {
      setCoverStatus('failed')
      return
    }

    setCoverStatus('loading')

    const timer = window.setTimeout(() => {
      setCoverStatus(prev => (prev === 'loading' ? 'ready' : prev))
    }, 6000)

    return () => window.clearTimeout(timer)
  }, [videoUrl])

  const handleCoverLoadedMetadata = () => {
    const video = coverVideoRef.current
    if (!video) return
    const t = Number.isFinite(video.duration) && video.duration > 0
      ? Math.min(0.8, Math.max(0.1, video.duration * 0.05))
      : 0.1
    try {
      video.currentTime = t
    } catch {
      setCoverStatus('ready')
    }
  }

  const handleDownloadWithTitle = async () => {
    try {
      // 直接调用API下载方法，它会处理文件名
      await onDownload(clip.id)
    } catch (error) {
      console.error('下载失败:', error)
      message.error('下载失败')
    }
  }

  const handleClosePlayer = () => {
    setShowPlayer(false)
  }

  const handleOpenSubtitleEditor = async () => {
    if (!projectId) {
      message.error('缺少项目信息，无法打开按台词剪辑')
      return
    }

    setLoadingSubtitles(true)
    try {
      const response = await subtitleEditorApi.getClipSubtitles(projectId, clip.id)
      if (!response.segments?.length) {
        message.warning('该切片暂无可用台词（需先有语音识别或字幕文件）')
        return
      }
      setSubtitleData(response.segments)
      setShowSubtitleEditor(true)
    } catch (error) {
      console.error('获取台词数据失败:', error)
      message.error(error instanceof Error ? error.message : '获取台词数据失败')
    } finally {
      setLoadingSubtitles(false)
    }
  }

  const handleSubtitleEditorClose = () => {
    setShowSubtitleEditor(false)
    setSubtitleData([])
  }

  const handleSubtitleEditorSave = async (operations: VideoEditOperation[]) => {
    if (!projectId) {
      throw new Error('缺少项目信息')
    }

    const deletedSegments = operations
      .filter(op => op.type === 'delete')
      .flatMap(op => op.segmentIds)

    if (deletedSegments.length === 0) {
      message.info('没有需要应用的删除操作')
      return
    }

    const result = await subtitleEditorApi.editClipBySubtitles(
      projectId,
      clip.id,
      deletedSegments
    )

    if (!result.success) {
      throw new Error(result.message || '视频编辑失败')
    }

    message.success(
      `编辑成功，已删除 ${result.deleted_duration?.toFixed(1) ?? 0}s，最终时长 ${result.final_duration?.toFixed(1) ?? 0}s`
    )

    try {
      await subtitleEditorApi.downloadEditedVideo(
        projectId,
        clip.id,
        `${clip.title || clip.generated_title || clip.id}_edited.mp4`
      )
    } catch (downloadError) {
      console.warn('自动下载编辑视频失败:', downloadError)
      message.info('编辑视频已生成，可稍后从编辑结果目录获取')
    }

    setShowSubtitleEditor(false)
    setSubtitleData([])
  }

  const handleTitleUpdate = (newTitle: string) => {
    // 更新本地状态
    onClipUpdate?.(clip.id, { title: newTitle })
  }


  const formatDuration = (seconds: number) => {
    if (!seconds || seconds <= 0) return '00:00'
    const minutes = Math.floor(seconds / 60)
    const remainingSeconds = Math.floor(seconds % 60)
    return `${minutes.toString().padStart(2, '0')}:${remainingSeconds.toString().padStart(2, '0')}`
  }

  const calculateDuration = (startTime: string, endTime: string): number => {
    if (!startTime || !endTime) return 0
    
    try {
      // 解析时间格式 "HH:MM:SS,mmm" 或 "HH:MM:SS.mmm"
      const parseTime = (timeStr: string): number => {
        const normalized = timeStr.replace(',', '.')
        const parts = normalized.split(':')
        if (parts.length !== 3) return 0
        
        const hours = parseInt(parts[0]) || 0
        const minutes = parseInt(parts[1]) || 0
        const seconds = parseFloat(parts[2]) || 0
        
        return hours * 3600 + minutes * 60 + seconds
      }
      
      const start = parseTime(startTime)
      const end = parseTime(endTime)
      
      return Math.max(0, end - start)
    } catch (error) {
      console.error('Error calculating duration:', error)
      return 0
    }
  }

  const getDuration = () => {
    if (!clip.start_time || !clip.end_time) return '00:00'
    const start = clip.start_time.replace(',', '.')
    const end = clip.end_time.replace(',', '.')
    return `${start.substring(0, 8)} - ${end.substring(0, 8)}`
  }

  const getScoreColor = (score: number) => {
    // 根据分数区间设置不同的颜色
    if (score >= 0.9) return '#52c41a' // 绿色 - 优秀
    if (score >= 0.8) return '#0e7c66' // 青绿 - 良好
    if (score >= 0.7) return '#faad14' // 橙色 - 一般
    if (score >= 0.6) return '#ff7a45' // 红橙色 - 较差
    return '#ff4d4f' // 红色 - 差
  }


  // 获取要显示的简介内容
  const getDisplayContent = () => {
    // 优先显示推荐理由（这是AI生成的内容要点）
    if (clip.recommend_reason && clip.recommend_reason.trim()) {
      return clip.recommend_reason
    }
    
    // 如果没有推荐理由，尝试从content中获取非转写文本的内容要点
    if (clip.content && clip.content.length > 0) {
      // 过滤掉可能是转写文本的内容（通常转写文本很长且包含标点符号）
      const contentPoints = clip.content.filter(item => {
        const text = item.trim()
        // 如果文本长度超过100字符或包含大量标点符号，可能是转写文本
        if (text.length > 100) return false
        if (text.split(/[，。！？；：""''（）【】]/).length > 3) return false
        return true
      })
      
      if (contentPoints.length > 0) {
        return contentPoints.join(' ')
      }
    }
    
    // 最后回退到outline（大纲）
    if (clip.outline && clip.outline.trim()) {
      return clip.outline
    }
    
    return '暂无内容要点'
  }

  const textRef = useRef<HTMLDivElement>(null)

  return (
    <>
      <Card
          className="clip-card"
          hoverable
          style={{ 
            height: '380px',
            borderRadius: '16px',
            border: '1px solid #d5dde6',
            background: '#ffffff',
            overflow: 'hidden',
            cursor: 'pointer'
          }}
          styles={{
            body: {
              padding: 0,
            },
          }}
          cover={
            <div 
              style={{ 
                height: '200px', 
                background: '#f7f9fb',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                position: 'relative',
                cursor: 'pointer',
                overflow: 'hidden'
              }}
              onClick={() => setShowPlayer(true)}
            >
              {videoUrl && coverStatus !== 'failed' ? (
                <video
                  ref={coverVideoRef}
                  src={videoUrl}
                  muted
                  playsInline
                  preload="metadata"
                  onLoadedMetadata={handleCoverLoadedMetadata}
                  onSeeked={() => setCoverStatus('ready')}
                  onError={() => setCoverStatus('failed')}
                  style={{
                    width: '100%',
                    height: '100%',
                    objectFit: 'cover',
                    display: 'block',
                    background: '#000'
                  }}
                />
              ) : (
                <PlayCircleOutlined style={{ fontSize: 40, color: '#6b7585' }} />
              )}
              {coverStatus === 'loading' && videoUrl && (
                <div
                  style={{
                    position: 'absolute',
                    inset: 0,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    background: 'rgba(0,0,0,0.35)',
                    color: 'rgba(255,255,255,0.75)',
                    fontSize: 13,
                    pointerEvents: 'none'
                  }}
                >
                  加载封面中...
                </div>
              )}
              <div 
                style={{
                  position: 'absolute',
                  top: 0,
                  left: 0,
                  right: 0,
                  bottom: 0,
                  background: 'rgba(0,0,0,0.35)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  opacity: 0,
                  transition: 'opacity 0.3s ease'
                }}
                className="video-overlay"
              >
                <PlayCircleOutlined style={{ fontSize: '40px', color: 'white' }} />
              </div>
              
              {/* 右上角推荐分数 */}
              <div 
                style={{
                  position: 'absolute',
                  top: '12px',
                  right: '12px',
                  background: getScoreColor(clip.final_score),
                  color: 'white',
                  padding: '4px 8px',
                  borderRadius: '8px',
                  fontSize: '12px',
                  fontWeight: 500,
                  display: 'flex',
                  alignItems: 'center',
                  gap: '4px'
                }}
              >
                <StarFilled style={{ fontSize: '12px' }} />
                {(clip.final_score * 100).toFixed(0)}分
              </div>
              
              {/* 左下角时间区间 */}
              <div 
                style={{
                  position: 'absolute',
                  bottom: '12px',
                  left: '12px',
                  background: 'rgba(0,0,0,0.7)',
                  color: 'white',
                  padding: '4px 8px',
                  borderRadius: '8px',
                  fontSize: '12px',
                  fontWeight: 500,
                  display: 'flex',
                  alignItems: 'center',
                  gap: '4px'
                }}
              >
                <ClockCircleOutlined style={{ fontSize: '12px' }} />
                {getDuration()}
              </div>
              
              {/* 右下角视频时长 */}
              <div 
                style={{
                  position: 'absolute',
                  bottom: '12px',
                  right: '12px',
                  background: 'rgba(0,0,0,0.7)',
                  color: 'white',
                  padding: '4px 8px',
                  borderRadius: '8px',
                  fontSize: '12px',
                  fontWeight: 500,
                  display: 'flex',
                  alignItems: 'center',
                  gap: '4px'
                }}
              >
                {formatDuration(calculateDuration(clip.start_time, clip.end_time))}
              </div>
            </div>
          }
        >
          <div style={{ 
            padding: '16px', 
            height: '180px', 
            display: 'flex', 
            flexDirection: 'column',
            justifyContent: 'space-between'
          }}>
            {/* 内容区域 - 固定高度 */}
            <div style={{ 
              flex: 1,
              display: 'flex',
              flexDirection: 'column',
              minHeight: 0 // 允许flex子项收缩
            }}>
              {/* 标题区域 - 固定高度 */}
              <div style={{ 
                height: '44px',
                marginBottom: '8px',
                display: 'flex',
                alignItems: 'flex-start'
              }}>
                <EditableTitle
                  title={clip.title || clip.generated_title || '未命名片段'}
                  clipId={clip.id}
                  onTitleUpdate={handleTitleUpdate}
                  style={{ 
                    fontSize: '16px',
                    fontWeight: 600,
                    lineHeight: '1.4',
                    color: '#14181f',
                    width: '100%'
                  }}
                />
              </div>
              
              {/* 内容要点 - 固定高度 */}
              <div style={{ 
                height: '58px',
                marginBottom: '12px',
                display: 'flex',
                alignItems: 'flex-start'
              }}>
                <Tooltip 
                  title={getDisplayContent()} 
                  placement="top" 
                  overlayStyle={{ maxWidth: '300px' }}
                  mouseEnterDelay={0.5}
                >
                  <div 
                    ref={textRef}
                    style={{ 
                      fontSize: '13px',
                      display: '-webkit-box',
                      WebkitLineClamp: 3,
                      WebkitBoxOrient: 'vertical',
                      overflow: 'hidden',
                      lineHeight: '1.5',
                      color: '#6b7585',
                      cursor: 'pointer',
                      wordBreak: 'break-word',
                      textOverflow: 'ellipsis',
                      width: '100%'
                    }}
                  >
                    {getDisplayContent()}
                  </div>
                </Tooltip>
              </div>
            </div>
            
            {/* 操作按钮 - 固定在底部 */}
            <div style={{ 
              display: 'flex', 
              gap: '8px',
              height: '28px',
              alignItems: 'center',
              marginTop: 'auto'
            }}>
              <Button 
                type="text" 
                size="small"
                icon={<PlayCircleOutlined />}
                onClick={() => setShowPlayer(true)}
                style={{
                  color: '#0e7c66',
                  border: '1px solid rgba(14, 124, 102, 0.3)',
                  borderRadius: '6px',
                  fontSize: '12px',
                  height: '28px',
                  padding: '0 12px',
                  background: 'rgba(14, 124, 102, 0.08)'
                }}
              >
                播放
              </Button>
              <Button 
                type="text" 
                size="small"
                icon={<DownloadOutlined />}
                onClick={handleDownloadWithTitle}
                style={{
                  color: '#52c41a',
                  border: '1px solid rgba(82, 196, 26, 0.3)',
                  borderRadius: '6px',
                  fontSize: '12px',
                  height: '28px',
                  padding: '0 12px',
                  background: 'rgba(82, 196, 26, 0.1)'
                }}
              >
                下载
              </Button>
              <Button 
                type="text" 
                size="small"
                icon={<UploadOutlined />}
                onClick={() => {
                  if (!projectId) {
                    message.warning('缺少项目信息，无法投稿')
                    return
                  }
                  setShowUploadModal(true)
                }}
                style={{
                  color: '#ff7875',
                  border: '1px solid rgba(255, 120, 117, 0.3)',
                  borderRadius: '6px',
                  fontSize: '12px',
                  height: '28px',
                  padding: '0 12px',
                  background: 'rgba(255, 120, 117, 0.1)'
                }}
              >
                投稿
              </Button>
            </div>
          </div>
        </Card>

      {/* 视频播放模态框 */}
      <Modal
        open={showPlayer}
        onCancel={handleClosePlayer}
        footer={[
          <Button key="download" type="primary" icon={<DownloadOutlined />} onClick={handleDownloadWithTitle}>
            下载视频
          </Button>,
          <Button 
            key="subtitle" 
            icon={<EditOutlined />} 
            loading={loadingSubtitles}
            onClick={handleOpenSubtitleEditor}
          >
            按台词剪辑
          </Button>,
          <Button 
            key="upload" 
            type="default" 
            icon={<UploadOutlined />} 
            onClick={() => {
              if (!projectId) {
                message.warning('缺少项目信息，无法投稿')
                return
              }
              setShowPlayer(false)
              setShowUploadModal(true)
            }}
          >
            投稿发布
          </Button>
        ]}
        width={800}
        centered
        destroyOnClose
        styles={{
          header: {
            borderBottom: '1px solid #d5dde6',
            background: '#ffffff'
          }
        }}
        closeIcon={
          <span style={{ color: '#14181f', fontSize: '16px' }}>×</span>
        }
        title={
          <div style={{ 
            display: 'flex', 
            alignItems: 'center', 
            width: '100%',
            paddingRight: '30px' // 为关闭按钮留出空间
          }}>
            <EditableTitle
              title={clip.title || clip.generated_title || '视频预览'}
              clipId={clip.id}
              onTitleUpdate={(newTitle) => {
                // 更新clip的标题
                console.log('播放器标题已更新:', newTitle)
                // 这里可以触发父组件的更新回调
                if (onClipUpdate) {
                  onClipUpdate(clip.id, { title: newTitle })
                }
              }}
              style={{ 
                color: '#14181f', 
                fontSize: '16px', 
                fontWeight: '500',
                flex: 1,
                maxWidth: 'calc(100% - 40px)' // 确保不会与关闭按钮重叠
              }}
            />
          </div>
        }
      >
        {videoUrl && (
          <ReactPlayer
            ref={playerRef}
            url={videoUrl}
            width="100%"
            height="400px"
            controls
            playing={showPlayer}
            config={{
              file: {
                attributes: {
                  controlsList: 'nodownload',
                  preload: 'metadata'
                },
                forceHLS: false,
                forceDASH: false
              }
            }}
            onReady={() => {
              console.log('Video ready for seeking')
            }}
            onError={(error) => {
              console.error('ReactPlayer error:', error)
            }}
          />
        )}
      </Modal>

      {/* 按台词剪辑 */}
      {showSubtitleEditor && (
          <SubtitleEditor
            videoUrl={videoUrl || ''}
            subtitles={subtitleData}
            onSave={handleSubtitleEditorSave}
            onClose={handleSubtitleEditorClose}
          />
      )}

      {/* 投稿弹窗（B站 / YouTube） */}
      <UploadModal
        visible={showUploadModal}
        onCancel={() => setShowUploadModal(false)}
        projectId={projectId || ''}
        clipIds={[clip.id]}
        clipTitles={[clip.title || clip.generated_title || '视频片段']}
        onSuccess={() => {
          message.success('投稿任务已创建')
        }}
      />
    </>
  )
}

export default ClipCard