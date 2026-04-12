<template>
  <div class="agent-config">
    <el-row :gutter="20">
      <el-col :span="6">
        <el-card>
          <template #header>
            <span>Agent列表</span>
          </template>
          <el-menu
            :default-active="selectedAgent"
            @select="selectAgent"
          >
            <el-menu-item v-for="agent in agents" :key="agent.role" :index="agent.role">
              <el-icon><User /></el-icon>
              <span>{{ agent.name }}</span>
            </el-menu-item>
          </el-menu>
        </el-card>
      </el-col>

      <el-col :span="18">
        <el-card v-if="currentAgent">
          <template #header>
            <div class="card-header">
              <span>{{ currentAgent.name }} 配置</span>
              <el-button type="primary" @click="saveConfig">保存配置</el-button>
            </div>
          </template>

          <el-form :model="editForm" label-width="120px">
            <el-divider content-position="left">基本配置</el-divider>
            
            <el-form-item label="显示名称">
              <el-input v-model="editForm.name" />
            </el-form-item>

            <el-form-item label="模型">
              <el-select v-model="editForm.model" style="width: 100%">
                <el-option label="GPT-4o" value="gpt-4o" />
                <el-option label="GPT-4o-mini" value="gpt-4o-mini" />
                <el-option label="Claude 3.5 Sonnet" value="claude-3-5-sonnet" />
              </el-select>
            </el-form-item>

            <el-form-item label="温度">
              <el-slider v-model="editForm.temperature" :min="0" :max="2" :step="0.1" show-input />
            </el-form-item>

            <el-form-item label="最大Token">
              <el-slider v-model="editForm.max_tokens" :min="1000" :max="16000" :step="500" show-input />
            </el-form-item>

            <el-form-item label="最大步数">
              <el-slider v-model="editForm.max_steps" :min="1" :max="50" show-input />
            </el-form-item>

            <el-divider content-position="left">系统提示词</el-divider>

            <el-form-item label="提示词">
              <el-input
                v-model="editForm.system_prompt"
                type="textarea"
                :rows="20"
                placeholder="输入系统提示词..."
              />
            </el-form-item>
          </el-form>
        </el-card>

        <el-empty v-else description="请选择Agent进行配置" />
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import axios from 'axios'

interface AgentConfig {
  role: string
  name: string
  model: string
  temperature: number
  max_tokens: number
  max_steps: number
  system_prompt: string
}

const agents = ref<AgentConfig[]>([])
const selectedAgent = ref('')
const currentAgent = ref<AgentConfig | null>(null)

const editForm = reactive({
  name: '',
  model: 'gpt-4o',
  temperature: 0,
  max_tokens: 4000,
  max_steps: 10,
  system_prompt: '',
})

// 加载配置
const loadConfigs = async () => {
  try {
    const { data } = await axios.get('/api/config/agents')
    agents.value = Object.entries(data).map(([role, config]: [string, any]) => ({
      role,
      ...config,
    }))
  } catch (error) {
    ElMessage.error('加载配置失败')
  }
}

// 选择Agent
const selectAgent = (role: string) => {
  selectedAgent.value = role
  currentAgent.value = agents.value.find(a => a.role === role) || null
  
  if (currentAgent.value) {
    Object.assign(editForm, currentAgent.value)
  }
}

// 保存配置
const saveConfig = async () => {
  try {
    // 保存完整的Agent配置（包括模型参数）
    await axios.put(`/api/config/agents/${selectedAgent.value}`, {
      name: editForm.name,
      model: editForm.model,
      temperature: editForm.temperature,
      max_tokens: editForm.max_tokens,
      max_steps: editForm.max_steps,
      system_prompt: editForm.system_prompt,
    })
    ElMessage.success('配置已保存')
    // 刷新配置列表
    await loadConfigs()
  } catch (error) {
    ElMessage.error('保存失败')
    console.error(error)
  }
}

onMounted(() => {
  loadConfigs()
})
</script>

<style scoped>
.agent-config {
  padding: 20px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
</style>
