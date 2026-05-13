'use client'

import { useState, useEffect } from 'react'
import { motion } from 'framer-motion'
import { BiMessage, BiBook, BiHelpCircle, BiPlus, BiRefresh } from 'react-icons/bi'
import PageHeader from '@/app/components/PageHeader'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'

const API_BASE = 'http://localhost:8888'

export default function InterviewPage() {
  const [stories, setStories] = useState<any[]>([])
  const [questions, setQuestions] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [activeTab, setActiveTab] = useState('questions')

  // 添加故事
  const [title, setTitle] = useState('')
  const [situation, setSituation] = useState('')
  const [task, setTask] = useState('')
  const [action, setAction] = useState('')
  const [result, setResult] = useState('')
  const [learning, setLearning] = useState('')

  // 生成面试准备
  const [companyName, setCompanyName] = useState('')
  const [jobName, setJobName] = useState('')
  const [prepResult, setPrepResult] = useState('')

  useEffect(() => {
    fetchData()
  }, [])

  const fetchData = async () => {
    setLoading(true)
    try {
      const [storiesRes, questionsRes] = await Promise.all([
        fetch(`${API_BASE}/api/interview/stories`),
        fetch(`${API_BASE}/api/interview/questions`),
      ])
      const sd = await storiesRes.json()
      const qd = await questionsRes.json()
      if (sd.success) setStories(sd.stories || [])
      if (qd.success) setQuestions(qd.questions || [])
    } catch (e) {
      console.error('获取数据失败', e)
    } finally {
      setLoading(false)
    }
  }

  const handleAddStory = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/interview/stories`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title, situation, task, action, result, learning }),
      })
      const data = await res.json()
      if (data.success) {
        setTitle(''); setSituation(''); setTask(''); setAction(''); setResult(''); setLearning('')
        fetchData()
      }
      alert(data.message)
    } catch (e) {
      alert('添加失败: ' + String(e))
    }
  }

  const handleGeneratePrep = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/interview/prepare`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ companyName, jobName, jd: '' }),
      })
      const data = await res.json()
      setPrepResult(data.message || '')
    } catch (e) {
      setPrepResult('生成失败: ' + String(e))
    }
  }

  return (
    <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}>
      <PageHeader
        icon={<BiMessage />}
        title="面试准备"
        subtitle="STAR+L 故事库 & 中文面试训练"
        actions={
          <Button size="sm" onClick={fetchData} className="flex items-center gap-1 bg-blue-600 hover:bg-blue-700 text-white">
            <BiRefresh className="text-lg" /> 刷新
          </Button>
        }
      />

      <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-6">
        <TabsList>
          <TabsTrigger value="questions">面试题库</TabsTrigger>
          <TabsTrigger value="stories">故事库</TabsTrigger>
          <TabsTrigger value="add">添加故事</TabsTrigger>
          <TabsTrigger value="prepare">生成准备</TabsTrigger>
        </TabsList>

        <TabsContent value="questions">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <BiHelpCircle className="text-primary" /> 中文面试常见问题
              </CardTitle>
            </CardHeader>
            <CardContent>
              {loading ? (
                <p className="text-center py-8 text-gray-500">加载中...</p>
              ) : (
                <div className="space-y-2">
                  {questions.map((q, i) => (
                    <div key={i} className="flex items-start gap-3 p-3 rounded-lg border border-stroke dark:border-strokedark hover:bg-gray-50 dark:hover:bg-gray-900/50">
                      <span className="text-xs font-mono text-gray-400 w-6 shrink-0">{i + 1}</span>
                      <div className="flex-1">
                        <p className="text-sm font-medium text-gray-900 dark:text-white">{q.question}</p>
                        <p className="text-xs text-gray-500 dark:text-manatee mt-0.5">{q.description}</p>
                      </div>
                      <span className="text-xs px-2 py-0.5 rounded-full bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400 shrink-0">
                        {q.category}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="stories">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <BiBook className="text-primary" /> STAR+L 故事库
              </CardTitle>
            </CardHeader>
            <CardContent>
              {stories.length === 0 ? (
                <p className="text-center py-8 text-gray-500 dark:text-manatee">
                  暂无故事，请先在"添加故事"标签页添加 STAR+L 故事
                </p>
              ) : (
                <div className="space-y-4">
                  {stories.map((s, i) => (
                    <Card key={i}>
                      <CardContent className="p-4">
                        <h3 className="font-medium text-gray-900 dark:text-white">{s.title}</h3>
                        <div className="mt-2 space-y-1 text-sm text-gray-600 dark:text-manatee">
                          <p><span className="font-medium">S 情境:</span> {s.situation}</p>
                          <p><span className="font-medium">T 任务:</span> {s.task}</p>
                          <p><span className="font-medium">A 行动:</span> {s.action}</p>
                          <p><span className="font-medium">R 结果:</span> {s.result}</p>
                          {s.learning && <p><span className="font-medium">L 经验:</span> {s.learning}</p>}
                        </div>
                      </CardContent>
                    </Card>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="add">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <BiPlus className="text-primary" /> 添加 STAR+L 故事
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                <div className="space-y-2">
                  <Label>故事标题</Label>
                  <Input value={title} onChange={e => setTitle(e.target.value)} placeholder="如：解决高并发系统崩溃问题" />
                </div>
                <div className="space-y-2">
                  <Label>S - 情境 (Situation)</Label>
                  <textarea className="w-full min-h-[60px] rounded-md border border-stroke dark:border-strokedark bg-white dark:bg-blacksection px-3 py-2 text-sm" value={situation} onChange={e => setSituation(e.target.value)} placeholder="当时的情况是怎样的？" />
                </div>
                <div className="space-y-2">
                  <Label>T - 任务 (Task)</Label>
                  <textarea className="w-full min-h-[60px] rounded-md border border-stroke dark:border-strokedark bg-white dark:bg-blacksection px-3 py-2 text-sm" value={task} onChange={e => setTask(e.target.value)} placeholder="你的任务目标是什么？" />
                </div>
                <div className="space-y-2">
                  <Label>A - 行动 (Action)</Label>
                  <textarea className="w-full min-h-[80px] rounded-md border border-stroke dark:border-strokedark bg-white dark:bg-blacksection px-3 py-2 text-sm" value={action} onChange={e => setAction(e.target.value)} placeholder="你采取了哪些具体行动？" />
                </div>
                <div className="space-y-2">
                  <Label>R - 结果 (Result)</Label>
                  <textarea className="w-full min-h-[60px] rounded-md border border-stroke dark:border-strokedark bg-white dark:bg-blacksection px-3 py-2 text-sm" value={result} onChange={e => setResult(e.target.value)} placeholder="取得了什么可量化的成果？" />
                </div>
                <div className="space-y-2">
                  <Label>L - 经验教训 (Learning)</Label>
                  <textarea className="w-full min-h-[60px] rounded-md border border-stroke dark:border-strokedark bg-white dark:bg-blacksection px-3 py-2 text-sm" value={learning} onChange={e => setLearning(e.target.value)} placeholder="你从中学到了什么？" />
                </div>
                <Button onClick={handleAddStory} className="bg-gradient-to-r from-blue-600 to-indigo-600 text-white">保存故事</Button>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="prepare">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <BiBook className="text-primary" /> 生成面试准备文档
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label>公司名称</Label>
                    <Input value={companyName} onChange={e => setCompanyName(e.target.value)} placeholder="输入公司名" />
                  </div>
                  <div className="space-y-2">
                    <Label>岗位名称</Label>
                    <Input value={jobName} onChange={e => setJobName(e.target.value)} placeholder="输入岗位名" />
                  </div>
                </div>
                <Button onClick={handleGeneratePrep} className="bg-gradient-to-r from-purple-600 to-indigo-600 text-white">生成准备文档</Button>
                {prepResult && <p className="text-sm text-gray-600 dark:text-manatee">{prepResult}</p>}
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </motion.div>
  )
}
