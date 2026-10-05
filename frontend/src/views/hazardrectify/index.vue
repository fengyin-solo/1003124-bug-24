<template>
  <section class="page" data-module="hazardrectify">
    <header class="page-head">
      <div>
        <h2>隐患整改跟踪</h2>
        <p class="page-desc">待办清单来自应急演练的复盘结论，与应急演练模块读的是同一份数据；存量演练按演练日期回填。</p>
      </div>
    </header>

    <form class="filter-bar" @submit.prevent="reload">
      <label class="filter-item">
        <span>演练编号</span>
        <input v-model="filters['演练编号']" placeholder="按演练编号检索" />
      </label>
      <label class="filter-item">
        <span>整改状态</span>
        <select v-model="filters['整改状态']">
          <option value="">全部</option>
          <option v-for="status in statuses" :key="status" :value="status">{{ status }}</option>
        </select>
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
          <td v-for="column in columns" :key="column">{{ row[column] ?? '—' }}</td>
          <td class="row-actions">
            <button
              v-for="action in availableActions(row)"
              :key="action"
              class="link"
              type="button"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
            <span v-if="!availableActions(row).length" class="muted-text">已闭环</span>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无隐患整改待办，演练复盘结论形成后会自动进入清单</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条整改待办</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>

const ENDPOINT = '/api/hazardrectify'
const columns = ["演练编号", "演练主题", "演练区域", "演练日期", "复盘结论", "改进措施", "整改状态"]
const statuses = ["待整改", "整改中", "已闭环"]
const ACTION_BY_STATUS: Record<string, string[]> = {
  '待整改': ['开始整改'],
  '整改中': ['整改闭环'],
}

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const filters = ref<Record<string, string>>({})

function availableActions(row: Row) {
  return ACTION_BY_STATUS[String(row['整改状态'] ?? '')] ?? []
}

function resetFilters() {
  filters.value = {}
  void reload()
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/todos/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action } }),
    })
    const payload = await response.json().catch(() => null)
    if (!response.ok || payload?.ok === false) {
      errorMessage.value = String(payload?.message ?? payload?.detail ?? `「${action}」未生效`)
      return
    }
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '隐患整改操作失败'
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams()
  if (filters.value['演练编号']) query.set('keyword', filters.value['演练编号'])
  if (filters.value['整改状态']) query.set('status', filters.value['整改状态'])
  try {
    const response = await request(`${ENDPOINT}/todos?${query.toString()}`)
    if (!response.ok) {
      throw new Error('整改待办清单读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '整改待办清单读取失败'
  }
}

onMounted(reload)
</script>
