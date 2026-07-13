# Provider 实际模型目录重构计划

## 目标

重构 Provider、实际模型和虚拟模型之间的关系：

- Provider 负责集中定义其提供的实际模型及价格。
- 虚拟模型只保存实际模型的有序引用，不再重复保存价格和显式优先级。
- Dashboard 中所有实际模型统一展示为 `<provider>/<model>`，例如 `zai/glm-5.2`。
- SQLite 保存每次调用实际使用的 Provider、模型和价格快照，确保历史费用可解释。
- 整体工作拆成三个顺序合并、可独立验收的 PR。

## 已确认的设计决策

- `config.toml` 继续作为配置真源，SQLite 只负责调用历史持久化。
- 实际模型的内部身份始终保存为结构化的 `{ provider, model }`；`<provider>/<model>` 只用于展示，禁止依赖 `/` 反向解析身份。
- 实际模型价格归属于 Provider 下的模型定义。
- 虚拟模型中的模型数组顺序就是路由优先级，运行时生成 `priority = index + 1`。
- Sticky 模式只保存一个结构化 `pinned_model: ModelRef | null`，它表示模型链中的一个实际模型引用。
- 删除仍被虚拟模型引用的 Provider 或实际模型时必须拒绝操作，并列出引用它的虚拟模型。
- 实际模型重命名不做隐式级联；第一版按“新建模型、切换引用、删除旧模型”处理。
- Provider 基础设置和实际模型编辑使用两个独立弹窗。
- 不兼容旧版配置格式，不实现旧配置自动迁移。
- 不兼容旧版 SQLite schema，不编写增量迁移链；开发者手动重建本地数据库。
- 程序不得擅自删除已有数据库，应在 schema 不兼容时给出明确错误和重建说明。
- 调用记录保存四类价格快照，不增加 `config_revision`。
- 四类价格均为可选值；存在时必须非负。未配置与显式配置 `0` 是不同状态。
- 未配置的价格快照写入 `NULL`，费用计算时按 `0` 参与计算；显式配置 `0` 时快照写入 `0`。
- README、设计文档和示例配置必须随对应 PR 同步更新，不集中拖到最后。

## 目标配置格式

```toml
[providers.zai]
type = "anthropic"
api_key = "${ZAI_API_KEY}"
base_url = "https://api.z.ai/api/anthropic"

[providers.zai.models."glm-5.2"]
input_price_per_million = 1.0
output_price_per_million = 4.0
cache_read_price_per_million = 0.1
cache_write_price_per_million = 1.25

[providers.deepseek]
type = "anthropic"
api_key = "${DEEPSEEK_API_KEY}"
base_url = "https://api.deepseek.com/anthropic"

[providers.deepseek.models."deepseek-v4-pro"]

[models.opus-router]
pinned_model = { provider = "zai", model = "glm-5.2" }
models = [
  { provider = "zai", model = "glm-5.2" },
  { provider = "deepseek", model = "deepseek-v4-pro" },
]
```

## 目标领域模型

```text
ProviderDef
├── type / api_key / base_url / timeout / limits
└── models: dict[str, ActualModelDef]

ActualModelDef
└── input/output/cache-read/cache-write prices

VirtualModelDef
├── pinned_model: ModelRef | null
└── models: list[ModelRef]

ModelRef
├── provider
└── model

ModelRef + ProviderDef + ActualModelDef + array index
                         ↓
               ResolvedProviderConfig
                         ↓
                       Router
```

---

## PR 1：调用价格快照与复合实际模型统计

建议分支：`feature/model-pricing-persistence`

建议标题：`feat: persist provider model pricing snapshots`

### 范围

本 PR 不修改配置格式，只调整调用持久化、统计语义和实际模型展示，使其可以独立合并。

### 后端与数据库

- [ ] 在 `calls` 表增加以下价格快照字段：
  - [ ] `input_price_per_million REAL`
  - [ ] `output_price_per_million REAL`
  - [ ] `cache_read_price_per_million REAL`
  - [ ] `cache_write_price_per_million REAL`
- [ ] 更新 `CallStore.record()`，显式接收并写入四类价格。
- [ ] 非流式请求成功后，把实际使用模型的四类价格写入调用记录。
- [ ] 流式请求成功后，把实际使用模型的四类价格写入调用记录。
- [ ] 失败调用没有实际成功模型时，价格快照保持 `NULL`，不伪造为 `0`。
- [ ] 保留现有 `cost_usd` 最终计算结果。
- [ ] 修改真实模型统计 SQL，使用 `provider_name + provider_model` 复合分组。
- [ ] 确保不同 Provider 下的同名模型不会合并统计。
- [ ] Metrics API 返回独立的 `provider`、`model` 字段。
- [ ] Metrics API 不返回拼接后的 `display_name`，展示名统一由 Dashboard 生成。
- [ ] 明确旧数据库不兼容；检测到缺失字段时给出可操作的重建提示。
- [ ] 不自动删除或覆盖已有 `calls.db`。
- [ ] 价格配置在运行时保留 `float | None` 语义，不能在持久化前把缺失价格提前归一化为 `0`。
- [ ] 费用计算将 `None` 视为 `0`，同时保留快照中的 `NULL`。

### Dashboard

- [ ] 更新真实模型统计类型，包含 `provider` 与 `model`。
- [ ] 真实模型图表、统计列表和筛选项显示 `<provider>/<model>`。
- [ ] 调用详情显示 `<provider>/<model>`。
- [ ] 提供统一的 `formatActualModel(provider, model)` 展示函数，避免各组件自行拼接。
- [ ] 不从展示字符串解析 Provider 或模型名。

### 测试

- [ ] 测试非流式调用保存四类价格快照。
- [ ] 测试流式调用保存四类价格快照。
- [ ] 测试未配置价格时快照为 `NULL`，费用计算按 `0` 处理。
- [ ] 测试显式配置 `0` 时快照为 `0`，不与 `NULL` 混淆。
- [ ] 测试失败调用的价格字段为 `NULL`。
- [ ] 测试非流式 failover 保存最终成功模型的 Provider、模型和价格，而不是首选失败模型的数据。
- [ ] 测试流式首字节前 failover 保存最终成功模型的 Provider、模型和价格。
- [ ] 断言 failover 调用的 `cost_usd` 使用最终成功模型的价格快照计算。
- [ ] 测试两个 Provider 提供同名模型时分别统计。
- [ ] 测试真实模型 Metrics API 的返回结构。
- [ ] 测试全新数据库创建后的完整 schema。
- [ ] 测试旧 schema 被识别并返回明确的手动重建提示。
- [ ] 测试旧 schema 检测失败后原数据库文件及已有内容保持不变。
- [ ] 测试 Dashboard 类型检查和生产构建。

### 文档

- [ ] 更新 README 的调用记录与费用说明。
- [ ] 更新 `docs/design.md` 的 SQLite schema、费用计算和实际模型身份说明。
- [ ] 明确开发环境需要手动重建旧数据库。

### 验收标准

- [ ] 每条成功调用都能追溯 Provider、模型、Token、四类价格快照和最终费用；未配置价格明确记录为 `NULL`，并能解释 `cost_usd` 的计算结果。
- [ ] 调价后历史记录的价格快照不会随当前配置变化。
- [ ] 同名模型按 Provider 正确区分。
- [ ] 后端测试、Ruff、格式、ty 和 Dashboard 构建通过。

---

## PR 2：Provider 实际模型目录与虚拟模型引用

建议分支：`refactor/provider-model-catalog`

建议标题：`refactor: move actual models into providers`

依赖：PR 1 已合并。

### 配置领域模型

- [ ] 新增 `ActualModelDef`，集中保存四类价格。
- [ ] 在 `ProviderDef` 中新增 `models: dict[str, ActualModelDef]`。
- [ ] 新增只包含 `provider` 与 `model` 的 `ModelRef`。
- [ ] 将虚拟模型配置改为 `models: list[ModelRef]`。
- [ ] 删除虚拟模型引用上的四类价格字段。
- [ ] 删除配置文件中的显式 `priority`；数组顺序决定优先级。
- [ ] 使用单一的 `pinned_model: ModelRef | null`，不再保存独立的 `pinned_provider`。
- [ ] 将原始配置对象和运行时解析后的 `ProviderConfig` 明确分层。
- [ ] 通过 `(provider, model)` 建立实际模型索引。
- [ ] 解析时合并 Provider 连接配置、实际模型价格和数组优先级。
- [ ] 保持 Router 消费完整的运行时 `ProviderConfig`，不让路由层反查原始配置。

### 配置校验

- [ ] 校验每个 `ModelRef.provider` 都存在。
- [ ] 校验每个 `ModelRef.model` 都定义在对应 Provider 下。
- [ ] 校验同一虚拟模型不能重复引用相同的 `(provider, model)`。
- [ ] 校验 Provider 下的实际模型名非空且在该 Provider 内唯一。
- [ ] 校验四类价格均可省略；存在时必须为非负数。
- [ ] Sticky 模式校验 `pinned_model` 非空，并且完整的 `{ provider, model }` 引用位于模型链中。
- [ ] 空 Provider 模型目录允许保存。
- [ ] 虚拟模型必须至少选择一个实际模型。
- [ ] 未知字段和旧版 `[[models.<name>.providers]]` 格式返回清晰的配置错误。
- [ ] 底层配置解析使用结构化异常，不在可复用解析逻辑中直接 `sys.exit()`。

### 引用完整性

- [ ] 删除 Provider 前检查所有虚拟模型引用。
- [ ] 删除实际模型前检查所有虚拟模型的模型链和结构化 `pinned_model`。
- [ ] 被引用时拒绝删除，并返回引用该对象的虚拟模型名称。
- [ ] 后端校验必须独立于 Dashboard，直接调用 API 也不能写入悬空引用。
- [ ] 第一版不提供实际模型原地重命名接口。
- [ ] 删除保护比较现有配置与候选配置；必须先单独保存引用移除，再允许删除 Provider 或实际模型。

### 配置 API 与热重载

- [ ] 更新 `GET /api/config` 返回新规范结构并继续脱敏 API key。
- [ ] 更新 `GET /api/config/providers`，包含 Provider 的实际模型目录。
- [ ] 更新 `GET /api/config/models`，返回有序 `ModelRef` 和单一结构化 `pinned_model`。
- [ ] 更新 `PUT /api/config` 的规范化、密钥保留和引用校验。
- [ ] 固定删除保护的 HTTP 契约：
  - [ ] 状态码为 `HTTP 409 Conflict`。
  - [ ] 响应包络为 `{"error": {...}}`。
  - [ ] `error.code = "provider_in_use" | "model_in_use"`。
  - [ ] `error.provider` 始终提供。
  - [ ] `error.model` 只在删除实际模型时提供；删除 Provider 时省略该字段，不返回 `null`。
  - [ ] `error.referenced_by: string[]` 列出引用它的虚拟模型。
- [ ] TOML 写回只生成目标新格式。
- [ ] 在触碰现有文件前完成候选配置校验、TOML 序列化验证和运行时配置构建。
- [ ] 候选配置准备完成后，先原子写回 TOML，再切换 Router。
- [ ] 写盘、运行时切换或日志重配置任一步失败时，回滚文件与运行时状态，确保两者仍为旧配置。
- [ ] 为写盘失败、候选构建失败、运行时切换失败和日志重配置失败增加回滚测试。
- [ ] 每个回滚测试断言 TOML 内容、Router 配置和日志配置仍为旧状态，且没有遗留临时文件。
- [ ] 不实现旧配置自动迁移或兼容读取。

### Dashboard 数据层与功能适配

- [ ] 更新 TypeScript 的 `ProviderConfig`、`ActualModelConfig`、`ModelRef` 和 `VirtualModelConfig`。
- [ ] 更新配置 normalize、draft、dirty check 和 PUT payload。
- [ ] 更新前端引用完整性校验。
- [ ] 虚拟模型页移除价格输入。
- [ ] 虚拟模型页移除自由输入的模型名。
- [ ] 使用一个组合选择器选择实际模型，标签为 `<provider>/<model>`。
- [ ] 选择器选项按 Provider 分组。
- [ ] 添加引用时只创建结构化 `{ provider, model }`。
- [ ] 拖动顺序保存为 `models` 数组顺序。
- [ ] Pin 保存为一个完整的结构化 `ModelRef`，不拆分为两个配置字段。
- [ ] 当前虚拟模型已选择的实际模型不能重复选择。
- [ ] 消费固定的 `provider_in_use` / `model_in_use` 错误契约并展示 `referenced_by`。
- [ ] 本 PR 完成虚拟模型页面的全部功能切换；PR 3 不再重复修改其数据结构、选择规则或校验行为。

### 数据库集成

- [ ] 调用成功时使用解析后的 `ActualModelDef` 价格生成 PR 1 定义的价格快照。
- [ ] 确保配置目录调价只影响后续调用，不改写历史记录。

### 测试

- [ ] 测试新 TOML 格式加载。
- [ ] 测试 Provider 下多个实际模型。
- [ ] 测试同一实际模型被多个虚拟模型引用。
- [ ] 测试数组顺序正确生成运行时优先级。
- [ ] 测试未知 Provider、未知模型和重复引用。
- [ ] 测试结构化 `pinned_model` 的加载、写回和 Sticky 校验。
- [ ] 测试被引用 Provider/模型的删除保护。
- [ ] 分别测试删除 Provider 和实际模型时的 HTTP 409、响应包络、字段省略规则与 `referenced_by`。
- [ ] 测试 Provider 下空模型名被拒绝。
- [ ] 测试配置 API 读写和热重载。
- [ ] 测试旧配置明确失败且错误信息可操作。
- [ ] 测试价格从 Provider 模型目录进入调用记录。
- [ ] 测试 Dashboard 类型检查和生产构建。

### 文档与示例

- [ ] 将 `config.toml.example` 完整切换到新格式。
- [ ] 更新 README 的 Provider、实际模型和虚拟模型配置示例。
- [ ] 更新 `docs/design.md` 的领域模型、配置结构、解析流程和引用完整性规则。
- [ ] 明确这是 breaking change，不提供旧配置兼容。

### 验收标准

- [ ] 实际模型与价格只在 Provider 下定义一次。
- [ ] 虚拟模型只包含有序的实际模型引用和一个结构化 `pinned_model`。
- [ ] 任意悬空引用都无法通过后端校验或写入磁盘。
- [ ] Router 的 sticky、failover、熔断、冷却和流式行为保持现有语义。
- [ ] 后端测试、Ruff、格式、ty 和 Dashboard 构建通过。

---

## PR 3：Dashboard Provider 模型管理体验

建议分支：`feature/provider-model-dashboard`

建议标题：`feat: redesign provider model management`

依赖：PR 2 已合并。

### Provider 卡片

- [ ] 将 Provider 列表行改为与虚拟模型页面一致的卡片布局。
- [ ] 卡片展示 Provider 名称、类型、密钥状态和简化后的 Base URL。
- [ ] 卡片小字展示实际模型数量与模型名。
- [ ] 模型较多时显示有限数量并追加“还有 N 个”。
- [ ] 卡片提供“添加模型”“设置”“删除”操作。
- [ ] 无实际模型时显示明确的空状态。

### Provider 设置弹窗

- [ ] 保留现有 Provider 基础设置字段。
- [ ] Provider 设置弹窗不直接承担实际模型表单。
- [ ] 保留 API key 脱敏值、留空保留和新 Provider 必填规则。
- [ ] 保留限流、队列、超时和熔断覆盖配置。

### 实际模型弹窗

- [ ] 点击“添加模型”打开空白实际模型弹窗。
- [ ] 点击卡片中的实际模型名打开编辑弹窗。
- [ ] 弹窗显示统一展示名 `<provider>/<model>`。
- [ ] 新建实际模型时允许填写模型名和四类价格。
- [ ] 编辑已有实际模型时模型名只读，只允许修改四类价格。
- [ ] 模型改名严格使用“新建模型、切换引用、删除旧模型”流程，不在编辑弹窗内伪装成原地重命名。
- [ ] 校验模型名非空且在同一 Provider 下唯一。
- [ ] 校验价格为空或非负数。
- [ ] 已被引用的模型不允许直接重命名。
- [ ] 删除被引用模型时展示引用它的虚拟模型并保持数据不变。
- [ ] 删除未被引用模型前显示确认弹窗。

### 虚拟模型页面

- [ ] 在 PR 2 已完成的功能基础上打磨引用行布局，不改变数据契约和校验规则。
- [ ] 优化 `<provider>/<model>` 长标签、分组选项和空状态的可读性。
- [ ] Provider 或模型数量较多时保证选择器尺寸和滚动体验可用。
- [ ] 保留现有拖动排序动画和交互。

### 交互与可访问性

- [ ] 弹窗支持 Escape 关闭和遮罩关闭。
- [ ] 删除、引用冲突和保存结果使用现有确认框与 Toast。
- [ ] 键盘焦点进入弹窗并在关闭后合理恢复。
- [ ] 小屏布局下卡片、模型名称和操作按钮保持可用。
- [ ] 长 Provider 名和长模型名不破坏布局。

### 测试与验证

- [ ] 覆盖 Provider 卡片摘要生成逻辑。
- [ ] 覆盖添加、编辑、删除实际模型的 store 行为。
- [ ] 覆盖引用冲突时的数据保持行为。
- [ ] 复用 PR 2 的组合选择、去重和 Pin 功能测试，不在本 PR 重复建立第二套状态逻辑。
- [ ] 运行 Dashboard TypeScript 检查和生产构建。
- [ ] 对 Provider、虚拟模型和调用详情页面进行人工视觉检查。

### 文档

- [ ] 更新 README 的 Dashboard 配置流程。
- [ ] 更新 `docs/design.md` 的 Dashboard 信息架构和删除保护交互。
- [ ] 如界面变化影响现有截图或示例，同步更新对应内容。

### 验收标准

- [ ] Provider 页面是 Dashboard 内管理实际模型的唯一入口；用户仍可直接编辑作为配置真源的 `config.toml`。
- [ ] Provider 卡片无需打开弹窗即可看见已配置模型摘要。
- [ ] 虚拟模型页面只能从已有实际模型目录中选择。
- [ ] 页面中实际模型统一展示为 `<provider>/<model>`。
- [ ] 用户无法通过 Dashboard 产生重复引用或悬空引用。
- [ ] Dashboard 构建通过，并完成主要页面人工视觉检查。

---

## PR 执行与 Git 约束

- [ ] 三个 PR 按 PR 1 → PR 2 → PR 3 顺序开发和合并。
- [ ] 每个 PR 从最新主分支创建独立语义化分支。
- [ ] 开始修改前检查当前目录、分支和工作区状态。
- [ ] 不在 `main` 或 `master` 上直接开发。
- [ ] 每个 PR 只包含自身范围内的代码、测试和文档。
- [ ] 不做无关格式化、重构、依赖升级或锁文件更新。
- [ ] 不在本地把功能分支直接合并到主分支。
- [ ] 未经用户明确确认不执行 `git push`。
- [ ] PR 使用 Squash and merge 或 Rebase and merge，不使用普通 merge commit。

## 每个 PR 的通用验证

```bash
uv run pytest
uv run ruff check src tests
uv run ruff format --check src tests
uv run ty check src tests

cd dashboard
bun run build
```

- [ ] Python 命令全部通过 `uv` 执行。
- [ ] JavaScript/TypeScript 命令全部通过 `bun` 执行。
- [ ] 如全项目存在与当前 PR 无关的既有错误，记录具体文件和诊断，不擅自扩大修改范围。
- [ ] 执行 `git diff --check`。
- [ ] 检查 `git status`、`git diff`；如有暂存内容再检查 `git diff --cached`。
- [ ] 最终汇报实际修改文件、关键命令、测试结果、文档状态、分支、提交和未完成事项。

## 整体完成标准

- [ ] Provider、实际模型、虚拟模型的职责边界与配置格式一致。
- [ ] `<provider>/<model>` 在 Dashboard、Metrics 和调用详情中统一展示。
- [ ] 实际模型身份在内部、API 和数据库中始终保留独立 Provider 与模型字段。
- [ ] 历史调用保存价格快照，调价不会改变旧记录的解释结果。
- [ ] Provider/模型删除保护同时由后端和 Dashboard 执行。
- [ ] 三个 PR 均包含与行为变更匹配的测试和文档。
- [ ] README、设计文档、示例配置和 Dashboard 行为不存在相互矛盾的描述。
