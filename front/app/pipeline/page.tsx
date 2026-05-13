'use client'

import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { BiTask, BiStats, BiRefresh, BiFilter, BiSearch } from 'react-icons/bi'
import PageHeader from '@/app/components/PageHeader'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Select } from '@/components/ui/select'

const API_BASE = 'http://localhost:8888'

interface PipelineEntry {
  id: number
  entryNumber: number
  entryDate: string
  platform: string
  companyName: string
  jobName: string
  score: number
  status: string
  notes: string
  updatedAt: string
}

interface PipelineStats {
  total: number
  evaluated: number
  applied: number
  responded: number
  interview: number
  offer: number
  rejected: number
  discarded: number
  skipped: number
  avgScore: number
}

const STATUS_COLORS: Record<string, string> = {
  Evaluated: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400',
  Applied: 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400',
  Responded: 'bg-cyan-100 text-cyan-800 dark:bg-cyan-900/30 dark:text-cyan-400',
  Interview: 'bg-purple-100 text-purple-800 dark:bg-purple-900/30 dark:text-purple-400',
  Offer: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400',
  Rejected: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400',
  Discarded: 'bg-gray-100 text-gray-800 dark:bg-gray-900/30 dark:text-gray-400',
  SKIP: 'bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-400',
}

const STATUS_LABELS: Record<string, string> = {
  Evaluated: '已评估',
  Applied: '已投递',
  Responded: '已回复',
  Interview: '面试中',
  Offer: 'Offer',
  Rejected: '已拒绝',
  Discarded: '已放弃',
  SKIP: '跳过',
}

const PLATFORM_LABELS: Record<string, string> = {
  boss: 'Boss直聘',
  liepin: '猎聘',
  zhilian: '智联招聘',
  job51: '51job',
}

export default function PipelinePage() {
  const [entries, setEntries] = useState<PipelineEntry[]>([])
  const [stats, setStats] = useState<PipelineStats | null>(null)
  const [loading, setLoading] = useState(true)
  const [statusFilter, setStatusFilter] = useState('all')
  const [searchTerm, setSearchTerm] = useState('')
  const [editingId, setEditingId] = useState<number | null>(null)
  const [newStatus, setNewStatus] = useState('')
  const [showStats, setShowStats] = useState(false)

  useEffect(() => {
    fetchEntries()
  }, [])

  const fetchEntries = async () => {
    setLoading(true)
    try {
      const [entriesRes, statsRes] = await Promise.all([
        fetch(`${API_BASE}/api/pipeline/entries`),
        fetch(`${API_BASE}/api/pipeline/stats`),
      ])
      const entriesData = await entriesRes.json()
      const statsData = await statsRes.json()
      if (entriesData.success) setEntries(entriesData.entries || [])
      if (statsData.success) setStats(statsData.stats)
    } catch (e) {
      console.error('获取管道数据失败', e)
    } finally {
      setLoading(false)
    }
  }

  const updateStatus = async (id: number, status: string) => {
    try {
      const res = await fetch(`${API_BASE}/api/pipeline/entries/${id}/status`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status }),
      })
      const data = await res.json()
      if (data.success) {
        fetchEntries()
        setEditingId(null)
      } else {
        alert('状态更新失败: ' + (data.message || ''))
      }
    } catch (e) {
      alert('状态更新失败: ' + String(e))
    }
  }

  const filteredEntries = entries.filter(e => {
    if (statusFilter !== 'all' && e.status !== statusFilter) return false
    if (searchTerm) {
      const q = searchTerm.toLowerCase()
      return (
        (e.companyName || '').toLowerCase().includes(q) ||
        (e.jobName || '').toLowerCase().includes(q)
      )
    }
    return true
  })

  const scoreColor = (score: number) => {
    if (score >= 4.0) return 'text-green-600 dark:text-green-400'
    if (score >= 3.0) return 'text-yellow-600 dark:text-yellow-400'
    return 'text-red-600 dark:text-red-400'
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
    >
      <PageHeader
        icon={<BiTask />}
        title="求职管道"
        subtitle="投递状态追踪与管理"
        actions={
          <div className="flex gap-2">
            <Button
              size="sm"
              variant="outline"
              onClick={() => setShowStats(!showStats)}
              className="flex items-center gap-1"
            >
              <BiStats className="text-lg" />
              {showStats ? '隐藏统计' : '查看统计'}
            </Button>
            <Button
              size="sm"
              onClick={fetchEntries}
              className="flex items-center gap-1 bg-blue-600 hover:bg-blue-700 text-white"
            >
              <BiRefresh className="text-lg" />
              刷新
            </Button>
          </div>
        }
      />

      {/* 统计卡片 */}
      <AnimatePresence>
        {showStats && stats && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-8 gap-3 mb-6"
          >
            {[
              { label: '总计', value: stats.total, color: 'text-blue-600' },
              { label: '已投递', value: stats.applied, color: 'text-blue-600' },
              { label: '面试中', value: stats.interview, color: 'text-purple-600' },
              { label: 'Offer', value: stats.offer, color: 'text-green-600' },
              { label: '已拒绝', value: stats.rejected, color: 'text-red-600' },
              { label: '已跳过', value: stats.skipped, color: 'text-orange-600' },
              { label: '平均分', value: stats.avgScore.toFixed(1), color: 'text-cyan-600' },
              { label: '已评估', value: stats.evaluated, color: 'text-yellow-600' },
            ].map((item, i) => (
              <Card key={i} className="dark:bg-blacksection">
                <CardContent className="p-4 text-center">
                  <div className={`text-2xl font-bold ${item.color}`}>{item.value}</div>
                  <div className="text-xs text-gray-500 dark:text-manatee mt-1">{item.label}</div>
                </CardContent>
              </Card>
            ))}
          </motion.div>
        )}
      </AnimatePresence>

      {/* 筛选栏 */}
      <div className="flex flex-wrap gap-3 mb-6 items-center">
        <div className="relative flex-1 min-w-[200px]">
          <BiSearch className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
          <Input
            placeholder="搜索公司/岗位..."
            value={searchTerm}
            onChange={e => setSearchTerm(e.target.value)}
            className="pl-10"
          />
        </div>
        <div className="flex items-center gap-2">
          <BiFilter className="text-gray-400" />
          <select
            className="rounded-md border border-stroke dark:border-strokedark bg-white dark:bg-blacksection px-3 py-2 text-sm"
            value={statusFilter}
            onChange={e => setStatusFilter(e.target.value)}
          >
            <option value="all">全部状态</option>
            <option value="Evaluated">已评估</option>
            <option value="Applied">已投递</option>
            <option value="Responded">已回复</option>
            <option value="Interview">面试中</option>
            <option value="Offer">Offer</option>
            <option value="Rejected">已拒绝</option>
            <option value="Discarded">已放弃</option>
            <option value="SKIP">跳过</option>
          </select>
        </div>
      </div>

      {/* 条目列表 */}
      {loading ? (
        <div className="text-center py-12 text-gray-500">加载中...</div>
      ) : filteredEntries.length === 0 ? (
        <div className="text-center py-12 text-gray-500 dark:text-manatee">
          <BiTask className="text-4xl mx-auto mb-3 opacity-50" />
          <p>暂无管道数据</p>
          <p className="text-sm mt-1">投递岗位后会自动创建管道条目</p>
        </div>
      ) : (
        <div className="space-y-2">
          {filteredEntries.map((entry, index) => (
            <motion.div
              key={entry.id}
              initial={{ opacity: 0, x: -10 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: index * 0.02 }}
              className="bg-white dark:bg-blacksection rounded-lg border border-stroke dark:border-strokedark p-4 hover:shadow-md transition-shadow"
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-4 flex-1 min-w-0">
                  <div className="text-xs text-gray-400 dark:text-manatee font-mono w-12 shrink-0">
                    #{entry.entryNumber}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="font-medium text-gray-900 dark:text-white truncate">
                      {entry.companyName}
                    </div>
                    <div className="text-sm text-gray-500 dark:text-manatee truncate">
                      {entry.jobName}
                    </div>
                    <div className="text-xs text-gray-400 dark:text-manatee mt-0.5 flex items-center gap-2">
                      <span>{entry.entryDate}</span>
                      <span>·</span>
                      <span>{PLATFORM_LABELS[entry.platform] || entry.platform}</span>
                    </div>
                  </div>
                </div>

                <div className="flex items-center gap-4">
                  {/* 评分 */}
                  {entry.score != null && (
                    <div className={`text-sm font-bold ${scoreColor(entry.score)}`}>
                      {entry.score.toFixed(1)}
                    </div>
                  )}

                  {/* 状态 */}
                  {editingId === entry.id ? (
                    <div className="flex items-center gap-1">
                      <select
                        className="rounded border border-stroke dark:border-strokedark bg-white dark:bg-blacksection px-2 py-1 text-xs"
                        value={newStatus}
                        onChange={e => setNewStatus(e.target.value)}
                      >
                        <option value="Evaluated">已评估</option>
                        <option value="Applied">已投递</option>
                        <option value="Responded">已回复</option>
                        <option value="Interview">面试中</option>
                        <option value="Offer">Offer</option>
                        <option value="Rejected">已拒绝</option>
                        <option value="Discarded">已放弃</option>
                        <option value="SKIP">跳过</option>
                      </select>
                      <button
                        onClick={() => updateStatus(entry.id, newStatus)}
                        className="text-green-600 hover:text-green-700 text-xs px-1"
                      >
                        ✓
                      </button>
                      <button
                        onClick={() => setEditingId(null)}
                        className="text-red-600 hover:text-red-700 text-xs px-1"
                      >
                        ✕
                      </button>
                    </div>
                  ) : (
                    <span
                      className={`px-2.5 py-1 rounded-full text-xs font-medium cursor-pointer hover:opacity-80 ${STATUS_COLORS[entry.status] || 'bg-gray-100 text-gray-800'}`}
                      onClick={() => {
                        setEditingId(entry.id)
                        setNewStatus(entry.status)
                      }}
                    >
                      {STATUS_LABELS[entry.status] || entry.status}
                    </span>
                  )}
                </div>
              </div>

              {/* 备注 */}
              {entry.notes && (
                <div className="mt-2 text-xs text-gray-400 dark:text-manatee ml-16">
                  📝 {entry.notes}
                </div>
              )}
            </motion.div>
          ))}
        </div>
      )}
    </motion.div>
  )
}
