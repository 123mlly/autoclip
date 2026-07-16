import React, { useEffect, useState } from 'react'
import {
  Modal,
  Button,
  Space,
  Table,
  message,
  Form,
  Input,
  Alert,
  Typography,
  Popconfirm,
  Tag,
  Tabs,
  Progress,
  Tooltip,
  Descriptions,
  Row,
  Col,
  Statistic,
  Card,
} from 'antd'
import {
  PlusOutlined,
  DeleteOutlined,
  LinkOutlined,
  ReloadOutlined,
  EyeOutlined,
  RedoOutlined,
  StopOutlined,
  CheckCircleOutlined,
  ExclamationCircleOutlined,
  ClockCircleOutlined,
  PlayCircleOutlined,
  UserOutlined,
  UploadOutlined,
} from '@ant-design/icons'
import {
  youtubeUploadApi,
  YouTubeAccount,
  YouTubeUploadRecord,
  YOUTUBE_CATEGORIES,
} from '../services/youtubeUploadApi'

const { Text, Paragraph } = Typography
const { TextArea } = Input

interface YouTubeAccountManagerProps {
  visible: boolean
  onClose: () => void
}

const getStatusTag = (status: string) => {
  const statusConfig: Record<string, { color: string; icon: React.ReactNode; text: string }> = {
    pending: { color: 'default', icon: <ClockCircleOutlined />, text: '等待中' },
    processing: { color: 'processing', icon: <PlayCircleOutlined />, text: '上传中' },
    success: { color: 'success', icon: <CheckCircleOutlined />, text: '成功' },
    completed: { color: 'success', icon: <CheckCircleOutlined />, text: '已完成' },
    failed: { color: 'error', icon: <ExclamationCircleOutlined />, text: '失败' },
    cancelled: { color: 'default', icon: <StopOutlined />, text: '已取消' },
  }
  const config = statusConfig[status] || statusConfig.pending
  return (
    <Tag color={config.color} icon={config.icon}>
      {config.text}
    </Tag>
  )
}

const formatFileSize = (bytes?: number) => {
  if (!bytes) return '-'
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(1024))
  return `${(bytes / Math.pow(1024, i)).toFixed(1)} ${sizes[i]}`
}

const privacyLabel = (value?: string) => {
  const map: Record<string, string> = {
    private: '私密',
    unlisted: '不公开列出',
    public: '公开',
  }
  return map[value || ''] || value || '-'
}

const categoryLabel = (id?: string) => {
  const cat = YOUTUBE_CATEGORIES.find((c) => c.id === id)
  return cat ? cat.name : id || '-'
}

const YouTubeAccountManager: React.FC<YouTubeAccountManagerProps> = ({ visible, onClose }) => {
  const [activeTab, setActiveTab] = useState('accounts')
  const [accounts, setAccounts] = useState<YouTubeAccount[]>([])
  const [uploadRecords, setUploadRecords] = useState<YouTubeUploadRecord[]>([])
  const [loading, setLoading] = useState(false)
  const [recordsLoading, setRecordsLoading] = useState(false)
  const [configured, setConfigured] = useState(false)
  const [showImport, setShowImport] = useState(false)
  const [selectedRecord, setSelectedRecord] = useState<YouTubeUploadRecord | null>(null)
  const [detailModalVisible, setDetailModalVisible] = useState(false)
  const [form] = Form.useForm()

  const fetchAccounts = async () => {
    setLoading(true)
    try {
      const [list, config] = await Promise.all([
        youtubeUploadApi.getAccounts(),
        youtubeUploadApi.getConfig(),
      ])
      setAccounts(list)
      setConfigured(config.configured)
    } catch (e: any) {
      message.error(e?.response?.data?.detail || e?.message || '获取 YouTube 账号失败')
    } finally {
      setLoading(false)
    }
  }

  const fetchUploadRecords = async () => {
    setRecordsLoading(true)
    try {
      const data = await youtubeUploadApi.getUploadRecords()
      setUploadRecords(data)
    } catch (e: any) {
      message.error(e?.response?.data?.detail || e?.message || '获取投稿记录失败')
    } finally {
      setRecordsLoading(false)
    }
  }

  const refreshAll = async () => {
    await Promise.all([fetchAccounts(), fetchUploadRecords()])
  }

  useEffect(() => {
    if (visible) {
      refreshAll()
    }
  }, [visible])

  const handleStartOAuth = async () => {
    try {
      const { auth_url } = await youtubeUploadApi.startOAuth()
      window.open(auth_url, '_blank', 'noopener,noreferrer')
      message.info('已打开 Google 授权页，完成后会自动回到设置页')
    } catch (e: any) {
      message.error(e?.response?.data?.detail || e?.message || '无法启动授权')
    }
  }

  const handleImportToken = async (values: any) => {
    try {
      setLoading(true)
      await youtubeUploadApi.importRefreshToken({
        refresh_token: values.refresh_token,
        client_id: values.client_id,
        client_secret: values.client_secret,
        nickname: values.nickname,
      })
      message.success('YouTube 账号导入成功')
      setShowImport(false)
      form.resetFields()
      fetchAccounts()
    } catch (e: any) {
      message.error(e?.response?.data?.detail || e?.message || '导入失败')
    } finally {
      setLoading(false)
    }
  }

  const handleDeleteAccount = async (id: number) => {
    try {
      await youtubeUploadApi.deleteAccount(id)
      message.success('已删除')
      fetchAccounts()
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '删除失败')
    }
  }

  const handleRetry = async (recordId: number) => {
    try {
      await youtubeUploadApi.retryUploadRecord(recordId)
      message.success('重试任务已提交')
      fetchUploadRecords()
    } catch (e: any) {
      message.error(e?.response?.data?.detail || e?.message || '重试失败')
    }
  }

  const handleCancel = async (recordId: number) => {
    try {
      await youtubeUploadApi.cancelUploadRecord(recordId)
      message.success('任务已取消')
      fetchUploadRecords()
    } catch (e: any) {
      message.error(e?.response?.data?.detail || e?.message || '取消失败')
    }
  }

  const handleDeleteRecord = async (recordId: number) => {
    try {
      await youtubeUploadApi.deleteUploadRecord(recordId)
      message.success('任务已删除')
      fetchUploadRecords()
    } catch (e: any) {
      message.error(e?.response?.data?.detail || e?.message || '删除失败')
    }
  }

  const getStatistics = () => {
    const total = uploadRecords.length
    const success = uploadRecords.filter(
      (r) => r.status === 'success' || r.status === 'completed'
    ).length
    const failed = uploadRecords.filter((r) => r.status === 'failed').length
    const processing = uploadRecords.filter((r) => r.status === 'processing').length
    const pending = uploadRecords.filter((r) => r.status === 'pending').length
    return { total, success, failed, processing, pending }
  }

  const accountColumns = [
    {
      title: '频道',
      dataIndex: 'channel_title',
      key: 'channel_title',
      render: (text: string, row: YouTubeAccount) => (
        <Space direction="vertical" size={0}>
          <Text>{text || '未命名频道'}</Text>
          <Text type="secondary" style={{ fontSize: 12 }}>{row.channel_id}</Text>
        </Space>
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (status: string) => (
        <Tag color={status === 'active' ? 'green' : 'default'}>{status}</Tag>
      ),
    },
    {
      title: '投稿数',
      dataIndex: 'upload_count',
      key: 'upload_count',
      width: 80,
    },
    {
      title: '操作',
      key: 'actions',
      width: 80,
      render: (_: any, row: YouTubeAccount) => (
        <Popconfirm title="确定删除该账号？" onConfirm={() => handleDeleteAccount(row.id)}>
          <Button type="text" danger icon={<DeleteOutlined />} />
        </Popconfirm>
      ),
    },
  ]

  const uploadStatusColumns = [
    {
      title: 'ID',
      dataIndex: 'id',
      key: 'id',
      width: 70,
      render: (id: number) => <Text code>{id}</Text>,
    },
    {
      title: '标题',
      dataIndex: 'title',
      key: 'title',
      ellipsis: true,
      render: (title: string) => (
        <Tooltip title={title}>
          <Text>{title}</Text>
        </Tooltip>
      ),
    },
    {
      title: '频道',
      dataIndex: 'account_title',
      key: 'account_title',
      width: 120,
      ellipsis: true,
      render: (title: string) => title || '-',
    },
    {
      title: '可见性',
      dataIndex: 'privacy_status',
      key: 'privacy_status',
      width: 100,
      render: (v: string) => <Tag>{privacyLabel(v)}</Tag>,
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (status: string) => getStatusTag(status),
    },
    {
      title: '进度',
      dataIndex: 'progress',
      key: 'progress',
      width: 110,
      render: (progress: number, record: YouTubeUploadRecord) => {
        if (record.status === 'success' || record.status === 'completed') {
          return <Progress percent={100} size="small" status="success" />
        }
        if (record.status === 'failed') {
          return <Progress percent={progress || 0} size="small" status="exception" />
        }
        if (record.status === 'processing') {
          return <Progress percent={Math.max(progress || 0, 10)} size="small" status="active" />
        }
        return <Progress percent={progress || 0} size="small" />
      },
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 160,
      render: (date: string) => (date ? new Date(date).toLocaleString() : '-'),
    },
    {
      title: '操作',
      key: 'actions',
      width: 200,
      render: (_: any, record: YouTubeUploadRecord) => (
        <Space size="small" wrap>
          <Button
            type="link"
            size="small"
            icon={<EyeOutlined />}
            onClick={() => {
              setSelectedRecord(record)
              setDetailModalVisible(true)
            }}
          >
            详情
          </Button>
          {record.status === 'failed' && (
            <Popconfirm title="确定重试该投稿？" onConfirm={() => handleRetry(record.id)}>
              <Button type="link" size="small" icon={<RedoOutlined />}>
                重试
              </Button>
            </Popconfirm>
          )}
          {(record.status === 'pending' || record.status === 'processing') && (
            <Popconfirm title="确定取消该投稿？" onConfirm={() => handleCancel(record.id)}>
              <Button type="link" size="small" icon={<StopOutlined />}>
                取消
              </Button>
            </Popconfirm>
          )}
          {record.status !== 'pending' && record.status !== 'processing' && (
            <Popconfirm title="确定删除该记录？" onConfirm={() => handleDeleteRecord(record.id)}>
              <Button type="link" size="small" danger icon={<DeleteOutlined />}>
                删除
              </Button>
            </Popconfirm>
          )}
        </Space>
      ),
    },
  ]

  const stats = getStatistics()

  return (
    <>
      <Modal
        title="YouTube 管理"
        open={visible}
        onCancel={onClose}
        footer={null}
        width={960}
        destroyOnClose
      >
        {!configured && activeTab === 'accounts' && (
          <Alert
            type="warning"
            showIcon
            style={{ marginBottom: 16 }}
            message="尚未配置 Google OAuth"
            description={
              <div>
                请先在 <Text strong>设置 → YouTube管理</Text> 中填写{' '}
                <Text code>Client ID</Text> 与 <Text code>Client Secret</Text>，并在 Google Cloud
                Console 将回调地址设为：
                <Paragraph copyable style={{ marginTop: 8, marginBottom: 0 }}>
                  http://localhost:8000/api/v1/youtube-upload/oauth/callback
                </Paragraph>
              </div>
            }
          />
        )}

        <Tabs
          activeKey={activeTab}
          onChange={setActiveTab}
          items={[
            {
              key: 'accounts',
              label: (
                <span>
                  <UserOutlined /> 账号管理
                </span>
              ),
              children: (
                <>
                  <Space style={{ marginBottom: 16 }}>
                    <Button
                      type="primary"
                      icon={<LinkOutlined />}
                      onClick={handleStartOAuth}
                      disabled={!configured}
                    >
                      Google 授权登录
                    </Button>
                    <Button icon={<PlusOutlined />} onClick={() => setShowImport(true)}>
                      导入 Refresh Token
                    </Button>
                    <Button icon={<ReloadOutlined />} onClick={fetchAccounts} loading={loading}>
                      刷新
                    </Button>
                  </Space>
                  <Table
                    rowKey="id"
                    loading={loading}
                    dataSource={accounts}
                    columns={accountColumns}
                    pagination={false}
                    locale={{ emptyText: '暂无 YouTube 账号，请先授权' }}
                  />
                </>
              ),
            },
            {
              key: 'status',
              label: (
                <span>
                  <UploadOutlined /> 投稿状态
                </span>
              ),
              children: (
                <>
                  <div
                    style={{
                      marginBottom: 16,
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center',
                    }}
                  >
                    <Text strong>投稿任务列表</Text>
                    <Button
                      icon={<ReloadOutlined />}
                      onClick={fetchUploadRecords}
                      loading={recordsLoading}
                    >
                      刷新
                    </Button>
                  </div>
                  <Row gutter={16} style={{ marginBottom: 16 }}>
                    <Col span={6}>
                      <Card size="small">
                        <Statistic title="总任务" value={stats.total} />
                      </Card>
                    </Col>
                    <Col span={6}>
                      <Card size="small">
                        <Statistic title="成功" value={stats.success} valueStyle={{ color: '#52c41a' }} />
                      </Card>
                    </Col>
                    <Col span={6}>
                      <Card size="small">
                        <Statistic title="进行中" value={stats.processing + stats.pending} valueStyle={{ color: '#1890ff' }} />
                      </Card>
                    </Col>
                    <Col span={6}>
                      <Card size="small">
                        <Statistic title="失败" value={stats.failed} valueStyle={{ color: '#ff4d4f' }} />
                      </Card>
                    </Col>
                  </Row>
                  <Table
                    rowKey="id"
                    loading={recordsLoading}
                    dataSource={uploadRecords}
                    columns={uploadStatusColumns}
                    pagination={{ pageSize: 10, showSizeChanger: false }}
                    locale={{ emptyText: '暂无投稿记录' }}
                    scroll={{ x: 900 }}
                  />
                </>
              ),
            },
          ]}
        />

        <Modal
          title="导入 Refresh Token"
          open={showImport}
          onCancel={() => setShowImport(false)}
          footer={null}
          destroyOnClose
        >
          <Form form={form} layout="vertical" onFinish={handleImportToken}>
            <Form.Item name="nickname" label="显示名称（可选）">
              <Input placeholder="我的 YouTube 频道" />
            </Form.Item>
            <Form.Item
              name="refresh_token"
              label="Refresh Token"
              rules={[{ required: true, message: '请输入 refresh_token' }]}
            >
              <TextArea rows={3} placeholder="1//..." />
            </Form.Item>
            <Form.Item name="client_id" label="Client ID（可选，默认用设置页配置）">
              <Input />
            </Form.Item>
            <Form.Item name="client_secret" label="Client Secret（可选，默认用设置页配置）">
              <Input.Password />
            </Form.Item>
            <Form.Item>
              <Button type="primary" htmlType="submit" loading={loading} block>
                导入
              </Button>
            </Form.Item>
          </Form>
        </Modal>
      </Modal>

      <Modal
        title="YouTube 投稿详情"
        open={detailModalVisible}
        onCancel={() => setDetailModalVisible(false)}
        footer={null}
        width={720}
      >
        {selectedRecord && (
          <>
            <Descriptions column={2} bordered size="small">
              <Descriptions.Item label="任务 ID">{selectedRecord.id}</Descriptions.Item>
              <Descriptions.Item label="状态">{getStatusTag(selectedRecord.status)}</Descriptions.Item>
              <Descriptions.Item label="标题" span={2}>
                {selectedRecord.title}
              </Descriptions.Item>
              <Descriptions.Item label="频道">
                {selectedRecord.account_title || selectedRecord.channel_id || '-'}
              </Descriptions.Item>
              <Descriptions.Item label="可见性">
                {privacyLabel(selectedRecord.privacy_status)}
              </Descriptions.Item>
              <Descriptions.Item label="分类">
                {categoryLabel(selectedRecord.category_id)}
              </Descriptions.Item>
              <Descriptions.Item label="文件大小">
                {formatFileSize(selectedRecord.file_size)}
              </Descriptions.Item>
              <Descriptions.Item label="项目 ID" span={2}>
                <Text code copyable>{selectedRecord.project_id || '-'}</Text>
              </Descriptions.Item>
              <Descriptions.Item label="切片 ID" span={2}>
                <Text code>{selectedRecord.clip_id || '-'}</Text>
              </Descriptions.Item>
              {selectedRecord.video_url && (
                <Descriptions.Item label="视频链接" span={2}>
                  <a href={selectedRecord.video_url} target="_blank" rel="noreferrer">
                    {selectedRecord.video_url}
                  </a>
                </Descriptions.Item>
              )}
              {selectedRecord.video_id && !selectedRecord.video_url && (
                <Descriptions.Item label="Video ID" span={2}>
                  <Text code>{selectedRecord.video_id}</Text>
                </Descriptions.Item>
              )}
              <Descriptions.Item label="创建时间">
                {selectedRecord.created_at
                  ? new Date(selectedRecord.created_at).toLocaleString()
                  : '-'}
              </Descriptions.Item>
              <Descriptions.Item label="更新时间">
                {selectedRecord.updated_at
                  ? new Date(selectedRecord.updated_at).toLocaleString()
                  : '-'}
              </Descriptions.Item>
              {selectedRecord.description && (
                <Descriptions.Item label="简介" span={2}>
                  {selectedRecord.description}
                </Descriptions.Item>
              )}
            </Descriptions>
            {selectedRecord.error_message && (
              <Alert
                type="error"
                showIcon
                style={{ marginTop: 16 }}
                message="错误信息"
                description={selectedRecord.error_message}
              />
            )}
            {selectedRecord.status === 'failed' && (
              <div style={{ marginTop: 16, textAlign: 'right' }}>
                <Button type="primary" icon={<RedoOutlined />} onClick={() => handleRetry(selectedRecord.id)}>
                  重试投稿
                </Button>
              </div>
            )}
          </>
        )}
      </Modal>
    </>
  )
}

export default YouTubeAccountManager
