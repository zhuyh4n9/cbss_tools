# 激活盒子盒子PC Tool

## Requirement

- 请使用Python实现一个AC8267设备激活根据, 有UI界面
- UI分为3个部分
  - 菜单栏
    - 文件
      - 配置加载: 加载ini格式的配置信息
      - 配置导出: 导出配置信息为ini格式
      - 配置日志
        - 日志级别
        - 日志路径
      - 查看日志
    - 工具
      - 使用工具时，不允许用户进行其他操作
      - 锁定激活盒子
        - 显示效果
          - 弹出弹框
            - 提示输入128个hex字符或者选择一个64 Bytes的二进制文件
            - 下拉框: 需要执行锁定操作的激活盒子序列号
            - 确认按钮以及取消按钮
          - 点击确认后，执行lock命令
            - 激活成功则弹出成功提示框，否则提示失败
        - 解锁定激活盒子，与锁定激活盒子系统，唯一不同点在于解锁定激活盒子执行unlock锁命令
        - 激活激活盒子，与锁定激活盒子系统，唯一不同点在于解锁定激活盒子执行activate命令
        - 配置激活盒子，与锁定激活盒子系统，唯一不同点在于解锁定激活盒子执行config命令
    - 帮助
      - 使用方法: 显示工具得到使用方法，工具配置文件进行配置，请根据该文档实现初稿
    - 关于
      - 显示工具的如下信息:
        - 厂商信息: "Autochips Inc"
        - 版本信息
        - 其他: 根据配置文件进行显示
  - 激活盒子信息信息
    - 根据refresh_rate配置执行检测频率, 单位为次/每秒，默认为5
      - 检测方法: 通过snapshot命令 获取激活盒子的设备信息
      - 需要重点显示如下信息:
        - 激活盒子过期时间(北京时间)
          - 需要使用不同颜色区分，即将过期，正常，已过期三个状态，即将过期时间可以配置，默认如下
            - 过期时间 > 1 week  ==> 即将过期
          - 对应snapshot的expired_date字段
        - 剩余可激活设备数
          - 对应snapshot的counter字段
        - 已经激活设备个数
          - 对应snapshot结果的的authorized_device_num字段
        - 设备状态
          - 对应device status字段
            - bit 0代表是否锁定
            - bit 1代表是否冻住
            - bit 2代表当前设备是否支持由于安全原因被临时锁定
          - 各个bit含义支持灵活配置
        - 显示信息以及检测字段需要支持灵活配置

  - 待激活设备列表
    - 根据refresh_rate配置，定时进行刷新激活列表信息
    - 对于每一个设备显示如下信息
      - 设备的uuid
        - 通过uuid命令获取
      - Serial Number
        - 通过adb获取serial number
      - 设备连接到PC的USB Port Id
      - 设备状态: 通过adb待激活设备status命令确认是否已经激活，根据激活执行结果判断是否成功
        - Authorization Success: 激活成功
        - Authorization Failed: 激活失败
        - Unauthorized: 设备未执行激活
        - Authorized: 设备已经执行激活
      - 执行激活按钮
        - 只允许Unauthorized状态设备进行激活
          - 执行如下操作:
            - 向待激活设备发起uuid命令，获取uuid
            - 向激活盒子发起sign命令, 获取uuid的签名
            - 向待激活设备发起activate, 将sign烧写到待激活平台
        - 弹出弹框提示激活状态
        - 激活期间不允许进行其他操作
    - 此外，还需要有一个按钮一键执行全部激活
      - 只对Unauthorized状态设备进行激活
      - 弹出弹框提示激活状态
      - 激活期间不允许进行其他操作

## ADB相关命令

### 约定

- 可以通过配置文件进行配置
  - 对于adb命令，配置文件中不包含 -s \<serial id\> 字段，执行时自动添加
- 所有的数据输入均为hex string
- 输出
  - 为了区分log输出以及结果输出，规定:
    - "[status]" 为前缀表示执行状态
      - "[status] 0", 表示成功
      - "[status] 1", 表示失败，将从配置文件中查找1代表的诊断信息
      - "[status] 1, xxx", 表示失败，将从配置文件中查找1代表的诊断信息, xxx为字符串，表示错误输出
    - "[result]" 为前缀表示结果输出，例如:
      - "[result] xxxxxxxx" 表示是uuid的结果输出为xxxxxx
    - 其他表示日志输出，与其他输出一并记录在执行日志即可
- 如何判断是否为激活盒子
  - 尝试激活盒子的snapshot命令，若执行成功，则认为是激活盒子
- 如何判断是否为待激活设备
  - 尝试待激活设备的uuid以及state命令，若执行成功，则认为是待激活设备

## 待激活设备的操作

- uuid命令
  - adb -s \<serial id> cbss_tool acquire_uuid
- activate命令
  - adb -s <待激活设备serial id> shell cbss_tool activate --sign \<sign hex\>
- state
  - adb -s \<serial id\> shell cbss_tool state
  - 结果为"Activated"表示已经激活，"Not activated" 表示未激活

## 激活盒子

- lock命令
  - adb -s \<serial id\> shell lock \<token hex\>
- unlock命令
  - adb -s \<serial id\> shell unlock \<token hex\>
- activate命令
  - adb -s \<serial id\> shell activate \<token hex\>
- sign命令
  - adb -s \<serial id\> shell sign \<uuid\>
  - 结果中包含签名信息
- config命令
  - adb -s \<serial id\> shell config \<config hex\>
- snapshot命令
  - adb -s \<serial id\> shell snapshot

## Notes

- 完成文件修改后请即使保存
- 注意缩进问题
- 测试文件请放在test/
- 配置文件放在config/
- 有效代码请放在src/
- 使用python3

## Update 1

- 请阅读CHECKPOINT_V1.0.md并基于现有代码增加如下功能
  - 工具栏选择中增加使设备wifi功能
    - 选择该功能后要求输入:
      - SSID
      - password
      - 选择加密方式(可选项: wpa2/wpa3, 默认为wpa2)
    - 连接wifi设计adb命令如下(可配置):
      - 打开wifi station: adb shell cmd wifi set-wifi-enabled enabled
      - 关闭wifi station: adb shell cmd wifi set-wifi-enabled disabled
      - 连接对端热点:  cmd wifi connect-network \<SSID\> \<加密方式\> \<password\>

## Update 2

- 请基于当前代码增加获取安全日志功能, 相关命令如下:
  - 获取token: adb shell cbss_tools diagnostic token {prefix}
  - 获取TA诊断信息: shell cbss_tools diagnostic trusted_service {prefix}
  - 获取激活记录: shell cbss_tools diagnostic authorization {prefix}
- 完成这些命令后将产生如下文件
  - 一些以prefix开头的日志文件，格式如下:
    - {prefix}_{idx}, 例如 {prefix}_0, {prefix}_1, etc...
    - 签名文件，名称为: {prefix}_prof.sign
    - 文件路径产生: /sdcard/CbssDiagnostic/
- prefix要求
  - 唯一性: 使用 "{类型}_{时间戳}" 作为prefix
- 行为面要求:
  - 增加诊断下拉栏
  - 在诊断下拉栏中增加3个选项分别为:
    - 获取token记录
    - 获取TA诊断信息
    - 获取激活记录
  - 用户点击后，提示用户选择文件保存路径
  - 通过adb pull 命令将产生的文件导出
  - 完成导出后，使用adb shell rm {文件} 命令将这些文件删除

## Update 3

- 请帮忙在stress_test/下编写单独的压力测试脚本，对激活盒子设备进行压力测试，要求如下
  - 对如下指令进行压力测试
    - diagnostic_token
      - 执行authenticator_sign > 100 次后后随机执行
    - diagnostic_trusted_service
      - 执行authenticator_sign > 100 次后后随机执行
    - diagnostic_authorization
      - 执行authenticator_sign > 100 次后后随机执行
    - authenticator_sign
      - 随机产生64长度的hex string, 作为uuid进行测试
      - 对该命令进行压力测试，测试压力 > 10K次
      - 使用pubkey/pub.pem(P256公钥)对获取签名进行验证
  - 测试日志保存在stress_log/

## Update 4

- 对现有功能进行check-point, readme/目录下
- 请实现如下功能:
  - 点击WIFI链接后，执行如下操作
    - 通过adb将认证器连接到WIFI
    - sleep 1s
    - 对认证器进行ping操作，若所有节点均ping失败，则认为wifi不可用, 默认测试列表如下，要求可配置:
      - ntp.ntsc.ac.cn
      - ntp1.aliyun.com
      - www.baidu.com
      - www.google.com
      - 8.8.8.8
      - oss-cn-hangzhou.aliyuncs.com
      - obs.cn-north-4.myhuaweicloud.com
      - dns.alidns.com
      - dns.pub
    - 测试需要有进度条
    - 成功/失败均弹出弹框
  - 状态信息中增加如下显示
    - 时间状态:
      - 从snapshot中time_status字段获取
    - 网络状态:
      - 每10s(可配置)启动一次ping操作，探测wifi状态。该行为不能block其他操作
      - ntp.ntsc.ac.cn 若无法ping通，需要进行提示
      - 显示连通百分比
