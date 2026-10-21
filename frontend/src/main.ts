import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import zhCn from 'element-plus/es/locale/lang/zh-cn'

// Element Plus 组件样式（含 .el-icon svg { width: 1em; height: 1em } 这条图标尺寸规则）。
// 图标组件本身不带宽高属性，缺这份 CSS 时 svg 会撑满父容器，
// 表现为感叹号、下拉箭头等图标变成满屏。必须放在 ./style.css 之前，
// 让项目自己的 .sm-* 覆盖样式仍然优先。
import 'element-plus/dist/index.css'

import App from './App.vue'
import { router } from './router'
import './style.css'

const app = createApp(App)
app.use(createPinia())
app.use(router)
// 组件仍按需 import；注册插件是为了给内置文案（Select/No Data 等）设定中文 locale。
app.use(ElementPlus, { locale: zhCn })
app.mount('#app')
