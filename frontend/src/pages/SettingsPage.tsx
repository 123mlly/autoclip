import React, { useState, useEffect } from 'react'
import { Layout, Card, Form, Input, Button, Typography, Space, Alert, Divider, Row, Col, Tabs, message, Select, Tag } from 'antd'
import { KeyOutlined, SaveOutlined, ApiOutlined, SettingOutlined, InfoCircleOutlined, UserOutlined, RobotOutlined } from '@ant-design/icons'
import { settingsApi } from '../services/api'
import BilibiliManager from '../components/BilibiliManager'
import YouTubeAccountManager from '../components/YouTubeAccountManager'
import './SettingsPage.css'

const { Content } = Layout
const { Title, Text, Paragraph } = Typography
const { TabPane } = Tabs

const SettingsPage: React.FC = () => {
  const [form] = Form.useForm()
  const [youtubeForm] = Form.useForm()
  const [loading, setLoading] = useState(false)
  const [youtubeLoading, setYoutubeLoading] = useState(false)
  const [youtubeConfigured, setYoutubeConfigured] = useState(false)
  const [showBilibiliManager, setShowBilibiliManager] = useState(false)
  const [showYouTubeManager, setShowYouTubeManager] = useState(false)
  const [availableModels, setAvailableModels] = useState<any>({})
  const [currentProvider, setCurrentProvider] = useState<any>({})
  const [selectedProvider, setSelectedProvider] = useState('dashscope')
  const [savedModelName, setSavedModelName] = useState('')

  const providerModelOptions = React.useMemo(() => {
    const list = availableModels[selectedProvider] || []
    if (
      savedModelName &&
      !list.some((model: { name: string }) => model.name === savedModelName)
    ) {
      return [
        {
          name: savedModelName,
          display_name: '自定义模型',
          max_tokens: 131072,
          description: '已保存的模型 ID',
        },
        ...list,
      ]
    }
    return list
  }, [availableModels, selectedProvider, savedModelName])

  // 提供商配置
  const providerConfig = {
    dashscope: {
      name: '阿里通义千问',
      icon: <RobotOutlined />,
      color: '#1890ff',
      description: '阿里云通义千问大模型服务',
      apiKeyField: 'dashscope_api_key',
      placeholder: '请输入通义千问API密钥'
    },
    openai: {
      name: 'OpenAI',
      icon: <RobotOutlined />,
      color: '#52c41a',
      description: 'OpenAI GPT系列模型',
      apiKeyField: 'openai_api_key',
      placeholder: '请输入OpenAI API密钥'
    },
    gemini: {
      name: 'Google Gemini',
      icon: <RobotOutlined />,
      color: '#faad14',
      description: 'Google Gemini大模型',
      apiKeyField: 'gemini_api_key',
      placeholder: '请输入Gemini API密钥'
    },
    siliconflow: {
      name: '硅基流动',
      icon: <RobotOutlined />,
      color: '#722ed1',
      description: '硅基流动模型服务',
      apiKeyField: 'siliconflow_api_key',
      placeholder: '请输入硅基流动API密钥'
    }
  }

  // 加载数据
  useEffect(() => {
    loadData()
    // YouTube OAuth 回调提示
    const params = new URLSearchParams(window.location.search)
    if (params.get('youtube') === '1') {
      if (params.get('success')) {
        message.success(`YouTube 账号授权成功${params.get('channel') ? ': ' + params.get('channel') : ''}`)
        setShowYouTubeManager(true)
      } else if (params.get('error')) {
        message.error(`YouTube 授权失败: ${params.get('error')}`)
      }
      window.history.replaceState({}, '', window.location.pathname)
    }
  }, [])

  const loadData = async () => {
    try {
      const [settings, models, provider] = await Promise.all([
        settingsApi.getSettings(),
        settingsApi.getAvailableModels(),
        settingsApi.getCurrentProvider()
      ])
      
      setAvailableModels(models)
      setCurrentProvider(provider)
      setSelectedProvider(settings.llm_provider || 'dashscope')
      setSavedModelName(settings.model_name || '')
      
      // 设置表单初始值（Select tags 模式用数组）
      form.setFieldsValue({
        ...settings,
        model_name: settings.model_name ? [settings.model_name] : [],
      })
      youtubeForm.setFieldsValue({
        youtube_client_id: settings.youtube_client_id || '',
        youtube_client_secret: settings.youtube_client_secret || '',
        youtube_redirect_uri:
          settings.youtube_redirect_uri ||
          'http://localhost:8000/api/v1/youtube-upload/oauth/callback',
        youtube_oauth_frontend_url: settings.youtube_oauth_frontend_url || '',
      })
      setYoutubeConfigured(Boolean(settings.youtube_client_id && settings.youtube_client_secret))
    } catch (error) {
      console.error('加载数据失败:', error)
    }
  }

  // 保存配置
  const handleSave = async (values: any) => {
    try {
      setLoading(true)
      const payload = { ...values }
      if (Array.isArray(payload.model_name)) {
        payload.model_name = payload.model_name[0]?.trim() || ''
      }
      await settingsApi.updateSettings(payload)
      message.success('配置保存成功！')
      await loadData() // 重新加载数据
    } catch (error: any) {
      message.error('保存失败: ' + (error.message || '未知错误'))
    } finally {
      setLoading(false)
    }
  }

  // 测试API密钥
  const handleTestApiKey = async () => {
    const apiKey = form.getFieldValue(providerConfig[selectedProvider as keyof typeof providerConfig].apiKeyField)
    const rawModel = form.getFieldValue('model_name')
    const modelName = Array.isArray(rawModel) ? rawModel[0] : rawModel
    
    if (!apiKey) {
      message.error('请先输入API密钥')
      return
    }

    if (!modelName) {
      message.error('请先选择模型')
      return
    }

    try {
      setLoading(true)
      const result = await settingsApi.testApiKey(selectedProvider, apiKey, modelName)
      if (result.success) {
        message.success('API密钥测试成功！')
      } else {
        message.error('API密钥测试失败: ' + (result.error || '未知错误'))
      }
    } catch (error: any) {
      message.error('测试失败: ' + (error.message || '未知错误'))
    } finally {
      setLoading(false)
    }
  }

  // 保存 YouTube OAuth 配置
  const handleYoutubeSave = async (values: any) => {
    try {
      setYoutubeLoading(true)
      await settingsApi.updateSettings(values)
      message.success('YouTube OAuth 配置已保存')
      await loadData()
    } catch (error: any) {
      message.error('保存失败: ' + (error.message || '未知错误'))
    } finally {
      setYoutubeLoading(false)
    }
  }

  // 提供商切换
  const handleProviderChange = (provider: string) => {
    setSelectedProvider(provider)
    form.setFieldsValue({ llm_provider: provider })
  }

  return (
    <Content className="settings-page">
      <div className="settings-container">
        <Title level={2} className="settings-title">
          <SettingOutlined /> 系统设置
        </Title>
        
        <Tabs defaultActiveKey="api" className="settings-tabs">
          <TabPane tab="AI 模型配置" key="api">
            <Card title="AI 模型配置" className="settings-card">
              <Alert
                message="多模型提供商支持"
                description="系统现在支持多个AI模型提供商，您可以根据需要选择不同的服务商和模型。"
                type="info"
                showIcon
                className="settings-alert"
              />
              
              <Form
                form={form}
                layout="vertical"
                className="settings-form"
                onFinish={handleSave}
                initialValues={{
                  llm_provider: 'dashscope',
                  model_name: 'qwen3.7-plus',
                  chunk_size: 5000,
                  min_score_threshold: 0.7,
                  max_clips_per_collection: 5
                }}
              >
                {/* 当前提供商状态 */}
                {currentProvider.available && (
                  <Alert
                    message={`当前使用: ${currentProvider.display_name} - ${currentProvider.model}`}
                    type="success"
                    showIcon
                    style={{ marginBottom: 24 }}
                  />
                )}

                {/* 提供商选择 */}
                <Form.Item
                  label="选择AI模型提供商"
                  name="llm_provider"
                  className="form-item"
                  rules={[{ required: true, message: '请选择AI模型提供商' }]}
                >
                  <Select
                    value={selectedProvider}
                    onChange={handleProviderChange}
                    className="settings-input"
                    placeholder="请选择AI模型提供商"
                  >
                    {Object.entries(providerConfig).map(([key, config]) => (
                      <Select.Option key={key} value={key}>
                        <Space>
                          <span style={{ color: config.color }}>{config.icon}</span>
                          <span>{config.name}</span>
                          <Tag color={config.color} size="small">{config.description}</Tag>
                        </Space>
                      </Select.Option>
                    ))}
                  </Select>
                </Form.Item>

                {/* 动态API密钥输入 */}
                <Form.Item
                  label={`${providerConfig[selectedProvider as keyof typeof providerConfig].name} API Key`}
                  name={providerConfig[selectedProvider as keyof typeof providerConfig].apiKeyField}
                  className="form-item"
                  rules={[
                    { required: true, message: '请输入API密钥' },
                    { min: 10, message: 'API密钥长度不能少于10位' }
                  ]}
                >
                  <Input.Password
                    placeholder={providerConfig[selectedProvider as keyof typeof providerConfig].placeholder}
                    prefix={<KeyOutlined />}
                    className="settings-input"
                  />
                </Form.Item>

                {/* 模型选择 */}
                <Form.Item
                  label="选择模型"
                  name="model_name"
                  className="form-item"
                  rules={[{ required: true, message: '请选择或输入模型' }]}
                  extra="可从列表选择；也可输入 DashScope 支持的任意模型 ID 后回车"
                >
                  <Select
                    className="settings-input"
                    placeholder="请选择或输入模型 ID"
                    showSearch
                    allowClear
                    mode="tags"
                    maxCount={1}
                    optionFilterProp="label"
                    tokenSeparators={[',']}
                  >
                    {providerModelOptions.map((model: any) => (
                      <Select.Option
                        key={model.name}
                        value={model.name}
                        label={`${model.display_name} ${model.name}`}
                      >
                        <Space>
                          <span>{model.display_name}</span>
                          <Tag>{model.name}</Tag>
                          <Tag size="small">最大{model.max_tokens} tokens</Tag>
                        </Space>
                      </Select.Option>
                    ))}
                  </Select>
                </Form.Item>

                <Form.Item className="form-item">
                  <Space>
                    <Button
                      type="default"
                      icon={<ApiOutlined />}
                      className="test-button"
                      onClick={handleTestApiKey}
                      loading={loading}
                    >
                      测试连接
                    </Button>
                  </Space>
                </Form.Item>

                <Divider className="settings-divider" />

                <Title level={4} className="section-title">模型配置</Title>
                
                <Row gutter={16}>
                  <Col span={12}>
                    <Form.Item
                      label="文本分块大小"
                      name="chunk_size"
                      className="form-item"
                    >
                      <Input 
                        type="number" 
                        placeholder="5000" 
                        addonAfter="字符" 
                        className="settings-input"
                      />
                    </Form.Item>
                  </Col>
                </Row>

                <Row gutter={16}>
                  <Col span={12}>
                    <Form.Item
                      label="最低评分阈值"
                      name="min_score_threshold"
                      className="form-item"
                    >
                      <Input 
                        type="number" 
                        step="0.1" 
                        min="0" 
                        max="1" 
                        placeholder="0.7" 
                        className="settings-input"
                      />
                    </Form.Item>
                  </Col>
                  <Col span={12}>
                    <Form.Item
                      label="每个合集最大切片数"
                      name="max_clips_per_collection"
                      className="form-item"
                    >
                      <Input 
                        type="number" 
                        placeholder="5" 
                        addonAfter="个" 
                        className="settings-input"
                      />
                    </Form.Item>
                  </Col>
                </Row>

                <Form.Item className="form-item">
                  <Button
                    type="primary"
                    htmlType="submit"
                    icon={<SaveOutlined />}
                    size="large"
                    className="save-button"
                    loading={loading}
                  >
                    保存配置
                  </Button>
                </Form.Item>
              </Form>
            </Card>

            <Card title="使用说明" className="settings-card">
              <Space direction="vertical" size="large" className="instructions-space">
                <div className="instruction-item">
                  <Title level={5} className="instruction-title">
                    <InfoCircleOutlined /> 1. 选择AI模型提供商
                  </Title>
                  <Paragraph className="instruction-text">
                    系统支持多个AI模型提供商：
                    <br />• <Text strong>阿里通义千问</Text>：访问阿里云控制台获取API密钥
                    <br />• <Text strong>OpenAI</Text>：访问 platform.openai.com 获取API密钥
                    <br />• <Text strong>Google Gemini</Text>：访问 ai.google.dev 获取API密钥
                    <br />• <Text strong>硅基流动</Text>：访问 docs.siliconflow.cn 获取API密钥
                  </Paragraph>
                </div>
                
                <div className="instruction-item">
                  <Title level={5} className="instruction-title">
                    <InfoCircleOutlined /> 2. 配置参数说明
                  </Title>
                  <Paragraph className="instruction-text">
                    • <Text strong>文本分块大小</Text>：影响处理速度和精度，建议5000字符<br />
                    • <Text strong>评分阈值</Text>：只有高于此分数的片段才会被保留<br />
                    • <Text strong>合集切片数</Text>：控制每个主题合集包含的片段数量
                  </Paragraph>
                </div>
                
                <div className="instruction-item">
                  <Title level={5} className="instruction-title">
                    <InfoCircleOutlined /> 3. 测试连接
                  </Title>
                  <Paragraph className="instruction-text">
                    保存前建议先测试API密钥是否有效，确保服务正常运行
                  </Paragraph>
                </div>
              </Space>
            </Card>
          </TabPane>

          <TabPane tab="B站管理" key="bilibili">
            <Card title="B站账号管理" className="settings-card">
              <div style={{ textAlign: 'center', padding: '40px 20px' }}>
                <div style={{ marginBottom: '24px' }}>
                  <UserOutlined style={{ fontSize: '48px', color: '#1890ff', marginBottom: '16px' }} />
                  <Title level={3} style={{ color: '#ffffff', margin: '0 0 8px 0' }}>
                    B站账号管理
                  </Title>
                  <Text type="secondary" style={{ color: '#b0b0b0', fontSize: '16px' }}>
                    管理您的B站账号，支持多账号切换和快速投稿
                  </Text>
                </div>
                
                <Space size="large">
                  <Button
                    type="primary"
                    size="large"
                    icon={<UserOutlined />}
                    onClick={() => setShowBilibiliManager(true)}
                    style={{
                      borderRadius: '8px',
                      background: '#0e7c66',
                      border: 'none',
                      fontWeight: 500,
                      height: '48px',
                      padding: '0 32px',
                      fontSize: '16px'
                    }}
                  >
                    管理B站账号
                  </Button>
                </Space>
                
                <div style={{ marginTop: '32px', textAlign: 'left', maxWidth: '600px', margin: '32px auto 0' }}>
                  <Title level={4} style={{ color: '#ffffff', marginBottom: '16px' }}>
                    功能特点
                  </Title>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(250px, 1fr))', gap: '16px' }}>
                    <div style={{ 
                      padding: '16px', 
                      background: 'rgba(255,255,255,0.05)', 
                      borderRadius: '8px',
                      border: '1px solid #404040'
                    }}>
                      <Text strong style={{ color: '#1890ff' }}>多账号支持</Text>
                      <br />
                      <Text type="secondary" style={{ color: '#b0b0b0' }}>
                        支持添加多个B站账号，方便管理和切换
                      </Text>
                    </div>
                    <div style={{ 
                      padding: '16px', 
                      background: 'rgba(255,255,255,0.05)', 
                      borderRadius: '8px',
                      border: '1px solid #404040'
                    }}>
                      <Text strong style={{ color: '#52c41a' }}>安全登录</Text>
                      <br />
                      <Text type="secondary" style={{ color: '#b0b0b0' }}>
                        使用Cookie导入，避免风控，安全可靠
                      </Text>
                    </div>
                    <div style={{ 
                      padding: '16px', 
                      background: 'rgba(255,255,255,0.05)', 
                      borderRadius: '8px',
                      border: '1px solid #404040'
                    }}>
                      <Text strong style={{ color: '#faad14' }}>快速投稿</Text>
                      <br />
                      <Text type="secondary" style={{ color: '#b0b0b0' }}>
                        在切片详情页直接选择账号投稿，操作简单
                      </Text>
                    </div>
                    <div style={{ 
                      padding: '16px', 
                      background: 'rgba(255,255,255,0.05)', 
                      borderRadius: '8px',
                      border: '1px solid #404040'
                    }}>
                      <Text strong style={{ color: '#722ed1' }}>批量管理</Text>
                      <br />
                      <Text type="secondary" style={{ color: '#b0b0b0' }}>
                        支持批量上传多个切片，提高效率
                      </Text>
                    </div>
                  </div>
                </div>
              </div>
            </Card>
          </TabPane>

          <TabPane tab="YouTube管理" key="youtube">
            <Card title="YouTube OAuth 配置" className="settings-card">
              <Alert
                type={youtubeConfigured ? 'success' : 'warning'}
                showIcon
                style={{ marginBottom: 24 }}
                message={youtubeConfigured ? 'YouTube OAuth 已配置' : '尚未配置 YouTube OAuth'}
                description={
                  youtubeConfigured
                    ? '可在下方修改 Client ID / Secret，保存后即可授权新账号。'
                    : '在 Google Cloud Console 创建 OAuth 客户端后，在此填写 Client ID 与 Client Secret。'
                }
              />

              <Form
                form={youtubeForm}
                layout="vertical"
                className="settings-form"
                onFinish={handleYoutubeSave}
              >
                <Form.Item
                  label="Client ID"
                  name="youtube_client_id"
                  rules={[{ required: true, message: '请输入 Client ID' }]}
                >
                  <Input placeholder="xxxx.apps.googleusercontent.com" className="settings-input" />
                </Form.Item>

                <Form.Item
                  label="Client Secret"
                  name="youtube_client_secret"
                  rules={[{ required: true, message: '请输入 Client Secret' }]}
                >
                  <Input.Password placeholder="Google OAuth Client Secret" className="settings-input" />
                </Form.Item>

                <Form.Item
                  label="OAuth 回调地址"
                  name="youtube_redirect_uri"
                  extra="需在 Google Cloud Console 的「已授权的重定向 URI」中添加此地址"
                >
                  <Input
                    placeholder="http://localhost:8000/api/v1/youtube-upload/oauth/callback"
                    className="settings-input"
                  />
                </Form.Item>

                <Form.Item
                  label="授权完成后跳转的前端地址（可选）"
                  name="youtube_oauth_frontend_url"
                  extra="Docker 仅暴露 8000 端口时可填 http://localhost:8000；留空则默认 http://localhost:3000"
                >
                  <Input placeholder="http://localhost:3000" className="settings-input" />
                </Form.Item>

                <Form.Item>
                  <Space>
                    <Button
                      type="primary"
                      htmlType="submit"
                      icon={<SaveOutlined />}
                      loading={youtubeLoading}
                      style={{ background: '#d64545', border: 'none' }}
                    >
                      保存 OAuth 配置
                    </Button>
                    <Button
                      icon={<UserOutlined />}
                      disabled={!youtubeConfigured}
                      onClick={() => setShowYouTubeManager(true)}
                    >
                      管理 YouTube 账号
                    </Button>
                  </Space>
                </Form.Item>
              </Form>

              <Divider />

              <Alert
                type="info"
                showIcon
                message="Google Cloud 配置步骤"
                description={
                  <div>
                    <Paragraph style={{ marginBottom: 8 }}>
                      1. 打开 Google Cloud Console，创建 OAuth 2.0 客户端（Web 应用）
                    </Paragraph>
                    <Paragraph style={{ marginBottom: 8 }}>
                      2. 将上方「OAuth 回调地址」添加到已授权的重定向 URI
                    </Paragraph>
                    <Paragraph style={{ marginBottom: 0 }}>
                      3. 保存 Client ID / Secret 后，点击「管理 YouTube 账号」进行 Google 授权
                    </Paragraph>
                  </div>
                }
              />
            </Card>
          </TabPane>
        </Tabs>

        {/* B站管理弹窗 */}
        <BilibiliManager
          visible={showBilibiliManager}
          onClose={() => setShowBilibiliManager(false)}
          onUploadSuccess={() => {
            message.success('操作成功')
          }}
        />
        <YouTubeAccountManager
          visible={showYouTubeManager}
          onClose={() => setShowYouTubeManager(false)}
        />
      </div>
    </Content>
  )
}

export default SettingsPage