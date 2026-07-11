import React, { useState, useRef } from 'react'
import { Modal, Typography, Button, Tag, Space, Row, Col, Divider, message } from 'antd'
import { 
  PlayCircleOutlined, 
  DownloadOutlined, 
  ClockCircleOutlined, 
  StarFilled,
  CloseOutlined,
  EditOutlined
} from '@ant-design/icons'
import ReactPlayer from 'react-player'
import { Clip } from '../store/useProjectStore'
import { projectApi } from '../services/api'
import SubtitleEditor from './SubtitleEditor'
import { subtitleEditorApi } from '../services/subtitleEditorApi'
import EditableTitle from './EditableTitle'
import { SubtitleSegment, VideoEditOperation } from '../types/subtitle'

const { Text, Title } = Typography

interface ClipDetailModalProps {
  visible: boolean
  clip: Clip | null
  projectId: string
  onClose: () => void
  onDownload: (clipId: string) => void
}

const ClipDetailModal: React.FC<ClipDetailModalProps> = ({
  visible,
  clip,
  projectId,
  onClose,
  onDownload
}) => {
  const [playing, setPlaying] = useState(false)
  const [downloading, setDownloading] = useState(false)
  const [showSubtitleEditor, setShowSubtitleEditor] = useState(false)
  const [subtitleData, setSubtitleData] = useState<SubtitleSegment[]>([])
  const [loadingSubtitles, setLoadingSubtitles] = useState(false)
  const playerRef = useRef<ReactPlayer>(null)

  const formatTime = (timeStr: string) => {
    if (!timeStr) return '00:00:00'
    // 移除小数点后的毫秒部分，只保留时分秒
    return timeStr.replace(',', '.').substring(0, 8)
  }

  const getDuration = () => {
    if (!clip?.start_time || !clip?.end_time) return '00:00:00'
    const start = clip.start_time.replace(',', '.')
    const end = clip.end_time.replace(',', '.')
    return `${start.substring(0, 8)} - ${end.substring(0, 8)}`
  }

  const getScoreColor = (score: number) => {
    // 根据分数区间设置不同的颜色
    if (score >= 0.9) return '#52c41a' // 绿色 - 优秀
    if (score >= 0.8) return '#1890ff' // 蓝色 - 良好
    if (score >= 0.7) return '#faad14' // 橙色 - 一般
    if (score >= 0.6) return '#ff7a45' // 红橙色 - 较差
    return '#ff4d4f' // 红色 - 差
  }

  const handleDownload = async () => {
    if (!clip) return
    setDownloading(true)
    try {
      await onDownload(clip.id)
    } finally {
      setDownloading(false)
    }
  }

  const handleClose = () => {
    setPlaying(false)
    onClose()
  }

  const handleOpenSubtitleEditor = async () => {
    if (!clip) return

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
    if (!clip) {
      throw new Error('切片不存在')
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

  if (!clip) return null

  return (
    <>
      <Modal
        visible={visible}
        onCancel={handleClose}
        footer={null}
        width={800}
        centered
        destroyOnClose
        style={{ top: 20 }}
        styles={{
          body: {
            padding: 0,
            background: '#ffffff',
            borderRadius: '12px'
          }
        }}
      >
        <div style={{ padding: '24px' }}>
          {/* 头部 */}
          <div style={{ 
            display: 'flex', 
            justifyContent: 'space-between', 
            alignItems: 'center',
            marginBottom: '20px'
          }}>
            <Title level={4} style={{ margin: 0, color: '#14181f' }}>
              切片详情
            </Title>
            <Button 
              type="text" 
              icon={<CloseOutlined />} 
              onClick={handleClose}
              style={{ color: '#6b7585' }}
            />
          </div>

          <Row gutter={24}>
            {/* 左侧视频播放器 */}
            <Col span={14}>
              <div style={{ 
                background: '#000', 
                borderRadius: '8px', 
                overflow: 'hidden',
                marginBottom: '16px'
              }}>
                <ReactPlayer
                  ref={playerRef}
                  url={projectApi.getClipVideoUrl(projectId, clip.id, clip.title || clip.generated_title)}
                  width="100%"
                  height="300px"
                  playing={playing}
                  controls
                  onPlay={() => setPlaying(true)}
                  onPause={() => setPlaying(false)}
                  style={{ borderRadius: '8px' }}
                />
              </div>

              {/* 视频信息 */}
              <div style={{ marginBottom: '16px' }}>
                <Space size="middle">
                  <Tag color="blue" icon={<ClockCircleOutlined />}>
                    {getDuration()}
                  </Tag>
                  {clip.final_score && (
                    <Tag 
                      icon={<StarFilled />}
                      style={{ 
                        background: getScoreColor(clip.final_score),
                        color: 'white',
                        border: 'none'
                      }}
                    >
                      评分: {(clip.final_score * 100).toFixed(0)}分
                    </Tag>
                  )}
                  {clip.outline && (
                    <Tag color="purple">{clip.outline}</Tag>
                  )}
                </Space>
              </div>

              {/* 操作按钮 */}
              {console.log('Rendering operation buttons in ClipDetailModal')}
              <Space>
                <Button 
                  type="primary" 
                  icon={<PlayCircleOutlined />}
                  onClick={() => setPlaying(!playing)}
                >
                  {playing ? '暂停' : '播放'}
                </Button>
                <Button 
                  type="default" 
                  icon={<DownloadOutlined />}
                  loading={downloading}
                  onClick={handleDownload}
                >
                  下载切片
                </Button>
                <Button 
                  type="default" 
                  icon={<EditOutlined />}
                  loading={loadingSubtitles}
                  onClick={handleOpenSubtitleEditor}
                >
                  按台词剪辑
                </Button>
              </Space>
            </Col>

            {/* 右侧详细信息 */}
            <Col span={10}>
              <div style={{ color: '#14181f' }}>
                {/* 标题 */}
                <div style={{ marginBottom: '16px' }}>
                  <div style={{ marginBottom: '8px' }}>
                    <EditableTitle
                      title={clip.generated_title || clip.title || '未命名片段'}
                      clipId={clip.id}
                      onTitleUpdate={(newTitle) => {
                        // 更新clip的标题
                        console.log('标题已更新:', newTitle)
                        // 这里可以触发父组件的更新回调
                      }}
                      style={{ color: '#14181f', fontSize: '18px', fontWeight: '600' }}
                    />
                  </div>
                  <Text style={{ color: '#6b7585', fontSize: '12px' }}>
                    ID: {clip.id}
                  </Text>
                </div>

                <Divider style={{ borderColor: '#d5dde6' }} />

                {/* 内容要点 */}
                {clip.content && clip.content.length > 0 && (
                  <div style={{ marginBottom: '16px' }}>
                    <Text strong style={{ color: '#14181f', display: 'block', marginBottom: '8px' }}>
                      内容要点:
                    </Text>
                    <div>
                      {clip.content.map((point, index) => (
                        <div key={index} style={{ 
                          color: '#3d4654', 
                          fontSize: '14px',
                          marginBottom: '4px',
                          padding: '4px 8px',
                          background: '#f7f9fb',
                          borderRadius: '4px'
                        }}>
                          • {point}
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* 时间戳信息 */}
                <div style={{ marginBottom: '16px' }}>
                  <Text strong style={{ color: '#ffffff', display: 'block', marginBottom: '8px' }}>
                    时间信息:
                  </Text>
                  <div style={{ color: '#3d4654', fontSize: '14px' }}>
                    <div>开始时间: {formatTime(clip.start_time)}</div>
                    <div>结束时间: {formatTime(clip.end_time)}</div>
                  </div>
                </div>


              </div>
            </Col>
          </Row>
        </div>
      </Modal>

      {/* 按台词剪辑 */}
      {showSubtitleEditor && clip && (
          <SubtitleEditor
            videoUrl={projectApi.getClipVideoUrl(projectId, clip.id, clip.title || clip.generated_title)}
            subtitles={subtitleData}
            onSave={handleSubtitleEditorSave}
            onClose={handleSubtitleEditorClose}
          />
      )}
    </>
  )
}

export default ClipDetailModal 