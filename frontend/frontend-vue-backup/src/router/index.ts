import { createRouter, createWebHistory } from 'vue-router'
import Dashboard from '../views/Dashboard.vue'
import AgentConfig from '../views/AgentConfig.vue'
import SkillsManager from '../views/SkillsManager.vue'
import ToolsConfig from '../views/ToolsConfig.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      name: 'Dashboard',
      component: Dashboard,
      meta: { title: '任务调度' },
    },
    {
      path: '/agents',
      name: 'AgentConfig',
      component: AgentConfig,
      meta: { title: 'Agent配置' },
    },
    {
      path: '/skills',
      name: 'SkillsManager',
      component: SkillsManager,
      meta: { title: 'Skills管理' },
    },
    {
      path: '/tools',
      name: 'ToolsConfig',
      component: ToolsConfig,
      meta: { title: '工具配置' },
    },
  ],
})

export default router
