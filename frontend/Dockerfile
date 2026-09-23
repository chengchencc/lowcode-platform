# 前端镜像：Node 构建 → nginx 静态托管（多阶段，最终镜像里没有 Node）。

FROM node:22-alpine AS build

WORKDIR /app

# 依赖先于源码：只改业务代码时 npm ci 这一层直接命中缓存
COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build


FROM nginx:1.27-alpine

# 站点配置（含 /api 反向代理与 SPA history 回退）
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=5 \
    CMD wget -q -O /dev/null http://127.0.0.1/ || exit 1
