# 代码审查流程

适用场景：审查代码变更，评估质量、安全性、性能和最佳实践。

## 审查维度

### 1. 功能正确性

- 代码是否正确实现了需求？
- 边界条件是否处理？
- 错误处理是否完善？
- 是否有逻辑漏洞？

### 2. 代码质量

- 命名是否清晰自解释？
- 函数是否职责单一？
- 是否有重复代码可以提取？
- 是否有死代码或未使用的导入？
- 代码风格是否与项目一致？

### 3. 安全性

- 是否有 SQL 注入风险？
- 是否有 XSS 漏洞？
- 敏感数据是否正确处理（加密、脱敏）？
- 认证和授权是否正确？
- 是否有硬编码的密钥/密码？

### 4. 性能

- 是否有 N+1 查询问题？
- 是否有不必要的循环或重复计算？
- 大数据量时是否有性能隐患？
- 是否有内存泄漏风险？
- 是否可以使用缓存优化？

### 5. 可维护性

- 代码是否易于理解？
- 是否有足够的测试覆盖？
- 文档是否需要更新？
- 是否有破坏性变更需要迁移？

## 审查流程

### 第 1 步：了解上下文

```bash
# 查看改动范围
git diff --stat

# 查看具体改动
git diff

# 了解提交历史
git log --oneline -10
```

### 第 2 步：逐文件审查

对每个改动的文件：
1. 阅读完整文件（不只是 diff），理解上下文
2. 检查上述 5 个维度
3. 记录发现的问题

### 第 3 步：整体评估

- 改动是否符合 PR 描述？
- 改动范围是否合理？（太大应该拆分）
- 是否有遗漏的改动？
- 测试是否充分？

### 第 4 步：输出审查报告

## 审查报告模板

```markdown
## 代码审查报告

### 总体评价
[总体评价：可合并 / 需要修改 / 需要重大修改]

### 发现的问题

#### 严重问题（必须修复）
1. **[文件名:行号]** [问题描述]
   - 原因：[为什么这是个问题]
   - 建议：[如何修复]

#### 一般问题（建议修复）
1. **[文件名:行号]** [问题描述]
   - 建议：[如何改进]

#### 轻微问题（可选修复）
1. **[文件名:行号]** [问题描述]
   - 建议：[如何改进]

### 亮点
- [做得好的地方，值得肯定]

### 测试建议
- [建议补充的测试用例]

### 总结
[总结主要发现和下一步建议]
```

## 常见代码问题清单

### Python 常见问题

```python
# ❌ 不要这样
def process(data):
    result = []
    for item in data:
        if item != None:  # 应该用 is not None
            result.append(item * 2)
    return result

# ✅ 应该这样
def process(data):
    return [item * 2 for item in data if item is not None]
```

### JavaScript/TypeScript 常见问题

```javascript
// ❌ 不要这样
async function getData() {
  try {
    const res = await fetch('/api/data')
    const data = await res.json()
    return data
  } catch (e) {
    console.log(e)  // 不要吞掉错误
  }
}

// ✅ 应该这样
async function getData() {
  const res = await fetch('/api/data')
  if (!res.ok) {
    throw new Error(`HTTP ${res.status}: ${res.statusText}`)
  }
  return res.json()
}
```

### SQL 注入风险

```python
# ❌ 危险：SQL 注入
query = f"SELECT * FROM users WHERE name = '{user_input}'"

# ✅ 安全：参数化查询
query = "SELECT * FROM users WHERE name = %s"
cursor.execute(query, (user_input,))
```

### XSS 风险

```javascript
// ❌ 危险：XSS
element.innerHTML = userInput

// ✅ 安全：使用 textContent 或转义
element.textContent = userInput
// 或使用框架的自动转义机制
```
