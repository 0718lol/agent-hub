import React, { useState, useEffect } from 'react'
import { Rocket, CheckCircle, XCircle, Loader, X } from 'lucide-react'
import { useCanvasStore } from '../../stores/canvasStore'

const DEPLOY_STEPS = [
  '初始化云部署沙盒环境',
  '检查工作目录并拉取依赖包',
  '运行自动化冒烟测试',
  '构建生产环境 Docker 容器镜像',
  '向远端镜像仓库推送镜像',
  'Kubernetes 资源调度与健康检查',
  '域名解析与 SSL 证书配置',
  '部署完成，服务上线',
]

export default function DeployProgressCard() {
  const logs = useCanvasStore((s) => s.deployLogs)
  const status = useCanvasStore((s) => s.deployStatus)
  const url = useCanvasStore((s) => s.deployedUrl)
  const resetDeploy = useCanvasStore((s) => s.resetDeploy)
  const [displayPercent, setDisplayPercent] = useState(0)

  const totalSteps = DEPLOY_STEPS.length
  const currentStep = logs.length
  const targetPercent = status === 'success' ? 100 : Math.min(Math.round((currentStep / totalSteps) * 100), 99)

  // 平滑动画递增百分比
  useEffect(() => {
    if (displayPercent >= targetPercent) return
    const timer = setInterval(() => {
      setDisplayPercent((prev) => {
        const next = prev + 1
        if (next >= targetPercent) {
          clearInterval(timer)
          return targetPercent
        }
        return next
      })
    }, 30)
    return () => clearInterval(timer)
  }, [targetPercent, displayPercent])

  // 重置百分比（新一轮部署）
  useEffect(() => {
    if (status === 'running' && currentStep <= 1) {
      setDisplayPercent(0)
    }
  }, [status, currentStep])

  if (status === 'idle') return null

  const isSuccess = status === 'success'
  const isFailed = status === 'failed'
  const isRunning = status === 'running'

  const stepLabel = isFailed
    ? '部署失败'
    : isSuccess
      ? '部署完成'
      : currentStep > 0
        ? DEPLOY_STEPS[Math.min(currentStep - 1, totalSteps - 1)]
        : '准备中...'

  return (
    <div className="deploy-progress-card">
      {/* 头部 */}
      <div className="deploy-progress-header">
        <div className="deploy-progress-icon">
          {isRunning ? (
            <Loader size={18} className="deploy-spin" />
          ) : isSuccess ? (
            <CheckCircle size={18} />
          ) : (
            <XCircle size={18} />
          )}
        </div>
        <div className="deploy-progress-title">
          {isRunning ? '正在部署' : isSuccess ? '部署成功' : '部署失败'}
        </div>
        <div className="deploy-progress-step">
          {isRunning && `${currentStep} / ${totalSteps}`}
        </div>
        {!isRunning && (
          <button
            onClick={resetDeploy}
            className="deploy-progress-close"
            title="关闭"
          >
            <X size={14} />
          </button>
        )}
      </div>

      {/* 进度条 */}
      <div className="deploy-progress-track">
        <div
          className={`deploy-progress-fill ${isSuccess ? 'success' : isFailed ? 'failed' : ''}`}
          style={{ width: `${displayPercent}%` }}
        />
      </div>

      {/* 百分比 + 当前步骤 */}
      <div className="deploy-progress-info">
        <span className="deploy-progress-percent">{displayPercent}%</span>
        <span className="deploy-progress-step-label">{stepLabel}</span>
      </div>

      {/* 成功后显示链接 */}
      {isSuccess && url && (
        <a
          href={url}
          target="_blank"
          rel="noopener noreferrer"
          className="deploy-progress-link"
        >
          <Rocket size={13} />
          <span>{url}</span>
        </a>
      )}
    </div>
  )
}
