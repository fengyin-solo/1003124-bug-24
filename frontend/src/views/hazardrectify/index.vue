<template>
  <section class="page" data-module="hazardrectify">
    <header class="page-head">
      <div>
        <h2>隐患整改跟踪</h2>
        <p class="page-desc">
          待办由演练复盘结论自动同步，「整改事项」实时引用演练复盘结论，两边永远是同一份；这里只维护整改进度。
        </p>
      </div>
      <div class="page-actions">
        <button class="btn" type="button" @click="exportRows">导出整改跟踪清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label class="filter-item">
        <span>关键字</span>
        <input v-model="keyword" placeholder="按跟踪编号或演练编号检索" />
      </label>
      <label class="filter-item">
        <span>完成情况</span>
        <select v-model="statusFilter">
          <option value="">全部</option>
          <option v-for="s in statuses" :key="s" :value="s">{{ s }}</option>
        </select>
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>来源</th>
          <th>操作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">{{ row[column] || '—' }}</td>
          <td>{{ row['来源'] || '复盘同步' }}</td>
          <td class="row-actions">
            <button class="link" type="button" @click="openEdit(row)">更新进度</button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 2" class="empty-state">
            暂无整改待办；演练完成复盘后，复盘结论会自动同步到这里
          </td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条整改待办</span>
      <span v-if="bannerMessage" :class="bannerType === 'error' ? 'error-text' : 'success-text'">{{ bannerMessage }}</span>
    </footer>

    <div v-if="editOpen" class="modal-mask" @click.self="closeEdit">
      <div class="modal">
        <h3>更新整改进度</h3>
        <p class="modal-sub">
          {{ editForm['跟踪编号'] }} · 来源演练 {{ editForm['演练编号'] }}（{{ editForm['演练日期'] }}）
        </p>

        <label class="form-item">
          <span>整改事项（引自演练复盘结论，只读）</span>
          <textarea :value="editForm['整改事项']" rows="4" readonly disabled></textarea>
        </label>

        <label class="form-item">
          <span>责任人</span>
          <input v-model="editForm['责任人']" placeholder="请填写责任人" />
        </label>

        <label class="form-item">
          <span>整改期限</span>
          <input v-model="editForm['期限']" placeholder="如 2026-10-20" />
        </label>

        <label class="form-item">
          <span>完成情况</span>
          <select v-model="editForm['完成情况']">
            <option v-for="s in statuses" :key="s" :value="s">{{ s }}</option>
          </select>
        </label>

        <div v-if="editError" class="inline-error" role="alert">
          <span>{{ editError }}</span>
          <button class="btn tiny primary" type="button" @click="submitEdit">重试</button>
        </div>

        <div class="modal-actions">
          <button class="btn ghost" type="button" @click="closeEdit">取消</button>
          <button class="btn primary" type="button" :disabled="saving" @click="submitEdit">
            {{ saving ? '保存中…' : '保存进度' }}
          </button>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>

const ENDPOINT = '/api/hazardrectify'
const columns = ["跟踪编号", "演练编号", "演练主题", "演练日期", "整改事项", "责任人", "期限", "完成情况"]
const statuses = ["待整改", "整改中", "已完成"]

const rows = ref<Row[]>([])
const total = ref(0)
const keyword = ref('')
const statusFilter = ref('')
const bannerMessage = ref('')
const bannerType = ref<'success' | 'error'>('success')

const stats = computed(() => [
  { label: '待整改', value: rows.value.filter((r) => r['完成情况'] === '待整改').length },
  { label: '整改中', value: rows.value.filter((r) => r['完成情况'] === '整改中').length },
  { label: '已完成', value: rows.value.filter((r) => r['完成情况'] === '已完成').length },
])

function resetFilters() {
  keyword.value = ''
  statusFilter.value = ''
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

async function reload() {
  bannerMessage.value = ''
  const query = new URLSearchParams()
  if (keyword.value) query.set('keyword', keyword.value)
  if (statusFilter.value) query.set('status', statusFilter.value)
  try {
    const response = await request(`${ENDPOINT}?${query.toString()}`)
    if (!response.ok) throw new Error('整改跟踪列表读取失败')
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    bannerType.value = 'error'
    bannerMessage.value = error instanceof Error ? error.message : '整改跟踪列表读取失败'
  }
}

const editOpen = ref(false)
const saving = ref(false)
const editError = ref('')
const editForm = ref<Row>({})
const editingId = ref<number | null>(null)

function openEdit(row: Row) {
  editingId.value = Number(row.id)
  editForm.value = { ...row }
  editError.value = ''
  editOpen.value = true
}

function closeEdit() {
  editOpen.value = false
}

async function submitEdit() {
  if (editingId.value === null) return
  saving.value = true
  editError.value = ''
  try {
    const response = await request(`${ENDPOINT}/${editingId.value}/actions`, {
      method: 'POST',
      body: JSON.stringify({
        values: {
          '责任人': String(editForm.value['责任人'] ?? ''),
          '期限': String(editForm.value['期限'] ?? ''),
          '完成情况': String(editForm.value['完成情况'] ?? '待整改'),
        },
      }),
    })
    const body = await response.json()
    if (!response.ok || !body.ok) {
      editError.value = body?.message || body?.detail || '进度保存失败'
      return
    }
    bannerType.value = 'success'
    bannerMessage.value = body.message || '整改进度已更新'
    editOpen.value = false
    await reload()
  } catch (error) {
    editError.value = error instanceof Error ? error.message : '进度保存失败，请重试'
  } finally {
    saving.value = false
  }
}

onMounted(reload)
</script>
