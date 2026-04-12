<template>
  <div class="skills-manager">
    <el-row :gutter="20">
      <el-col :span="6">
        <el-card>
          <template #header>
            <div class="card-header">
              <span>Skills分类</span>
              <el-button type="primary" size="small" @click="showCreateDialog = true">
                <el-icon><Plus /></el-icon>
              </el-button>
            </div>
          </template>
          
          <el-tree
            :data="skillTree"
            :props="treeProps"
            @node-click="handleNodeClick"
            highlight-current
          >
            <template #default="{ node, data }">
              <span class="tree-node">
                <el-icon v-if="data.is_category"><Folder /></el-icon>
                <el-icon v-else><Document /></el-icon>
                <span>{{ node.label }}</span>
              </span>
            </template>
          </el-tree>
        </el-card>
      </el-col>

      <el-col :span="18">
        <el-card v-if="currentSkill">
          <template #header>
            <div class="card-header">
              <span>{{ currentSkill.name }}</span>
              <div>
                <el-button @click="resetForm">重置</el-button>
                <el-button type="primary" @click="saveSkill">保存</el-button>
              </div>
            </div>
          </template>

          <el-form :model="skillForm" label-width="100px">
            <el-form-item label="名称">
              <el-input v-model="skillForm.name" disabled />
            </el-form-item>

            <el-form-item label="分类">
              <el-input v-model="skillForm.category" disabled />
            </el-form-item>

            <el-form-item label="描述">
              <el-input v-model="skillForm.description" type="textarea" :rows="2" />
            </el-form-item>

            <el-form-item label="使用场景">
              <el-input v-model="skillForm.when_to_use" type="textarea" :rows="2" />
            </el-form-item>

            <el-form-item label="标签">
              <el-select
                v-model="skillForm.tags"
                multiple
                filterable
                allow-create
                style="width: 100%"
              >
                <el-option
                  v-for="tag in skillForm.tags"
                  :key="tag"
                  :label="tag"
                  :value="tag"
                />
              </el-select>
            </el-form-item>

            <el-form-item label="优先级">
              <el-slider v-model="skillForm.priority" :min="0" :max="10" show-input />
            </el-form-item>

            <el-form-item label="内容">
              <el-input
                v-model="skillForm.content"
                type="textarea"
                :rows="15"
                placeholder="输入Skill详细内容..."
              />
            </el-form-item>
          </el-form>
        </el-card>

        <el-empty v-else description="请选择Skill或分类" />
      </el-col>
    </el-row>

    <!-- 创建Skill对话框 -->
    <el-dialog v-model="showCreateDialog" title="创建新Skill" width="500px">
      <el-form :model="createForm" label-width="80px">
        <el-form-item label="名称">
          <el-input v-model="createForm.name" placeholder="skill名称" />
        </el-form-item>
        <el-form-item label="分类">
          <el-cascader
            v-model="createForm.category"
            :options="categoryOptions"
            :props="{ value: 'path', label: 'name' }"
            style="width: 100%"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreateDialog = false">取消</el-button>
        <el-button type="primary" @click="createSkill">创建</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import axios from 'axios'

interface SkillNode {
  name: string
  path: string
  is_category: boolean
  children?: SkillNode[]
  skill?: any
}

const skillTree = ref<SkillNode[]>([])
const categoryOptions = ref<any[]>([])
const currentSkill = ref<any>(null)
const showCreateDialog = ref(false)

const treeProps = {
  label: 'name',
  children: 'children',
}

const skillForm = reactive({
  name: '',
  category: '',
  description: '',
  when_to_use: '',
  content: '',
  tags: [] as string[],
  priority: 0,
})

const createForm = reactive({
  name: '',
  category: [],
})

// 加载Skills树
const loadSkills = async () => {
  try {
    const { data } = await axios.get('/api/skills')
    if (data.tree) {
      skillTree.value = data.tree.children || []
      categoryOptions.value = buildCategoryOptions(data.tree)
    }
  } catch (error) {
    ElMessage.error('加载Skills失败')
  }
}

// 构建分类选项
const buildCategoryOptions = (node: SkillNode): any[] => {
  if (!node.children) return []
  
  return node.children
    .filter(child => child.is_category)
    .map(child => ({
      name: child.name,
      path: child.path,
      children: buildCategoryOptions(child),
    }))
}

// 节点点击
const handleNodeClick = (data: SkillNode) => {
  if (!data.is_category && data.skill) {
    currentSkill.value = data.skill
    Object.assign(skillForm, data.skill)
  }
}

// 保存Skill
const saveSkill = async () => {
  try {
    await axios.post('/api/skills', skillForm)
    ElMessage.success('保存成功')
    loadSkills()
  } catch (error) {
    ElMessage.error('保存失败')
  }
}

// 重置表单
const resetForm = () => {
  if (currentSkill.value) {
    Object.assign(skillForm, currentSkill.value)
  }
}

// 创建Skill
const createSkill = async () => {
  const category = createForm.category.join('/')
  try {
    await axios.post('/api/skills', {
      name: createForm.name,
      category,
      description: '',
      content: '',
      tags: [],
      priority: 0,
    })
    ElMessage.success('创建成功')
    showCreateDialog.value = false
    loadSkills()
  } catch (error) {
    ElMessage.error('创建失败')
  }
}

onMounted(() => {
  loadSkills()
})
</script>

<style scoped>
.skills-manager {
  padding: 20px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.tree-node {
  display: flex;
  align-items: center;
  gap: 5px;
}

.tree-node .el-icon {
  margin-right: 5px;
}
</style>
