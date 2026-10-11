# xhs-cli 安装 + camoufox 手动部署（服务器/GFW 环境）

## 安装 xhs-cli（按 USER.md 的 uv 约定）

```bash
uv pip install --python /opt/hermes/.venv/bin/python3 --index-url https://pypi.tuna.tsinghua.edu.cn/simple xhs-cli
```

- 命令入口：`/opt/hermes/.venv/bin/xhs`（不在 PATH，用全路径）
- 数据命令（search/read/user-posts/feed/topics）都支持 `--json`
- 登录态检查：`xhs status`（轻量，无需浏览器）

## ⚠️ xhs login --qrcode 需要 camoufox，官方 fetch 在 GFW 下会超时

`xhs login --qrcode` 底层用 `Camoufox(headless=True)`（反检测 Firefox）。首次运行要下载 ~632MB 浏览器包，`camoufox fetch` 从 GitHub 直连会超时（300s+）。**不要反复重试官方 fetch**，改为手动部署：

### 手动部署 camoufox（已验证，SHA256 校验通过）

1. 从 repo_cache 拿精确 URL + SHA256：
   ```bash
   cat ~/.cache/camoufox/repo_cache.json   # repos[0].versions[0] 里有 url / sha256 / asset_size
   ```

2. 用 GitHub 加速镜像下载（ghfast.top 实测可用；直连 632MB 会断）：
   ```bash
   curl -sL -o /tmp/camoufox.zip "https://ghfast.top/https://github.com/daijro/camoufox/releases/download/<tag>/<asset>.zip"
   ```

3. 校验 SHA256：
   ```bash
   sha256sum /tmp/camoufox.zip   # 必须与 repo_cache.json 中 sha256 一致
   ```

4. 解压到 `~/.cache/camoufox/browsers/<repo>/<version-hash>/`：
   - 版本目录名 = repo_cache 里的 `asset` 名去掉前缀，如 `152.0.4-beta.28-924f3109`
   - **repo 子目录必须有**：路径是 `browsers/official/<version-hash>/`，不是 `browsers/<version-hash>/`（xhs 报 "official/stable is not installed" 就是因为目录层级不对）
   - zip 解压后是平铺文件（camoufox-bin、omni.ja 等直接在该目录），不要多套一层同名目录

5. 写 version.json + config.json：
   ```bash
   echo '{"version": "152.0.4", "build": "beta.28"}' > <dir>/version.json
   # config.json 在 ~/.cache/camoufox/config.json：
   {"active_version": "browsers/official/152.0.4-beta.28-924f3109"}
   ```

6. 验证激活：
   ```bash
   /opt/hermes/.venv/bin/python3 -c "from camoufox.multiversion import get_active_path; print(get_active_path())"
   # 应输出版本目录路径；None = config/目录没对上
   ```

### ⚠️ 第三坑（最隐蔽）：COMPAT_FLAG 缺失会清空整个缓存目录

`camoufox_path()`（pkgman.py 728 行附近）在 `~/.cache/camoufox/` 存在但**没有 `.0.5_FLAG` 文件**时，会把**整个 INSTALL_DIR 删掉重建**（config.json + browsers 全部清空）。手动部署后必须：

```bash
touch ~/.cache/camoufox/.0.5_FLAG
```

否则：`get_active_path()` 第一次验证是好的，但一旦跑 `camoufox_path()`（xhs login 会走）→ 缓存被清 → 下次报 "not installed"。**症状是"刚装好验证通过，一登录就说不存在"**。

### ⚠️ 第四坑：camoufox-bin 无执行权限（EACCES）

zip 解压后 `camoufox-bin` 默认没有执行位，启动报 `EACCES`：

```bash
chmod +x ~/.cache/camoufox/browsers/official/<version-hash>/camoufox-bin
```

### ⚠️ 第五坑：headless 容器缺 GTK3 —— 无 root 也能装（apt 重定向 + deb 解压 + LD_LIBRARY_PATH）

camoufox 启动需要系统 GTK3 库（`libgtk-3.so.0`）。无 root 容器里 `apt-get update` 会因无法写 `/var/lib/apt/lists` 失败，但**可以重定向 apt 状态目录到 /tmp 再下载 deb 包**，解压到用户目录即可，全程不需要 root：

```bash
# 1. update（重定向 lists/cache 到 /tmp，避开 /var/lib 写权限）
mkdir -p /tmp/aptlists/partial /tmp/aptcache/archives/partial
apt-get -o Dir::State::Lists=/tmp/aptlists -o Dir::Cache=/tmp/aptcache update

# 2. download（download 模式只是把 .deb 拉到当前目录，不需要 root）
mkdir -p /tmp/aptdl && cd /tmp/aptdl
apt-get -o Dir::State::Lists=/tmp/aptlists -o Dir::Cache=/tmp/aptcache \
  -o Dir::Cache::Archives=/tmp/aptdl download \
  libgtk-3-0t64 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 libxrender1 libxtst6 libepoxy0

# 3. 解压到用户目录
mkdir -p ~/.local/gtk-libs && for f in *.deb; do dpkg-deb -x "$f" ~/.local/gtk-libs/; done

# 4. 跑 xhs 前导出（每次 shell 都要）
export LD_LIBRARY_PATH=~/.local/gtk-libs/usr/lib/x86_64-linux-gnu
```

**包名坑**：Debian trixie 里 GTK3 包名是 `libgtk-3-0t64`（t64 迁移改名），不是 `libgtk-3-0`（后者报 "no candidate"）。缺的 8 个包：libgtk-3-0t64 + libxcomposite1/libxdamage1/libxfixes3/libxrandr2/libxrender1/libxtst6/libepoxy0（其余 GTK 依赖系统已有）。`libcloudproviders`/`libXinerama` 缺失可容忍，不影响加载。

**验证用 ldd 而不是直接跑二进制**：`camoufox-bin --version` 在容器里会挂起/超时；用
`LD_LIBRARY_PATH=... ldd <dir>/libmozgtk.so | grep -iE 'gtk|not found'`，核心库（libgtk-3/libgdk-3/libepoxy）全解析即就绪。

**沙箱 EPERM**：容器缺 user namespace 权限时启动报 `Sandbox: CanCreateUserNamespace() clone() failure: EPERM`，需禁沙箱（`--no-sandbox`）。xhs-cli 若未透传该参数、camoufox 仍起不来，最后兜底：

```bash
xhs login --cookie "<从浏览器 F12 Network 复制的 Cookie 字符串>"
```

### ⚠️ 第二坑修正：uBlock Origin 扩展下载 451

camoufox 启动时会从 `addons.mozilla.org` 下载 uBlock Origin（`camoufox/addons.py` 中 `DefaultAddons.UBO`），GFW 下返回 **451 Client Error**。**但这是非致命警告**——`maybe_download_addons()` 的 try/except 会打印 "Failed to download and extract UBO" 后继续，登录流程照常往下走。

**❌ 不要预置空目录"绕过"**：addons.py 里目录存在会 append 到 addons_list，随后 `confirm_paths()` 检查该目录必须有 `manifest.json`——空目录会抛 `InvalidAddonPath`，反而导致失败。**正确做法是让 addons 目录保持不存在**（下载失败被吞掉、addons_list 为空、confirm_paths([]) 通过）。

真正绕不过去的是 camoufox 本身的问题（GTK3 缺失见第五坑的无 root 方案；沙箱 EPERM 见上），UBO 451 可以忽略。只有当 camoufox 仍因容器限制起不来时才用 cookie 登录兜底。

## 其他已知限制

- xsec_token 机制：不能裸 note_id 读，先 search 拿完整 URL/ID 再 read
- 高频请求触发验证码，每次操作间隔 2-3 秒
