#!/bin/zsh
set -eu

project_root="$(cd "$(dirname "$0")/../.." && pwd)"
config_file="$project_root/.ios/wda.env"
python_bin="$project_root/.venv/bin/python"

if [[ -f "$config_file" ]]; then
  source "$config_file"
fi

device_udid="${IOS_DEVICE_UDID:-}"
team_id="${IOS_TEAM_ID:-}"
wda_project="$project_root/tools/WebDriverAgent/WebDriverAgent.xcodeproj"
failed=0

check_command() {
  local name="$1"
  if command -v "$name" >/dev/null 2>&1; then
    print "[OK] $name: $(command -v "$name")"
  else
    print "[缺失] 找不到 $name"
    failed=1
  fi
}

print "== 算鸟 iPhone 运行环境检查 =="
check_command xcodebuild
check_command xcrun
check_command curl
if [[ -x "$python_bin" ]]; then
  print "[OK] 项目 Python: $python_bin"
elif command -v python3 >/dev/null 2>&1; then
  python_bin="$(command -v python3)"
  print "[OK] Python: $python_bin"
else
  print "[缺失] 找不到 Python"
  failed=1
fi

if [[ -d "$wda_project" ]]; then
  print "[OK] WebDriverAgent: $wda_project"
else
  print "[缺失] WebDriverAgent 源码不存在：$wda_project"
  failed=1
fi

if [[ -z "$device_udid" ]]; then
  print "[缺失] .ios/wda.env 中未设置 IOS_DEVICE_UDID"
  failed=1
else
  details="$(xcrun devicectl device info details --device "$device_udid" 2>&1 || true)"
  if [[ "$details" == *"tunnelState: connected"* ]]; then
    device_name="$(print -r -- "$details" | awk -F': ' '/marketingName:/ {print $2; exit}')"
    tunnel_ip="$(print -r -- "$details" | awk '/tunnelIPAddress:/ {print $NF; exit}')"
    print "[OK] iPhone: ${device_name:-$device_udid}"
    print "[OK] CoreDevice 隧道: $tunnel_ip"
  else
    print "[失败] iPhone 未连接或 CoreDevice 隧道未建立：$device_udid"
    failed=1
  fi
fi

if [[ -z "$team_id" ]]; then
  print "[缺失] .ios/wda.env 中未设置 IOS_TEAM_ID"
  failed=1
else
  xcode_preferences="$(defaults export com.apple.dt.Xcode - 2>/dev/null || true)"
  if print -r -- "$xcode_preferences" | grep -q ">$team_id<"; then
    print "[OK] Xcode 已配置开发团队: $team_id"
  else
    print "[失败] Xcode Accounts 中没有 Team $team_id"
    failed=1
  fi

  profile_ready=0
  profile_dir="$HOME/Library/Developer/Xcode/UserData/Provisioning Profiles"
  for profile in "$profile_dir"/*.mobileprovision(N); do
    profile_team="$(
      security cms -D -i "$profile" 2>/dev/null \
        | plutil -extract TeamIdentifier.0 raw -o - - 2>/dev/null \
        || true
    )"
    if [[ "$profile_team" == "$team_id" ]]; then
      profile_ready=1
      break
    fi
  done
  if [[ "$profile_ready" -eq 1 ]]; then
    print "[OK] WDA provisioning profile: $team_id"
  else
    print "[提示] 尚无 Team $team_id 的 provisioning profile；首次构建将由 Xcode 自动创建"
  fi
fi

if [[ "$failed" -ne 0 ]]; then
  print "\n环境尚未就绪。请修复以上项目后再次运行。"
  exit 1
fi

print "\n本地工具、设备和证书检查通过。"
print "下一步：运行 scripts/ios/run.sh --dry-run"
