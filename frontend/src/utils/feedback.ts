/**
 * 全局消息 / 弹窗实例的持有者。
 *
 * Ant Design Vue 4 的 message/Modal 静态方法不消费 ConfigProvider 的上下文
 * （中文 locale、主题都会丢），所以必须在组件里用 `App.useApp()` 取实例。
 * 但 axios 拦截器、store 这些非组件代码也需要弹提示，于是由 App.vue 在启动时
 * 把实例注册到这里，业务代码统一从这里取。
 */

type Notify = (content: string) => void

interface FeedbackApi {
  success: Notify
  error: Notify
  warning: Notify
  info: Notify
  confirm: (options: {
    title: string
    content?: string
    okText?: string
    cancelText?: string
    danger?: boolean
  }) => Promise<boolean>
}

let impl: FeedbackApi | null = null

export function registerFeedback(api: FeedbackApi): void {
  impl = api
}

/** 实例注册前（如应用启动早期的报错）静默降级到 console，不要因此崩溃。 */
export const feedback: FeedbackApi = {
  success: (c) => impl?.success(c) ?? console.info(c),
  error: (c) => impl?.error(c) ?? console.error(c),
  warning: (c) => impl?.warning(c) ?? console.warn(c),
  info: (c) => impl?.info(c) ?? console.info(c),
  confirm: (o) => (impl ? impl.confirm(o) : Promise.resolve(window.confirm(o.title))),
}
