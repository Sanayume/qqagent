<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import {
  Blocks,
  ChevronDown,
  ChevronRight,
  CircleHelp,
  Plus,
  RefreshCw,
  Save,
  Search,
  Settings2,
  Shield,
  Trash2,
} from 'lucide-vue-next'

import api from '../api'
import InlineNotice from '../components/InlineNotice.vue'
import ConfirmDialog from '../components/ConfirmDialog.vue'

interface ConfigEffect {
  kind: string
  label: string
  detail: string
}

interface ConfigField {
  key: string
  path?: string
  label: string
  type: string
  help: string
  effect?: ConfigEffect
}

interface ConfigSection {
  key: string
  title: string
  description: string
  fields: ConfigField[]
}

interface FilteredSection extends ConfigSection {
  visibleFields: ConfigField[]
}

interface ConfigSchemaResponse {
  sections: ConfigSection[]
  defaults: Record<string, any>
  values: Record<string, any>
  content: string
  path: string
}

const schema = ref<ConfigSchemaResponse | null>(null)
const values = ref<Record<string, any>>({})
const originalValues = ref<Record<string, any>>({})
const loading = ref(false)
const saving = ref(false)
const searchQuery = ref('')
const yamlPreview = ref('')
const collapsedSections = ref<Record<string, boolean>>({})
const errorMsg = ref('')
const successMsg = ref('')
const refreshConfirmOpen = ref(false)

const sections = computed(() => schema.value?.sections ?? [])
const hasUnsavedChanges = computed(() => JSON.stringify(values.value) !== JSON.stringify(originalValues.value))

function fieldLookupKey(sectionKey: string, field: ConfigField) {
  const path = field.path ?? field.key
  return path ? `${sectionKey}.${path}` : sectionKey
}

function localizedSectionTitle(section: ConfigSection) {
  const titles: Record<string, string> = {
    admin: '\u7ba1\u7406\u63a7\u5236\u53f0',
    onebot: 'OneBot / NapCat',
    agent: 'Agent \u8fd0\u884c\u65f6',
    session: '\u4f1a\u8bdd\u8def\u7531',
    aggregator: '\u7fa4\u6d88\u606f\u805a\u5408',
    private_aggregator: '\u79c1\u804a\u805a\u5408',
    llm: 'LLM \u4e0e\u56de\u9000\u6a21\u578b',
    embeddings: '\u5411\u91cf Embeddings',
    telegram: 'Telegram \u76d1\u542c',
    observability: '\u53ef\u89c2\u6d4b\u6027',
    integrations: '\u5916\u90e8\u96c6\u6210',
    plugins: '\u63d2\u4ef6\u5f00\u5173',
    tuning: '\u8fd0\u884c\u8c03\u4f18',
    presets: '\u9884\u8bbe\u6a21\u677f',
  }
  return titles[section.key] || section.title
}

function localizedSectionDescription(section: ConfigSection) {
  const descriptions: Record<string, string> = {
    admin: '\u7ba1\u7406\u540e\u53f0\u8d26\u53f7\u3001\u7aef\u53e3\u4e0e\u9274\u6743\u5bc6\u94a5\u3002',
    onebot: 'NapCat / OneBot \u8fde\u63a5\u65b9\u5f0f\u4e0e\u76d1\u542c\u53c2\u6570\u3002',
    agent: '\u673a\u5668\u4eba\u884c\u4e3a\u3001\u9ed8\u8ba4\u9884\u8bbe\u3001\u8bed\u97f3\u6a21\u5f0f\u548c STT \u914d\u7f6e\u3002',
    session: '\u63a7\u5236\u7528\u6237\u548c\u7fa4\u804a\u7684\u4f1a\u8bdd\u9694\u79bb\u65b9\u5f0f\u3002',
    aggregator: '\u7fa4\u6d88\u606f\u805a\u5408\u7a97\u53e3\u3001\u5bc6\u5ea6\u89e6\u53d1\u4e0e\u7b49\u5f85\u7b56\u7565\u3002',
    private_aggregator: '\u79c1\u804a\u6d88\u606f\u805a\u5408\u7b49\u5f85\u7b56\u7565\u3002',
    llm: '\u4e3b\u6a21\u578b\u3001OpenAI \u517c\u5bb9\u63a5\u53e3\u4e0e\u56de\u9000\u6a21\u578b\u5217\u8868\u3002',
    embeddings: '\u77e5\u8bc6\u5e93\u5411\u91cf\u6a21\u578b\u4e0e\u72ec\u7acb Embedding \u63a5\u53e3\u3002',
    telegram: 'Telegram \u767b\u5f55\u3001\u76d1\u63a7\u3001\u805a\u5408\u548c\u8f6c\u53d1\u8bbe\u7f6e\u3002',
    observability: '\u65e5\u5fd7\u7ea7\u522b\u4e0e LangSmith \u8ffd\u8e2a\u914d\u7f6e\u3002',
    integrations: 'Brave Search\u3001OpenClaw \u4e0e Telegram \u4ee3\u7406\u3002',
    plugins: '\u5c55\u793a\u5e76\u4fdd\u5b58\u6240\u6709\u53ef\u914d\u7f6e\u63d2\u4ef6\u5f00\u5173\u3002',
    tuning: '\u7184\u65ad\u3001\u8d85\u65f6\u3001\u77e5\u8bc6\u68c0\u7d22\u4e0e OpenClaw \u8c03\u4f18\u53c2\u6570\u3002',
    presets: '\u5728 config.yaml \u4e2d\u7ef4\u62a4\u9ed8\u8ba4\u53ef\u7528\u7684\u4eba\u8bbe\u6a21\u677f\u3002',
  }
  return descriptions[section.key] || (section.description.includes('?') ? `\u914d\u7f6e\u5206\u7ec4\uff1a${section.key}` : section.description)
}

function localizedFieldHelp(sectionKey: string, field: ConfigField) {
  const raw = field.help || ''
  if (raw && !raw.includes('?')) return raw
  return `\u914d\u7f6e\u9879\uff1a${fieldLookupKey(sectionKey, field)}`
}

function localizedEffectLabel(effect?: ConfigEffect) {
  const labels: Record<string, string> = {
    hot_reload: '\u70ed\u66f4\u65b0',
    next_request: '\u4e0b\u6b21\u8bf7\u6c42\u751f\u6548',
    reconnect: '\u91cd\u8fde\u751f\u6548',
    restart: '\u91cd\u542f\u540e\u751f\u6548',
    relogin: '\u91cd\u65b0\u767b\u5f55',
    new_login: '\u65b0\u767b\u5f55\u751f\u6548',
    stored_only: '\u4ec5\u4fdd\u5b58',
    unknown: '\u672a\u6807\u6ce8',
  }
  return labels[effect?.kind || 'unknown'] || effect?.label || '\u672a\u6807\u6ce8'
}

function localizedEffectDetail(effect?: ConfigEffect) {
  const details: Record<string, string> = {
    hot_reload: '\u4fdd\u5b58\u540e\u7acb\u5373\u751f\u6548\u3002',
    next_request: '\u4e0b\u4e00\u6b21\u5904\u7406\u8bf7\u6c42\u65f6\u751f\u6548\u3002',
    reconnect: '\u9700\u8981\u91cd\u8fde\u76f8\u5173\u8fde\u63a5\u540e\u751f\u6548\u3002',
    restart: '\u9700\u8981\u91cd\u542f\u670d\u52a1\u540e\u751f\u6548\u3002',
    relogin: '\u73b0\u6709\u767b\u5f55\u6001\u4f1a\u5931\u6548\uff0c\u9700\u8981\u91cd\u65b0\u767b\u5f55\u3002',
    new_login: '\u53ea\u5f71\u54cd\u65b0\u7684\u767b\u5f55\u4f1a\u8bdd\u3002',
    stored_only: '\u76ee\u524d\u53ea\u4f1a\u4fdd\u5b58\uff0c\u8fd0\u884c\u65f6\u672a\u5b8c\u5168\u63a5\u7ebf\u3002',
    unknown: '\u8be5\u9879\u7684\u751f\u6548\u65b9\u5f0f\u5c1a\u672a\u5206\u7c7b\u3002',
  }
  return details[effect?.kind || 'unknown'] || effect?.detail || '\u8be5\u9879\u7684\u751f\u6548\u65b9\u5f0f\u5c1a\u672a\u5206\u7c7b\u3002'
}

function deepClone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T
}

function normalizeText(value: unknown) {
  return String(value ?? '').trim().toLowerCase()
}

function ensureSection(sectionKey: string) {
  if (!values.value[sectionKey] || typeof values.value[sectionKey] !== 'object' || Array.isArray(values.value[sectionKey])) {
    values.value[sectionKey] = {}
  }
}

function getByPath(source: Record<string, any> | null | undefined, sectionKey: string, path?: string) {
  const section = source?.[sectionKey]
  if (!path) return section

  const parts = path.split('.')
  let current: any = section
  for (const part of parts) {
    if (current == null) return undefined
    current = current[part]
  }
  return current
}

function setByPath(sectionKey: string, path: string | undefined, newValue: any) {
  ensureSection(sectionKey)
  if (!path) {
    values.value[sectionKey] = newValue
    return
  }

  const parts = path.split('.')
  let current = values.value[sectionKey]
  for (const part of parts.slice(0, -1)) {
    if (!current[part] || typeof current[part] !== 'object' || Array.isArray(current[part])) {
      current[part] = {}
    }
    current = current[part]
  }

  const lastKey = parts[parts.length - 1] as string
  current[lastKey] = newValue
}

function currentValue(sectionKey: string, field: ConfigField) {
  return getByPath(values.value, sectionKey, field.path ?? field.key)
}

function defaultValue(sectionKey: string, field: ConfigField) {
  return getByPath(schema.value?.defaults ?? {}, sectionKey, field.path ?? field.key)
}

function originalValue(sectionKey: string, field: ConfigField) {
  return getByPath(originalValues.value, sectionKey, field.path ?? field.key)
}

function fieldChanged(sectionKey: string, field: ConfigField) {
  return JSON.stringify(currentValue(sectionKey, field)) !== JSON.stringify(defaultValue(sectionKey, field))
}

function fieldDirty(sectionKey: string, field: ConfigField) {
  return JSON.stringify(currentValue(sectionKey, field)) !== JSON.stringify(originalValue(sectionKey, field))
}

function formatValuePreview(value: any) {
  if (value === undefined || value === null || value === '') return '\u9ed8\u8ba4\u503c\u4e3a\u7a7a'
  if (Array.isArray(value)) return value.length ? `\u9ed8\u8ba4\u503c\uff1a${value.join(', ')}` : '\u9ed8\u8ba4\u503c\uff1a[]'
  if (typeof value === 'object') return '\u9ed8\u8ba4\u503c\uff1a\u7ed3\u6784\u5316\u5bf9\u8c61'
  return `\u9ed8\u8ba4\u503c\uff1a${String(value)}`
}

function fieldDefaultText(sectionKey: string, field: ConfigField) {
  return formatValuePreview(defaultValue(sectionKey, field))
}
function updatePrimitive(sectionKey: string, field: ConfigField, rawValue: string) {
  if (field.type === 'int') {
    const parsed = rawValue === '' ? 0 : Number.parseInt(rawValue, 10)
    if (!Number.isNaN(parsed)) setByPath(sectionKey, field.path ?? field.key, parsed)
    return
  }

  if (field.type === 'float') {
    const parsed = rawValue === '' ? 0 : Number.parseFloat(rawValue)
    if (!Number.isNaN(parsed)) setByPath(sectionKey, field.path ?? field.key, parsed)
    return
  }

  setByPath(sectionKey, field.path ?? field.key, rawValue)
}

function listToText(value: any) {
  if (!Array.isArray(value)) return ''
  return value.map((item) => String(item)).join('\n')
}

function updateList(sectionKey: string, field: ConfigField, raw: string) {
  const lines = raw
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)

  let parsed: any[] = lines
  if (field.type === 'int_list') {
    parsed = lines.map((line) => Number(line)).filter((item) => !Number.isNaN(item))
  } else if (field.type === 'mixed_list') {
    parsed = lines.map((line) => (/^-?\d+$/.test(line) ? Number(line) : line))
  }

  setByPath(sectionKey, field.path ?? field.key, parsed)
}

function boolMapEntries(sectionKey: string, field: ConfigField) {
  const value = currentValue(sectionKey, field)
  if (!value || typeof value !== 'object' || Array.isArray(value)) return [] as Array<[string, boolean]>
  return Object.entries(value as Record<string, boolean>)
}

function updateBoolMapValue(sectionKey: string, field: ConfigField, key: string, checked: boolean) {
  const current = currentValue(sectionKey, field)
  const next = {
    ...(current && typeof current === 'object' && !Array.isArray(current) ? current : {}),
    [key]: checked,
  }
  setByPath(sectionKey, field.path ?? field.key, next)
}

function llmModels() {
  const models = values.value.llm?.models
  return Array.isArray(models) ? models : []
}

function addLlmModel() {
  ensureSection('llm')
  if (!Array.isArray(values.value.llm.models)) {
    values.value.llm.models = []
  }
  values.value.llm.models.push({ model: '', api_key: '', base_url: '' })
}

function removeLlmModel(index: number) {
  if (!Array.isArray(values.value.llm?.models)) return
  values.value.llm.models.splice(index, 1)
}

function updateLlmModelField(index: number, key: 'model' | 'api_key' | 'base_url', value: string) {
  ensureSection('llm')
  if (!Array.isArray(values.value.llm.models)) {
    values.value.llm.models = []
  }
  if (!values.value.llm.models[index]) {
    values.value.llm.models[index] = { model: '', api_key: '', base_url: '' }
  }
  values.value.llm.models[index][key] = value
}

function presetEntries() {
  const presetMap = values.value.presets
  if (!presetMap || typeof presetMap !== 'object' || Array.isArray(presetMap)) return [] as Array<[string, { system_prompt: string }]>
  return Object.entries(presetMap as Record<string, { system_prompt: string }>)
}

function addPreset() {
  ensureSection('presets')
  let index = 1
  let name = `preset_${index}`
  while (values.value.presets[name]) {
    index += 1
    name = `preset_${index}`
  }
  values.value.presets[name] = { system_prompt: '' }
}

function removePreset(name: string) {
  if (!values.value.presets) return
  delete values.value.presets[name]
}

function renamePreset(oldName: string, newName: string) {
  const target = newName.trim()
  if (!target || target === oldName || values.value.presets?.[target]) return
  const payload = values.value.presets?.[oldName]
  if (!payload) return
  values.value.presets[target] = payload
  delete values.value.presets[oldName]
}

function updatePresetPrompt(name: string, value: string) {
  ensureSection('presets')
  if (!values.value.presets[name]) {
    values.value.presets[name] = { system_prompt: '' }
  }
  values.value.presets[name].system_prompt = value
}

function effectClass(kind?: string) {
  switch (kind) {
    case 'hot_reload':
      return 'bg-emerald-50 text-emerald-700 border-emerald-200'
    case 'next_request':
      return 'bg-sky-50 text-sky-700 border-sky-200'
    case 'reconnect':
      return 'bg-amber-50 text-amber-700 border-amber-200'
    case 'restart':
      return 'bg-rose-50 text-rose-700 border-rose-200'
    case 'relogin':
    case 'new_login':
      return 'bg-violet-50 text-violet-700 border-violet-200'
    case 'stored_only':
      return 'bg-slate-100 text-slate-700 border-slate-200'
    default:
      return 'bg-gray-100 text-gray-700 border-gray-200'
  }
}

function fieldSearchText(section: ConfigSection, field: ConfigField) {
  return normalizeText([
    section.key,
    section.title,
    localizedSectionTitle(section),
    section.description,
    localizedSectionDescription(section),
    field.key,
    field.path,
    field.label,
    localizedFieldHelp(section.key, field),
    localizedEffectLabel(field.effect),
    localizedEffectDetail(field.effect),
    field.effect?.kind,
  ].join(' '))
}

const filteredSections = computed<FilteredSection[]>(() => {
  const query = normalizeText(searchQuery.value)
  return sections.value
    .map((section) => {
      if (!query) return { ...section, visibleFields: section.fields }
      const sectionText = normalizeText([
        section.key,
        section.title,
        localizedSectionTitle(section),
        section.description,
        localizedSectionDescription(section),
      ].join(' '))
      const sectionMatches = sectionText.includes(query)
      const visibleFields = sectionMatches ? section.fields : section.fields.filter((field) => fieldSearchText(section, field).includes(query))
      return { ...section, visibleFields }
    })
    .filter((section) => section.visibleFields.length > 0)
})

function countModifiedFields(section: ConfigSection, fields: ConfigField[] = section.fields) {
  return fields.filter((field) => fieldChanged(section.key, field)).length
}

function countDirtyFields(section: ConfigSection, fields: ConfigField[] = section.fields) {
  return fields.filter((field) => fieldDirty(section.key, field)).length
}

function countFieldsByEffect(kinds: string[]) {
  return filteredSections.value.reduce((total, section) => {
    return total + section.visibleFields.filter((field) => fieldChanged(section.key, field) && kinds.includes(field.effect?.kind || '')).length
  }, 0)
}

const summaryCards = computed(() => {
  const visibleSectionsCount = filteredSections.value.length
  const visibleFieldCount = filteredSections.value.reduce((total, section) => total + section.visibleFields.length, 0)
  const modifiedFieldCount = filteredSections.value.reduce((total, section) => total + countModifiedFields(section, section.visibleFields), 0)
  return [
    { title: '\u53ef\u89c1\u8303\u56f4', value: `${visibleSectionsCount} \u4e2a\u5206\u7ec4`, hint: `\u5c55\u793a ${visibleFieldCount} \u4e2a\u5b57\u6bb5`, icon: Blocks, tone: 'border-gray-100 text-kivotos-navy' },
    { title: '\u5df2\u914d\u7f6e\u5b57\u6bb5', value: String(modifiedFieldCount), hint: '\u4e0e\u9ed8\u8ba4\u503c\u4e0d\u540c', icon: Settings2, tone: modifiedFieldCount ? 'border-kivotos-cyan/20 text-kivotos-navy' : 'border-gray-100 text-kivotos-navy' },
    { title: '\u53ef\u70ed\u66f4\u65b0', value: String(countFieldsByEffect(['hot_reload', 'next_request'])), hint: '\u65e0\u9700\u91cd\u542f\u5373\u53ef\u751f\u6548', icon: RefreshCw, tone: 'border-emerald-200 text-kivotos-navy' },
    { title: '\u654f\u611f\u53d8\u66f4', value: String(countFieldsByEffect(['restart', 'reconnect', 'relogin', 'new_login'])), hint: '\u6d89\u53ca\u91cd\u542f / \u91cd\u8fde / \u767b\u5f55', icon: Shield, tone: 'border-rose-200 text-kivotos-navy' },
  ]
})

const pendingEditCount = computed(() => sections.value.reduce((total, section) => total + countDirtyFields(section), 0))

function toggleSection(sectionKey: string) {
  collapsedSections.value[sectionKey] = !collapsedSections.value[sectionKey]
}

function expandVisibleSections() {
  for (const section of filteredSections.value) collapsedSections.value[section.key] = false
}

function collapseVisibleSections() {
  for (const section of filteredSections.value) collapsedSections.value[section.key] = true
}

function scrollToSection(sectionKey: string) {
  collapsedSections.value[sectionKey] = false
  document.getElementById(`config-section-${sectionKey}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

function isCollapsed(sectionKey: string) {
  return Boolean(collapsedSections.value[sectionKey])
}

watch(searchQuery, (query) => {
  if (query.trim()) expandVisibleSections()
})

async function fetchSchema() {
  loading.value = true
  errorMsg.value = ''
  try {
    const res = await api.get<ConfigSchemaResponse>('/api/config/schema')
    schema.value = res.data
    values.value = deepClone(res.data.values)
    originalValues.value = deepClone(res.data.values)
    yamlPreview.value = res.data.content
    const nextCollapsed: Record<string, boolean> = {}
    for (const section of res.data.sections) nextCollapsed[section.key] = collapsedSections.value[section.key] ?? false
    collapsedSections.value = nextCollapsed
  } catch (error: any) {
    errorMsg.value = error.response?.data?.detail || '\u52a0\u8f7d\u914d\u7f6e\u7ed3\u6784\u5931\u8d25'
  } finally {
    loading.value = false
  }
}

async function refreshConfig() {
  if (hasUnsavedChanges.value) {
    refreshConfirmOpen.value = true
    return
  }
  await fetchSchema()
}

async function confirmRefreshConfig() {
  refreshConfirmOpen.value = false
  await fetchSchema()
}

async function saveStructuredConfig() {
  saving.value = true
  errorMsg.value = ''
  successMsg.value = ''
  try {
    const res = await api.post('/api/config/structured', { values: values.value })
    originalValues.value = deepClone(res.data.values)
    values.value = deepClone(res.data.values)
    yamlPreview.value = res.data.content
    successMsg.value = '\u914d\u7f6e\u4fdd\u5b58\u6210\u529f'
  } catch (error: any) {
    errorMsg.value = error.response?.data?.detail || '\u914d\u7f6e\u4fdd\u5b58\u5931\u8d25'
  } finally {
    saving.value = false
  }
}

onMounted(fetchSchema)
</script>
<template>
  <div class="h-full min-h-0 flex flex-col gap-6 overflow-hidden">
    <div class="flex items-center justify-between gap-4 flex-wrap">
      <div>
        <h2 class="text-3xl font-black text-kivotos-navy tracking-tight uppercase">&#x7ED3;&#x6784;&#x5316;&#x914D;&#x7F6E;</h2>
        <p class="text-kivotos-gray font-mono text-xs mt-1 font-bold">&#x628A; CONFIG.YAML &#x5F53;&#x4F5C;&#x53EF;&#x7BA1;&#x7406;&#x63A7;&#x5236;&#x53F0;</p>
      </div>
      <div class="flex items-center gap-2 flex-wrap justify-end">
        <div class="px-4 py-2 rounded-xl border border-gray-200 bg-white text-sm text-gray-600 shadow-sm">
          <span class="font-bold text-kivotos-navy">{{ pendingEditCount }}</span>
          &#x4E2A;&#x5B57;&#x6BB5;&#x672A;&#x4FDD;&#x5B58;
        </div>
        <button @click="refreshConfig" :disabled="loading" class="px-4 py-2 rounded-xl border border-gray-200 bg-white text-kivotos-navy font-bold flex items-center gap-2 hover:border-kivotos-cyan disabled:opacity-60">
          <RefreshCw :size="16" :class="loading ? 'animate-spin' : ''" />
          &#x91CD;&#x65B0;&#x52A0;&#x8F7D;
        </button>
        <button @click="saveStructuredConfig" :disabled="saving || !hasUnsavedChanges" class="px-4 py-2 rounded-xl bg-kivotos-navy text-white font-bold flex items-center gap-2 hover:bg-slate-800 disabled:opacity-60">
          <Save :size="16" />
          {{ saving ? '\u4fdd\u5b58\u4e2d...' : '\u4fdd\u5b58\u914d\u7f6e' }}
        </button>
      </div>
    </div>

    <div class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
      <div v-for="card in summaryCards" :key="card.title" class="bg-white p-4 rounded-2xl border shadow-sm" :class="card.tone">
        <div class="flex items-center justify-between gap-3">
          <p class="text-xs font-bold text-gray-500 uppercase tracking-wider">{{ card.title }}</p>
          <component :is="card.icon" :size="18" class="text-kivotos-cyan" />
        </div>
        <p class="mt-3 text-2xl font-black text-kivotos-navy">{{ card.value }}</p>
        <p class="mt-1 text-xs text-gray-500 font-mono">{{ card.hint }}</p>
      </div>
    </div>

    <InlineNotice v-if="errorMsg" type="error" :message="errorMsg" @close="errorMsg = ''" />
    <InlineNotice v-if="successMsg" type="success" :message="successMsg" @close="successMsg = ''" />

    <div class="grid grid-cols-1 xl:grid-cols-[320px_minmax(0,1fr)] gap-6 min-h-0 flex-1 overflow-hidden items-start">
      <aside class="bg-white rounded-2xl border border-gray-100 shadow-sm overflow-hidden h-full min-h-0 flex flex-col">
        <div class="p-5 border-b border-gray-100 space-y-4">
          <div>
            <h3 class="text-xl font-black text-kivotos-navy flex items-center gap-2">
              <Settings2 :size="18" class="text-kivotos-cyan" />
              &#x914D;&#x7F6E;&#x5206;&#x7EC4;
            </h3>
            <p class="text-sm text-gray-600 mt-1">&#x5C55;&#x793A;&#x5B8C;&#x6574;&#x914D;&#x7F6E;&#x6A21;&#x578B;&#xFF0C;&#x5305;&#x62EC;&#x9ED8;&#x8BA4;&#x9879;&#x4E0E;&#x5F53;&#x524D;&#x5173;&#x95ED;&#x7684;&#x529F;&#x80FD;&#x3002;</p>
          </div>
          <div class="relative">
            <Search :size="16" class="absolute left-4 top-1/2 -translate-y-1/2 text-gray-400" />
            <input v-model="searchQuery" type="text" placeholder="&#x641C;&#x7D22;&#x5206;&#x7EC4;&#x3001;&#x5B57;&#x6BB5;&#x3001;&#x8BF4;&#x660E;&#x3001;&#x751F;&#x6548;&#x65B9;&#x5F0F;..." class="w-full rounded-xl border border-gray-200 bg-slate-50 pl-11 pr-4 py-3 text-sm text-kivotos-navy outline-none focus:border-kivotos-cyan" />
          </div>
          <div class="flex items-center gap-2">
            <button @click="expandVisibleSections" class="px-3 py-2 rounded-lg bg-slate-100 text-slate-700 text-sm font-bold hover:bg-slate-200">&#x5168;&#x90E8;&#x5C55;&#x5F00;</button>
            <button @click="collapseVisibleSections" class="px-3 py-2 rounded-lg bg-slate-100 text-slate-700 text-sm font-bold hover:bg-slate-200">&#x5168;&#x90E8;&#x6298;&#x53E0;</button>
          </div>
          <div class="rounded-xl bg-slate-50 border border-gray-200 p-4 text-xs text-gray-600 font-mono break-all">
            <div class="text-gray-500 uppercase tracking-wider mb-1">&#x914D;&#x7F6E;&#x6587;&#x4EF6;</div>
            <div class="font-bold text-kivotos-navy">{{ schema?.path || 'config.yaml' }}</div>
          </div>
        </div>
        <div class="flex-1 overflow-y-auto p-3 space-y-2">
          <button v-for="section in filteredSections" :key="section.key" @click="scrollToSection(section.key)" class="w-full text-left rounded-2xl border border-gray-200 bg-slate-50 hover:bg-white hover:border-kivotos-cyan transition-all px-4 py-3">
            <div class="flex items-start justify-between gap-3">
              <div class="min-w-0">
                <div class="font-black text-kivotos-navy truncate">{{ localizedSectionTitle(section) }}</div>
                <div class="text-xs text-gray-500 font-mono mt-1">{{ section.key }}</div>
              </div>
              <div class="text-right shrink-0">
                <div class="text-sm font-black text-kivotos-navy">{{ countModifiedFields(section) }}/{{ section.fields.length }}</div>
                <div class="text-[11px] text-gray-500">&#x5DF2;&#x914D;&#x7F6E;</div>
              </div>
            </div>
            <div class="mt-3 flex items-center gap-2 flex-wrap text-[11px]">
              <span class="px-2 py-1 rounded-full bg-white border border-gray-200 text-gray-600">&#x53EF;&#x89C1; {{ section.visibleFields.length }}</span>
              <span class="px-2 py-1 rounded-full bg-white border border-gray-200 text-gray-600">&#x672A;&#x4FDD;&#x5B58; {{ countDirtyFields(section) }}</span>
            </div>
          </button>
          <div v-if="filteredSections.length === 0" class="p-4 text-sm text-gray-500">&#x6CA1;&#x6709;&#x5339;&#x914D;&#x5F53;&#x524D;&#x641C;&#x7D22;&#x6761;&#x4EF6;&#x7684;&#x5206;&#x7EC4;&#x3002;</div>
        </div>
      </aside>

      <div class="h-full min-h-0 overflow-y-auto space-y-6 pr-1">
        <section v-for="section in filteredSections" :id="`config-section-${section.key}`" :key="section.key" class="bg-white rounded-2xl border border-gray-100 shadow-sm overflow-hidden">
          <button @click="toggleSection(section.key)" class="w-full px-6 py-5 border-b border-gray-100 flex items-start justify-between gap-4 text-left hover:bg-slate-50 transition-colors">
            <div>
              <div class="flex items-center gap-2 flex-wrap">
                <h3 class="text-xl font-black text-kivotos-navy">{{ localizedSectionTitle(section) }}</h3>
                <span class="px-2 py-1 rounded-full bg-slate-100 text-slate-600 text-[11px] font-mono">{{ section.key }}</span>
                <span class="px-2 py-1 rounded-full bg-kivotos-cyan/10 text-kivotos-cyan text-[11px] font-bold">{{ countModifiedFields(section) }}/{{ section.fields.length }} &#x5DF2;&#x914D;&#x7F6E;</span>
                <span class="px-2 py-1 rounded-full bg-slate-100 text-slate-600 text-[11px] font-bold">{{ section.visibleFields.length }} &#x53EF;&#x89C1;</span>
              </div>
              <p class="text-sm text-gray-600 mt-2">{{ localizedSectionDescription(section) }}</p>
            </div>
            <div class="flex items-center gap-3 shrink-0">
              <span class="text-xs text-gray-500 font-mono">&#x672A;&#x4FDD;&#x5B58; {{ countDirtyFields(section) }}</span>
              <component :is="isCollapsed(section.key) ? ChevronRight : ChevronDown" :size="18" class="text-gray-400" />
            </div>
          </button>

          <div v-show="!isCollapsed(section.key)" class="p-6 grid grid-cols-1 2xl:grid-cols-2 gap-4">
            <div v-for="field in section.visibleFields" :key="`${section.key}-${field.path ?? field.key}`" class="rounded-2xl border border-gray-200 bg-slate-50 p-5" :class="fieldDirty(section.key, field) ? 'ring-1 ring-kivotos-cyan/30 border-kivotos-cyan/30' : ''">
              <div class="flex items-start justify-between gap-3 mb-3 flex-wrap">
                <div>
                  <div class="flex items-center gap-2 flex-wrap">
                    <label class="font-black text-kivotos-navy">{{ field.label }}</label>
                    <CircleHelp :size="14" class="text-gray-400" />
                    <span v-if="fieldChanged(section.key, field)" class="text-[10px] px-2 py-0.5 rounded-full bg-kivotos-pink/10 text-kivotos-pink font-bold">&#x5DF2;&#x914D;&#x7F6E;</span>
                    <span v-if="fieldDirty(section.key, field)" class="text-[10px] px-2 py-0.5 rounded-full bg-kivotos-cyan/10 text-kivotos-cyan font-bold">&#x672A;&#x4FDD;&#x5B58;</span>
                  </div>
                  <p class="text-sm text-gray-600 mt-1">{{ localizedFieldHelp(section.key, field) }}</p>
                  <p class="text-xs text-gray-400 font-mono mt-2">{{ section.key }}.{{ field.path ?? field.key }}</p>
                </div>
                <div class="flex flex-col items-end gap-2 max-w-full">
                  <span class="text-[11px] px-2.5 py-1 rounded-full border font-bold whitespace-nowrap" :class="effectClass(field.effect?.kind)">{{ localizedEffectLabel(field.effect) }}</span>
                  <span class="text-[11px] text-right text-gray-500 max-w-[260px]">{{ localizedEffectDetail(field.effect) }}</span>
                </div>
              </div>

              <template v-if="field.type === 'bool'">
                <div class="flex items-center justify-between gap-4 rounded-xl bg-white border border-gray-200 px-4 py-3">
                  <div>
                    <div class="font-bold text-kivotos-navy">{{ currentValue(section.key, field) ? '\u5df2\u542f\u7528' : '\u5df2\u5173\u95ed' }}</div>
                    <div class="text-xs text-gray-500">{{ fieldDefaultText(section.key, field) }}</div>
                  </div>
                  <label class="inline-flex items-center cursor-pointer">
                    <input type="checkbox" class="sr-only" :checked="Boolean(currentValue(section.key, field))" @change="setByPath(section.key, field.path ?? field.key, ($event.target as HTMLInputElement).checked)" />
                    <span class="w-11 h-6 rounded-full transition-colors relative" :class="Boolean(currentValue(section.key, field)) ? 'bg-kivotos-cyan' : 'bg-gray-300'">
                      <span class="absolute top-1 left-1 w-4 h-4 rounded-full bg-white transition-transform" :class="Boolean(currentValue(section.key, field)) ? 'translate-x-5' : ''"></span>
                    </span>
                  </label>
                </div>
              </template>

              <template v-else-if="['string', 'password', 'int', 'float'].includes(field.type)">
                <input :type="field.type === 'password' ? 'password' : field.type === 'string' ? 'text' : 'number'" :step="field.type === 'float' ? 'any' : '1'" class="w-full rounded-xl border border-gray-200 bg-white px-4 py-3 text-kivotos-navy outline-none focus:border-kivotos-cyan" :value="currentValue(section.key, field) ?? ''" @input="updatePrimitive(section.key, field, ($event.target as HTMLInputElement).value)" />
                <p class="text-xs text-gray-400 mt-2">{{ fieldDefaultText(section.key, field) }}</p>
              </template>

              <template v-else-if="field.type === 'textarea'">
                <textarea rows="5" class="w-full rounded-xl border border-gray-200 bg-white px-4 py-3 text-kivotos-navy outline-none focus:border-kivotos-cyan" :value="currentValue(section.key, field)" @input="updatePrimitive(section.key, field, ($event.target as HTMLTextAreaElement).value)" />
                <p class="text-xs text-gray-400 mt-2">{{ fieldDefaultText(section.key, field) }}</p>
              </template>

              <template v-else-if="['int_list', 'string_list', 'mixed_list'].includes(field.type)">
                <textarea rows="5" class="w-full rounded-xl border border-gray-200 bg-white px-4 py-3 font-mono text-sm text-kivotos-navy outline-none focus:border-kivotos-cyan" :value="listToText(currentValue(section.key, field))" @input="updateList(section.key, field, ($event.target as HTMLTextAreaElement).value)" />
                <p class="text-xs text-gray-400 mt-2">&#x6BCF;&#x884C;&#x4E00;&#x9879;&#x3002;{{ fieldDefaultText(section.key, field) }}</p>
              </template>

              <template v-else-if="field.type === 'bool_map'">
                <div class="space-y-2">
                  <div v-for="([key, value]) in boolMapEntries(section.key, field)" :key="key" class="flex items-center justify-between gap-3 rounded-xl bg-white border border-gray-200 px-4 py-3">
                    <div><div class="font-mono text-sm text-kivotos-navy">{{ key }}</div></div>
                    <label class="inline-flex items-center cursor-pointer">
                      <input type="checkbox" class="sr-only" :checked="Boolean(value)" @change="updateBoolMapValue(section.key, field, key, ($event.target as HTMLInputElement).checked)" />
                      <span class="w-11 h-6 rounded-full transition-colors relative" :class="Boolean(value) ? 'bg-kivotos-cyan' : 'bg-gray-300'">
                        <span class="absolute top-1 left-1 w-4 h-4 rounded-full bg-white transition-transform" :class="Boolean(value) ? 'translate-x-5' : ''"></span>
                      </span>
                    </label>
                  </div>
                </div>
                <p class="text-xs text-gray-400 mt-2">{{ fieldDefaultText(section.key, field) }}</p>
              </template>
              <template v-else-if="field.type === 'llm_models'">
                <div class="flex items-start justify-between gap-4 flex-wrap mb-3">
                  <div class="text-xs text-gray-500">&#x5728;&#x8FD9;&#x91CC;&#x7EF4;&#x62A4;&#x56DE;&#x9000;&#x6A21;&#x578B;&#x6216;&#x5907;&#x7528;&#x6A21;&#x578B;&#x7AEF;&#x70B9;&#x3002;</div>
                  <button @click="addLlmModel" class="px-3 py-2 rounded-lg bg-kivotos-cyan text-white text-sm font-bold flex items-center gap-2 hover:opacity-90">
                    <Plus :size="14" />
                    &#x65B0;&#x589E;&#x6A21;&#x578B;
                  </button>
                </div>
                <div class="space-y-3">
                  <div v-for="(model, index) in llmModels()" :key="index" class="rounded-2xl bg-white border border-gray-200 p-4">
                    <div class="grid grid-cols-1 lg:grid-cols-[1.2fr_1fr_1fr_auto] gap-3 items-start">
                      <input :value="model.model" type="text" placeholder="model name" class="rounded-xl border border-gray-200 px-4 py-3 outline-none focus:border-kivotos-cyan" @input="updateLlmModelField(index, 'model', ($event.target as HTMLInputElement).value)" />
                      <input :value="model.api_key" type="password" placeholder="api key (optional)" class="rounded-xl border border-gray-200 px-4 py-3 outline-none focus:border-kivotos-cyan" @input="updateLlmModelField(index, 'api_key', ($event.target as HTMLInputElement).value)" />
                      <input :value="model.base_url" type="text" placeholder="base url (optional)" class="rounded-xl border border-gray-200 px-4 py-3 outline-none focus:border-kivotos-cyan" @input="updateLlmModelField(index, 'base_url', ($event.target as HTMLInputElement).value)" />
                      <button @click="removeLlmModel(index)" class="h-12 px-3 rounded-xl border border-red-200 text-red-500 hover:bg-red-50 flex items-center justify-center">
                        <Trash2 :size="16" />
                      </button>
                    </div>
                  </div>
                  <div v-if="llmModels().length === 0" class="text-sm text-gray-400">&#x5F53;&#x524D;&#x6CA1;&#x6709;&#x914D;&#x7F6E;&#x56DE;&#x9000;&#x6A21;&#x578B;&#x3002;</div>
                </div>
                <p class="text-xs text-gray-400 mt-2">{{ fieldDefaultText(section.key, field) }}</p>
              </template>

              <template v-else-if="field.type === 'preset_map'">
                <div class="flex items-start justify-between gap-4 flex-wrap mb-3">
                  <div class="text-xs text-gray-500">&#x9884;&#x8BBE;&#x5DF2;&#x6B63;&#x5F0F;&#x7EB3;&#x5165;&#x914D;&#x7F6E;&#x9875;&#xFF0C;&#x8FD9;&#x91CC;&#x4F1A;&#x5B8C;&#x6574;&#x5C55;&#x793A;&#x9ED8;&#x8BA4;&#x9879;&#x548C;&#x5DF2;&#x5173;&#x95ED;&#x9879;&#x3002;</div>
                  <button @click="addPreset" class="px-3 py-2 rounded-lg bg-kivotos-cyan text-white text-sm font-bold flex items-center gap-2 hover:opacity-90">
                    <Plus :size="14" />
                    &#x65B0;&#x589E;&#x9884;&#x8BBE;
                  </button>
                </div>
                <div class="space-y-3">
                  <div v-for="([name, preset]) in presetEntries()" :key="name" class="rounded-2xl bg-white border border-gray-200 p-4">
                    <div class="flex items-center gap-3 mb-3">
                      <input :value="name" @change="renamePreset(name, ($event.target as HTMLInputElement).value)" class="flex-1 rounded-xl border border-gray-200 px-4 py-3 font-bold text-kivotos-navy outline-none focus:border-kivotos-cyan" />
                      <button @click="removePreset(name)" class="h-12 px-3 rounded-xl border border-red-200 text-red-500 hover:bg-red-50 flex items-center justify-center">
                        <Trash2 :size="16" />
                      </button>
                    </div>
                    <textarea :value="preset.system_prompt" rows="6" class="w-full rounded-xl border border-gray-200 px-4 py-3 text-kivotos-navy outline-none focus:border-kivotos-cyan" @input="updatePresetPrompt(name, ($event.target as HTMLTextAreaElement).value)" />
                  </div>
                </div>
                <p class="text-xs text-gray-400 mt-2">{{ fieldDefaultText(section.key, field) }}</p>
              </template>
            </div>
          </div>
        </section>

        <section class="bg-white rounded-2xl border border-gray-100 shadow-sm overflow-hidden">
          <div class="px-6 py-5 border-b border-gray-100">
            <h3 class="text-xl font-black text-kivotos-navy">&#x751F;&#x6210;&#x540E;&#x7684; YAML &#x9884;&#x89C8;</h3>
            <p class="text-sm text-gray-600 mt-1">&#x8FD9;&#x91CC;&#x5C55;&#x793A;&#x6700;&#x7EC8;&#x5C06;&#x5199;&#x5165; <code>config.yaml</code> &#x7684;&#x5B8C;&#x6574; YAML &#x5185;&#x5BB9;&#x3002;</p>
          </div>
          <div class="p-6">
            <textarea readonly rows="18" class="w-full rounded-2xl border border-gray-200 bg-slate-50 px-4 py-3 font-mono text-xs text-kivotos-navy outline-none">{{ yamlPreview }}</textarea>
          </div>
        </section>
      </div>
    </div>

    <ConfirmDialog
      :open="refreshConfirmOpen"
      title="确认重新加载"
      message="当前有未保存修改。继续会丢弃本地修改。"
      confirm-text="丢弃并重载"
      cancel-text="取消"
      @close="refreshConfirmOpen = false"
      @confirm="confirmRefreshConfig"
    />
  </div>
</template>
