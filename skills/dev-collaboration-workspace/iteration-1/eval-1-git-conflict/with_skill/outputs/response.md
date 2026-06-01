# Git 合并冲突解决指导

## 场景识别

你遇到了 **Git 合并冲突**——执行 `git merge main` 后，有 3 个文件因双方都做了修改而产生冲突：
- `package.json`
- `src/api/user.ts`
- `src/config/database.conf`

下面按步骤帮你逐一解决。

---

## 第 1 步：确认当前状态

先运行以下命令，确认冲突文件列表和分支状态：

```bash
git status
```

你应该会看到类似输出：

```
You have unmerged paths.
  (fix conflicts and run "git commit")

Unmerged paths:
  (use "git add <file>..." to mark resolution)
        both modified:   package.json
        both modified:   src/api/user.ts
        both modified:   src/config/database.conf
```

再看一下最近的提交记录，了解两边各自的改动意图：

```bash
git log --oneline -5          # 当前分支的最近提交
git log --oneline -5 main     # main 分支的最近提交
```

---

## 第 2 步：逐个分析冲突

对每个冲突文件，查看具体的冲突内容：

```bash
git diff package.json
git diff src/api/user.ts
git diff src/config/database.conf
```

冲突标记的含义：
- `<<<<<<< HEAD` 到 `=======` 之间是**你当前分支**的改动
- `=======` 到 `>>>>>>> main` 之间是 **main 分支**的改动

---

## 第 3 步：解决每个文件的冲突

### 文件 1：`package.json`

**冲突类型**：双方都修改了依赖配置（最常见的情况）

**解决策略**：合并两边的依赖，保留所有有效项。

1. 打开 `package.json`，找到冲突标记
2. **保留两边新增的依赖**——不要丢弃任何一方添加的包
3. 如果同一个包两边都改了版本号：
   - 选择更新的版本（通常向后兼容）
   - 如果不确定兼容性，先保留 main 分支的版本，后续测试验证
4. 合并 `scripts`、`devDependencies` 等其他字段时同样遵循"保留双方改动"原则
5. 确保 JSON 格式正确（逗号、括号匹配）

**示例**：

假设冲突内容如下：
```json
<<<<<<< HEAD
    "axios": "^1.6.0",
    "zustand": "^4.5.0"
=======
    "axios": "^1.7.0",
    "dayjs": "^1.11.0"
>>>>>>> main
```

正确合并结果：
```json
    "axios": "^1.7.0",
    "zustand": "^4.5.0",
    "dayjs": "^1.11.0"
```

解释：`axios` 取更新版本 `^1.7.0`，`zustand` 来自你的分支保留，`dayjs` 来自 main 保留。

**验证**：
```bash
# 确认 JSON 语法正确
node -e "JSON.parse(require('fs').readFileSync('package.json','utf8'))"

# 安装依赖验证兼容性
npm install
```

---

### 文件 2：`src/api/user.ts`

**冲突类型**：双方都修改了同一函数或代码区域

**解决策略**：理解两边的修改意图，合并保留所有有效逻辑。

1. 打开 `src/api/user.ts`，找到冲突标记
2. 仔细阅读两边的改动，理解各自的目的：
   - HEAD（你的分支）做了什么改动？（比如：新增了某个 API 调用、修改了参数类型）
   - main 分支做了什么改动？（比如：修复了 bug、增加了错误处理）
3. 合并策略：
   - 如果两边改的是**不同函数**——保留两边全部代码
   - 如果两边改的是**同一函数的不同部分**——合并两处改动
   - 如果两边改的是**同一行/同一逻辑**——判断哪个更正确，或融合两者

**示例**：

假设冲突内容如下：
```typescript
<<<<<<< HEAD
export async function getUserProfile(userId: string) {
  const response = await api.get(`/users/${userId}`);
  return response.data;
}
=======
export async function getUserProfile(userId: string, options?: { cache?: boolean }) {
  const cacheKey = `user_${userId}`;
  if (options?.cache && cacheStore.has(cacheKey)) {
    return cacheStore.get(cacheKey);
  }
  const response = await api.get(`/users/${userId}`);
  return response.data;
}
>>>>>>> main
```

正确合并结果（保留 main 的缓存功能）：
```typescript
export async function getUserProfile(userId: string, options?: { cache?: boolean }) {
  const cacheKey = `user_${userId}`;
  if (options?.cache && cacheStore.has(cacheKey)) {
    return cacheStore.get(cacheKey);
  }
  const response = await api.get(`/users/${userId}`);
  return response.data;
}
```

**验证**：
```bash
# TypeScript 类型检查
npx tsc --noEmit

# 如果有测试
npm test -- --testPathPattern=user
```

---

### 文件 3：`src/config/database.conf`

**冲突类型**：双方都修改了配置文件

**解决策略**：保留两边的配置项，检查是否有冲突的配置值。

1. 打开 `src/config/database.conf`，找到冲突标记
2. 分析两边的改动：
   - 如果两边添加了**不同的配置项**——全部保留
   - 如果两边修改了**同一个配置项的值**——需要判断哪个是正确的
   - 如果一边新增、一边删除了某配置项——确认删除是否合理

**示例**：

假设冲突内容如下：
```conf
<<<<<<< HEAD
host=localhost
port=5432
database=myapp_dev
max_connections=50
=======
host=localhost
port=5432
database=myapp_dev
connection_timeout=30
ssl_mode=require
>>>>>>> main
```

正确合并结果：
```conf
host=localhost
port=5432
database=myapp_dev
max_connections=50
connection_timeout=30
ssl_mode=require
```

解释：两边的基础配置相同，你新增了 `max_connections`，main 新增了 `connection_timeout` 和 `ssl_mode`，全部保留。

**验证**：
```bash
# 检查配置文件语法（如果有对应工具）
# 手动检查是否有重复的 key 或格式错误
```

---

## 第 4 步：验证所有冲突已解决

```bash
# 确认没有残留的冲突标记
grep -rn "<<<<<<" package.json src/api/user.ts src/config/database.conf
grep -rn ">>>>>>>" package.json src/api/user.ts src/config/database.conf
grep -rn "=======" package.json src/api/user.ts src/config/database.conf
# 以上命令都应该没有输出
```

---

## 第 5 步：标记解决并完成合并

```bash
# 将解决后的文件加入暂存区
git add package.json
git add src/api/user.ts
git add src/config/database.conf

# 完成合并提交
git commit
```

Git 会自动生成类似 "Merge branch 'main' into xxx" 的提交信息，你可以直接使用或修改。

---

## 第 6 步：最终验证

```bash
# 确认分支状态干净
git status

# 运行项目测试（如果有）
npm test

# 启动项目验证功能正常
npm run dev
```

---

## 注意事项

1. **不要直接用 `git checkout --theirs` 或 `--ours` 一键覆盖**——这样会丢失另一方的改动
2. **package.json 合并后务必运行 `npm install`**——确保依赖安装正常
3. **TypeScript 文件合并后务必运行类型检查**——防止类型不兼容
4. **配置文件合并后检查是否有重复 key**——重复 key 可能导致运行时行为不确定
5. 如果某个文件的冲突太复杂无法判断，可以用 `git diff :1:<文件>` 查看共同祖先版本，帮助理解改动的上下文

## 如果想放弃本次合并

如果你在解决过程中发现冲突太多或合并方向不对，可以中止：

```bash
git merge --abort
```

这会恢复到合并前的状态，不会丢失任何代码。
