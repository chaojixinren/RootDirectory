<template>
  <div class="dashboard">
    <!-- 任务执行面板 -->
    <el-row :gutter="20">
      <el-col :span="16">
        <el-card class="workflow-card">
          <template #header>
            <div class="card-header">
              <span>任务执行流程</span>
              <div class="status-indicators">
                <el-tag v-if="isConnected" type="success">已连接</el-tag>
                <el-tag v-else type="danger">未连接</el-tag>
                <el-tag v-if="isRunning" type="warning">执行中</el-tag>
              </div>
            </div>
          </template>
          
          <!-- 工作流图 -->
          <div class="workflow-graph">
            <div class="workflow-step" :class="{ active: currentStep === 'orchestrator' }">
              <div class="step-icon">
                <el-icon><UserFilled /></el-icon>
              </div>
              <div class="step-label">决策Agent</div>
            </div>
            <div class="workflow-arrow">→</div>
            <div class="workflow-step" :class="{ active: currentStep === 'thinker' }">
              <div class="step-icon">
                <el-icon><Lightbulb /></el-icon>
              </div>
              <div class="step-label">思考专家</div>
            </div>
            <div class="workflow-arrow">→</div>
            <div class="workflow-step" :class="{ active: currentStep === 'executor' }">
              <div class="step-icon">
                <el-icon><Tools /></el-icon>
              </div>
              <div class="step-label">执行专家</div>
            </div>
            <div class="workflow-arrow">→</div>
            <div class="workflow-step" :class="{ active: currentStep === 'memory' }">
              <div class="step-icon">
                <el-icon><Collection /></el-icon>
              </div>
              <div class="step-label">记忆Agent</div>
            </div>
          </div>

          <!-- 当前计划 -->
          <div v-if="currentPlan" class="current-plan">
            <h4>当前计划</h4>
            <el-descriptions :column="1" border>
              <el-descriptions-item label="轮次">第 {{ currentRound }} 轮</el-descriptions-item>
              <el-descriptions-item label="计划内容">
                <pre>{{ currentPlan }}</pre>
              </el-descriptions-item>
            </el-descriptions>
          </div>

          <!-- 执行日志 -->
          <div class="execution-logs">
            <h4>执行日志</h4>
            <el-timeline>
              <el-timeline-item
                v-for="(log, index) in executionLogs"
                :key="index"
                :type="log.type"
                :timestamp="log.time"
              >
                {{ log.message }}
              </el-timeline-item>
            </el-timeline>
          </div>
        </el-card>
      </el-col>

      <el-col :span="8">
        <!-- A2A消息监控 -->
        <el-card class="messages-card">
          <template #header>
            <div class="card-header">
              <span>A2A消息监控</span>
              <el-button size="small" @click="clearMessages">清空</el-button>
            </div>
          </template>
          
          <div class="message-list" ref="messageList">
            <div
              v-for="msg in messages"
              :key="msg.msg_id"
              class="message-item"
              :class="msg.from_agent"
            >
              <div class="message-header">
                <el-tag size="small">{{ msg.from_agent }}</el-tag>
                <span class="message-type">{{ msg.msg_type }}</span>
                <span class="message-time">{{ formatTime(msg.timestamp) }}</span>
              </div>
              <div class="message-content">
                {{ msg.natural_language || JSON.stringify(msg.payload).slice(0, 100) }}
              </div>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 任务结果 -->
    <el-row v-if="taskResult" :gutter="20" class="result-row">
      <el-col :span="24">
        <el-card>
          <template #header>
            <span>任务结果</span>
          </template>
          <pre class="result-content">{{ taskResult }}</pre>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'

const route = useRoute()

// WebSocket
let ws: WebSocket | null = null
let monitorWs: WebSocket | null = null

// 状态
const isConnected = ref(false)
const isRunning = ref(false)
const currentStep = ref('')
const currentRound = ref(0)
const currentPlan = ref('')
const executionLogs = ref<any[]>([])
const messages = ref<any[]>([])
const taskResult = ref('')
const messageList = ref<HTMLElement | null>(null)

// 连接WebSocket
const connectWebSocket = () => {
  const wsUrl = `ws://${window.location.host}/ws`
  ws = new WebSocket(wsUrl)
  
  ws.onopen = () => {
    isConnected.value = true
    ElMessage.success('WebSocket已连接')
  }
  
  ws.onmessage = (event) => {
    const data = JSON.parse(event.data)
    handleMessage(data)
  }
  
  ws.onclose = () => {
    isConnected.value = false
    isRunning.value = false
  }
  
  ws.onerror = (error) => {
    console.error('WebSocket error:', error)
    ElMessage.error('WebSocket连接失败')
  }

  // 监控WebSocket
  const monitorUrl = `ws://${window.location.host}/ws/monitor`
  monitorWs = new WebSocket(monitorUrl)
  
  monitorWs.onmessage = (event) => {
    const data = JSON.parse(event.data)
    if (data.type === 'a2a_message') {
      messages.value.push(data.data)
      scrollToBottom()
    }
  }
}

// 处理消息
const handleMessage = (data: any) => {
  switch (data.type) {
    case 'state_update':
      updateState(data.data)
      break
    case 'task_complete':
      isRunning.value = false
      ElMessage.success('任务执行完成')
      break
    case 'error':
      isRunning.value = false
      ElMessage.error(data.error)
      break
  }
}

// 更新状态
const updateState = (state: any) => {
  currentRound.value = state.current_round
  
  // 更新当前步骤
  if (state.agent_states && state.agent_states.length > 0) {
    const activeAgent = state.agent_states.find((a: any) => a.status === 'running')
    if (activeAgent) {
      currentStep.value = activeAgent.role
    }
  }
  
  // 更新计划
  if (state.current_plan) {
    currentPlan.value = state.current_plan
  }
  
  // 添加日志
  executionLogs.value.push({
    time: new Date().toLocaleTimeString(),
    message: `轮次 ${state.current_round}: ${state.current_plan?.slice(0, 50) || '执行中'}...`,
    type: state.is_stalled ? 'warning' : 'primary',
  })
  
  // 保存最终结果
  if (state.final_result) {
    taskResult.value = state.final_result
  }
}

// 开始任务
const startTask = (goal: string, context: string, maxRounds: number) => {
  if (!ws || ws.readyState !== WebSocket.OPEN) {
    ElMessage.error('WebSocket未连接')
    return
  }
  
  isRunning.value = true
  executionLogs.value = []
  messages.value = []
  taskResult.value = ''
  
  ws.send(JSON.stringify({
    type: 'start_task',
    goal,
    context,
    maxRounds,
  }))
  
  executionLogs.value.push({
    time: new Date().toLocaleTimeString(),
    message: `开始任务: ${goal.slice(0, 50)}...`,
    type: 'success',
  })
}

// 清空消息
const clearMessages = () => {
  messages.value = []
}

// 滚动到底部
const scrollToBottom = () => {
  nextTick(() => {
    if (messageList.value) {
      messageList.value.scrollTop = messageList.value.scrollHeight
    }
  })
}

// 格式化时间
const formatTime = (timestamp: string) => {
  return new Date(timestamp).toLocaleTimeString()
}

// 监听路由参数变化
watch(() => route.query, (query) => {
  if (query.goal) {
    startTask(
      query.goal as string,
      (query.context as string) || '',
      parseInt(query.maxRounds as string) || 20
    )
  }
}, { immediate: true })

onMounted(() => {
  connectWebSocket()
})

onUnmounted(() => {
  ws?.close()
  monitorWs?.close()
})
</script>

<style scoped>
.dashboard {
  padding: 20px;
}

.workflow-card,
.messages-card {
  height: calc(100vh - 180px);
  overflow-y: auto;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.status-indicators {
  display: flex;
  gap: 8px;
}

.workflow-graph {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 30px 0;
  border-bottom: 1px solid #ebeef5;
}

.workflow-step {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 15px;
  border-radius: 8px;
  transition: all 0.3s;
}

.workflow-step.active {
  background-color: #ecf5ff;
  box-shadow: 0 0 10px rgba(64, 158, 255, 0.3);
}

.step-icon {
  width: 50px;
  height: 50px;
  border-radius: 50%;
  background-color: #909399;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  font-size: 24px;
  margin-bottom: 8px;
}

.workflow-step.active .step-icon {
  background-color: #409EFF;
}

.workflow-arrow {
  font-size: 24px;
  color: #909399;
  margin: 0 10px;
}

.current-plan {
  margin-top: 20px;
  padding: 15px;
  background-color: #f5f7fa;
  border-radius: 4px;
}

.current-plan pre {
  white-space: pre-wrap;
  word-wrap: break-word;
  margin: 0;
}

.execution-logs {
  margin-top: 20px;
}

.message-list {
  height: calc(100vh - 280px);
  overflow-y: auto;
}

.message-item {
  padding: 10px;
  margin-bottom: 10px;
  border-radius: 4px;
  background-color: #f5f7fa;
}

.message-item.orchestrator {
  border-left: 3px solid #409EFF;
}

.message-item.thinker {
  border-left: 3px solid #67C23A;
}

.message-item.executor {
  border-left: 3px solid #E6A23C;
}

.message-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 5px;
}

.message-type {
  font-size: 12px;
  color: #909399;
}

.message-time {
  font-size: 12px;
  color: #C0C4CC;
}

.message-content {
  font-size: 13px;
  color: #606266;
}

.result-row {
  margin-top: 20px;
}

.result-content {
  background-color: #f5f7fa;
  padding: 15px;
  border-radius: 4px;
  white-space: pre-wrap;
  word-wrap: break-word;
  max-height: 400px;
  overflow-y: auto;
}
</style>
