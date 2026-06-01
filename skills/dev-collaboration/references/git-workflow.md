# Git 工作流指南

适用场景：日常 Git 操作，包括分支管理、提交、PR、cherry-pick 等。

## 分支管理

### 分支命名规范

| 类型 | 前缀 | 示例 |
|------|------|------|
| 功能开发 | `feature/` | `feature/user-auth` |
| Bug 修复 | `fix/` | `fix/login-crash` |
| 重构 | `refactor/` | `refactor/api-layer` |
| 文档 | `docs/` | `docs/api-spec` |
| 测试 | `test/` | `test/unit-auth` |
| 热修复 | `hotfix/` | `hotfix/security-patch` |

### 分支操作

```bash
# 创建并切换到新分支
git checkout -b feature/新功能名

# 查看所有分支
git branch -a

# 切换分支
git checkout 目标分支

# 删除本地分支（已合并的）
git branch -d 分支名

# 删除远程分支
git push origin --delete 分支名
```

## 提交规范

### 提交信息格式

```
<type>(<scope>): <subject>

<body>

<footer>
```

**Type 类型：**
- `feat`: 新功能
- `fix`: Bug 修复
- `docs`: 文档更新
- `style`: 代码格式（不影响功能）
- `refactor`: 重构
- `perf`: 性能优化
- `test`: 测试相关
- `chore`: 构建/工具相关

**示例：**
```
feat(auth): 添加 JWT 认证支持

- 实现登录接口
- 添加 token 刷新机制
- 集成中间件验证

Closes #123
```

### 原子提交

每个提交应该是独立的、可回滚的：
- 一个提交只做一件事
- 提交后代码应该能正常编译和运行
- 不要把多个不相关的改动放在一个提交中

## Pull Request 流程

### 创建 PR 前

```bash
# 确保基于最新的主分支
git fetch origin
git rebase origin/main

# 运行测试
npm test / pytest

# 检查代码风格
npm run lint / flake8
```

### PR 描述模板

```markdown
## 改动说明
简要描述这个 PR 做了什么

## 改动类型
- [ ] 新功能
- [ ] Bug 修复
- [ ] 重构
- [ ] 文档更新
- [ ] 其他：___

## 测试
- [ ] 已添加/更新单元测试
- [ ] 已手动测试核心功能
- [ ] 所有现有测试通过

## 截图/录屏（如适用）
添加截图或录屏展示改动效果

## 关联 Issue
Closes #___
```

## Cherry-pick

```bash
# 拣选单个提交
git cherry-pick <commit-hash>

# 拣选多个提交
git cherry-pick <hash1> <hash2> <hash3>

# 拣选一个范围的提交
git cherry-pick <start-hash>..<end-hash>

# 拣选但不自动提交（可以修改后再提交）
git cherry-pick --no-commit <commit-hash>
```

## Stash 暂存

```bash
# 暂存当前改动
git stash

# 暂存并添加描述
git stash push -m "描述信息"

# 查看暂存列表
git stash list

# 恢复最近的暂存
git stash pop

# 恢复但不删除暂存
git stash apply

# 恢复指定的暂存
git stash apply stash@{2}

# 删除暂存
git stash drop stash@{0}

# 清空所有暂存
git stash clear
```

## 查看历史

```bash
# 简洁的提交历史
git log --oneline -20

# 图形化分支结构
git log --oneline --graph --all

# 查看某个文件的历史
git log --follow -p <文件路径>

# 查看某人的提交
git log --author="名字"

# 查看某个时间段的提交
git log --since="2024-01-01" --until="2024-01-31"
```

## 撤销操作

```bash
# 撤销工作区的修改（未暂存）
git checkout -- <文件>

# 撤销暂存（保留修改）
git reset HEAD <文件>

# 撤销最近一次提交（保留修改）
git reset --soft HEAD~1

# 撤销最近一次提交（丢弃修改）⚠️ 危险
git reset --hard HEAD~1

# 安全地撤销已推送的提交
git revert <commit-hash>
```

## .gitattributes 配置

对于容易产生冲突的文件，配置合并策略：

```gitattributes
# 锁定文件使用 union 合并策略
package-lock.json merge=union
yarn.lock merge=union

# 二进制文件不尝试合并
*.png binary
*.jpg binary
*.pdf binary

# 数据库迁移文件按顺序合并
migrations/*.sql merge=union
```
