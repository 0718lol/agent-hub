# /api/users 接口性能排查指南

## 问题描述

- 接口：`/api/users`
- 数据库：PostgreSQL
- 原始响应时间：约 200ms
- 当前响应时间：约 3 秒+
- 性能退化幅度：约 15 倍

---

## 一、排查思路总览

性能从 200ms 劣化到 3s，原因通常集中在以下几个层面：

1. **数据库层**（最常见，概率约 60%）
2. **应用层 / ORM 层**
3. **连接池 / 资源争用**
4. **数据量变化**
5. **基础设施 / 网络**

按优先级从高到低依次排查。

---

## 二、数据库层排查（最高优先级）

### 2.1 慢查询日志

首先定位慢 SQL。PostgreSQL 开启慢查询日志：

```sql
-- 查看当前配置
SHOW log_min_duration_statement;

-- 设置记录超过 200ms 的查询（生产环境建议 500ms 以上）
ALTER SYSTEM SET log_min_duration_statement = 200;
SELECT pg_reload_conf();
```

然后查看日志文件，找到 `/api/users` 对应的 SQL 语句及其执行时间。

### 2.2 使用 EXPLAIN ANALYZE 分析执行计划

拿到慢 SQL 后，用 `EXPLAIN ANALYZE` 查看实际执行计划：

```sql
EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
SELECT * FROM users WHERE ... ;
```

重点关注以下指标：

| 指标 | 含义 | 警戒值 |
|------|------|--------|
| `Seq Scan` | 全表扫描 | 大表出现则需加索引 |
| `actual time` | 实际耗时 | 单节点超过 100ms 需关注 |
| `rows` vs `rows removed by filter` | 过滤效率 | 过滤比过高说明索引失效 |
| `Buffers: shared hit/read` | 缓存命中率 | read 远大于 hit 说明缓存不足 |
| `Sort` / `HashAggregate` | 排序/聚合 | 内存不足会溢出到磁盘 |

### 2.3 索引问题排查

这是最常见的性能退化原因：

```sql
-- 检查 users 表上的索引
SELECT indexname, indexdef
FROM pg_indexes
WHERE tablename = 'users';

-- 检查是否有未使用的索引（占用写入性能）
SELECT schemaname, relname, indexrelname, idx_scan
FROM pg_stat_user_indexes
WHERE relname = 'users'
ORDER BY idx_scan ASC;

-- 检查表的统计信息是否过时
SELECT relname, last_analyze, last_autoanalyze, n_live_tup, n_dead_tup
FROM pg_stat_user_tables
WHERE relname = 'users';
```

常见索引问题：

- **缺少索引**：新增了 WHERE 条件或 JOIN 条件但没有对应索引
- **索引失效**：对索引列使用了函数（如 `LOWER(email)`、`::text` 类型转换）
- **统计信息过时**：大量 INSERT/DELETE 后未执行 `ANALYZE`
- **复合索引顺序错误**：最左前缀不匹配查询条件

修复示例：

```sql
-- 如果查询是 WHERE status = 'active' AND created_at > '...'
-- 则需要复合索引
CREATE INDEX CONCURRENTLY idx_users_status_created
ON users (status, created_at DESC);

-- 如果涉及模糊查询
CREATE INDEX CONCURRENTLY idx_users_name_trgm
ON users USING gin (name gin_trgm_ops);

-- 更新统计信息
ANALYZE users;
```

### 2.4 锁等待排查

并发场景下，查询可能被锁阻塞：

```sql
-- 查看当前被阻塞的查询
SELECT
    blocked.pid AS blocked_pid,
    blocked.query AS blocked_query,
    blocking.pid AS blocking_pid,
    blocking.query AS blocking_query,
    blocked.wait_event_type,
    blocked.wait_event
FROM pg_stat_activity AS blocked
JOIN pg_locks AS bl ON bl.pid = blocked.pid
JOIN pg_locks AS kl ON kl.locktype = bl.locktype
    AND kl.database IS NOT DISTINCT FROM bl.database
    AND kl.relation IS NOT DISTINCT FROM bl.relation
    AND kl.page IS NOT DISTINCT FROM bl.page
    AND kl.tuple IS NOT DISTINCT FROM bl.tuple
    AND kl.transactionid IS NOT DISTINCT FROM bl.transactionid
    AND kl.pid != bl.pid
    AND kl.granted
JOIN pg_stat_activity AS blocking ON blocking.pid = kl.pid
WHERE NOT bl.granted;
```

如果发现锁等待，检查是否有：
- 长事务未提交
- 大批量 UPDATE/DELETE 操作
- ALTER TABLE 等 DDL 操作持有 AccessExclusiveLock

### 2.5 数据量增长

```sql
-- 查看 users 表大小和行数
SELECT
    pg_size_pretty(pg_total_relation_size('users')) AS total_size,
    pg_size_pretty(pg_relation_size('users')) AS table_size,
    (SELECT count(*) FROM users) AS row_count;

-- 查看表的增长趋势（需要 pg_stat_statements 扩展或监控系统）
SELECT
    relname,
    n_live_tup,
    n_dead_tup,
    round(n_dead_tup::numeric / GREATEST(n_live_tup, 1) * 100, 2) AS dead_pct
FROM pg_stat_user_tables
WHERE relname = 'users';
```

如果 `n_dead_tup` 占比过高（超过 20%），需要执行：

```sql
VACUUM ANALYZE users;
-- 或者在业务低峰期执行（会锁表）
VACUUM FULL users;
```

### 2.6 连接数与连接池

```sql
-- 查看当前连接数
SELECT count(*) FROM pg_stat_activity;

-- 查看连接状态分布
SELECT state, count(*)
FROM pg_stat_activity
GROUP BY state;

-- 查看等待连接的请求
SELECT count(*) FROM pg_stat_activity
WHERE wait_event_type = 'Client';
```

如果连接数接近 `max_connections`，说明连接池耗尽，请求在排队等待。

---

## 三、应用层排查

### 3.1 ORM / 查询代码审查

检查 `/api/users` 的查询代码，常见性能陷阱：

**N+1 查询问题**（最常见）：

```python
# 反面示例：循环中逐个查询关联数据
users = db.query(User).all()
for user in users:
    user.role = db.query(Role).get(user.role_id)  # N 次额外查询
    user.profile = db.query(Profile).filter_by(user_id=user.id).first()  # N 次额外查询
```

修复：使用 eager loading

```python
# 正面示例：一次查询加载关联数据
from sqlalchemy.orm import selectinload, joinedload

users = db.query(User).options(
    selectinload(User.role),
    selectinload(User.profile)
).all()
```

**查询未分页**：

```python
# 反面示例：一次性加载所有用户
users = db.query(User).all()  # 数据量大时极慢

# 正面示例：分页查询
users = db.query(User).offset(skip).limit(limit).all()
```

**SELECT * 问题**：

```python
# 反面示例：查询所有字段
users = db.query(User).all()

# 正面示例：只查需要的字段
users = db.query(User.id, User.name, User.email).all()
```

### 3.2 序列化开销

检查返回数据的序列化过程：

```python
# 如果用户对象包含大量关联数据，序列化可能很慢
# 检查 Pydantic 模型是否有不必要的嵌套
class UserResponse(BaseModel):
    id: int
    name: str
    email: str
    # 以下字段可能导致大量额外查询和序列化
    # orders: List[OrderResponse]  # 如果有大量订单数据
    # logs: List[LogResponse]      # 如果有大量日志数据
```

### 3.3 中间件和拦截器

检查是否有新增的中间件：

- 日志中间件（特别是同步写文件的日志）
- 认证/鉴权中间件（每次请求都验证 token）
- 限流中间件（Redis 连接慢）
- CORS 中间件配置不当

### 3.4 缓存失效

如果之前有缓存加速，检查：

- Redis 连接是否正常
- 缓存 key 是否过期或被清理
- 缓存策略是否被修改

---

## 四、基础设施排查

### 4.1 数据库服务器资源

```bash
# CPU 使用率
top -p $(pgrep postgres)

# 磁盘 I/O
iostat -x 1 5

# 内存使用
free -h

# PostgreSQL 共享内存使用
SHOW shared_buffers;
SHOW effective_cache_size;
SHOW work_mem;
```

### 4.2 网络延迟

```bash
# 检查应用到数据库的网络延迟
ping <db_host>
traceroute <db_host>

# 检查 DNS 解析是否变慢
time nslookup <db_host>
```

### 4.3 应用服务器资源

```bash
# 检查应用进程资源占用
ps aux | grep uvicorn  # 或你的应用进程名

# 检查文件描述符是否耗尽
ls /proc/<pid>/fd | wc -l
ulimit -n
```

---

## 五、快速排查流程（5 分钟定位）

按照以下步骤快速定位问题：

```
步骤 1：查看 PostgreSQL 慢查询日志
  ├─ 找到具体 SQL → 进入步骤 2
  └─ 没有慢 SQL → 问题在应用层（步骤 4）

步骤 2：EXPLAIN ANALYZE 该 SQL
  ├─ Seq Scan / 缺少索引 → 添加索引
  ├─ 索引存在但未使用 → 检查统计信息，执行 ANALYZE
  ├─ 锁等待 → 排查长事务和并发操作
  └─ 执行计划正常但慢 → 进入步骤 3

步骤 3：检查数据库资源
  ├─ CPU 高 → 检查是否有全表扫描或复杂计算
  ├─ 内存不足 → 调整 shared_buffers / work_mem
  ├─ 磁盘 I/O 高 → 检查是否有大量写操作
  └─ 连接数满 → 增加连接池或优化连接使用

步骤 4：检查应用层
  ├─ N+1 查询 → 改用 eager loading
  ├─ 缺少分页 → 添加分页
  ├─ 新增中间件耗时 → 优化或异步化
  └─ 序列化慢 → 精简返回字段

步骤 5：检查基础设施
  ├─ 网络延迟 → 检查网络配置
  └─ 服务器资源 → 扩容或优化配置
```

---

## 六、PostgreSQL 性能优化参数参考

如果排查后发现是数据库配置问题，以下参数可参考调整：

```sql
-- 共享缓冲区（建议为系统内存的 25%）
SHOW shared_buffers;  -- 默认 128MB，建议 2-4GB

-- 有效缓存大小（建议为系统内存的 50-75%）
SHOW effective_cache_size;  -- 默认 4GB

-- 工作内存（排序、哈希操作使用，每个连接独立分配）
SHOW work_mem;  -- 默认 4MB，复杂查询可调到 64-256MB

-- 维护工作内存（VACUUM、CREATE INDEX 使用）
SHOW maintenance_work_mem;  -- 默认 64MB，建议 512MB-1GB

-- 随机页面读取成本（SSD 建议调低）
SHOW random_page_cost;  -- 默认 4.0，SSD 建议 1.1-1.5
```

---

## 七、监控建议（防止再次退化）

长期建议：

1. **启用 pg_stat_statements 扩展**：追踪所有 SQL 的执行时间和频率
2. **配置慢查询告警**：超过 500ms 的查询触发告警
3. **定期 VACUUM ANALYZE**：设置 autovacuum 参数，确保统计信息及时更新
4. **应用层 APM**：接入如 Sentry、Datadog 等工具，监控接口级别的耗时
5. **数据库连接池监控**：监控活跃连接数、等待连接数、空闲连接数

```sql
-- 启用 pg_stat_statements
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;

-- 查看最慢的 10 条 SQL
SELECT
    query,
    calls,
    round(total_exec_time::numeric, 2) AS total_time_ms,
    round(mean_exec_time::numeric, 2) AS avg_time_ms,
    round(max_exec_time::numeric, 2) AS max_time_ms
FROM pg_stat_statements
ORDER BY mean_exec_time DESC
LIMIT 10;
```

---

## 总结

从 200ms 劣化到 3s 的典型原因排序：

1. **索引缺失或失效**（最常见）-- 检查查询计划，添加缺失索引
2. **N+1 查询问题** -- 检查 ORM 代码，使用 eager loading
3. **锁等待** -- 排查长事务和并发操作
4. **统计信息过时** -- 执行 ANALYZE 更新
5. **数据量激增** -- 检查表大小，添加分页
6. **连接池耗尽** -- 检查连接数配置
7. **新增中间件** -- 检查代码变更记录

建议先从慢查询日志和 EXPLAIN ANALYZE 入手，80% 的情况能在这一步定位到根因。
