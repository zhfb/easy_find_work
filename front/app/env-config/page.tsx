'use client'

import { useState, useEffect } from 'react'
import { BiSave, BiKey, BiLinkExternal, BiCodeAlt, BiInfoCircle } from 'react-icons/bi'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import PageHeader from '@/app/components/PageHeader'

export default function EnvConfig() {
  const [envConfig, setEnvConfig] = useState({
    hookUrl: '',
    baseUrl: '',
    apiKey: '',
    model: '',
    botIsSend: 0,
  })

  const [showApiKey, setShowApiKey] = useState(false)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [showSaveDialog, setShowSaveDialog] = useState(false)
  const [saveResult, setSaveResult] = useState<{ success: boolean; message: string } | null>(null)

  // 从数据库加载配置
  const fetchConfig = async () => {
    try {
      setLoading(true)
      const response = await fetch('http://localhost:8888/api/config', {
        method: 'GET',
        headers: {
          'Content-Type': 'application/json',
        },
      })

      if (!response.ok) {
        throw new Error('获取配置失败')
      }

      const result = await response.json()

      if (result.success && result.data) {
        setEnvConfig({
          hookUrl: result.data.HOOK_URL || '',
          baseUrl: result.data.BASE_URL || '',
          apiKey: result.data.API_KEY || '',
          model: result.data.MODEL || '',
          botIsSend: (() => {
            const raw = result.data.BOT_IS_SEND
            const val = String(raw ?? '').trim().toLowerCase()
            return val === '1' || val === 'true' ? 1 : 0
          })(),
        })
      }
    } catch (error) {
      console.error('获取配置失败:', error)
      alert('获取配置失败，请检查后端服务是否正常运行')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchConfig()
  }, [])

  const handleSave = async (silent: boolean = false) => {
    try {
      setSaving(true)

      const configMap = {
        HOOK_URL: envConfig.hookUrl,
        BASE_URL: envConfig.baseUrl,
        API_KEY: envConfig.apiKey,
        MODEL: envConfig.model,
        BOT_IS_SEND: String(envConfig.botIsSend ?? 0),
      }

      const response = await fetch('http://localhost:8888/api/config', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(configMap),
      })

      if (!response.ok) {
        throw new Error('保存配置失败')
      }

      const result = await response.json()

      if (result.success) {
        if (!silent) {
          setSaveResult({ success: true, message: '保存成功' })
          setShowSaveDialog(true)
        }
      } else {
        throw new Error(result.message || '保存配置失败')
      }
    } catch (error) {
      console.error('保存配置失败:', error)
      if (!silent) {
        setSaveResult({ success: false, message: '保存配置失败：网络或服务异常。' })
        setShowSaveDialog(true)
      }
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        icon={<BiCodeAlt className="text-2xl" />}
        title="环境变量配置"
        subtitle=".env_template 环境变量管理"
        actions={
          <Button
            onClick={() => handleSave(false)}
            size="sm"
            className="rounded-full bg-gradient-to-r from-blue-500 to-indigo-500 hover:from-blue-600 hover:to-indigo-600 text-white px-4 shadow-lg hover:shadow-xl transition-all duration-300 hover:scale-105"
          >
            <BiSave className="mr-1" /> 保存配置
          </Button>
        }
      />

      {loading && (
        <Card className="border-blue-500/20 bg-blue-500/5">
          <CardContent className="pt-6">
            <p className="text-center text-sm text-muted-foreground">加载配置中...</p>
          </CardContent>
        </Card>
      )}

      <div className="space-y-6">
        {/* 企业微信 Webhook */}
        <Card className="animate-in fade-in slide-in-from-bottom-5 duration-700">
          <CardHeader className="flex items-start gap-4">
            <div className="min-w-0 space-y-2">
              <CardTitle className="flex items-center gap-2">
                <BiLinkExternal className="text-primary" />
                企业微信 Webhook
              </CardTitle>
              <CardDescription>配置企业微信群机器人，用于接收通知消息</CardDescription>
            </div>
            <div>
              <button
                type="button"
                aria-label="企业微信发送开关"
                onClick={() => setEnvConfig({ ...envConfig, botIsSend: envConfig.botIsSend ? 0 : 1 })}
                className={`relative inline-flex h-7 w-14 rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-emerald-400/40 border border-white/30 shadow-[inset_0_1px_0_rgba(255,255,255,.25)] ${envConfig.botIsSend ? 'bg-emerald-500/80 hover:bg-emerald-500' : 'bg-white/10 hover:bg-white/15'}`}
              >
                <span
                  className={`absolute top-1 left-1 h-5 w-5 rounded-full bg-white shadow transition-transform ${envConfig.botIsSend ? 'translate-x-7' : 'translate-x-0'}`}
                />
              </button>
            </div>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              <Label htmlFor="hookUrl">Webhook URL</Label>
              <Input
                id="hookUrl"
                type="text"
                value={envConfig.hookUrl}
                onChange={(e) => setEnvConfig({ ...envConfig, hookUrl: e.target.value })}
                placeholder="https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=your_key"
              />
              <p className="text-xs text-muted-foreground">
                企业微信群机器人webhook地址，用于接收通知消息
              </p>
            </div>
          </CardContent>
        </Card>

        {/* API 配置 */}
        <Card className="animate-in fade-in slide-in-from-bottom-6 duration-700">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <BiCodeAlt className="text-primary" />
              API 配置
            </CardTitle>
            <CardDescription>配置 API 服务器地址和使用的 AI 模型</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="mb-4">
              <Label className="mb-2 block">快速选择提供商</Label>
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={() => setEnvConfig(prev => ({ ...prev, baseUrl: 'https://api.deepseek.com', model: 'deepseek-v4-flash' }))}
                  className="px-3 py-1.5 text-sm rounded-full border border-purple-300 dark:border-purple-600 bg-purple-50 dark:bg-purple-900/30 text-purple-700 dark:text-purple-300 hover:bg-purple-100 dark:hover:bg-purple-900/50 transition-colors"
                >
                  DeepSeek (deepseek-v4-flash)
                </button>
                <button
                  type="button"
                  onClick={() => setEnvConfig(prev => ({ ...prev, baseUrl: 'https://api.openai.com/v1', model: 'gpt-4o' }))}
                  className="px-3 py-1.5 text-sm rounded-full border border-green-300 dark:border-green-600 bg-green-50 dark:bg-green-900/30 text-green-700 dark:text-green-300 hover:bg-green-100 dark:hover:bg-green-900/50 transition-colors"
                >
                  OpenAI (GPT-4o)
                </button>
                <button
                  type="button"
                  onClick={() => setEnvConfig(prev => ({ ...prev, baseUrl: 'https://api.moonshot.cn/v1', model: 'moonshot-v1-8k' }))}
                  className="px-3 py-1.5 text-sm rounded-full border border-blue-300 dark:border-blue-600 bg-blue-50 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 hover:bg-blue-100 dark:hover:bg-blue-900/50 transition-colors"
                >
                  月之暗面 (Moonshot)
                </button>
                <button
                  type="button"
                  onClick={() => setEnvConfig(prev => ({ ...prev, baseUrl: '', model: '' }))}
                  className="px-3 py-1.5 text-sm rounded-full border border-gray-300 dark:border-gray-600 bg-gray-50 dark:bg-gray-900/30 text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-900/50 transition-colors"
                >
                  清空
                </button>
              </div>
              <p className="text-xs text-muted-foreground mt-2">点击预设自动填充 Base URL 和模型名称</p>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div className="space-y-2">
                <Label htmlFor="baseUrl">API Base URL</Label>
                <Input
                  id="baseUrl"
                  type="text"
                  value={envConfig.baseUrl}
                  onChange={(e) => setEnvConfig({ ...envConfig, baseUrl: e.target.value })}
                  placeholder="https://api.deepseek.com"
                />
                <p className="text-xs text-muted-foreground">API服务器地址</p>
              </div>

              <div className="space-y-2">
                <Label htmlFor="model">AI模型</Label>
                <Input
                  id="model"
                  type="text"
                  value={envConfig.model}
                  onChange={(e) => setEnvConfig({ ...envConfig, model: e.target.value })}
                  placeholder="deepseek-chat"
                />
                <p className="text-xs text-muted-foreground">使用的AI模型名称</p>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* API 密钥 */}
        <Card className="animate-in fade-in slide-in-from-bottom-7 duration-700">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <BiKey className="text-primary" />
              API 密钥
            </CardTitle>
            <CardDescription>配置 API 访问密钥，请妥善保管</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              <Label htmlFor="apiKey">API Key</Label>
              <div className="relative">
                <Input
                  id="apiKey"
                  type={showApiKey ? 'text' : 'password'}
                  value={envConfig.apiKey}
                  onChange={(e) => setEnvConfig({ ...envConfig, apiKey: e.target.value })}
                  placeholder="sk-xxxxxxxxxxxxxxxxx"
                />
                <Button
                  onClick={() => setShowApiKey(!showApiKey)}
                  variant="ghost"
                  size="sm"
                  className="absolute right-1 top-1/2 -translate-y-1/2 h-7"
                  type="button"
                >
                  {showApiKey ? '隐藏' : '显示'}
                </Button>
              </div>
              <p className="text-xs text-muted-foreground">
                🔐 API密钥将被安全存储，请妥善保管
              </p>
            </div>
          </CardContent>
        </Card>

        {/* 安全提示 */}
        <Card className="border-primary/20 bg-primary/5 animate-in fade-in slide-in-from-bottom-8 duration-700">
          <CardContent className="pt-6">
            <div className="flex gap-3">
              <BiInfoCircle className="h-5 w-5 text-primary flex-shrink-0 mt-0.5" />
              <div>
                <p className="text-sm text-foreground">
                  <strong className="font-semibold">提示：</strong> 这些环境变量将保存到{' '}
                  <code className="bg-primary/10 px-2 py-0.5 rounded text-primary font-mono text-xs">.env</code>{' '}
                  文件中。请勿将包含敏感信息的 .env 文件提交到版本控制系统。
                </p>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* 操作按钮已移至页头右上角 */}

        {/* 保存结果弹框 —— 与 Boss 配置一致样式 */}
        {showSaveDialog && saveResult && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30" role="dialog" aria-modal="true">
            <div className="bg-white dark:bg-neutral-900 rounded-2xl shadow-2xl w-[92%] max-w-sm border border-gray-200 dark:border-neutral-800 animate-in fade-in zoom-in-95">
              <Card className="border-0">
                <CardHeader className="pb-2">
                  <CardTitle className="text-lg flex items-center gap-2">
                    <BiSave className={saveResult.success ? 'text-green-500' : 'text-red-500'} />
                    {saveResult.success ? '保存成功' : '保存失败'}
                  </CardTitle>
                </CardHeader>
                <CardContent className="pt-0">
                  <p className="text-sm text-muted-foreground mb-4">{saveResult.message}</p>
                  <div className="flex justify-end gap-2">
                    <Button
                      onClick={() => setShowSaveDialog(false)}
                      className={`rounded-full px-4 ${saveResult.success ? 'bg-gradient-to-r from-green-500 to-emerald-600 hover:from-green-600 hover:to-emerald-700 text-white' : 'bg-gradient-to-r from-red-500 to-rose-600 hover:from-red-600 hover:to-rose-700 text-white'}`}
                    >
                      知道了
                    </Button>
                  </div>
                </CardContent>
              </Card>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
