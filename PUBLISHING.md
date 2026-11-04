# 插件市场投稿

依据2026-11-04查阅的 [AstrBot 官方发布说明](https://docs.astrbot.app/dev/star/plugin-publish.html)和[开发指南](https://docs.astrbot.app/dev/star/plugin-new.html)。市场入口使用 AstrBot Cloud，旧插件集合仓库或历史 Issue 流程不作为当前提交依据。

## 提交步骤

1. 使用专用 GitHub 仓库：https://github.com/ryujou/astrbot_plugin_bangdream_birthday 。插件文件应直接位于仓库根目录，不上传整个机器人部署目录。
2. 确认代码与随包资源的分发许可，上传经过测试的插件源码；`metadata.yaml` 的 repo 应与仓库一致。
3. 注册或登录 [AstrBot Cloud](https://cloud.astrbot.app/publish)，按发布表单填写仓库及插件信息并提交。AstrBot 插件市场中的“提交我的插件”也指向该入口。
4. 以平台实际审核结果确认是否收录；创建仓库、上传 ZIP 或写好 README 都不代表已上架。

发布表单需要登录，本文未核实登录后才显示的额外字段或审核条件。

## 官方规定与建议

| 项目 | 官方说明及本项目处理 |
| --- | --- |
| GitHub 托管、Cloud 账号 | 官方发布流程所需；专用仓库已经创建；市场需通过 Cloud 提交并审核 |
| metadata.yaml | 使用真实标识、作者、描述、语义化版本和 repo；本项目另声明 aiocqhttp 与 AstrBot 版本范围，补充 short_desc、tags |
| ZIP 大小 | 官方上限16 MB；打包时检查实际字节数 |
| 依赖 | requirements.txt 列出实际运行依赖；浏览器安装要求写入 README |
| 测试、错误处理、持久化 | 官方开发原则；测试入口随源码提供，状态存储使用插件数据目录 |
| Ruff | 官方开发指南要求提交前格式化；本项目使用独立开发工具，不加入运行依赖 |
| 第三方资源 | 保留适用的版权及许可说明；不附带字体与游戏星星素材，数据来源见 THIRD_PARTY_NOTICES.md |
| 仓库清理 | .gitignore 排除缓存、虚拟环境、日志与运行数据；发布包不包含群头像、私人配置或测试运行产物 |
| logo.png | 官方可选，建议方形256×256；不是必需项，本项目未为凑齐文件加入占位 Logo |

原创代码与原创文档采用 MIT，见 LICENSE。字体与装饰图由用户自行配置，不随公开源码分发。

## README 参考

参考了以下项目的文档组织方式，未引入其代码：

- [astrbot_plugin_babirthday](https://github.com/laopanmemz/astrbot_plugin_babirthday)：安装、用法及配置标识说明。
- [astrbot_plugin_skyland](https://github.com/kelai141/astrbot_plugin_skyland)：功能、安装、快速使用、配置与依赖边界。
- [astrbot_plugin_autocheckin](https://github.com/Morturi/astrbot_plugin_autocheckin)：浏览器依赖、配置表和运行说明。

本插件是后台自动化，不照搬这些项目的聊天命令、订阅功能或不存在的配置项。
