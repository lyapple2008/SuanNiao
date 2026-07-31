WebDriverAgent（通常简称 **WDA**）是 iOS 自动化测试领域最核心的组件之一。**如果你使用过 Appium、Airtest、ATX、Facebook WDA、Maestro（部分场景）等 iOS 自动化方案，几乎都会间接使用到 WDA。**它本质上是在 iPhone 上运行的一个 HTTP Server，负责把外部发送的自动化命令转换成 iOS 的 XCTest API 调用。([GitHub][1])

## 一、WebDriverAgent 是什么？

官方定义：

> WebDriverAgent 是一个运行在 iOS 设备上的 WebDriver Server，它利用 Apple 的 XCTest Framework 来控制 iPhone 或 Simulator。([GitHub][1])

可以理解成下面这个结构：

```text
                 HTTP/WebDriver 请求
                         │
                         ▼
                Appium / Python / Java
                         │
                    WebDriver 协议
                         │
                         ▼
                WebDriverAgent(WDA)
                 (运行在 iPhone 上)
                         │
                   XCTest Framework
                         │
                         ▼
                  iOS Accessibility
                         │
                         ▼
                     被测 App
```

也就是说：

**WDA = WebDriver 协议 + XCTest 的桥梁。**

---

# 二、为什么需要 WebDriverAgent？

苹果并没有开放：

```text
tap(x, y)
findElement()
swipe()
inputText()
```

这种供外部程序直接调用的 API。

苹果官方提供的是：

```text
XCTest
```

它只能在 Xcode 的测试环境中运行。

例如：

```swift
let app = XCUIApplication()
app.buttons["Login"].tap()
```

这段代码只能放在 XCTest 中。

那么：

> Python 如何点击按钮？
>
> Java 如何点击按钮？
>
> Appium 怎么点击按钮？

答案就是：

全部发 HTTP 请求给 WDA。

例如：

```http
POST /wda/tap/0
{
    "x":100,
    "y":300
}
```

WDA 收到以后：

```
HTTP
    ↓
XCTest API
    ↓
XCUIElement.tap()
```

所以：

**WDA 的真正作用就是把 HTTP 命令转换成 XCTest 调用。**

---

# 三、WebDriverAgent 能做什么？

几乎所有 UI 自动化能力都支持。

例如：

### 点击

```text
tap
```

↓

```swift
element.tap()
```

---

### 输入文字

```text
sendKeys
```

↓

```swift
textField.typeText()
```

---

### 滑动

```text
swipe
```

↓

```swift
element.swipeUp()
```

---

### 查找元素

```text
findElement
```

↓

```swift
app.buttons["OK"]
```

---

### 获取页面结构

```text
/source
```

返回：

```xml
Application
    Window
        Button
        Label
        TextField
```

Appium Inspector 就是依赖这个接口显示元素树。

---

### 获取截图

```
GET /screenshot
```

返回 Base64 图片。

---

### 获取元素属性

例如：

```
enabled

visible

selected

value

label

frame
```

这些都来自 Accessibility。

---

# 四、WDA 工作流程

例如：

Python：

```python
driver.find_element(...).click()
```

发生了什么？

```
Python
    │
    ▼
Appium Client
    │
    ▼
HTTP Request
    │
    ▼
Appium Server
    │
    ▼
HTTP Request
    │
    ▼
WebDriverAgent
    │
    ▼
XCTest
    │
    ▼
iPhone
```

整个流程可以表示为：

```text
Python
    │
    ▼
Appium
    │
    ▼
WDA
    │
    ▼
XCTest
    │
    ▼
Accessibility
```

---

# 五、WDA 是怎么运行起来的？

WDA 本身其实就是一个 Xcode 工程。

里面有：

```
WebDriverAgent.xcodeproj
```

真正运行的是：

```
WebDriverAgentRunner
```

它实际上是一个 XCTest Target。

启动方式：

```
Xcode
    ↓
Run Test
    ↓
WebDriverAgentRunner
```

设备上会看到：

```
Automation Running...
```

说明 XCTest 已经启动。

同时：

```
8100端口
```

开始监听 HTTP 请求。

例如：

```
http://localhost:8100/status
```

返回：

```json
{
    "value": {
        "ready": true
    }
}
```

---

# 六、为什么 WDA 能控制别人的 App？

很多人第一次接触都会疑惑。

答案是：

**因为 XCTest 拥有系统级 UI Automation 权限。**

它不是：

```
App A
    │
    ▼
控制 App B
```

而是：

```
XCTest
      │
      ▼
Accessibility
      │
      ▼
整个系统 UI
```

因此可以：

* SpringBoard
* Safari
* 设置
* 微信
* 支付宝
* 自己的 App

全部可以操作（受系统自动化权限限制）。

---

# 七、WDA 与 Appium 的关系

很多人误以为：

```
Appium == WebDriverAgent
```

实际上不是。

关系如下：

```text
          Appium
             │
             ▼
     XCUITest Driver
             │
             ▼
      WebDriverAgent
             │
             ▼
          XCTest
```

可以认为：

* **Appium**：跨平台自动化框架
* **XCUITest Driver**：Appium 的 iOS 驱动
* **WebDriverAgent**：真正运行在 iPhone 上执行命令的代理
* **XCTest**：Apple 官方测试框架

所以：

> Appium 本身并不会直接控制 iPhone。

真正点击按钮的是：

```
WebDriverAgent
```

---

# 八、WDA 的典型使用方法

## 方法一：直接使用 Appium（最常见）

Python 示例：

```python
from appium import webdriver

driver = webdriver.Remote(
    "http://127.0.0.1:4723",
    {
        "platformName": "iOS",
        "automationName": "XCUITest",
        "deviceName": "iPhone",
        "bundleId": "com.demo.app"
    }
)

driver.find_element("accessibility id", "Login").click()
```

整个过程中：

```
Python
    ↓
Appium
    ↓
WDA
```

用户通常无需直接操作 WDA。

---

## 方法二：直接调用 WDA HTTP 接口

例如：

```
GET /status
```

```
GET /source
```

```
POST /session
```

```
POST /wda/tap
```

很多自动化平台都会直接访问这些接口，而不是通过 Appium。

---

## 方法三：Python WDA 客户端

社区提供了 `facebook-wda` 等客户端，可以直接连接 WDA，而不经过 Appium。([GitHub][2])

例如：

```python
import wda

c = wda.Client("http://127.0.0.1:8100")

c(text="登录").tap()
```

流程变成：

```
Python
    │
    ▼
WDA Client
    │
    ▼
WebDriverAgent
```

相比 Appium 少了一层转发，适合一些轻量级自动化场景。

---

# 九、WDA 的优缺点

**优点：**

* Apple 官方 XCTest 支持，稳定性较高。
* 可控制真机和模拟器。
* 支持点击、滑动、输入、截图、元素树获取等完整 UI 自动化能力。
* 已成为 Appium iOS 自动化事实上的标准组件。([GitHub][1])

**局限性：**

* 首次部署需要 Xcode、开发者证书和代码签名配置。
* 每次 iOS 或 Xcode 大版本升级，都可能需要适配新的 WDA 版本。
* 性能受 XCTest 和 Accessibility 框架限制，复杂页面获取元素树可能较慢。([GitHub][3])

## 十、与你之前关注的 iOS UI 自动化的关系

结合你之前咨询过的 **Windows/Android/iOS UI 自动化测试**，可以把几种主流方案对应起来：

| 平台              | 底层自动化引擎                       |
| --------------- | ----------------------------- |
| Android Appium  | UiAutomator2 / Espresso       |
| iOS Appium      | **WebDriverAgent + XCTest**   |
| Android Maestro | UiAutomator                   |
| iOS Maestro     | **WebDriverAgent（通过 XCTest）** |
| Windows FlaUI   | UI Automation (UIA)           |

因此，在 **iOS UI 自动化** 中，**WebDriverAgent 的地位相当于 Android 的 UiAutomator2**：它是负责与操作系统交互、执行点击、滑动、查找元素等操作的底层执行引擎，而 Appium、Maestro 等框架则是在其之上提供更友好的自动化接口。

[1]: https://github.com/facebookarchive/WebDriverAgent?utm_source=chatgpt.com "GitHub - facebookarchive/WebDriverAgent: A WebDriver server for iOS that runs inside the Simulator. · GitHub"
[2]: https://github.com/openatx/facebook-wda?utm_source=chatgpt.com "GitHub - openatx/facebook-wda: Facebook WebDriverAgent Python Client Library (not official) · GitHub"
[3]: https://github.com/appium/WebDriverAgent/security?utm_source=chatgpt.com "Overview · appium/WebDriverAgent · GitHub"
