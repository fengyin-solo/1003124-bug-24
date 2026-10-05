<template>
  <section class="page" data-module="emergencydrill">
    <header class="page-head">
      <div>
        <h2>应急演练管理</h2>
        <p class="page-desc">
          演练评估为空时按「暂无评估」保存草稿；复盘后结论锁定、改进措施仍可补充；未复盘不许归档。
        </p>
      </div>
      <div class="page-actions">
        <button class="btn" type="button" @click="simulateFailure">模拟下一次落库失败</button>
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
      <label class="filter-item">
        <span>演练编号</span>
        <input v-model="keyword" placeholder="按演练编号检索" />
      </label>
      <label class="filter-item">
        <span>演练状态</span>
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
          <th>复盘结论</th>
          <th>可执行操作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">{{ displayValue(row, column) }}</td>
          <td class="conclusion-cell">{{ row['复盘结论'] || '—' }}</td>
          <td class="row-actions">
            <button
              v-if="canAdvance(row, '组织演练')"
              class="link"
              type="button"
              @click="runAction('组织演练', row)"
            >组织演练</button>
            <button
              v-if="canAdvance(row, '完成演练')"
              class="link"
              type="button"
              @click="runAction('完成演练', row)"
            >完成演练</button>
            <button
              v-if="canAdvance(row, '复盘总结')"
              class="link"
              type="button"
              @click="openReview(row)"
            >复盘总结</button>
            <button
              class="link"
              type="button"
              :disabled="row.status !== '已复盘'"
              :title="row.status === '已复盘' ? '归档演练' : '尚未复盘，不能归档'"
              @click="runAction('归档', row)"
            >归档</button>
            <button class="link" type="button" @click="openDraft(row)">
              {{ row.status === '已归档' ? '补充改进措施' : '评估/改进措施' }}
            </button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 2" class="empty-state">暂无符合条件的演练记录</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条应急演练记录</span>
      <span v-if="bannerMessage" :class="bannerType === 'error' ? 'error-text' : 'success-text'">{{ bannerMessage }}</span>
    </footer>

    <!-- 保存评估与改进措施（草稿，不推进状态；归档后仍可补充措施） -->
    <div v-if="draftOpen" class="modal-mask" @click.self="closeDraft">
      <div class="modal">
        <h3>{{ draftForm.status === '已归档' ? '补充改进措施' : '填写演练评估与改进措施' }}</h3>
        <p class="modal-sub">
          演练：{{ draftForm['演练编号'] }} · {{ draftForm['演练主题'] }} · 当前状态：{{ draftForm.status }}
        </p>

        <label class="form-item">
          <span>演练评估</span>
          <textarea
            v-model="draftForm['演练评估']"
            rows="3"
            placeholder="不填将按「暂无评估」保存"
            :disabled="assessmentLocked"
          ></textarea>
          <em v-if="assessmentLocked" class="hint">演练已复盘，评估结论已锁定，仅可补充改进措施。</em>
          <em v-else class="hint">留空保存时系统自动记为「暂无评估」，可先存草稿。</em>
        </label>

        <label class="form-item">
          <span>改进措施（仅保留最新一版{{ measuresVersionHint }}）</span>
          <textarea v-model="draftForm['改进措施']" rows="4" placeholder="可反复保存，后一次覆盖前一次"></textarea>
        </label>

        <div v-if="draftError" class="inline-error" role="alert">
          <span>{{ draftError }}</span>
          <button v-if="draftErrorRetryable" class="btn tiny primary" type="button" @click="submitDraft">重试</button>
        </div>

        <div class="modal-actions">
          <button class="btn ghost" type="button" @click="closeDraft">关闭（内容暂留本次弹窗）</button>
          <button class="btn primary" type="button" :disabled="draftSaving" @click="submitDraft">
            {{ draftSaving ? '保存中…' : '保存' }}
          </button>
        </div>
      </div>
    </div>

    <!-- 复盘总结：结论必填，评估可空（按暂无评估），措施可一并填 -->
    <div v-if="reviewOpen" class="modal-mask" @click.self="closeReview">
      <div class="modal">
        <h3>复盘总结</h3>
        <p class="modal-sub">演练：{{ reviewForm['演练编号'] }} · {{ reviewForm['演练主题'] }}</p>

        <label class="form-item">
          <span>演练评估</span>
          <textarea v-model="reviewForm['演练评估']" rows="3" placeholder="不填将按「暂无评估」记录"></textarea>
        </label>

        <label class="form-item">
          <span>改进措施（可选，只留最新一版）</span>
          <textarea v-model="reviewForm['改进措施']" rows="4"></textarea>
        </label>

        <label class="form-item">
          <span>复盘结论（必填，复盘后锁定并同步到隐患整改跟踪）</span>
          <textarea v-model="reviewForm['复盘结论']" rows="4" placeholder="例如：某区域某设施存在隐患，需某日之前完成整改"></textarea>
        </label>

        <div v-if="reviewError" class="inline-error" role="alert">
          <span>{{ reviewError }}</span>
          <button v-if="reviewErrorRetryable" class="btn tiny primary" type="button" @click="submitReview">重试</button>
        </div>

        <div class="modal-actions">
          <button class="btn ghost" type="button" @click="closeReview">取消</button>
          <button class="btn primary" type="button" :disabled="reviewSaving" @click="submitReview">
            {{ reviewSaving ? '提交中…' : '完成复盘' }}
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
type FormState = Row & { status?: string }

const ENDPOINT = '/api/emergencydrill'
const columns = ["演练编号", "演练主题", "演练区域", "参演人数", "演练日期", "演练评估", "改进措施", "演练状态"]
const statuses = ["待组织", "已组织", "已完成", "已复盘", "已归档"]
const NEXT_ACTION: Record<string, string> = {
  待组织: '组织演练',
  已组织: '完成演练',
  已完成: '复盘总结',
}

const rows = ref<Row[]>([])
const total = ref(0)
const keyword = ref('')
const statusFilter = ref('')
const bannerMessage = ref('')
const bannerType = ref<'success' | 'error'>('success')

const stats = computed(() => [
  { label: '待组织/进行中', value: rows.value.filter((r) => ['待组织', '已组织', '已完成'].includes(String(r.status))).length },
  { label: '已复盘', value: rows.value.filter((r) => r.status === '已复盘').length },
  { label: '已归档', value: rows.value.filter((r) => r.status === '已归档').length },
])

function displayValue(row: Row, column: string): string {
  if (column === '演练状态') return String(row.status ?? '—')
  const value = row[column]
  return value === null || value === undefined || value === '' ? '—' : String(value)
}

function canAdvance(row: Row, action: string): boolean {
  return NEXT_ACTION[String(row.status)] === action
}

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
    if (!response.ok) throw new Error('演练记录列表读取失败')
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    bannerType.value = 'error'
    bannerMessage.value = error instanceof Error ? error.message : '应急演练列表读取失败'
  }
}

// 把「内容缺失（不可重试）」和「落库失败（可重试）」分开解析。
// body 是已经解析过的响应 JSON：503 时 detail 为对象，业务拒绝时为 ActionResult。
interface SubmitFailure {
  message: string
  retryable: boolean
}

function readFailure(response: Response, body: any, fallback: string): SubmitFailure {
  if (response.status === 503 && body?.detail && typeof body.detail === 'object') {
    return {
      message: body.detail.message || fallback,
      retryable: Boolean(body.detail.retryable),
    }
  }
  if (typeof body?.detail === 'string') return { message: body.detail, retryable: false }
  if (body?.message) return { message: body.message, retryable: Boolean(body.retryable) }
  return { message: fallback, retryable: response.status >= 500 }
}

async function runAction(action: string, row: Row) {
  bannerMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action } }),
    })
    const payload = await response.json()
    if (!response.ok || !payload.ok) {
      bannerType.value = 'error'
      bannerMessage.value = payload?.message || `「${action}」未生效`
      return
    }
    bannerType.value = 'success'
    bannerMessage.value = payload.message
    await reload()
  } catch (error) {
    bannerType.value = 'error'
    bannerMessage.value = error instanceof Error ? error.message : '操作失败，请重试'
  }
}

// ---- 评估 / 改进措施草稿 ----
const draftOpen = ref(false)
const draftSaving = ref(false)
const draftError = ref('')
const draftErrorRetryable = ref(false)
const draftForm = ref<FormState>({})
const editingId = ref<number | null>(null)

const assessmentLocked = computed(() => ['已复盘', '已归档'].includes(String(draftForm.value.status)))
const measuresVersionHint = computed(() => {
  const version = Number(draftForm.value['改进措施版本'] || 0)
  return version > 0 ? `，当前第 ${version} 版` : ''
})

function openDraft(row: Row) {
  editingId.value = Number(row.id)
  // 深拷贝一份到本地：保存失败时重试不清空，关闭列表刷新也不影响已输入内容。
  draftForm.value = { ...row }
  if (!draftForm.value['演练评估']) draftForm.value['演练评估'] = ''
  if (!draftForm.value['改进措施']) draftForm.value['改进措施'] = ''
  draftError.value = ''
  draftErrorRetryable.value = false
  draftOpen.value = true
}

function closeDraft() {
  draftOpen.value = false
}

async function submitDraft() {
  if (editingId.value === null) return
  draftSaving.value = true
  draftError.value = ''
  const payload: Record<string, string> = {
    '改进措施': String(draftForm.value['改进措施'] ?? ''),
  }
  if (!assessmentLocked.value) payload['演练评估'] = String(draftForm.value['演练评估'] ?? '')
  try {
    const response = await request(`${ENDPOINT}/${editingId.value}/draft`, {
      method: 'PUT',
      body: JSON.stringify({ values: payload }),
    })
    const body = await response.json()
    if (!response.ok || !body.ok) {
      const failure = readFailure(response, body, '保存失败，请重试')
      draftError.value = failure.message
      draftErrorRetryable.value = failure.retryable
      return
    }
    bannerType.value = 'success'
    bannerMessage.value = body.message || '内容已保存'
    draftOpen.value = false
    await reload()
  } catch (error) {
    // 网络层失败同样可重试，表单内容原样保留。
    draftError.value = error instanceof Error ? error.message : '保存失败，请重试'
    draftErrorRetryable.value = true
  } finally {
    draftSaving.value = false
  }
}

// ---- 复盘总结 ----
const reviewOpen = ref(false)
const reviewSaving = ref(false)
const reviewError = ref('')
const reviewErrorRetryable = ref(false)
const reviewForm = ref<FormState>({})
const reviewId = ref<number | null>(null)

function openReview(row: Row) {
  reviewId.value = Number(row.id)
  reviewForm.value = { ...row }
  if (!reviewForm.value['演练评估'] || reviewForm.value['演练评估'] === '暂无评估') {
    reviewForm.value['演练评估'] = ''
  }
  if (!reviewForm.value['改进措施']) reviewForm.value['改进措施'] = ''
  reviewForm.value['复盘结论'] = ''
  reviewError.value = ''
  reviewErrorRetryable.value = false
  reviewOpen.value = true
}

function closeReview() {
  reviewOpen.value = false
}

async function submitReview() {
  if (reviewId.value === null) return
  const conclusion = String(reviewForm.value['复盘结论'] ?? '').trim()
  if (!conclusion) {
    // 内容缺失：本地直接拦，已填内容一律保留。
    reviewError.value = '缺少复盘结论，不能完成复盘；请填写复盘结论后再提交（已填内容不会清空）'
    reviewErrorRetryable.value = false
    return
  }
  reviewSaving.value = true
  reviewError.value = ''
  try {
    const response = await request(`${ENDPOINT}/${reviewId.value}/actions`, {
      method: 'POST',
      body: JSON.stringify({
        values: {
          action: '复盘总结',
          '演练评估': String(reviewForm.value['演练评估'] ?? ''),
          '改进措施': String(reviewForm.value['改进措施'] ?? ''),
          '复盘结论': conclusion,
        },
      }),
    })
    const body = await response.json()
    if (!response.ok || !body.ok) {
      const failure = readFailure(response, body, '复盘提交失败，请重试')
      reviewError.value = failure.message
      reviewErrorRetryable.value = failure.retryable
      return
    }
    bannerType.value = 'success'
    bannerMessage.value = body.message || '演练已复盘'
    reviewOpen.value = false
    await reload()
  } catch (error) {
    reviewError.value = error instanceof Error ? error.message : '复盘提交失败，请重试'
    reviewErrorRetryable.value = true
  } finally {
    reviewSaving.value = false
  }
}

async function simulateFailure() {
  try {
    await request(`${ENDPOINT}/debug/fail-next-write`, {
      method: 'POST',
      body: JSON.stringify({ values: { times: 1 } }),
    })
    bannerType.value = 'success'
    bannerMessage.value = '已注入故障：下一次保存/动作将返回落库失败，可观察提示与重试行为'
  } catch {
    bannerType.value = 'error'
    bannerMessage.value = '故障注入失败'
  }
}

onMounted(reload)
</script>
