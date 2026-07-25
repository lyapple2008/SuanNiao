#!/bin/zsh
set -eu

project_root="$(cd "$(dirname "$0")/../.." && pwd)"
config_file="$project_root/.ios/wda.env"
wda_project="$project_root/tools/WebDriverAgent/WebDriverAgent.xcodeproj"
wda_root="$project_root/tools/WebDriverAgent"
derived_data="$project_root/.ios/DerivedData"
wda_log="$project_root/.ios/wda.log"
identity_patch="$project_root/scripts/ios/wda-profile-identity.patch"
python_bin="$project_root/.venv/bin/python"

if [[ ! -f "$config_file" ]]; then
  print -u2 "缺少 $config_file，请从 .ios/wda.env.example 复制并填写。"
  exit 2
fi
source "$config_file"

: "${IOS_DEVICE_UDID:?请在 .ios/wda.env 中设置 IOS_DEVICE_UDID}"
: "${IOS_TEAM_ID:?请在 .ios/wda.env 中设置 IOS_TEAM_ID}"
: "${IOS_WDA_BUNDLE_ID:?请在 .ios/wda.env 中设置 IOS_WDA_BUNDLE_ID}"

if [[ ! -d "$wda_project" ]]; then
  print -u2 "缺少 WebDriverAgent 源码：$wda_project"
  exit 2
fi

if [[ ! -x "$python_bin" ]]; then
  python_bin="$(command -v python3 || true)"
fi
if [[ -z "$python_bin" ]]; then
  print -u2 "找不到 Python；请先创建 .venv 或安装 Python 3.10+"
  exit 2
fi

if git -C "$wda_root" apply --check "$identity_patch" >/dev/null 2>&1; then
  git -C "$wda_root" apply "$identity_patch"
elif ! git -C "$wda_root" apply --reverse --check "$identity_patch" >/dev/null 2>&1; then
  print -u2 "无法应用 WDA 证书消歧补丁，请检查 $identity_patch"
  exit 2
fi

device_details="$(xcrun devicectl device info details --device "$IOS_DEVICE_UDID")"
tunnel_ip="$(print -r -- "$device_details" | awk '/tunnelIPAddress:/ {print $NF; exit}')"
if [[ -z "$tunnel_ip" ]]; then
  print -u2 "无法获取 iPhone CoreDevice 隧道地址。请连接、解锁并信任此 Mac。"
  exit 2
fi
wda_url="http://[$tunnel_ip]:8100"

mkdir -p "$derived_data"
print "正在为设备 $IOS_DEVICE_UDID 构建并启动 WebDriverAgent…"
print "日志：$wda_log"

xcodebuild \
  -project "$wda_project" \
  -scheme WebDriverAgentRunner \
  -destination "id=$IOS_DEVICE_UDID" \
  -derivedDataPath "$derived_data" \
  "DEVELOPMENT_TEAM=$IOS_TEAM_ID" \
  CODE_SIGN_STYLE=Automatic \
  "PRODUCT_BUNDLE_IDENTIFIER=$IOS_WDA_BUNDLE_ID" \
  -allowProvisioningUpdates \
  -allowProvisioningDeviceRegistration \
  test >"$wda_log" 2>&1 &
wda_pid=$!

cleanup() {
  if kill -0 "$wda_pid" 2>/dev/null; then
    kill "$wda_pid" 2>/dev/null || true
    wait "$wda_pid" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

ready=0
for attempt in {1..90}; do
  if curl --noproxy '*' --connect-timeout 1 --max-time 2 -fsS "$wda_url/status" >/dev/null 2>&1; then
    ready=1
    break
  fi
  if ! kill -0 "$wda_pid" 2>/dev/null; then
    if grep -q "Developer App Certificate is not trusted" "$wda_log"; then
      print -u2 "WebDriverAgent 已安装，但 iPhone 尚未信任开发者证书。"
      print -u2 "请在 iPhone 打开：设置 → 通用 → VPN 与设备管理 → 开发者 App → 信任。"
      print -u2 "完成后重新运行 scripts/ios/run.sh --dry-run"
      exit 2
    fi
    print -u2 "WebDriverAgent 构建或启动失败："
    tail -n 60 "$wda_log" >&2
    exit 2
  fi
  sleep 2
done

if [[ "$ready" -ne 1 ]]; then
  print -u2 "等待 WebDriverAgent 超时。最近日志："
  tail -n 60 "$wda_log" >&2
  exit 2
fi

print "WebDriverAgent 已就绪：$wda_url"
cd "$project_root"
PYTHONPATH="$project_root/src" "$python_bin" -m suanniao play \
  --platform ios \
  --wda-url "$wda_url" \
  "$@"
