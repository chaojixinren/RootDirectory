<template>
  <div class="tools-config">
    <el-row :gutter="20">
      <el-col :span="12">
        <el-card>
          <template #header>
            <span>内置工具</span>
          </template>
          
          <el-table :data="builtinTools" style="width: 100%">
            <el-table-column prop="name" label="名称" width="150">
              <template #default="{ row }">
                <el-tag>{{ row.name }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="description" label="描述" />
            <el-table-column prop="source" label="来源" width="100">
              <template #default="{ row }">
                <el-tag type="success">{{ row.source }}</el-tag>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>

      <el-col :span="12">
        <el-card>
          <template #header>
            <div class="card-header">
              <span>MCP服务器</span>
              <el-button type="primary" size="small" @click="showAddMCP = true">
                <el-icon><Plus /></el-icon>添加
              </el-button>
            </div>
          </template>
          
          <el-empty v-if="mcpServers.length === 0" description="暂无MCP服务器" />
          
          <el-card
            v-for="server in mcpServers"
            :key="server.id"
            class="mcp-server-card"
            shadow="hover"
          >
            <template #header>
              <div class="server-header">
                <span>{{ server.name }}</span>
                <el-tag :type="server.connected ? 'success' : 'danger'">
                  {{ server.connected ? '已连接' : '未连接' }}
                </el-tag>
              </div>
            </template>
            <div class="server-info">
              <p><strong>传输方式:</strong> {{ server.transport }}</p>
              <p><strong>URL:</strong> {{ server.url || 'N/A' }}</p>
              <p><strong>工具数:</strong> {{ server.toolsCount || 0 }}</p>
            </div>
            <div class="server-actions">
              <el-button size="small" @click="testConnection(server)">测试</el-button>
              <el-button size="small" type="danger" @click="removeServer(server)">删除</el-button>
            </div>
          </el-card>
        </el-card>
      </el-col>
    </el-row>

    <!-- 添加MCP对话框 -->
    <el-dialog v-model="showAddMCP" title="添加MCP服务器" width="500px">
      <el-form :model="mcpForm" label-width="100px">
        <el-form-item label="名称">
          <el-input v-model="mcpForm.name" placeholder="服务器名称" />
        </el-form-item>
        <el-form-item label="传输方式">
          <el-select v-model="mcpForm.transport" style="width: 100%">
            <el-option label="STDIO" value="stdio" />
            <el-option label="SSE" value="sse" />
            <el-option label="HTTP" value="http" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="mcpForm.transport === 'stdio'" label="命令">
          <el-input v-model="mcpForm.command" placeholder="命令路径" />
        </el-form-item>
        <el-form-item v-if="mcpForm.transport !== 'stdio'" label="URL">
          <el-input v-model="mcpForm.url" placeholder="http://localhost:3000" />
        </el-form-item>
        <el-form-item label="超时">
          <el-slider v-model="mcpForm.timeout" :min="5" :max="120" show-input />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showAddMCP = false">取消</el-button>
        <el-button type="primary" @click="addMCPServer">添加</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import axios from 'axios'

interface Tool {
  name: string
  description: string
  source: string
}

interface MCPServer {
  id: string
  name: string
  transport: string
  url?: string
  connected: boolean
  toolsCount?: number
}

const builtinTools = ref<Tool[]>([])
const mcpServers = ref<MCPServer[]>([])
const showAddMCP = ref(false)

const mcpForm = reactive({
  name: '',
  transport: 'stdio',
  command: '',
  url: '',
  timeout: 30,
})

// 加载工具
const loadTools = async () => {
  try {
    const { data } = await axios.get('/api/tools')
    builtinTools.value = data
  } catch (error) {
    ElMessage.error('加载工具失败')
  }
}

// 添加MCP服务器
const addMCPServer = async () => {
  // 这里应该调用API
  mcpServers.value.push({
    id: Date.now().toString(),
    name: mcpForm.name,
    transport: mcpForm.transport,
    url: mcpForm.url,
    connected: false,
    toolsCount: 0,
  })
  
  showAddMCP.value = false
  ElMessage.success('添加成功')
  
  // 重置表单
  Object.assign(mcpForm, {
    name: '',
    transport: 'stdio',
    command: '',
    url: '',
    timeout: 30,
  })
}

// 测试连接
const testConnection = async (server: MCPServer) => {
  ElMessage.info(`正在测试 ${server.name}...`)
  // 这里应该调用API
  setTimeout(() => {
    server.connected = true
    ElMessage.success('连接成功')
  }, 1000)
}

// 删除服务器
const removeServer = (server: MCPServer) => {
  const index = mcpServers.value.findIndex(s => s.id === server.id)
  if (index > -1) {
    mcpServers.value.splice(index, 1)
    ElMessage.success('已删除')
  }
}

onMounted(() => {
  loadTools()
})
</script>

<style scoped>
.tools-config {
  padding: 20px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.mcp-server-card {
  margin-bottom: 15px;
}

.server-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.server-info {
  margin-bottom: 10px;
}

.server-info p {
  margin: 5px 0;
  color: #606266;
}

.server-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}
</style>
