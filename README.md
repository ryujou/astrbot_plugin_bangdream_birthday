# BanG Dream! 生日管理

为 QQ 同好群自动设置生日群名和应援色头像框，支持 BanG Dream! 角色及声优。

**AstrBot ≥4.28、<5 · OneBot v11 / aiocqhttp · 无需配置大模型**

[安装](#安装) · [快速开始](#快速开始) · [配置](#配置) · [常见问题](#常见问题) · [开发与测试](#开发与测试)

## 功能

- 内置119条角色、声优生日；各群独立设置生日时区。
- 自动群名：`邦邦同好群` → `邦邦同好群@千石由乃生日快乐`。
- 头像使用角色应援色圆环、Happy Birthday、日期和主名字；声优沿用对应角色配色。
- 同日多位已知角色或声优每小时轮换头像，群名显示完整名单。
- 无生日时恢复保存的原头像与基础群名，重启避免重复换图。
- 可导入 XLSX、UTF-8 CSV 补充或替代内置生日表。

本插件通过后台配置和定时任务运行，**没有聊天指令；可按群开启修改后的文字提示，默认关闭**。独立安装即可运行，不依赖蔚蓝档案插件。

## 安装

### 环境要求

| 项目 | 要求 |
| --- | --- |
| AstrBot | `>=4.28,<5`；已在4.28.2环境测试 |
| 消息平台 | `aiocqhttp`，使用支持群名和群头像操作的 OneBot v11 实现；已验证 NapCat |
| QQ 权限 | 机器人账号能修改目标群的群名和群头像 |
| Python 依赖 | `requirements.txt` 中的 openpyxl、Playwright |
| 头像渲染 | AstrBot 同一运行用户及 Python 环境中的 Chromium |

不声明支持 QQ 官方机器人适配器或其他消息平台。

### 从仓库或 ZIP 安装

在 AstrBot WebUI → 插件 → 安装插件中，选择从链接安装，填入：

```text
https://github.com/ryujou/astrbot_plugin_bangdream_birthday
```

也可以选择从文件安装并上传完整插件 ZIP。市场收录后才可从市场搜索安装。

启用头像功能前，在 AstrBot 实际使用的 Python 环境中安装浏览器：

```sh
python -m playwright install chromium
```

Linux 缺少 Chromium 系统库时，可由有系统管理权限的用户执行 `python -m playwright install-deps chromium`。Docker 部署须在 AstrBot 容器内准备依赖；仅在宿主机安装无效。依赖已满足时不需要重复安装。

## 快速开始

1. 打开插件配置，在“分群生日设置”添加一条群规则。
2. 填写 **QQ 平台实例 ID** 和 **纯数字群号**。平台实例 ID 来自 AstrBot 消息平台配置，不是 UMO；群号不是 `GroupMessage:...`。
3. 选择本群时区，保留“使用 BanG Dream! 内置生日表”。默认东京时间；需要按北京时间切换则选 `Asia/Shanghai`。
4. 开启“启用本群生日自动化”，按需开启自动群名和生日头像。
5. 保存配置。插件同步当天状态，之后每30秒检查一次。

默认没有群规则，不会自动操作任何群。仅需自动群名时，可以保持头像功能关闭。

## 配置

| 字段 | 默认值 | 说明 |
| --- | --- | --- |
| `group_rules` | 空列表 | 每群一条；同一平台下群号不能重复 |
| `enabled` | `false` | 启用本群自动化 |
| `platform_id` | `qq_private` | 修改为自己的 QQ 平台实例 ID |
| `group_id` | 空 | 目标群的纯数字群号 |
| `timezone` | `Asia/Tokyo` | 本群生日时区 |
| `name_enabled` | `true` | 自动更新群名 |
| `avatar_enabled` | `false` | 自动添加生日应援色边框 |
| `use_builtin_calendar` | `true` | 使用邦邦内置生日表 |
| `import_names` | 空列表 | 本群使用的已上传文件名，含扩展名 |
| `import_files` | 空列表 | 插件级文件上传入口，支持 `.xlsx`、`.csv` |

### 导入生日表

先通过“导入生日表”上传，再把完整文件名填入该群的“使用的导入文件”。CSV 示例：

```csv
姓名,生日
千石由乃,11-04
自定义角色,02-29
```

也支持“月份、日期、角色名”列、标题行、多工作表，以及 `11月4日`、Excel 日期等格式。空白生日跳过，相同姓名和日期去重；非法日期或没有有效生日会报错。关闭内置生日表后可以仅使用导入表。日期中的年份不参与每年生日匹配。

内置姓名使用已保存的角色配色；未知姓名使用通用边框，同日未知姓名合并显示。

## 自动更新规则

| 场景 | 行为 |
| --- | --- |
| 当天一人生日 | 更新生日群名与该人的头像框 |
| 当天多人生日 | 群名列出完整名单；全部为已知姓名时，头像按名单顺序从当地零点每小时轮换 |
| 当天无生日 | 恢复保存的原头像与基础群名 |
| 重启、保存配置 | 同步当天；已成功应用的相同头像状态不重复上传 |
| 上传失败 | 保留旧状态，下一轮检查重试 |
| 单群异常 | 记录错误，继续处理其他群 |

基础群名取当前群名第一个 `@` 之前的内容。原本含有 `@` 的群名也会按此规则处理。

### 停用与恢复

需要恢复原头像时，先关闭 `avatar_enabled`，**保持本群 `enabled` 和插件开启**，保存并等待恢复完成，再关闭本群或整个插件。直接关闭插件或本群自动化会停止任务，不会执行恢复。

关闭自动群名只会停止后续群名修改，不会主动恢复当前群名。

## 外观和修改提示

以下配置按群独立设置。默认使用 Cooper Black 英文字体、荆南波波黑中文字体、角色应援色与白描边，并显示星星拖尾。底部使用中文姓名，字号106、字间距6px，长姓名自动缩小。文字为空时不显示对应文字；头像始终保持圆心居中，文字自动缩小以适应圆环。

通过插件级 `asset_files` 上传自己的字体或装饰图，然后在该群 `font_file`、`cjk_font_file` 或 `decoration_file` 填写完整文件名。也可放入本插件持久化数据目录并填写相对路径。字体支持 TTF/OTF/WOFF/WOFF2，装饰图支持 PNG/JPEG/WEBP/SVG；内置素材使用 builtin: 前缀；将文件配置清空即可使用系统字体或关闭装饰图。

模板变量：`{base}` 基础群名、`{name}` 首位姓名、`{names}` 全部姓名、`{display_name}` 显示名、`{character}` 对应角色、`{date}` 格式化日期、`{year}`、`{month}`、`{day}`、`{spacing}` 多人时空格。日期格式例如 `{year}.{month:02d}.{day:02d}`。`date_format` 仅接受年月日变量。

`base_group_name` 为空时保存首次读取的群名（首个 @ 之前），后续使用保存值，避免自定义后缀叠加。保存位置为 `group_names/<平台>/<群号>.txt`。需要更换基础群名时直接填写配置。

`notify_enabled` 默认关闭。开启后群名或头像修改成功才发送一次文字提示，同一次同步合并为一条；重复检查不发送。`notify_template` 默认 `已更新{action}。`，额外支持 `{action}` 和 `{group_name}`。空白模板不发送。通知发送失败会记录错误，已完成的修改保留，不因通知失败重复修改或补发。只更改通知配置不会重新生成头像。

| 配置 | 默认值 |
| --- | --- |
| `base_group_name` | `""` |
| `birthday_name_format` | `"{base}@{names}{spacing}生日快乐"` |
| `normal_name_format` | `"{base}"` |
| `name_separator` | `"&"` |
| `date_format` | `"{year}.{month}.{day}"` |
| `greeting_template` | `"Happy Birthday"` |
| `date_template` | `"{date}"` |
| `label_template` | `"{names}"` |
| `subtitle_template` | `""` |
| `font_family` | `"Arial, sans-serif"` |
| `cjk_font_family` | `"\"Noto Sans CJK SC\", \"Microsoft YaHei\", sans-serif"` |
| `font_file` | `"builtin:CooperBlack.ttf"` |
| `cjk_font_file` | `"builtin:KNBobohei-Bold.ttf"` |
| `font_weight` | `900` |
| `greeting_size` | `96` |
| `date_size` | `60` |
| `label_size` | `106` |
| `label_spacing` | `6` |
| `subtitle_size` | `64` |
| `color` | `""` |
| `ring_colors` | `[]` |
| `greeting_color` | `""` |
| `date_color` | `""` |
| `label_color` | `""` |
| `subtitle_color` | `""` |
| `outline_color` | `"#FFFFFF"` |
| `outline_width` | `8` |
| `background_color` | `"#FFFFFF"` |
| `show_avatar` | `true` |
| `avatar_radius` | `400` |
| `top_angle` | `0` |
| `bottom_angle` | `0` |
| `decoration_file` | `"builtin:star-trail.svg"` |
| `decoration_size` | `56` |
| `notify_enabled` | `false` |
| `notify_template` | `"已更新{action}。"` |

升级不会覆盖已保存的配置。已有安装若保留空字体、空装饰或英文显示名，需将对应项改为上述默认值。

外观配置或本地素材改变后，下次加载配置会刷新当天头像。颜色使用 #RRGGBB；空色号跟随角色配色，ring_colors 留空自动生成三色。

## 常见问题

**保存后没有变化？**

检查插件和本群开关、平台实例 ID、群号、群权限及所选时区。当天无生日且没有待恢复的生日头像时，不会更换头像。加载失败时查看 AstrBot 日志中的具体错误。

**群名能改，头像失败？**

确认 `avatar_enabled` 已开启、账号具有群头像权限，以及 Chromium 和系统依赖安装在正确的 AstrBot 运行环境。QQ 操作失败时，插件会记录错误并重试。

**小头像中的日期读不清？**

QQ 会生成40、100像素等缩略图。主名字和配色优先供小图识别，完整祝福和日期需点开大图查看。

**人工换了群头像，为什么还原到以前的图？**

插件使用首次保存的 `original.jpg` 作为原头像，不会自动将人工新换的头像覆盖为基准。需要变更基准时，先关闭自动化，再用确认的原图替换对应文件。

**更新插件会丢生日表或原头像吗？**

运行数据保存在 `data/plugin_data/astrbot_plugin_bangdream_birthday/`，不放在插件代码目录。卸载时若要保留原图与上传表格，不要选择删除持久化数据。

## 数据与网络

配置：`data/config/astrbot_plugin_bangdream_birthday_config.json`。

每群文件位于本插件数据目录的 `avatars/<平台>/<群号>/`：`original.jpg` 是原图，`birthday.png` 是生成结果，`active.json` 记录姓名、日期和模板版本。原图用于恢复，应妥善保留。

日常生成使用本地生日表、字体和 SVG 模板。首次获取原头像访问 QQ 头像地址，修改群名、头像通过已连接的 OneBot 客户端；不调用聊天模型或图片生成服务。

## 开发与测试

| 文件或函数 | 职责 |
| --- | --- |
| `calendar_from_rows` / `import_calendar` | 表格解析与日期校验 |
| `load_group_rules` / `group_name_for_day` | 配置合并与群名计算 |
| `render_portrait` / `portrait.html` | 浏览器渲染，不提交 QQ 更新 |
| `sync_group_portrait` | 原图、活动状态和 QQ 头像更新 |
| `BanGDreamBirthdayPlugin` | AstrBot 接入、后台任务生命周期与调度 |

QQ client 通过参数传入，解析和群名计算可独立测试。插件不导入其他生日插件，也不共享其配置或数据目录。修改头像模板并需要刷新当天头像时，应更新 `FRAME_VERSION`；插件版本号本身不会强制换图。

在已安装 AstrBot 和本插件依赖的 Python 环境中，从源码目录运行：

```sh
python tests/test_behavior.py .
ruff check main.py presentation.py tests
ruff format --check main.py presentation.py tests
```

26项测试覆盖生日输入格式、CSV/XLSX、非法日期、分群配置、头像轮换恢复、失败重试及调度异常分支。测试使用临时目录和模拟 QQ 客户端，不修改真实群头像；这不代表所有分支100%覆盖。默认样式已完成120名角色及声优的浏览器渲染检查。实群验证群名、头像提交、通知开关及去重；不等于未来日期的定时触发已验证。

反馈问题时请提供 AstrBot 版本、OneBot 实现、复现步骤及脱敏错误日志，不要附带登录凭据、原始群配置或私人头像。

## 来源与许可

非官方社区工具，与 BanG Dream! 官方无隶属关系。生日、角色色号与声优关系的来源记录在 [character_colors.json](character_colors.json)。内置字体与星星素材的来源和许可范围见第三方资源说明。

原创代码与原创文档采用 [MIT License](LICENSE)，允许使用、修改和再分发，需保留许可证及版权声明。MIT 同样允许商业使用；本项目的非盈利粉丝用途不构成对代码许可证的额外限制。

第三方字体、游戏素材与数据不纳入本项目 MIT 授权，仍适用各自的许可及权利归属，详见 [第三方资源说明](THIRD_PARTY_NOTICES.md)。

维护者投稿流程及当前发布条件见 [PUBLISHING.md](PUBLISHING.md)。
