'use client'

import { useState, useEffect, useRef } from 'react'
import { motion } from 'framer-motion'
import { BiFile, BiRefresh, BiDownload, BiPlus, BiHistory, BiUpload, BiBrain, BiCheck, BiInfoCircle } from 'react-icons/bi'
import PageHeader from '@/app/components/PageHeader'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select } from '@/components/ui/select'

const API_BASE = 'http://localhost:8888'

export default function ResumesPage() {
  const [resumes, setResumes] = useState<any[]>([])
  const [reviews, setReviews] = useState<string[]>([])
  const [loading, setLoading] = useState(true)
  const [source, setSource] = useState('manual')
  const [companyName, setCompanyName] = useState('')
  const [jobName, setJobName] = useState('')
  const [jobDescription, setJobDescription] = useState('')
  const [generating, setGenerating] = useState(false)
  const [message, setMessage] = useState('')

  // 上传相关
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [uploading, setUploading] = useState(false)
  const [uploadResult, setUploadResult] = useState<any>(null)
  const [analyzing, setAnalyzing] = useState(false)
  const [analysisResult, setAnalysisResult] = useState<any>(null)
  const [activeTab, setActiveTab] = useState<'generate' | 'upload'>('generate')

  useEffect(() => { fetchResumes() }, [])

  const fetchResumes = async () => {
    setLoading(true)
    try {
      const res = await fetch(`${API_BASE}/api/resume/list`)
      const data = await res.json()
      if (data.success) {
        setResumes(data.resumes || [])
        setReviews(data.reviews || [])
      }
    } catch (e) {
      console.error('获取简历列表失败', e)
    } finally {
      setLoading(false)
    }
  }

  const handleGenerate = async () => {
    setGenerating(true)
    setMessage('')
    try {
      const res = await fetch(`${API_BASE}/api/resume/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          source,
          companyName,
          jobName,
          jobDescription,
        }),
      })
      const data = await res.json()
      setMessage(data.message || (data.success ? '简历已生成' : '生成失败'))
      if (data.success) fetchResumes()
    } catch (e) {
      setMessage('生成失败: ' + String(e))
    } finally {
      setGenerating(false)
    }
  }

  // 上传简历文件
  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return

    setUploading(true)
    setUploadResult(null)
    setAnalysisResult(null)

    try {
      const formData = new FormData()
      formData.append('file', file)

      const res = await fetch(`${API_BASE}/api/resume/upload`, {
        method: 'POST',
        body: formData,
      })
      const data = await res.json()
      if (data.success) {
        setUploadResult(data)
        // 自动开始 AI 分析
        await handleAnalyze(data.extractedText)
      } else {
        setUploadResult({ success: false, error: data.message })
      }
    } catch (e) {
      setUploadResult({ success: false, error: String(e) })
    } finally {
      setUploading(false)
    }
  }

  // AI 分析简历文本
  const handleAnalyze = async (text: string) => {
    setAnalyzing(true)
    try {
      const res = await fetch(`${API_BASE}/api/resume/analyze`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text }),
      })
      const data = await res.json()
      setAnalysisResult(data)
    } catch (e) {
      setAnalysisResult({ success: false, error: String(e) })
    } finally {
      setAnalyzing(false)
    }
  }

  return (
    <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}>
      <PageHeader
        icon={<BiFile />}
        title="简历管理"
        subtitle="简历生成、上传与 AI 自动分析"
        actions={
          <Button size="sm" onClick={fetchResumes} className="flex items-center gap-1 bg-blue-600 hover:bg-blue-700 text-white">
            <BiRefresh className="text-lg" /> 刷新
          </Button>
        }
      />

      {/* Tab 切换 */}
      <div className="flex gap-2 mb-6">
        <button
          onClick={() => setActiveTab('generate')}
          className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
            activeTab === 'generate'
              ? 'bg-blue-600 text-white'
              : 'bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-700'
          }`}
        >
          <BiPlus className="inline mr-1" />生成简历
        </button>
        <button
          onClick={() => setActiveTab('upload')}
          className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
            activeTab === 'upload'
              ? 'bg-purple-600 text-white'
              : 'bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-700'
          }`}
        >
          <BiUpload className="inline mr-1" />上传简历分析
        </button>
      </div>

      {activeTab === 'generate' ? (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-6">
          {/* 生成简历 */}
          <Card className="lg:col-span-2">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <BiPlus className="text-primary" /> 生成简历
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                <div className="space-y-2">
                  <Label>简历来源</Label>
                  <Select value={source} onChange={e => setSource(e.target.value)}>
                    <option value="manual">手动上传</option>
                    <option value="ai">AI 自动生成</option>
                  </Select>
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label>公司名称</Label>
                    <Input value={companyName} onChange={e => setCompanyName(e.target.value)} placeholder="目标公司" />
                  </div>
                  <div className="space-y-2">
                    <Label>岗位名称</Label>
                    <Input value={jobName} onChange={e => setJobName(e.target.value)} placeholder="目标岗位" />
                  </div>
                </div>
                <div className="space-y-2">
                  <Label>岗位描述 (JD)</Label>
                  <textarea
                    className="w-full min-h-[120px] rounded-md border border-stroke dark:border-strokedark bg-white dark:bg-blacksection px-3 py-2 text-sm"
                    value={jobDescription}
                    onChange={e => setJobDescription(e.target.value)}
                    placeholder="粘贴岗位描述，AI 将根据 JD 自动优化简历..."
                  />
                </div>
                <Button
                  onClick={handleGenerate}
                  disabled={generating}
                  className="bg-gradient-to-r from-blue-600 to-indigo-600 text-white"
                >
                  {generating ? '生成中...' : '生成简历'}
                </Button>
                {message && (
                  <p className="text-sm text-gray-600 dark:text-manatee mt-2">{message}</p>
                )}
              </div>
            </CardContent>
          </Card>

          {/* 评审报告 */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <BiHistory className="text-primary" /> 评审报告
              </CardTitle>
            </CardHeader>
            <CardContent>
              {reviews.length === 0 ? (
                <p className="text-sm text-gray-500 dark:text-manatee text-center py-8">
                  暂无评审报告（每 10 份简历自动触发一次评审）
                </p>
              ) : (
                <ul className="space-y-2">
                  {reviews.map((r, i) => (
                    <li key={i} className="text-sm text-blue-600 dark:text-blue-400 hover:underline cursor-pointer">
                      {r}
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>
        </div>
      ) : (
        /* 上传简历分析 Tab */
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
          {/* 上传区域 */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <BiUpload className="text-purple-500" /> 上传简历
              </CardTitle>
              <CardDescription>支持 PDF、Word 格式，AI 自动解析提取技能和经验</CardDescription>
            </CardHeader>
            <CardContent>
              <div
                onClick={() => fileInputRef.current?.click()}
                className="border-2 border-dashed border-purple-300 dark:border-purple-700 rounded-xl p-12 text-center cursor-pointer hover:bg-purple-50 dark:hover:bg-purple-900/20 transition-colors"
              >
                <BiUpload className="text-4xl text-purple-400 mx-auto mb-3" />
                <p className="text-sm text-gray-600 dark:text-gray-400 mb-1">
                  点击上传简历文件
                </p>
                <p className="text-xs text-gray-400 dark:text-gray-500">
                  PDF / DOCX / DOC
                </p>
              </div>
              <input
                ref={fileInputRef}
                type="file"
                accept=".pdf,.docx,.doc"
                className="hidden"
                onChange={handleFileChange}
              />

              {uploading && (
                <div className="mt-4 p-3 bg-purple-50 dark:bg-purple-900/30 rounded-lg text-sm text-purple-700 dark:text-purple-300">
                  正在上传并解析...
                </div>
              )}

              {uploadResult && !uploadResult.success && (
                <div className="mt-4 p-3 bg-red-50 dark:bg-red-900/30 rounded-lg text-sm text-red-600 dark:text-red-400">
                  上传失败: {uploadResult.error}
                </div>
              )}
            </CardContent>
          </Card>

          {/* 分析结果 */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <BiBrain className="text-purple-500" /> AI 分析结果
              </CardTitle>
              <CardDescription>自动提取的技能和经验信息</CardDescription>
            </CardHeader>
            <CardContent>
              {analyzing ? (
                <div className="text-center py-8">
                  <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-purple-500 mx-auto mb-3"></div>
                  <p className="text-sm text-gray-500">AI 正在分析简历...</p>
                </div>
              ) : analysisResult?.success ? (
                <div className="space-y-4">
                  {/* 技能标签 */}
                  <div>
                    <Label className="flex items-center gap-1 text-purple-600 dark:text-purple-400">
                      <BiCheck /> 技能
                    </Label>
                    <div className="flex flex-wrap gap-1.5 mt-1">
                      {analysisResult.skills.split(', ').filter((s: string) => s.trim()).map((skill: string, i: number) => (
                        <span key={i} className="px-2 py-0.5 text-xs rounded-full bg-purple-100 dark:bg-purple-900/40 text-purple-700 dark:text-purple-300">
                          {skill.trim()}
                        </span>
                      ))}
                    </div>
                  </div>

                  {analysisResult.yearsOfExperience > 0 && (
                    <div>
                      <Label className="text-purple-600 dark:text-purple-400">工作年限</Label>
                      <p className="text-sm mt-1">{analysisResult.yearsOfExperience} 年</p>
                    </div>
                  )}

                  {analysisResult.targetRoles && (
                    <div>
                      <Label className="text-purple-600 dark:text-purple-400">目标岗位</Label>
                      <p className="text-sm mt-1">{analysisResult.targetRoles}</p>
                    </div>
                  )}

                  {analysisResult.experience && (
                    <div>
                      <Label className="text-purple-600 dark:text-purple-400">工作经历</Label>
                      <p className="text-sm mt-1 text-gray-600 dark:text-gray-400 whitespace-pre-wrap line-clamp-4">{analysisResult.experience}</p>
                    </div>
                  )}

                  <div className="p-3 bg-green-50 dark:bg-green-900/20 rounded-lg border border-green-200 dark:border-green-800">
                    <p className="text-xs text-green-700 dark:text-green-400 flex items-center gap-1">
                      <BiInfoCircle /> 技能介绍已自动保存到 AI 配置中
                    </p>
                  </div>
                </div>
              ) : analysisResult ? (
                <div className="p-3 bg-red-50 dark:bg-red-900/30 rounded-lg text-sm text-red-600 dark:text-red-400">
                  分析失败: {analysisResult.error}
                </div>
              ) : (
                <div className="text-center py-8 text-sm text-gray-400 dark:text-gray-500">
                  上传简历后将自动显示 AI 分析结果
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      )}

      {/* 简历列表 */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <BiDownload className="text-primary" /> 已生成的简历
          </CardTitle>
        </CardHeader>
        <CardContent>
          {loading ? (
            <p className="text-center py-8 text-gray-500">加载中...</p>
          ) : resumes.length === 0 ? (
            <p className="text-center py-8 text-gray-500 dark:text-manatee">
              暂无简历，请先生成或上传一份
            </p>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {resumes.map((r, i) => (
                <div key={i} className="border border-stroke dark:border-strokedark rounded-lg p-4 hover:shadow-md transition-shadow">
                  <p className="text-sm font-medium text-gray-900 dark:text-white truncate">{r.name}</p>
                  <p className="text-xs text-gray-500 dark:text-manatee mt-1">
                    {(r.size / 1024).toFixed(1)} KB
                  </p>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </motion.div>
  )
}
