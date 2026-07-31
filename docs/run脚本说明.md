这个脚本是“算鸟”项目的 iPhone 真机自动化启动器。

它完成两件事：

1. 在指定 iPhone 上构建、签名、安装并启动 WebDriverAgent（WDA）。
2. WDA 就绪后，启动项目的 Python 自动识别和点击程序，通过 WDA 控制 iPhone。

脚本入口：[scripts/ios/run.sh](/Volumes/tiger/Workspace/side-projects/2026/05_SuanNiao/scripts/ios/run.sh:1)

整体流程：

```text
读取 iOS 配置
  → 检查 WDA 和 Python
  → 应用签名补丁
  → 获取 iPhone 隧道地址
  → xcodebuild 构建并启动 WDA
  → 轮询 WDA /status
  → 启动 suanniao play
  → 退出时关闭 WDA/xcodebuild
```

## 1. Shell 环境与错误策略

[scripts/ios/run.sh:1](/Volumes/tiger/Workspace/side-projects/2026/05_SuanNiao/scripts/ios/run.sh:1)

```zsh
#!/bin/zsh
set -eu
```

- `#!/bin/zsh`：指定使用 zsh 执行脚本。
- `set -e`：普通命令失败时立即退出，避免带着错误状态继续运行。
- `set -u`：使用未定义变量时立即报错，避免因为变量为空而操作错误设备或目录。

## 2. 定位项目目录和相关文件

[scripts/ios/run.sh:4](/Volumes/tiger/Workspace/side-projects/2026/05_SuanNiao/scripts/ios/run.sh:4)

```zsh
project_root="$(cd "$(dirname "$0")/../.." && pwd)"
```

这里没有依赖“当前终端所在目录”，而是根据 `run.sh` 自己的位置计算项目根目录。因此下面两种调用方式都可以：

```bash
scripts/ios/run.sh
/完整路径/scripts/ios/run.sh
```

随后定义各类路径：

- `config_file`：iPhone UDID、Apple Team ID 等本地配置。
- `wda_project`：WDA 的 Xcode 工程。
- `wda_root`：WDA 源码仓库。
- `derived_data`：Xcode 编译缓存和产物目录。
- `wda_log`：WDA 构建、安装和运行日志。
- `identity_patch`：解决签名证书歧义的补丁。
- `python_bin`：优先使用项目虚拟环境中的 Python。

这些生成文件统一放在 `.ios/` 下，避免污染 WDA 源码目录。

## 3. 加载 iOS 配置

[scripts/ios/run.sh:13](/Volumes/tiger/Workspace/side-projects/2026/05_SuanNiao/scripts/ios/run.sh:13)

首先检查：

```text
.ios/wda.env
```

不存在时提示用户根据 `.ios/wda.env.example` 创建，然后退出。

```zsh
source "$config_file"
```

这会在当前 Shell 中执行配置文件。配置文件虽然叫 `.env`，实际使用的是 Shell 语法。

脚本要求下面三个变量不能为空：

```zsh
IOS_DEVICE_UDID
IOS_TEAM_ID
IOS_WDA_BUNDLE_ID
```

它们分别表示：

- `IOS_DEVICE_UDID`：目标 iPhone 的唯一设备标识。
- `IOS_TEAM_ID`：Xcode 登录的 Apple 开发团队 ID，用于代码签名。
- `IOS_WDA_BUNDLE_ID`：WDA Runner 使用的唯一 Bundle ID。

Bundle ID 需要唯一，因为 Xcode 要使用它创建开发签名和 provisioning profile。

## 4. 检查 WebDriverAgent 源码

[scripts/ios/run.sh:23](/Volumes/tiger/Workspace/side-projects/2026/05_SuanNiao/scripts/ios/run.sh:23)

脚本要求下面的 Xcode 工程存在：

```text
tools/WebDriverAgent/WebDriverAgent.xcodeproj
```

WebDriverAgent 是安装在 iPhone 上的 XCTest Runner，对外提供 HTTP 接口，例如：

- 获取屏幕截图。
- 获取窗口尺寸。
- 查询可访问性控件。
- 模拟点击。
- 创建自动化会话。

项目直接访问 WDA，不需要另外启动 Appium Server。

## 5. 选择 Python

[scripts/ios/run.sh:28](/Volumes/tiger/Workspace/side-projects/2026/05_SuanNiao/scripts/ios/run.sh:28)

脚本优先使用：

```text
.venv/bin/python
```

这样可以确保使用项目虚拟环境以及其中安装的依赖。

如果虚拟环境中的 Python 不存在或不可执行，则退回到：

```zsh
command -v python3
```

如果系统里也找不到 `python3`，脚本退出。

这里的提示要求 Python 3.10+，不过脚本本身只检查命令是否存在，没有实际检查版本号。

## 6. 自动应用 WDA 签名补丁

[scripts/ios/run.sh:36](/Volumes/tiger/Workspace/side-projects/2026/05_SuanNiao/scripts/ios/run.sh:36)

补丁文件是：

[scripts/ios/wda-profile-identity.patch](/Volumes/tiger/Workspace/side-projects/2026/05_SuanNiao/scripts/ios/wda-profile-identity.patch:1)

判断过程：

```text
补丁可以正向应用
  → 应用补丁

补丁不能正向应用，但可以反向应用
  → 说明补丁已经应用，什么也不做

正向和反向都无法检查通过
  → WDA 文件可能被其他方式修改，停止执行
```

因此这部分具有幂等性，多次运行不会重复打补丁。

补丁解决的问题是：Mac 钥匙串中可能存在多个显示名称相同的开发证书。如果仅把证书名称传给 `codesign`，可能产生“签名身份不明确”的问题。

补丁会：

1. 读取 WDA App 中的 `embedded.mobileprovision`。
2. 提取 provisioning profile 内实际使用的开发证书。
3. 计算证书的 SHA-1。
4. 把这个唯一 SHA-1 作为 `codesign` 的签名身份。

这样能确保 WDA 使用 provisioning profile 对应的准确证书重新签名。

## 7. 获取 iPhone CoreDevice 隧道地址

[scripts/ios/run.sh:43](/Volumes/tiger/Workspace/side-projects/2026/05_SuanNiao/scripts/ios/run.sh:43)

执行：

```zsh
xcrun devicectl device info details --device "$IOS_DEVICE_UDID"
```

`devicectl` 是 Xcode 提供的真机管理工具。脚本从输出中提取：

```text
tunnelIPAddress
```

这个地址是 Mac 通过 Xcode CoreDevice 隧道访问 iPhone 的地址。

如果没有获得地址，通常意味着：

- iPhone 没有连接 Mac。
- iPhone 没有解锁。
- iPhone 没有信任这台 Mac。
- 开发者模式没有启用。
- CoreDevice 隧道尚未建立。
- 配置的 UDID 不正确。

随后生成 WDA 地址：

```zsh
wda_url="http://[$tunnel_ip]:8100"
```

方括号说明这个地址按 IPv6 地址处理，端口为 WDA 默认使用的 `8100`。

这也是为什么项目不需要手动运行 `iproxy`。

## 8. 准备 Xcode 构建目录和日志

[scripts/ios/run.sh:51](/Volumes/tiger/Workspace/side-projects/2026/05_SuanNiao/scripts/ios/run.sh:51)

```zsh
mkdir -p "$derived_data"
```

创建：

```text
.ios/DerivedData
```

将 Xcode 编译产物固定放在项目里，可以：

- 复用构建缓存。
- 加快后续启动。
- 避免混入 Xcode 默认的全局 DerivedData。
- 方便清理和排查问题。

构建日志写入：

```text
.ios/wda.log
```

每次启动会重新覆盖这个日志文件。

## 9. 构建、签名、安装并启动 WDA

[scripts/ios/run.sh:55](/Volumes/tiger/Workspace/side-projects/2026/05_SuanNiao/scripts/ios/run.sh:55)

核心命令是：

```zsh
xcodebuild ... test
```

各参数作用如下：

- `-project "$wda_project"`  
  指定 WDA 的 Xcode 工程。

- `-scheme WebDriverAgentRunner`  
  构建 WDA 的 XCTest Runner。

- `-destination "id=$IOS_DEVICE_UDID"`  
  明确把程序安装到配置的那台 iPhone，而不是模拟器或其他设备。

- `-derivedDataPath "$derived_data"`  
  指定编译缓存与产物目录。

- `DEVELOPMENT_TEAM=$IOS_TEAM_ID`  
  使用指定 Apple 开发团队签名。

- `CODE_SIGN_STYLE=Automatic`  
  启用 Xcode 自动签名。

- `PRODUCT_BUNDLE_IDENTIFIER=$IOS_WDA_BUNDLE_ID`  
  覆盖 WDA Runner 的 Bundle ID，避免与其他开发者或现有安装冲突。

- `-allowProvisioningUpdates`  
  允许 Xcode 创建或更新 provisioning profile。

- `-allowProvisioningDeviceRegistration`  
  允许 Xcode在必要时把目标 iPhone 注册到开发团队。

- `test`  
  构建测试 Runner、签名、安装到 iPhone 并启动 XCTest。WDA 的 HTTP 服务也会随测试 Runner 启动。

命令末尾：

```zsh
>"$wda_log" 2>&1 &
```

表示：

- 标准输出和错误输出都写入 `.ios/wda.log`。
- `&` 让 `xcodebuild` 在后台运行。
- `$!` 保存后台进程 PID。

后台运行的原因是：脚本还需要继续检测 WDA，并启动 Python 主程序。

## 10. 注册退出清理逻辑

[scripts/ios/run.sh:68](/Volumes/tiger/Workspace/side-projects/2026/05_SuanNiao/scripts/ios/run.sh:68)

`cleanup()` 会先检查 `xcodebuild` 是否还活着：

```zsh
kill -0 "$wda_pid"
```

`kill -0` 不会真正发送终止信号，只用于检测进程是否存在。

如果还在运行，则：

1. `kill "$wda_pid"`：终止后台 `xcodebuild`。
2. `wait "$wda_pid"`：回收后台进程，避免留下僵尸进程。

```zsh
trap cleanup EXIT INT TERM
```

表示在以下情况执行清理：

- 脚本正常退出。
- 用户按 `Ctrl+C`。
- 脚本收到终止信号。
- Python 自动运行程序结束或报错。

所以 WDA/xcodebuild 的生命周期与这个脚本绑定，不会有意在脚本退出后继续常驻。

## 11. 等待 WDA 真正就绪

[scripts/ios/run.sh:76](/Volumes/tiger/Workspace/side-projects/2026/05_SuanNiao/scripts/ios/run.sh:76)

脚本最多检查 90 次：

```zsh
curl "$wda_url/status"
```

具体参数：

- `--noproxy '*'`：绕过系统代理。CoreDevice 地址是本机到 iPhone 的隧道，不应该经过 HTTP 代理。
- `--connect-timeout 1`：建立连接最多等待 1 秒。
- `--max-time 2`：整个 HTTP 请求最多等待 2 秒。
- `-f`：HTTP 4xx/5xx 视为失败。
- `-sS`：隐藏正常进度，但保留错误能力。
- 输出重定向到 `/dev/null`：这里只判断是否可访问，不关心响应内容。

请求成功说明 WDA 的 HTTP 服务已经可用。

每次失败后等待 2 秒。90 轮通常意味着约 3 分钟轮询时间；如果每次 HTTP 请求都耗尽 2 秒，极端情况下会更久。

## 12. 构建或启动失败时的处理

[scripts/ios/run.sh:82](/Volumes/tiger/Workspace/side-projects/2026/05_SuanNiao/scripts/ios/run.sh:82)

等待期间，脚本还会检查后台 `xcodebuild` 是否提前退出。

如果日志里出现：

```text
Developer App Certificate is not trusted
```

脚本会给出针对性提示：

```text
设置 → 通用 → VPN 与设备管理 → 开发者 App → 信任
```

这是个人或开发证书首次安装 WDA 时很常见的步骤。

如果不是证书信任问题，则输出 `.ios/wda.log` 最后 60 行，方便看到真正的 Xcode 构建、签名或安装错误。

如果 `xcodebuild` 一直活着，但 90 轮后 WDA 仍不可访问，则同样输出最后 60 行日志并退出。

## 13. 启动“算鸟”Python 自动操作程序

[scripts/ios/run.sh:102](/Volumes/tiger/Workspace/side-projects/2026/05_SuanNiao/scripts/ios/run.sh:102)

WDA 就绪后执行：

```zsh
cd "$project_root"

PYTHONPATH="$project_root/src" "$python_bin" -m suanniao play \
  --platform ios \
  --wda-url "$wda_url" \
  "$@"
```

这里：

- `cd "$project_root"`：保证截图、运行日志等相对路径都从项目根目录计算。
- `PYTHONPATH="$project_root/src"`：让 Python 可以直接导入 `src/suanniao`，不要求先把项目安装成 Python 包。
- `python -m suanniao play`：运行项目的自动游戏命令。
- `--platform ios`：选择 WDA 控制器，而不是 Android ADB。
- `--wda-url "$wda_url"`：把刚才检测成功的 WDA 地址传给 Python。

Python 程序随后会通过 WDA：

1. 创建自动化会话。
2. 获取 iPhone 截图。
3. 识别树枝和鸟。
4. 规划移动步骤。
5. 将截图像素坐标转换成 iPhone 逻辑坐标。
6. 发送点击操作。
7. 重复截图和规划，直到完成或遇到错误。

## 14. `"$@"` 的作用

最后的：

```zsh
"$@"
```

表示把调用 `run.sh` 时提供的所有参数原样传给 `suanniao play`。

例如：

```bash
scripts/ios/run.sh --dry-run
```

最终相当于：

```bash
python -m suanniao play \
  --platform ios \
  --wda-url http://[设备隧道地址]:8100 \
  --dry-run
```

`--dry-run` 仍然会：

- 构建并启动 WDA。
- 连接 iPhone。
- 获取截图。
- 识别棋盘。
- 计算解法。

但不会点击游戏或广告按钮，适合第一次验证环境和识别结果。

也可以传递其他参数：

```bash
scripts/ios/run.sh \
  --moves-per-plan 4 \
  --move-wait 0.6 \
  --time-limit 30
```

## 最终总结

这个脚本相当于把 iPhone 自动化所需的多步操作封装成一个命令：

```text
配置设备和签名
→ 修复 WDA 签名问题
→ 建立真机访问地址
→ 用 Xcode 编译和安装 WDA
→ 确认 WDA HTTP 服务可用
→ 运行算鸟识别、求解和点击程序
→ 结束时清理后台进程
```

日常建议先运行：

```bash
scripts/ios/doctor.sh
scripts/ios/run.sh --dry-run
```

确认环境和识别都正常后，再执行：

```bash
scripts/ios/run.sh
```