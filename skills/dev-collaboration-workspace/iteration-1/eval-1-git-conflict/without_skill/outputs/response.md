# Git 合并冲突解决方案

## 问题概述

执行 `git merge main` 后，以下三个文件产生了合并冲突：
- `package.json`
- `src/api/user.ts`
- `src/config/database.conf`

## 冲突原因分析

这三个文件在当前分支和 main 分支上都被修改了，Git 无法自动判断应该保留哪一方的改动，因此标记为冲突状态，需要人工介入解决。

## 通用解决步骤

### 第一步：查看冲突状态

```bash
# 确认哪些文件有冲突
git status

# 查看具体冲突内容
git diff
```

冲突文件中会出现如下标记：

```
<<<<<<< HEAD（当前分支的改动）
当前分支的内容
=======
main 分支的内容
>>>>>>> main
```

### 第二步：逐个解决冲突

下面针对每个文件给出具体的解决策略。

---

## 文件一：package.json

### 冲突特点

`package.json` 是项目依赖配置文件，冲突通常发生在：
- 两边都添加了不同的依赖包
- 同一依赖包版本号不同
- scripts 字段被不同修改

### 解决策略

**原则：合并两边的依赖，保留更高版本号。**

1. **依赖冲突**：两边新增的依赖都应该保留，同名依赖取更高版本
2. **版本冲突**：如果同一包版本不同，通常取更高版本，但需注意兼容性
3. **scripts 冲突**：确认两边脚本的功能后合并，避免覆盖

### 操作示例

```bash
# 编辑 package.json，删除冲突标记，合并内容
# 例如：
# <<<<<<< HEAD
# "axios": "^1.6.0",
# "lodash": "^4.17.21"
# =======
# "axios": "^1.7.0",
# "dayjs": "^1.11.10"
# >>>>>>> main
#
# 应合并为：
# "axios": "^1.7.0",        # 取更高版本
# "lodash": "^4.17.21",     # 保留当前分支新增
# "dayjs": "^1.11.10"       # 保留 main 分支新增

# 编辑完成后安装依赖确认无误
npm install

# 标记为已解决
git add package.json
```

### 验证要点

- `npm install` 无报错
- `npm run build`（或项目构建命令）能正常执行
- 检查 `package-lock.json` 是否需要同步更新

---

## 文件二：src/api/user.ts

### 冲突特点

这是 TypeScript API 接口文件，冲突通常发生在：
- 两边都添加了新的 API 接口函数
- 同一接口的参数或返回值类型被修改
- 接口地址或请求方式被改变

### 解决策略

**原则：保留两边新增的接口，对于修改的接口需要确认业务逻辑后合并。**

1. **新增接口**：两边新增的不同接口都应该保留
2. **接口修改**：如果同一接口两边都改了，需要了解各自的改动目的，通常保留更完整的实现
3. **类型定义**：确保合并后的类型定义不冲突，导出的接口名称不重复

### 操作示例

```bash
# 编辑 src/api/user.ts
# 例如两边都新增了接口：

# <<<<<<< HEAD
# export async function getUserProfile(userId: string): Promise<UserProfile> {
#   const res = await api.get(`/users/${userId}/profile`);
#   return res.data;
# }
# =======
# export async function updateUserAvatar(userId: string, avatar: File): Promise<void> {
#   const formData = new FormData();
#   formData.append('avatar', avatar);
#   await api.put(`/users/${userId}/avatar`, formData);
# }
# >>>>>>> main
#
# 应合并为（两个接口都保留）：
# export async function getUserProfile(userId: string): Promise<UserProfile> {
#   const res = await api.get(`/users/${userId}/profile`);
#   return res.data;
# }
#
# export async function updateUserAvatar(userId: string, avatar: File): Promise<void> {
#   const formData = new FormData();
#   formData.append('avatar', avatar);
#   await api.put(`/users/${userId}/avatar`, formData);
# }

# 编辑完成后检查 TypeScript 编译
npx tsc --noEmit

# 标记为已解决
git add src/api/user.ts
```

### 验证要点

- TypeScript 编译无类型错误
- 确认所有导入（import）的模块仍然存在
- 检查是否有重复的函数或类型导出

---

## 文件三：src/config/database.conf

### 冲突特点

这是数据库配置文件，冲突通常发生在：
- 数据库连接参数被修改（如地址、端口、库名）
- 新增了不同的配置项
- 配置值针对不同环境做了调整

### 解决策略

**原则：配置文件的冲突需要格外谨慎，确认环境差异后再合并。**

1. **连接参数**：确认两边修改的目的（开发环境 vs 生产环境），可能需要保留两套配置
2. **新增配置**：两边新增的配置项通常都应该保留
3. **敏感信息**：注意不要将密码、密钥等敏感信息提交到版本库

### 操作示例

```bash
# 编辑 src/config/database.conf
# 例如：

# <<<<<<< HEAD
# host=localhost
# port=5432
# database=myapp_dev
# =======
# host=db.example.com
# port=5432
# database=myapp_prod
# max_connections=100
# >>>>>>> main
#
# 解决方案取决于场景：
# - 如果是开发环境配置，保留 localhost
# - 如果需要区分环境，建议拆分为 database.dev.conf 和 database.prod.conf
# - 新增的配置项 max_connections 应该保留

# 标记为已解决
git add src/config/database.conf
```

### 验证要点

- 应用能成功连接数据库
- 敏感配置（密码等）未硬编码在文件中
- 配置格式正确（无语法错误）

---

## 第三步：完成合并

所有冲突解决后，执行以下命令完成合并：

```bash
# 确认所有冲突已解决（不应再有 "both modified" 的文件）
git status

# 完成合并提交
git commit -m "merge: 解决与 main 分支的合并冲突，保留双方新增功能"

# 验证项目正常运行
npm run dev    # 或项目的启动命令
```

## 注意事项

1. **不要使用 `git merge --abort` 除非确定要放弃合并**：这会回到合并前的状态，所有解决工作将丢失
2. **解决冲突前先理解两边的改动目的**：盲目选择一方可能导致功能丢失
3. **解决后务必测试**：至少运行一次构建和基本功能测试
4. **如果不确定如何合并**：可以先 `git stash` 保存当前改动，分别切换到两个分支查看各自的完整改动，再回来解决
5. **善用工具**：可以使用 VS Code 的合并编辑器、GitKraken、SourceTree 等图形化工具辅助解决冲突

## 快速参考命令

```bash
# 查看冲突文件列表
git diff --name-only --diff-filter=U

# 放弃本次合并（慎用）
git merge --abort

# 使用某一方的版本（慎用，会丢弃另一方改动）
git checkout --ours src/config/database.conf    # 保留当前分支版本
git checkout --theirs src/config/database.conf  # 保留 main 分支版本

# 查看某文件在两个分支的差异
git diff main...HEAD -- src/api/user.ts
```
