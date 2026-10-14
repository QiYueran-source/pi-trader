
## 动态知识文件与路径

cronjob 是静态运行资产，`cronjob.yml` 和 `prompt.txt` 负责描述任务，不负责定义动态知识文档的内部治理规则。

任务需要读取或生成动态知识时：

- 可以在 prompt 中使用目录模板、日期变量、体系标识和查询协议；
- 运行时可以读取、生成和传递具体动态知识逻辑路径；
- prompt.txt和cronjob.yml中不应写死某个具体动态知识文件路径；
- 应加载 `knowledge-management`，遵守其文件类型、路由、逻辑路径和归档协议；


cronjob 自身的 `cronjob.yml`、`prompt.txt`、`delivery.json` 和运行时注册记录属于静态资产，不能因为动态知识归档而移动或改写。
