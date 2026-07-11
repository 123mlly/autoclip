import React, { useState, useEffect } from 'react';
import { 
  Card, 
  Table, 
  Tag, 
  Button, 
  Space, 
  message, 
  Progress, 
  Tooltip, 
  Modal, 
  Descriptions,
  Typography,
  Row,
  Col,
  Statistic,
  Alert,
  Popconfirm
} from 'antd';
import { 
  ReloadOutlined, 
  EyeOutlined, 
  RedoOutlined, 
  StopOutlined,
  DeleteOutlined,
  CheckCircleOutlined,
  ExclamationCircleOutlined,
  ClockCircleOutlined,
  PlayCircleOutlined
} from '@ant-design/icons';
import { uploadApi, UploadRecord } from '../services/uploadApi';
import { BILIBILI_PARTITIONS } from '../services/uploadApi';

const { Title, Text } = Typography;

interface UploadStatusPageProps {}

const UploadStatusPage: React.FC<UploadStatusPageProps> = () => {
  const [records, setRecords] = useState<UploadRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedRecord, setSelectedRecord] = useState<UploadRecord | null>(null);
  const [detailModalVisible, setDetailModalVisible] = useState(false);

  // 获取投稿记录
  const fetchRecords = async () => {
    setLoading(true);
    try {
      const data = await uploadApi.getUploadRecords();
      setRecords(data);
    } catch (error) {
      message.error('获取投稿记录失败');
      console.error('获取投稿记录失败:', error);
    } finally {
      setLoading(false);
    }
  };

  // 重试投稿
  const handleRetry = async (recordId: string | number) => {
    try {
      await uploadApi.retryUpload(recordId);
      message.success('重试任务已提交');
      fetchRecords();
    } catch (error) {
      message.error('重试失败');
      console.error('重试失败:', error);
    }
  };

  // 取消投稿
  const handleCancel = async (recordId: string | number) => {
    try {
      await uploadApi.cancelUpload(recordId);
      message.success('任务已取消');
      fetchRecords();
    } catch (error) {
      message.error('取消失败');
      console.error('取消失败:', error);
    }
  };

  // 删除投稿
  const handleDelete = async (recordId: string | number) => {
    try {
      await uploadApi.deleteUpload(recordId);
      message.success('任务已删除');
      fetchRecords();
    } catch (error) {
      message.error('删除失败');
      console.error('删除失败:', error);
    }
  };

  // 查看详情
  const handleViewDetail = (record: UploadRecord) => {
    setSelectedRecord(record);
    setDetailModalVisible(true);
  };

  // 获取状态标签
  const getStatusTag = (status: string) => {
    const statusConfig = {
      pending: { color: 'default', icon: <ClockCircleOutlined />, text: '等待中' },
      processing: { color: 'processing', icon: <PlayCircleOutlined />, text: '处理中' },
      success: { color: 'success', icon: <CheckCircleOutlined />, text: '成功' },
      completed: { color: 'success', icon: <CheckCircleOutlined />, text: '完成' },
      failed: { color: 'error', icon: <ExclamationCircleOutlined />, text: '失败' },
      cancelled: { color: 'default', icon: <StopOutlined />, text: '已取消' }
    };
    
    const config = statusConfig[status as keyof typeof statusConfig] || statusConfig.pending;
    return (
      <Tag color={config.color} icon={config.icon}>
        {config.text}
      </Tag>
    );
  };

  // 获取分区名称
  const getPartitionName = (partitionId: number) => {
    const partition = BILIBILI_PARTITIONS.find(p => p.id === partitionId);
    return partition ? partition.name : `分区${partitionId}`;
  };

  // 格式化文件大小
  const formatFileSize = (bytes?: number) => {
    if (!bytes) return '-';
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(1024));
    return `${(bytes / Math.pow(1024, i)).toFixed(1)} ${sizes[i]}`;
  };

  // 格式化时长
  const formatDuration = (seconds?: number) => {
    if (!seconds) return '-';
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = seconds % 60;
    
    if (hours > 0) {
      return `${hours}小时${minutes}分钟`;
    } else if (minutes > 0) {
      return `${minutes}分钟${secs}秒`;
    } else {
      return `${secs}秒`;
    }
  };

  // 表格列定义
  const columns = [
    {
      title: '任务ID',
      dataIndex: 'id',
      key: 'id',
      width: 80,
      render: (id: string | number) => <Text code style={{ color: '#14181f' }}>{id}</Text>
    },
    {
      title: '标题',
      dataIndex: 'title',
      key: 'title',
      ellipsis: true,
      render: (title: string, record: UploadRecord) => (
        <Tooltip title={title}>
          <Text style={{ color: '#14181f' }}>{title}</Text>
        </Tooltip>
      )
    },
    {
      title: '投稿账号',
      dataIndex: 'account_nickname',
      key: 'account_nickname',
      width: 120,
      render: (nickname: string, record: UploadRecord) => (
        <div>
          <div style={{ color: '#14181f' }}>{nickname || record.account_username}</div>
          <Text type="secondary" style={{ fontSize: '12px', color: '#6b7585' }}>
            {record.account_username}
          </Text>
        </div>
      )
    },
    {
      title: '分区',
      dataIndex: 'partition_id',
      key: 'partition_id',
      width: 100,
      render: (partitionId: number) => (
        <Tag style={{ color: '#14181f' }}>{getPartitionName(partitionId)}</Tag>
      )
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (status: string) => getStatusTag(status)
    },
    {
      title: '进度',
      dataIndex: 'progress',
      key: 'progress',
      width: 120,
      render: (progress: number, record: UploadRecord) => {
        if (record.status === 'success' || record.status === 'completed') {
          return <Progress percent={100} size="small" status="success" />;
        } else if (record.status === 'failed') {
          return <Progress percent={progress} size="small" status="exception" />;
        } else if (record.status === 'processing') {
          return <Progress percent={progress} size="small" status="active" />;
        } else {
          return <Progress percent={progress} size="small" />;
        }
      }
    },
    {
      title: '文件大小',
      dataIndex: 'file_size',
      key: 'file_size',
      width: 100,
      render: (fileSize: number) => <span style={{ color: '#14181f' }}>{formatFileSize(fileSize)}</span>
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 150,
      render: (date: string) => <span style={{ color: '#14181f' }}>{new Date(date).toLocaleString()}</span>
    },
    {
      title: '操作',
      key: 'actions',
      width: 200,
      render: (_, record: UploadRecord) => (
        <Space size="small">
          <Button 
            type="link" 
            icon={<EyeOutlined style={{ color: '#0e7c66' }} />} 
            onClick={() => handleViewDetail(record)}
            size="small"
            style={{ color: '#0e7c66' }}
          >
            详情
          </Button>
          {record.status === 'failed' && (
            <Popconfirm
              title="确定要重试这个投稿任务吗？"
              onConfirm={() => handleRetry(record.id)}
              okText="确定"
              cancelText="取消"
            >
              <Button 
                type="link" 
                icon={<RedoOutlined style={{ color: '#0e7c66' }} />} 
                size="small"
                style={{ color: '#0e7c66' }}
              >
                重试
              </Button>
            </Popconfirm>
          )}
          {(record.status === 'pending' || record.status === 'processing') && (
            <Popconfirm
              title="确定要取消这个投稿任务吗？"
              onConfirm={() => handleCancel(record.id)}
              okText="确定"
              cancelText="取消"
            >
              <Button 
                type="link" 
                icon={<StopOutlined style={{ color: '#ff4d4f' }} />} 
                danger
                size="small"
                style={{ color: '#ff4d4f' }}
              >
                取消
              </Button>
            </Popconfirm>
          )}
          {(record.status === 'success' || record.status === 'completed' || record.status === 'failed' || record.status === 'cancelled') && (
            <Popconfirm
              title="确定要删除这个投稿任务吗？删除后无法恢复。"
              onConfirm={() => handleDelete(record.id)}
              okText="确定"
              cancelText="取消"
            >
              <Button 
                type="link" 
                icon={<DeleteOutlined style={{ color: '#ff4d4f' }} />} 
                danger
                size="small"
                style={{ color: '#ff4d4f' }}
              >
                删除
              </Button>
            </Popconfirm>
          )}
        </Space>
      )
    }
  ];

  // 统计信息
  const getStatistics = () => {
    const total = records.length;
    const success = records.filter(r => r.status === 'success' || r.status === 'completed').length;
    const failed = records.filter(r => r.status === 'failed').length;
    const processing = records.filter(r => r.status === 'processing').length;
    const pending = records.filter(r => r.status === 'pending').length;
    
    return { total, success, failed, processing, pending };
  };

  const stats = getStatistics();

  useEffect(() => {
    fetchRecords();
    // 每30秒自动刷新
    const interval = setInterval(fetchRecords, 30000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div style={{ padding: '24px', background: 'transparent', minHeight: '100vh' }}>
      <style>
        {`
          .upload-status-table .ant-table-thead > tr > th {
            background: #f7f9fb !important;
            color: #14181f !important;
            border-bottom: 1px solid #d5dde6 !important;
            font-weight: 600 !important;
          }
          .upload-status-table .ant-table-tbody > tr > td {
            background: #ffffff !important;
            color: #3d4654 !important;
            border-bottom: 1px solid #d5dde6 !important;
          }
          .upload-status-table .ant-table-tbody > tr:hover > td {
            background: #f7f9fb !important;
          }
          .upload-status-table .ant-pagination .ant-pagination-item {
            background: #ffffff !important;
            border-color: #d5dde6 !important;
          }
          .upload-status-table .ant-pagination .ant-pagination-item a {
            color: #3d4654 !important;
          }
          .upload-status-table .ant-pagination .ant-pagination-item-active {
            background: #0e7c66 !important;
            border-color: #0e7c66 !important;
          }
          .upload-status-table .ant-pagination .ant-pagination-item-active a {
            color: #ffffff !important;
          }
          .upload-status-table .ant-btn-link {
            color: #0e7c66 !important;
          }
          .upload-status-table .ant-btn-link:hover {
            color: #0a6352 !important;
          }
          .upload-status-table .ant-btn-link.ant-btn-dangerous {
            color: #ff4d4f !important;
          }
          .upload-status-table .ant-btn-link.ant-btn-dangerous:hover {
            color: #ff7875 !important;
          }
          .upload-status-table .ant-tag-blue {
            color: #0e7c66 !important;
          }
          .upload-status-table .ant-pagination-prev:hover,
          .upload-status-table .ant-pagination-next:hover {
            color: #0e7c66 !important;
          }
          .upload-status-modal .ant-modal-content {
            background: #ffffff !important;
            border: 1px solid #d5dde6 !important;
          }
          .upload-status-modal .ant-modal-header {
            background: #ffffff !important;
            border-bottom: 1px solid #d5dde6 !important;
          }
          .upload-status-modal .ant-modal-title {
            color: #14181f !important;
          }
          .upload-status-modal .ant-modal-body {
            background: #ffffff !important;
            color: #14181f !important;
          }
          .upload-status-modal .ant-modal-close {
            color: #6b7585 !important;
          }
          .upload-status-modal .ant-modal-close:hover {
            color: #0e7c66 !important;
          }
        `}
      </style>
      <Card style={{ background: '#ffffff', border: '1px solid #d5dde6' }}>
        <div style={{ marginBottom: '24px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <Title level={3} style={{ margin: 0, color: '#14181f' }}>投稿任务状态</Title>
          <Button 
            type="primary" 
            icon={<ReloadOutlined />} 
            onClick={fetchRecords}
            loading={loading}
          >
            刷新
          </Button>
        </div>

        {/* 统计信息 */}
        <Row gutter={16} style={{ marginBottom: '24px' }}>
          <Col span={6}>
            <Card style={{ background: '#f7f9fb', border: '1px solid #d5dde6' }}>
              <Statistic 
                title={<span style={{ color: '#6b7585' }}>总任务数</span>} 
                value={stats.total} 
                valueStyle={{ color: '#14181f' }} 
              />
            </Card>
          </Col>
          <Col span={6}>
            <Card style={{ background: '#f7f9fb', border: '1px solid #d5dde6' }}>
              <Statistic 
                title={<span style={{ color: '#6b7585' }}>成功</span>} 
                value={stats.success} 
                valueStyle={{ color: '#52c41a' }}
                prefix={<CheckCircleOutlined />}
              />
            </Card>
          </Col>
          <Col span={6}>
            <Card style={{ background: '#f7f9fb', border: '1px solid #d5dde6' }}>
              <Statistic 
                title={<span style={{ color: '#6b7585' }}>失败</span>} 
                value={stats.failed} 
                valueStyle={{ color: '#ff4d4f' }}
                prefix={<ExclamationCircleOutlined />}
              />
            </Card>
          </Col>
          <Col span={6}>
            <Card style={{ background: '#f7f9fb', border: '1px solid #d5dde6' }}>
              <Statistic 
                title={<span style={{ color: '#6b7585' }}>进行中</span>} 
                value={stats.processing + stats.pending} 
                valueStyle={{ color: '#0e7c66' }}
                prefix={<PlayCircleOutlined />}
              />
            </Card>
          </Col>
        </Row>

        {/* 任务列表 */}
        <Table
          columns={columns}
          dataSource={records}
          rowKey="id"
          loading={loading}
          pagination={{
            pageSize: 20,
            showSizeChanger: true,
            showQuickJumper: true,
            showTotal: (total, range) => `第 ${range[0]}-${range[1]} 条，共 ${total} 条`
          }}
          scroll={{ x: 1200 }}
          style={{ background: '#ffffff' }}
          className="upload-status-table"
        />
      </Card>

      {/* 详情模态框 */}
      <Modal
        title="投稿任务详情"
        open={detailModalVisible}
        onCancel={() => setDetailModalVisible(false)}
        footer={null}
        width={800}
        styles={{
          body: { background: '#ffffff', color: '#14181f' },
          header: { background: '#ffffff', color: '#14181f', borderBottom: '1px solid #d5dde6' }
        }}
        className="upload-status-modal"
      >
        {selectedRecord && (
          <div>
            <Descriptions 
              column={2} 
              bordered
              labelStyle={{ 
                background: '#f7f9fb', 
                color: '#14181f',
                fontWeight: 'bold',
                borderRight: '1px solid #d5dde6'
              }}
              contentStyle={{ 
                background: '#ffffff', 
                color: '#3d4654',
                borderLeft: '1px solid #d5dde6'
              }}
              style={{ 
                background: '#ffffff',
                border: '1px solid #d5dde6'
              }}
            >
              <Descriptions.Item label="任务ID" span={1}>
                <Text code style={{ color: '#14181f' }}>{selectedRecord.id}</Text>
              </Descriptions.Item>
              <Descriptions.Item label="状态" span={1}>
                {getStatusTag(selectedRecord.status)}
              </Descriptions.Item>
              <Descriptions.Item label="标题" span={2}>
                <Text style={{ color: '#14181f' }}>{selectedRecord.title}</Text>
              </Descriptions.Item>
              <Descriptions.Item label="投稿账号" span={1}>
                <Text style={{ color: '#14181f' }}>{selectedRecord.account_nickname || selectedRecord.account_username}</Text>
              </Descriptions.Item>
              <Descriptions.Item label="分区" span={1}>
                <Tag>{getPartitionName(selectedRecord.partition_id)}</Tag>
              </Descriptions.Item>
              <Descriptions.Item label="项目名称" span={1}>
                <Text style={{ color: '#14181f' }}>{selectedRecord.project_name || '-'}</Text>
              </Descriptions.Item>
              <Descriptions.Item label="切片ID" span={1}>
                <Text code style={{ color: '#14181f' }}>{selectedRecord.clip_id}</Text>
              </Descriptions.Item>
              <Descriptions.Item label="进度" span={2}>
                <Progress 
                  percent={selectedRecord.progress} 
                  status={
                    selectedRecord.status === 'failed' ? 'exception' :
                    selectedRecord.status === 'success' || selectedRecord.status === 'completed' ? 'success' :
                    selectedRecord.status === 'processing' ? 'active' : 'normal'
                  }
                />
              </Descriptions.Item>
              <Descriptions.Item label="文件大小" span={1}>
                <Text style={{ color: '#14181f' }}>{formatFileSize(selectedRecord.file_size)}</Text>
              </Descriptions.Item>
              <Descriptions.Item label="上传时长" span={1}>
                <Text style={{ color: '#14181f' }}>{formatDuration(selectedRecord.upload_duration)}</Text>
              </Descriptions.Item>
              <Descriptions.Item label="BV号" span={1}>
                {selectedRecord.bv_id ? <Text code style={{ color: '#14181f' }}>{selectedRecord.bv_id}</Text> : <Text style={{ color: '#14181f' }}>-</Text>}
              </Descriptions.Item>
              <Descriptions.Item label="AV号" span={1}>
                {selectedRecord.av_id ? <Text code style={{ color: '#14181f' }}>{selectedRecord.av_id}</Text> : <Text style={{ color: '#14181f' }}>-</Text>}
              </Descriptions.Item>
              <Descriptions.Item label="创建时间" span={1}>
                <Text style={{ color: '#14181f' }}>{new Date(selectedRecord.created_at).toLocaleString()}</Text>
              </Descriptions.Item>
              <Descriptions.Item label="更新时间" span={1}>
                <Text style={{ color: '#14181f' }}>{new Date(selectedRecord.updated_at).toLocaleString()}</Text>
              </Descriptions.Item>
            </Descriptions>

            {selectedRecord.description && (
              <div style={{ marginTop: '16px' }}>
                <Title level={5} style={{ color: '#14181f' }}>描述</Title>
                <Text style={{ color: '#14181f' }}>{selectedRecord.description}</Text>
              </div>
            )}

            {selectedRecord.tags && (
              <div style={{ marginTop: '16px' }}>
                <Title level={5} style={{ color: '#14181f' }}>标签</Title>
                <Text style={{ color: '#14181f' }}>{selectedRecord.tags}</Text>
              </div>
            )}

            {selectedRecord.error_message && (
              <div style={{ marginTop: '16px' }}>
                <Title level={5} style={{ color: '#14181f' }}>错误信息</Title>
                <Alert
                  message="投稿失败"
                  description={selectedRecord.error_message}
                  type="error"
                  showIcon
                />
              </div>
            )}

            <div style={{ marginTop: '24px', textAlign: 'right' }}>
              <Space>
                {selectedRecord.status === 'failed' && (
                  <Popconfirm
                    title="确定要重试这个投稿任务吗？"
                    onConfirm={() => {
                      handleRetry(selectedRecord.id);
                      setDetailModalVisible(false);
                    }}
                    okText="确定"
                    cancelText="取消"
                  >
                    <Button type="primary" icon={<RedoOutlined />}>
                      重试
                    </Button>
                  </Popconfirm>
                )}
                <Button onClick={() => setDetailModalVisible(false)}>
                  关闭
                </Button>
              </Space>
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
};

export default UploadStatusPage;
