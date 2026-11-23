# GitHub 双远端与代理配置

> 当前状态（2026-11-20）：双远端已建立。
> - `origin`：`git@gitee.com:Chaphets/lowcode-platform.git`（主仓）
> - `github`：`git@github.com:chengchencc/lowcode-platform.git`
> - `master` / `f_aitest` 已推送；日常默认跟踪仍是 `origin`，GitHub 用 `git push github <branch>` 或 `scripts/push-all.sh`。
> - 待确认：GitHub Actions 首次运行结果、分支保护、nightly。

> 目标：保留 Gitee 为 `origin`，新增 GitHub 为 `github`；两边可独立推送，互不阻塞。
> 前置：本机代理已启动（默认 `127.0.0.1:7890`），GitHub 仓库已创建。

## 1. 代理：只让 GitHub 走代理

Gitee 当前用 SSH，不受 Git HTTP 代理影响。给 GitHub 单独配置 URL 级代理：

```bash
git config --global http.https://github.com.proxy http://127.0.0.1:7890
```

验证（代理需先启动）：

```bash
curl -x http://127.0.0.1:7890 -I https://github.com
git ls-remote https://github.com/<owner>/<repo>.git
```

> 现有全局 `http.proxy=socks5://127.0.0.1:7890` 可以保留；URL 级配置优先于全局。
> 如果代理只支持 SOCKS，把上面的 `http://` 改成 `socks5://`。

### 用 SSH 访问 GitHub

`~/.ssh/config` 已配置：

```sshconfig
Host github.com
    HostName github.com
    User git
    ProxyCommand connect -S 127.0.0.1:7890 %h %p
```

注意：
- `connect.exe` 在 Git for Windows 的 `mingw64/bin` 下；确保它在 PATH 中，或写绝对路径。
- 需要把 `~/.ssh/id_rsa.pub` 加到 GitHub → Settings → SSH and GPG keys。
- 验证：`ssh -T git@github.com`，看到 `successfully authenticated` 即可。

## 2. 认证方式

推荐 HTTPS + Personal Access Token（PAT，classic，勾 `repo`）：

```bash
git config --global credential.helper manager
```

首次 push 时输入 GitHub 用户名和 PAT；Windows 凭据管理器会保存，后续不用再输。
**不要把 token 写进 remote URL、脚本或仓库。**

或者继续用 SSH（上面已配置）。

## 3. 添加 GitHub 远端

在 GitHub 网页创建空仓库（不要初始化 README），然后：

```bash
# HTTPS 方式
git remote add github https://github.com/<owner>/<repo>.git

# 或 SSH 方式
git remote add github git@github.com:<owner>/<repo>.git

git remote -v
```

预期：

```text
origin   git@gitee.com:Chaphets/lowcode-platform.git (fetch/push)
github   git@github.com:<owner>/<repo>.git (fetch/push)
```

## 4. 首次推送

```bash
git push -u github master
git push -u github f_aitest
git push github --tags
```

Gitee 仍是 `origin`，不受影响。

## 5. 日常双推

两个远端独立推送，避免 GitHub 被墙时阻塞 Gitee：

```bash
git push origin "$(git branch --show-current)"
git push github "$(git branch --show-current)"
```

或使用封装脚本：

```bash
bash scripts/push-all.sh          # 推送当前分支
bash scripts/push-all.sh master   # 推送指定分支
```

> 不建议把一个 remote 配两个 push URL：GitHub 不通时整次 push 会失败，
> 连 Gitee 也推不上去。

## 6. GitHub Actions

推送后进入仓库 **Actions** 页启用工作流：

- `ci.yml`：PR / push master 时跑后端、前端、不变量、API、E2E。
- `nightly.yml`：定时跑全量 E2E + 2,000 轮不变量 + MySQL/PG 矩阵。

需要确认：
- 私有仓库的 Actions 分钟数；
- `master` 分支保护：要求 PR + CI 必需检查；
- 不需要为测试配置 Secrets；只有推 GHCR 镜像时才需要 `GITHUB_TOKEN`（默认提供）。

## 7. 迁移顺序建议

1. 代理启动，`git ls-remote` 验证 GitHub 可达。
2. 建空仓库，加 `github` remote。
3. 推 `master` 与 `f_aitest`。
4. 在 GitHub 上启用 Actions，观察 `ci.yml` 首跑。
5. 稳定 2–3 次后再开分支保护 / nightly。
6. Gitee 保留为镜像；确认 GitHub 稳定后再决定是否切换主仓。
