# 前端镜像：Node 构建 → nginx 静态托管（多阶段，最终镜像里没有 Node）。

FROM node:22-alpine AS build

# 依赖下载源。compose 会从 .env 的 NPM_REGISTRY 透传（默认国内镜像），
# 单独 docker build 时走官方源；海外环境传 --build-arg NPM_REGISTRY=https://registry.npmjs.org
ARG NPM_REGISTRY=https://registry.npmjs.org

WORKDIR /app

COPY package.json package-lock.json ./

# 依赖先于源码：只改业务代码时 npm ci 这一层直接命中缓存。
# cache mount 让 npm 的下载缓存在构建之间复用（不进镜像），换 lockfile 时也不必重下。
RUN --mount=type=cache,target=/root/.npm \
    npm ci --registry="$NPM_REGISTRY" --no-audit --no-fund

COPY . .
RUN npm run build


FROM nginx:1.27-alpine

# 站点配置（含 /api 反向代理与 SPA history 回退）
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=5 \
    CMD wget -q -O /dev/null http://127.0.0.1/ || exit 1
