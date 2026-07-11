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
} from 'antd'
import { PlusOutlined, DeleteOutlined, LinkOutlined, ReloadOutlined } from '@ant-design/icons'
import { youtubeUploadApi, YouTubeAccount } from '../services/youtubeUploadApi'

const { Text, Paragraph } = Typography
const { TextArea } = Input

interface YouTubeAccountManagerProps {
  visible: boolean
  onClose: () => void
}

const YouTubeAccountManager: React.FC<YouTubeAccountManagerProps> = ({ visible, onClose }) => {
  const [accounts, setAccounts] = useState<YouTubeAccount[]>([])
  const [loading, setLoading] = useState(false)
  const [configured, setConfigured] = useState(false)
  const [showImport, setShowImport] = useState(false)
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

  useEffect(() => {
    if (visible) fetchAccounts()
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

  const handleDelete = async (id: number) => {
    try {
      await youtubeUploadApi.deleteAccount(id)
      message.success('已删除')
      fetchAccounts()
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '删除失败')
    }
  }

  const columns = [
    {
      title: '频道',
      dataIndex: 'channel_title',
      key: 'channel_title',
      render: (text: string, row: YouTubeAccount) => (
        <Space direction="vertical" size={0}>
          <Text style={{ color: '#fff' }}>{text || '未命名频道'}</Text>
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
        <Popconfirm title="确定删除该账号？" onConfirm={() => handleDelete(row.id)}>
          <Button type="text" danger icon={<DeleteOutlined />} />
        </Popconfirm>
      ),
    },
  ]

  return (
    <Modal
      title="YouTube 账号管理"
      open={visible}
      onCancel={onClose}
      footer={null}
      width={720}
      destroyOnClose
    >
      {!configured && (
        <Alert
          type="warning"
          showIcon
          style={{ marginBottom: 16 }}
          message="尚未配置 Google OAuth"
          description={
            <div>
              请在 <Text code>.env</Text> 中设置 <Text code>YOUTUBE_CLIENT_ID</Text> 与{' '}
              <Text code>YOUTUBE_CLIENT_SECRET</Text>，并在 Google Cloud Console 将回调地址设为：
              <Paragraph copyable style={{ marginTop: 8, marginBottom: 0 }}>
                http://localhost:8000/api/v1/youtube-upload/oauth/callback
              </Paragraph>
            </div>
          }
        />
      )}

      <Space style={{ marginBottom: 16 }}>
        <Button type="primary" icon={<LinkOutlined />} onClick={handleStartOAuth} disabled={!configured}>
          Google 授权登录
        </Button>
        <Button icon={<PlusOutlined />} onClick={() => setShowImport(true)}>
          导入 Refresh Token
        </Button>
        <Button icon={<ReloadOutlined />} onClick={fetchAccounts}>
          刷新
        </Button>
      </Space>

      <Table
        rowKey="id"
        loading={loading}
        dataSource={accounts}
        columns={columns}
        pagination={false}
        locale={{ emptyText: '暂无 YouTube 账号，请先授权' }}
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
          <Form.Item name="client_id" label="Client ID（可选，默认用 .env）">
            <Input />
          </Form.Item>
          <Form.Item name="client_secret" label="Client Secret（可选，默认用 .env）">
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
  )
}

export default YouTubeAccountManager
