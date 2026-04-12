<template>
  <el-container class="app-container">
    <el-aside width="200px" class="sidebar">
      <div class="logo">
        <el-icon :size="32"><Connection /></el-icon>
        <span>Nexus</span>
      </div>
      <el-menu
        :default-active="$route.path"
        router
        class="nav-menu"
        background-color="#304156"
        text-color="#bfcbd9"
        active-text-color="#409EFF"
      >
        <el-menu-item index="/">
          <el-icon><Odometer /></el-icon>
          <span>任务调度</span>
        </el-menu-item>
        <el-menu-item index="/agents">
          <el-icon><UserFilled /></el-icon>
          <span>Agent配置</span>
        </el-menu-item>
        <el-menu-item index="/skills">
          <el-icon><Collection /></el-icon>
          <span>Skills管理</span>
        </el-menu-item>
        <el-menu-item index="/tools">
          <el-icon><Tools /></el-icon>
          <span>工具配置</span>
        </el-menu-item>
      </el-menu>
    </el-aside>
    <el-container>
      <el-header class="header">
        <div class="header-title">{{ $route.meta.title || 'Nexus' }}</div>
        <div class="header-actions">
          <el-button type="primary" @click="showNewTaskDialog = true">
            <el-icon><Plus /></el-icon>新建任务
          </el-button>
        </div>
      </el-header>
      <el-main class="main-content">
        <router-view />
      </el-main>
    </el-container>
  </el-container>

  <!-- 新建任务对话框 -->
  <el-dialog
    v-model="showNewTaskDialog"
    title="新建任务"
    width="600px"
  >
    <el-form :model="newTaskForm" label-width="100px">
      <el-form-item label="任务目标">
        <el-input
          v-model="newTaskForm.goal"
          type="textarea"
          :rows="3"
          placeholder="描述任务目标..."
        />
      </el-form-item>
      <el-form-item label="上下文">
        <el-input
          v-model="newTaskForm.context"
          type="textarea"
          :rows="2"
          placeholder="任务背景信息（可选）"
        />
      </el-form-item>
      <el-form-item label="最大轮数">
        <el-slider v-model="newTaskForm.maxRounds" :min="5" :max="50" show-input />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="showNewTaskDialog = false">取消</el-button>
      <el-button type="primary" @click="submitTask">开始执行</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'

const router = useRouter()
const showNewTaskDialog = ref(false)
const newTaskForm = ref({
  goal: '',
  context: '',
  maxRounds: 20,
})

const submitTask = () => {
  if (!newTaskForm.value.goal.trim()) {
    ElMessage.warning('请输入任务目标')
    return
  }
  
  // 跳转到任务页面并携带参数
  router.push({
    path: '/',
    query: {
      goal: newTaskForm.value.goal,
      context: newTaskForm.value.context,
      maxRounds: newTaskForm.value.maxRounds.toString(),
    },
  })
  
  showNewTaskDialog.value = false
  newTaskForm.value = { goal: '', context: '', maxRounds: 20 }
}
</script>

<style scoped>
.app-container {
  height: 100vh;
}

.sidebar {
  background-color: #304156;
  color: #fff;
}

.logo {
  height: 60px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
  font-weight: bold;
  border-bottom: 1px solid #1f2d3d;
}

.logo .el-icon {
  margin-right: 10px;
  color: #409EFF;
}

.nav-menu {
  border-right: none;
}

.header {
  background-color: #fff;
  box-shadow: 0 1px 4px rgba(0, 21, 41, 0.08);
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.header-title {
  font-size: 18px;
  font-weight: 500;
}

.main-content {
  background-color: #f0f2f5;
  padding: 20px;
  overflow-y: auto;
}
</style>

<style>
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
}
</style>
