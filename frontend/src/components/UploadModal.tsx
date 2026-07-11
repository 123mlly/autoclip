import React, { useState, useEffect } from 'react'
import {
  Modal,
  Form,
  Input,
  Select,
  Button,
  Space,
  Tag,
  Progress,
  message,
  Divider,
  Row,
  Col,
  Typography,
  Alert,
  Spin
} from 'antd'
import {
  UploadOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  ExclamationCircleOutlined,
  ClockCircleOutlined
} from '@ant-design/icons'
import { uploadApi } from '../services/uploadApi'
import { BILIBILI_PARTITIONS } from '../services/uploadApi'
import { youtubeUploadApi, YOUTUBE_CATEGORIES, YouTubeAccount } from '../services/youtubeUploadApi'

const { Option } = Select
const { TextArea } = Input
const { Text } = Typography

type UploadPlatform = 'bilibili' | 'youtube'

interface UploadModalProps {
  visible: boolean
  onCancel: () => void
  projectId: string
  clipIds: string[]
  clipTitles: string[]
  onSuccess?: () => void
}

interface UploadProgress {
  status: 'pending' | 'processing' | 'success' | 'failed'
  message: string
  progress: number
  bvid?: string
  videoUrl?: string
  error?: string
}

const UploadModal: React.FC<UploadModalProps> = ({
  visible,
  onCancel,
  projectId,
  clipIds,
  clipTitles,
  onSuccess
}) => {
  const [form] = Form.useForm()
  const [platform, setPlatform] = useState<UploadPlatform>('bilibili')
  const [uploading, setUploading] = useState(false)
  const [uploadProgress, setUploadProgress] = useState<UploadProgress>({
    status: 'pending',
    message: '准备上传...',
    progress: 0
  })
  const [uploadRecordId, setUploadRecordId] = useState<string>('')
  const [pollingInterval, setPollingInterval] = useState<ReturnType<typeof setInterval> | null>(null)

  const initialValues = {
    title: clipTitles.length === 1 ? clipTitles[0] : `${clipTitles[0]} 等${clipIds.length}个视频`,
    description: '',
    tags: [],
    partition_id: 21,
    category_id: '22',
    privacy_status: 'private',
    account_id: undefined
  }

  const [bilibiliAccounts, setBilibiliAccounts] = useState<any[]>([])
  const [youtubeAccounts, setYoutubeAccounts] = useState<YouTubeAccount[]>([])

  useEffect(() => {
    if (!visible) return
    uploadApi.getBilibiliAccounts()
      .then(setBilibiliAccounts)
      .catch((error) => {
        console.error('获取B站账号列表失败:', error)
        setBilibiliAccounts([])
      })
    youtubeUploadApi.getAccounts()
      .then(setYoutubeAccounts)
      .catch((error) => {
        console.error('获取YouTube账号列表失败:', error)
        setYoutubeAccounts([])
      })
  }, [visible])

  useEffect(() => {
    if (visible) {
      form.setFieldsValue({
        ...initialValues,
        account_id: undefined,
      })
    }
  }, [visible, platform])

  const accounts = platform === 'bilibili' ? bilibiliAccounts : youtubeAccounts

  const handleSubmit = async (values: any) => {
    if (!values.account_id) {
      message.error(platform === 'bilibili' ? '请选择B站账号' : '请选择YouTube账号')
      return
    }
    if (!accounts.length) {
      message.error(
        platform === 'bilibili'
          ? '请先在设置页导入 B 站账号 Cookie'
          : '请先在设置页授权 YouTube 账号'
      )
      return
    }

    setUploading(true)
    setUploadProgress({
      status: 'pending',
      message: '正在创建投稿任务...',
      progress: 10
    })

    try {
      let response: { record_id: string; clip_count: number }
      if (platform === 'bilibili') {
        response = await uploadApi.createUploadTask(projectId, {
          clip_ids: clipIds,
          account_id: values.account_id,
          title: values.title,
          description: values.description,
          tags: values.tags || [],
          partition_id: values.partition_id
        })
      } else {
        response = await youtubeUploadApi.createUploadTask(projectId, {
          clip_ids: clipIds,
          account_id: Number(values.account_id),
          title: values.title,
          description: values.description || '',
          tags: values.tags || [],
          category_id: values.category_id || '22',
          privacy_status: values.privacy_status || 'private',
        })
      }

      setUploadRecordId(String(response.record_id))
      setUploadProgress({
        status: 'processing',
        message: `投稿任务已创建，正在处理 ${response.clip_count} 个视频...`,
        progress: 30
      })

      startPolling(String(response.record_id), platform)
      message.success('投稿任务创建成功！')
    } catch (error: any) {
      console.error('创建投稿任务失败:', error)
      const detail = error?.response?.data?.detail || error?.message || '未知错误'
      setUploadProgress({
        status: 'failed',
        message: `创建投稿任务失败: ${detail}`,
        progress: 0,
        error: detail
      })
      setUploading(false)
    }
  }

  const startPolling = (recordId: string, currentPlatform: UploadPlatform) => {
    const interval = setInterval(async () => {
      try {
        if (currentPlatform === 'youtube') {
          const status = await youtubeUploadApi.getUploadRecord(recordId)
          if (status.status === 'success' || status.status === 'completed') {
            setUploadProgress({
              status: 'success',
              message: '投稿成功！',
              progress: 100,
              videoUrl: status.video_url,
              bvid: status.video_id,
            })
            setUploading(false)
            clearInterval(interval)
            setTimeout(() => {
              onSuccess?.()
              onCancel()
            }, 2500)
          } else if (status.status === 'failed' || status.status === 'cancelled') {
            setUploadProgress({
              status: 'failed',
              message: `投稿失败: ${status.error_message || '未知错误'}`,
              progress: 0,
              error: status.error_message
            })
            setUploading(false)
            clearInterval(interval)
          } else {
            setUploadProgress({
              status: 'processing',
              message: status.status === 'pending' ? '任务排队中...' : '正在上传到 YouTube...',
              progress: Math.max(40, status.progress || 60)
            })
          }
          return
        }

        const status = await uploadApi.getUploadRecord(recordId)
        const bvid = (status as any).bv_id || status.bvid
        
        if (status.status === 'success' || status.status === 'completed') {
          setUploadProgress({
            status: 'success',
            message: '投稿成功！',
            progress: 100,
            bvid
          })
          setUploading(false)
          clearInterval(interval)
          
          setTimeout(() => {
            onSuccess?.()
            onCancel()
          }, 2000)
        } else if (status.status === 'failed' || status.status === 'cancelled') {
          setUploadProgress({
            status: 'failed',
            message: `投稿失败: ${status.error_message || '未知错误'}`,
            progress: 0,
            error: status.error_message
          })
          setUploading(false)
          clearInterval(interval)
        } else if (status.status === 'processing') {
          setUploadProgress({
            status: 'processing',
            message: '正在上传到B站...',
            progress: Math.min(90, (status as any).progress || 60)
          })
        } else if (status.status === 'pending') {
          setUploadProgress({
            status: 'processing',
            message: '任务排队中，请稍候...',
            progress: 40
          })
        } else {
          setUploadProgress(prev => ({
            ...prev,
            message: `任务状态: ${status.status}`,
            progress: Math.min(prev.progress + 5, 90)
          }))
        }
      } catch (error) {
        console.error('获取上传状态失败:', error)
        setUploadProgress({
          status: 'failed',
          message: '获取上传状态失败',
          progress: 0,
          error: '网络错误'
        })
        setUploading(false)
        clearInterval(interval)
      }
    }, 2000)

    setPollingInterval(interval)
  }

  // 清理轮询
  useEffect(() => {
    return () => {
      if (pollingInterval) {
        clearInterval(pollingInterval)
      }
    }
  }, [pollingInterval])

  // 弹窗关闭时清理状态
  const handleCancel = () => {
    if (pollingInterval) {
      clearInterval(pollingInterval)
    }
    setUploading(false)
    setUploadProgress({
      status: 'pending',
      message: '准备上传...',
      progress: 0
    })
    setUploadRecordId('')
    form.resetFields()
    onCancel()
  }

  // 取消投稿任务
  const handleCancelUpload = async () => {
    if (!uploadRecordId) {
      handleCancel()
      return
    }

    try {
      // 调用取消投稿API
      await uploadApi.cancelUploadTask(uploadRecordId)
      
      // 清理状态
      if (pollingInterval) {
        clearInterval(pollingInterval)
      }
      setUploading(false)
      setUploadProgress({
        status: 'pending',
        message: '准备上传...',
        progress: 0
      })
      setUploadRecordId('')
      form.resetFields()
      
      // 显示取消成功消息
      message.success('投稿任务已取消')
      onCancel()
    } catch (error) {
      console.error('取消投稿失败:', error)
      message.error('取消投稿失败，请重试')
    }
  }

  // 获取状态图标
  const getStatusIcon = () => {
    switch (uploadProgress.status) {
      case 'pending':
        return <ClockCircleOutlined style={{ color: '#1890ff' }} />
      case 'processing':
        return <ExclamationCircleOutlined style={{ color: '#faad14' }} />
      case 'success':
        return <CheckCircleOutlined style={{ color: '#52c41a' }} />
      case 'failed':
        return <CloseCircleOutlined style={{ color: '#ff4d4f' }} />
      default:
        return <ClockCircleOutlined style={{ color: '#1890ff' }} />
    }
  }

  // 获取进度条状态
  const getProgressStatus = () => {
    if (uploadProgress.status === 'failed') return 'exception'
    if (uploadProgress.status === 'success') return 'success'
    return 'active'
  }

  return (
    <Modal
      className="upload-publish-modal"
      title={
        <Space>
          <UploadOutlined style={{ color: '#1890ff' }} />
          <span style={{ color: '#14181f' }}>投稿发布</span>
          {clipIds.length > 1 && (
            <Tag color="blue">{clipIds.length} 个视频</Tag>
          )}
        </Space>
      }
      open={visible}
      onCancel={handleCancel}
      footer={null}
      width={700}
      destroyOnClose
      maskClosable={!uploading}
      closable={!uploading}
      styles={{
        content: { background: '#ffffff' },
        header: { background: '#ffffff', borderBottom: '1px solid #d5dde6' },
        body: { background: '#ffffff', color: '#14181f' },
      }}
    >
      {!uploading ? (
        // 投稿表单
        <Form
          form={form}
          layout="vertical"
          initialValues={initialValues}
          onFinish={handleSubmit}
        >
          <Form.Item label="发布平台">
            <Select
              value={platform}
              onChange={(v: UploadPlatform) => {
                setPlatform(v)
                form.setFieldValue('account_id', undefined)
              }}
            >
              <Option value="bilibili">Bilibili 哔哩哔哩</Option>
              <Option value="youtube">YouTube</Option>
            </Select>
          </Form.Item>

          <Row gutter={16}>
            <Col span={12}>
              <Form.Item
                label={platform === 'bilibili' ? 'B站账号' : 'YouTube 账号'}
                name="account_id"
                rules={[{ required: true, message: '请选择账号' }]}
                extra={
                  accounts.length === 0
                    ? (
                      <span className="form-extra-reminder">
                        {platform === 'bilibili'
                          ? '暂无账号，请先到设置页用 Cookie 导入'
                          : '暂无账号，请先到设置页完成 Google 授权'}
                      </span>
                    )
                    : undefined
                }
              >
                <Select placeholder="选择账号" disabled={accounts.length === 0}>
                  {platform === 'bilibili'
                    ? bilibiliAccounts.map(account => (
                        <Option key={account.id} value={account.id}>
                          {account.nickname || account.username} ({account.username})
                        </Option>
                      ))
                    : youtubeAccounts.map(account => (
                        <Option key={account.id} value={account.id}>
                          {account.channel_title || account.channel_id}
                        </Option>
                      ))}
                </Select>
              </Form.Item>
            </Col>
            <Col span={12}>
              {platform === 'bilibili' ? (
                <Form.Item
                  label="分区"
                  name="partition_id"
                  rules={[{ required: true, message: '请选择视频分区' }]}
                >
                  <Select placeholder="选择视频分区" showSearch optionFilterProp="children">
                    {BILIBILI_PARTITIONS.map(partition => (
                      <Option key={partition.id} value={partition.id}>
                        {partition.name}
                      </Option>
                    ))}
                  </Select>
                </Form.Item>
              ) : (
                <Form.Item
                  label="分类"
                  name="category_id"
                  rules={[{ required: true, message: '请选择分类' }]}
                >
                  <Select placeholder="选择 YouTube 分类">
                    {YOUTUBE_CATEGORIES.map(cat => (
                      <Option key={cat.id} value={cat.id}>
                        {cat.name}
                      </Option>
                    ))}
                  </Select>
                </Form.Item>
              )}
            </Col>
          </Row>

          {platform === 'youtube' && (
            <Form.Item
              label="可见性"
              name="privacy_status"
              rules={[{ required: true, message: '请选择可见性' }]}
            >
              <Select>
                <Option value="private">私密 Private</Option>
                <Option value="unlisted">不公开列出 Unlisted</Option>
                <Option value="public">公开 Public</Option>
              </Select>
            </Form.Item>
          )}

          <Form.Item
            label="标题"
            name="title"
            rules={[{ required: true, message: '请输入视频标题' }]}
          >
            <Input placeholder="输入视频标题" maxLength={platform === 'youtube' ? 100 : 80} showCount />
          </Form.Item>

          <Form.Item
            label="描述"
            name="description"
            rules={[{ required: platform === 'bilibili', message: '请输入视频描述' }]}
          >
            <TextArea
              placeholder="输入视频描述"
              rows={4}
              maxLength={platform === 'youtube' ? 5000 : 250}
              showCount
            />
          </Form.Item>

          <Form.Item
            label="标签"
            name="tags"
            extra={<span style={{ color: 'var(--muted)' }}>最多添加10个标签，按回车确认</span>}
          >
            <Select
              mode="tags"
              placeholder="输入标签，按回车确认"
              maxTagCount={10}
              maxTagTextLength={20}
            />
          </Form.Item>

          <Divider />

          <div style={{ textAlign: 'right' }}>
            <Space>
              <Button onClick={handleCancel}>
                取消
              </Button>
              <Button
                type="primary"
                htmlType="submit"
                icon={<UploadOutlined />}
                disabled={accounts.length === 0}
              >
                开始投稿
              </Button>
            </Space>
          </div>
        </Form>
      ) : (
        // 上传进度
        <div style={{ textAlign: 'center', padding: '20px 0' }}>
          <div style={{ marginBottom: '24px' }}>
            {getStatusIcon()}
            <Text style={{ marginLeft: '8px', fontSize: '16px', color: '#14181f' }}>
              {uploadProgress.message}
            </Text>
          </div>

          <Progress
            percent={uploadProgress.progress}
            status={getProgressStatus()}
            strokeWidth={8}
            style={{ marginBottom: '24px' }}
          />

          {uploadProgress.status === 'success' && (uploadProgress.bvid || uploadProgress.videoUrl) && (
            <Alert
              message="投稿成功！"
              description={
                uploadProgress.videoUrl
                  ? <a href={uploadProgress.videoUrl} target="_blank" rel="noreferrer">{uploadProgress.videoUrl}</a>
                  : `BV号: ${uploadProgress.bvid}`
              }
              type="success"
              showIcon
              style={{ marginBottom: '16px' }}
            />
          )}

          {uploadProgress.status === 'failed' && uploadProgress.error && (
            <Alert
              message="投稿失败"
              description={uploadProgress.error}
              type="error"
              showIcon
              style={{ marginBottom: '16px' }}
            />
          )}

          {uploadProgress.status === 'processing' && (
            <div style={{ color: '#666', fontSize: '14px' }}>
              <Spin size="small" style={{ marginRight: '8px' }} />
              正在处理中，请稍候...
              {uploadRecordId && (
                <div style={{ marginTop: '8px', fontSize: '12px', color: '#999' }}>
                  任务ID: {uploadRecordId}
                </div>
              )}
            </div>
          )}

          <div style={{ marginTop: '16px' }}>
            {uploadProgress.status === 'failed' && (
              <Button
                type="primary"
                onClick={() => {
                  setUploading(false)
                  setUploadProgress({
                    status: 'pending',
                    message: '准备上传...',
                    progress: 0
                  })
                }}
                style={{ marginRight: '8px' }}
              >
                重新投稿
              </Button>
            )}
            
            <Button
              onClick={handleCancelUpload}
              disabled={uploadProgress.status === 'success'}
            >
              {uploadProgress.status === 'success' ? '关闭' : '取消投稿'}
            </Button>
          </div>
        </div>
      )}
    </Modal>
  )
}

export default UploadModal
