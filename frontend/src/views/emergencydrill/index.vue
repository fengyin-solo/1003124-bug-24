<template>
  <section class="page" data-module="emergencydrill">
    <header class="page-head">
      <div>
        <h2>应急演练管理</h2>
        <p class="page-desc">维护演练记录，围绕演练编号、演练主题、演练区域、参演人数做登记、筛选与状态流转。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记演练记录</button>
        <button class="btn" type="button" @click="exportRows">导出应急演练清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label v-for="field in filterFields" :key="field" class="filter-item">
        <span>{{ field }}</span>
        <input v-model="filters[field]" :placeholder="`按${field}检索`" />
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">
            <template v-if="column === '演练评估'">{{ displayEvaluation(row) }}</template>
            <template v-else>{{ row[column] ?? '—' }}</template>
          </td>
          <td class="row-actions">
            <button
              v-for="action in actions"
              :key="action"
              class="link"
              type="button"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
            <button class="link" type="button" @click="openImprovement(row)">改进措施</button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无应急演练数据，可先登记演练记录</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条应急演练记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>

    <div v-if="improvementRow" class="modal-mask" @click.self="closeImprovement">
      <div class="modal">
        <h3>填写改进措施 · {{ improvementRow['演练编号'] }}</h3>
        <p class="modal-desc">
          当前状态：{{ improvementRow['status'] }}；改进措施只保留最新一版。
          <template v-if="isArchived">演练已归档，复盘结论（演练评估）不可改动，只能补充改进措施。</template>
          <template v-else>演练评估为空时将记为「暂无评估」，改进措施先存为草稿。</template>
        </p>
        <label class="form-item">
          <span>演练评估（复盘结论）</span>
          <textarea
            v-model="improvementForm['演练评估']"
            rows="3"
            :disabled="isArchived"
            :placeholder="isArchived ? '已归档，复盘结论不可改动' : '留空则记为暂无评估并存为草稿'"
          ></textarea>
        </label>
        <label class="form-item">
          <span>改进措施</span>
          <textarea v-model="improvementForm['改进措施']" rows="4" placeholder="必填，保存后覆盖上一版"></textarea>
        </label>
        <p v-if="improvementError" class="error-text">保存失败：{{ improvementError }}</p>
        <div class="modal-actions">
          <button class="btn ghost" type="button" @click="closeImprovement">取消</button>
          <button v-if="improvementError" class="btn" type="button" :disabled="saving" @click="saveImprovement">
            重试
          </button>
          <button class="btn primary" type="button" :disabled="saving" @click="saveImprovement">
            {{ saving ? '保存中…' : '保存改进措施' }}
          </button>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>

const ENDPOINT = '/api/emergencydrill'
const columns = ["演练编号", "演练主题", "演练区域", "参演人数", "演练日期", "演练评估", "改进措施", "改进措施状态", "演练状态"]
const actions = ["组织演练", "完成演练", "复盘总结", "归档"]
const statuses = ["待组织", "已组织", "已完成", "已复盘", "已归档"]
const stats = [{"label": "待组织演练", "value": 0}, {"label": "已完成演练", "value": 0}, {"label": "已复盘演练", "value": 0}]

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const filters = ref<Record<string, string>>({})
const filterFields = columns.slice(0, 3)

const improvementRow = ref<Row | null>(null)
const improvementForm = reactive<Record<string, string>>({ '演练评估': '', '改进措施': '' })
const improvementError = ref('')
const saving = ref(false)
const isArchived = computed(() => improvementRow.value?.['status'] === '已归档')

function displayEvaluation(row: Row) {
  const value = String(row['演练评估'] ?? '').trim()
  return value || '暂无评估'
}

function resetFilters() {
  filters.value = {}
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  errorMessage.value = '演练记录登记入口尚未接入审批流'
}

async function readPayload(response: Response): Promise<{ ok: boolean; message: string }> {
  try {
    const payload = await response.json()
    return { ok: response.ok && payload?.ok !== false, message: String(payload?.message ?? payload?.detail ?? '') }
  } catch {
    return { ok: false, message: `接口返回 ${response.status}，响应内容无法解析` }
  }
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action } }),
    })
    const result = await readPayload(response)
    if (!result.ok) {
      errorMessage.value = result.message || `「${action}」未生效`
      return
    }
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '应急演练操作失败'
  }
}

function openImprovement(row: Row) {
  improvementRow.value = row
  improvementForm['演练评估'] = String(row['演练评估'] ?? '')
  improvementForm['改进措施'] = String(row['改进措施'] ?? '')
  improvementError.value = ''
}

function closeImprovement() {
  if (saving.value) return
  improvementRow.value = null
  improvementError.value = ''
}

async function saveImprovement() {
  if (!improvementRow.value || saving.value) return
  saving.value = true
  improvementError.value = ''
  try {
    const response = await request(`${ENDPOINT}/${improvementRow.value.id}/improvement`, {
      method: 'POST',
      body: JSON.stringify({ values: { ...improvementForm } }),
    })
    const result = await readPayload(response)
    if (!result.ok) {
      // 失败时保留已填内容，给出可读原因与重试入口
      improvementError.value = result.message || '改进措施保存失败，请重试'
      return
    }
    improvementRow.value = null
    await reload()
  } catch (error) {
    improvementError.value = error instanceof Error ? error.message : '改进措施保存失败，请重试'
  } finally {
    saving.value = false
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams(filters.value as Record<string, string>).toString()
  try {
    const response = await request(`${ENDPOINT}?${query}`)
    if (!response.ok) {
      throw new Error('演练记录列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '应急演练列表读取失败'
  }
}

onMounted(reload)
</script>
