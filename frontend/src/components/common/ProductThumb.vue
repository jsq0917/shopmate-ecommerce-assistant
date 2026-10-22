<script setup lang="ts">
/**
 * 商品视觉占位：合成数据没有真实图片，用「品类图形 + 渐变」生成稳定的封面，
 * 避免空图框显得残缺；一旦后端提供 image_url 就直接展示真实图片。
 */

import { computed } from 'vue'

const props = withDefaults(
  defineProps<{
    category?: string | null
    title?: string
    imageUrl?: string | null
    size?: 'sm' | 'md' | 'lg'
  }>(),
  { category: '', title: '', imageUrl: null, size: 'md' },
)

interface Visual {
  icon: string
  from: string
  to: string
}

const MAP: Array<{ keys: string[]; visual: Visual }> = [
  { keys: ['降噪耳机', '蓝牙耳机', '耳机'], visual: { icon: '🎧', from: '#e8ecff', to: '#d5dcff' } },
  { keys: ['机械键盘', '薄膜键盘', '键盘'], visual: { icon: '⌨️', from: '#e9f0ff', to: '#d6e4ff' } },
  { keys: ['鼠标'], visual: { icon: '🖱️', from: '#eaf4ff', to: '#d8e9ff' } },
  { keys: ['充电器', '数据线', '无线充电器'], visual: { icon: '🔌', from: '#eef1ff', to: '#dfe4ff' } },
  { keys: ['移动电源'], visual: { icon: '🔋', from: '#eef7ee', to: '#dcf0dc' } },
  { keys: ['智能手表', '智能手环'], visual: { icon: '⌚', from: '#eef0ff', to: '#dde0ff' } },
  { keys: ['音箱'], visual: { icon: '🔊', from: '#f1edff', to: '#e2dbff' } },
  { keys: ['摄像头'], visual: { icon: '📷', from: '#eef2f7', to: '#dde5ef' } },
  { keys: ['手机支架'], visual: { icon: '📱', from: '#edf1ff', to: '#dce3ff' } },
  { keys: ['显示器'], visual: { icon: '🖥️', from: '#e9eefb', to: '#d8e1f5' } },
  { keys: ['跑步鞋', '运动鞋'], visual: { icon: '👟', from: '#fff0e8', to: '#ffdcc9' } },
  { keys: ['T恤', '卫衣'], visual: { icon: '👕', from: '#fff2ea', to: '#ffe0cf' } },
  { keys: ['双肩包', '行李箱', '登山包'], visual: { icon: '🎒', from: '#fdf0e6', to: '#f7ddc9' } },
  { keys: ['保温杯', '饮水机', '保鲜盒'], visual: { icon: '🥤', from: '#e8f7f4', to: '#d2efe8' } },
  { keys: ['枕头', '床品四件套', '浴巾'], visual: { icon: '🛏️', from: '#eef6f3', to: '#dbeee7' } },
  { keys: ['台灯'], visual: { icon: '💡', from: '#fff8e5', to: '#ffedc2' } },
  { keys: ['边几'], visual: { icon: '🪑', from: '#f6f1ea', to: '#eadfd0' } },
  { keys: ['空气炸锅', '料理机', '咖啡机'], visual: { icon: '🍳', from: '#fff4e8', to: '#ffe3c7' } },
  { keys: ['电动牙刷'], visual: { icon: '🪥', from: '#eaf6fb', to: '#d6ecf7' } },
  { keys: ['吹风机'], visual: { icon: '💨', from: '#eef4fb', to: '#dbe9f7' } },
  { keys: ['洗发水', '面膜', '护手霜'], visual: { icon: '🧴', from: '#fdeef6', to: '#f9d9ea' } },
  { keys: ['瑜伽垫', '哑铃'], visual: { icon: '🏋️', from: '#eef7ef', to: '#d9efdc' } },
  { keys: ['猫粮', '猫砂'], visual: { icon: '🐱', from: '#fdf3e8', to: '#f8e2ca' } },
  { keys: ['咖啡', '坚果'], visual: { icon: '🥜', from: '#fbf1e6', to: '#f3dfc8' } },
]

const DEFAULT_VISUAL: Visual = { icon: '🛍️', from: '#eef1fb', to: '#dde3f5' }

const visual = computed<Visual>(() => {
  const category = props.category ?? ''
  const hit = MAP.find((entry) => entry.keys.some((key) => category.includes(key)))
  return hit?.visual ?? DEFAULT_VISUAL
})

const style = computed(() => ({
  background: `linear-gradient(135deg, ${visual.value.from} 0%, ${visual.value.to} 100%)`,
}))

const initial = computed(() => props.title?.trim().slice(0, 1) ?? '')
</script>

<template>
  <div class="sm-thumb" :class="`sm-thumb-${size}`" :style="style" :aria-label="title">
    <img v-if="imageUrl" :src="imageUrl" :alt="title" class="sm-thumb-img" />
    <template v-else>
      <span class="sm-thumb-icon" aria-hidden="true">{{ visual.icon }}</span>
      <span v-if="size === 'lg'" class="sm-thumb-watermark" aria-hidden="true">{{ initial }}</span>
    </template>
  </div>
</template>

<style scoped>
.sm-thumb {
  position: relative;
  display: grid;
  place-items: center;
  overflow: hidden;
  border-radius: var(--sm-radius-sm);
  flex: none;
}

.sm-thumb-sm {
  width: 56px;
  height: 56px;
}

.sm-thumb-md {
  width: 100%;
  aspect-ratio: 4 / 3;
  border-radius: var(--sm-radius-sm) var(--sm-radius-sm) 0 0;
}

.sm-thumb-lg {
  width: 100%;
  aspect-ratio: 16 / 10;
  border-radius: var(--sm-radius);
}

.sm-thumb-icon {
  font-size: 34px;
  filter: saturate(0.9);
  opacity: 0.92;
}

.sm-thumb-md .sm-thumb-icon {
  font-size: 48px;
}

.sm-thumb-lg .sm-thumb-icon {
  font-size: 64px;
}

.sm-thumb-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.sm-thumb-watermark {
  position: absolute;
  right: 12px;
  bottom: 2px;
  font-size: 68px;
  font-weight: 800;
  color: rgb(255 255 255 / 45%);
  line-height: 1;
}
</style>
