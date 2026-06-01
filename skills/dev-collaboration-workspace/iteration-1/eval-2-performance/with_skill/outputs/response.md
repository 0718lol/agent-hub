# /api/users 接口性能排查方案

## 场景识别

你描述的是一个**性能问题**：接口响应时间从 200ms 恶化到 3 秒以上。这是一个典型的「性能劣化」排查场景，需要系统化地定位瓶颈。

---

## 第 1 步：收集信息

在开始排查之前，需要确认以下关键信息：

### 需要你提供的信息

| 信息项 | 说明 |
|--------|------|
| **完整代码** | `/api/users` 接口的路由处理函数、涉及的数据库查询代码、ORM 模型定义 |
| **最近变更** | 最近一周是否有代码提交、数据库 schema 变更、依赖升级、配置调整 |
| **数据量级** | users 表当前有多少条记录？最近是否有数据量激增？ |
| **环境信息** | PostgreSQL 版本、连接方式（连接池/直连）、部署方式（单机/集群） |
| **复现条件** | 是所有请求都慢，还是特定参数/分页才慢？是持续慢还是间歇性慢？ |
| **监控数据** | 是否有 APM/慢查询日志？数据库 CPU/内存/IO 使用率如何？ |

---

## 第 2 步：快速定位——按可能性排序的排查清单

### 2.1 数据库层面（最常见原因）

#### (1) 缺失索引或索引失效

**症状**：查询时间随数据量线性增长

```sql
-- 查看 users 表的索引情况
\d+ users

-- 用 EXPLAIN ANALYZE 分析慢查询
EXPLAIN ANALYZE
SELECT * FROM users WHERE ...;  -- 替换为你的实际查询

-- 查看是否有全表扫描（Seq Scan）
-- 如果看到 Seq Scan 且 rows 很大，说明缺少索引
```

**常见缺失索引场景**：
- `WHERE` 条件的字段没有索引
- `ORDER BY` 字段没有索引
- `JOIN` 关联字段没有索引
- 复合查询需要联合索引而非单列索引

**修复**：
```sql
-- 为常用查询字段添加索引
CREATE INDEX CONCURRENTLY idx_users_email ON users(email);
CREATE INDEX CONCURRENTLY idx_users_status_created ON users(status, created_at DESC);

-- 如果是模糊查询，考虑 GIN 索引
CREATE INDEX CONCURRENTLY idx_users_name_trgm ON users USING gin(name gin_trgm_ops);
```

#### (2) N+1 查询问题

**症状**：接口代码看似简单，但实际执行了大量 SQL

```python
# 反面示例：N+1 问题
users = db.query(User).all()          # 1 次查询
for user in users:
    roles = user.roles                 # 每个用户再查一次！N 次查询
    profile = user.profile             # 又 N 次查询
```

**诊断方法**：
```python
# 开启 SQLAlchemy 查询日志
import logging
logging.getLogger('sqlalchemy.engine').setLevel(logging.INFO)

# 或者用 pg_stat_statements 查看执行次数最多的查询
SELECT query, calls, mean_exec_time, total_exec_time
FROM pg_stat_statements
ORDER BY calls DESC
LIMIT 20;
```

**修复**：使用 `joinedload` 或 `selectinload` 预加载关联数据
```python
from sqlalchemy.orm import joinedload

users = db.query(User).options(
    joinedload(User.roles),
    joinedload(User.profile)
).all()
```

#### (3) 锁等待 / 死锁

**症状**：时快时慢，并发时更明显

```sql
-- 查看当前锁等待情况
SELECT blocked_locks.pid     AS blocked_pid,
       blocked_activity.usename  AS blocked_user,
       blocking_locks.pid    AS blocking_pid,
       blocking_activity.usename AS blocking_user,
       blocked_activity.query    AS blocked_query
FROM pg_catalog.pg_locks blocked_locks
JOIN pg_catalog.pg_stat_activity blocked_activity  ON blocked_activity.pid = blocked_locks.pid
JOIN pg_catalog.pg_locks blocking_locks 
    ON blocking_locks.locktype = blocked_locks.locktype
    AND blocking_locks.relation = blocked_locks.relation
    AND blocking_locks.pid != blocked_locks.pid
JOIN pg_catalog.pg_stat_activity blocking_activity ON blocking_activity.pid = blocking_locks.pid
WHERE NOT blocked_locks.granted;

-- 查看长时间运行的事务
SELECT pid, now() - pg_stat_activity.query_start AS duration, query, state
FROM pg_stat_activity
WHERE state != 'idle' AND now() - pg_stat_activity.query_start > interval '5 seconds'
ORDER BY duration DESC;
```

#### (4) 连接池耗尽

**症状**：并发量大时响应变慢，低谷时正常

```sql
-- 查看当前连接数
SELECT count(*) FROM pg_stat_activity;
SELECT state, count(*) FROM pg_stat_activity GROUP BY state;

-- 查看最大连接数
SHOW max_connections;
```

**修复**：检查应用的连接池配置（如 SQLAlchemy 的 `pool_size`、`max_overflow`）

#### (5) 表膨胀 / 统计信息过期

```sql
-- 检查表膨胀
SELECT relname, n_dead_tup, n_live_tup, 
       round(n_dead_tup::numeric / GREATEST(n_live_tup, 1) * 100, 2) AS dead_pct
FROM pg_stat_user_tables
WHERE relname = 'users';

-- 更新统计信息
ANALYZE users;

-- 如果膨胀严重，执行 VACUUM
VACUUM FULL VERBOSE users;  -- 会锁表，生产环境慎用
-- 或者用 pg_repack 在线清理（不锁表）
```

### 2.2 应用代码层面

#### (6) 序列化开销

**问题**：返回大量数据时，JSON 序列化可能成为瓶颈

```python
# 反面示例：返回所有字段
@router.get("/api/users")
async def list_users():
    users = db.query(User).all()  # 加载所有字段，包括大文本字段
    return [user.to_dict() for user in users]  # 逐个序列化
```

**修复**：
```python
# 只查询需要的字段
@router.get("/api/users")
async def list_users(limit: int = 50, offset: int = 0):
    users = db.query(User.id, User.name, User.email, User.avatar_url)\
              .offset(offset).limit(limit).all()
    return [{"id": u.id, "name": u.name, "email": u.email, "avatar": u.avatar_url} for u in users]
```

#### (7) 缺少分页

```python
# 如果 users 表有 10 万条记录，不分页就是灾难
# 必须分页
@router.get("/api/users")
async def list_users(page: int = 1, page_size: int = 20):
    offset = (page - 1) * page_size
    users = db.query(User).offset(offset).limit(page_size).all()
    total = db.query(func.count(User.id)).scalar()
    return {"items": users, "total": total, "page": page}
```

#### (8) 同步阻塞调用在异步上下文中

参考你们项目 `database.py` 的做法——同步数据库操作必须用线程池包装：

```python
# 错误：同步 DB 调用会阻塞事件循环
@router.get("/api/users")
async def list_users():
    return db.query(User).all()  # 阻塞！所有并发请求排队

# 正确：用线程池
@router.get("/api/users")
async def list_users():
    return await asyncio.to_thread(_get_users_sync)

def _get_users_sync():
    with Session(engine) as session:
        return session.exec(select(User)).all()
```

### 2.3 基础设施层面

#### (9) PostgreSQL 配置不当

```sql
-- 检查关键配置
SHOW shared_buffers;          -- 建议：总内存的 25%
SHOW effective_cache_size;    -- 建议：总内存的 75%
SHOW work_mem;                -- 排序/哈希操作的内存
SHOW random_page_cost;        -- SSD 应设为 1.1（默认 4.0 过高）
```

#### (10) 磁盘 IO 瓶颈

```bash
# Linux 下检查磁盘 IO
iostat -x 1 5
# 关注 %util 和 await，如果 %util > 80% 说明 IO 饱和
```

---

## 第 3 步：高效诊断命令速查

### PostgreSQL 慢查询日志

```sql
-- 开启慢查询日志（需要 superuser）
ALTER SYSTEM SET log_min_duration_statement = 200;  -- 记录超过 200ms 的查询
ALTER SYSTEM SET log_statement = 'none';  -- 只记录慢查询，不记录所有
SELECT pg_reload_conf();

-- 之后查看日志文件中的慢查询
```

### pg_stat_statements（推荐安装）

```sql
-- 如果没安装，先启用
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;

-- 查看最慢的查询
SELECT query, calls, mean_exec_time, total_exec_time, rows
FROM pg_stat_statements
ORDER BY mean_exec_time DESC
LIMIT 10;

-- 重置统计
SELECT pg_stat_statements_reset();
```

### 实时监控活跃查询

```sql
-- 查看正在执行的查询
SELECT pid, now() - query_start AS duration, state, query
FROM pg_stat_activity
WHERE state = 'active' AND pid != pg_backend_pid()
ORDER BY duration DESC;
```

---

## 第 4 步：修复方案建议（按优先级）

| 优先级 | 操作 | 预期效果 | 风险 |
|--------|------|---------|------|
| P0 | `EXPLAIN ANALYZE` 定位慢查询 | 精确定位瓶颈 | 无 |
| P1 | 添加缺失索引 | 查询速度提升 10-100x | 写入性能微降 |
| P1 | 解决 N+1 查询 | 减少数据库往返次数 | 需改代码 |
| P2 | 添加分页 + 限制返回字段 | 减少数据传输量 | 无 |
| P2 | 确保异步不阻塞 | 提升并发能力 | 需改代码 |
| P3 | VACUUM / ANALYZE 清理 | 恢复查询计划准确性 | VACUUM FULL 会锁表 |
| P3 | 调优 PostgreSQL 参数 | 整体性能提升 | 需重启 PG |

---

## 第 5 步：验证修复

修复后需要验证：

1. **响应时间**：`curl -w "time_total: %{time_total}\n" -o /dev/null -s http://your-host/api/users`
2. **查询计划**：再次 `EXPLAIN ANALYZE` 确认走了索引
3. **并发测试**：用 `ab` 或 `wrk` 做压力测试
   ```bash
   wrk -t4 -c100 -d30s http://your-host/api/users
   ```
4. **监控观察**：修复后持续观察 1-2 天，确认无回归

---

## 总结

从 200ms 劣化到 3s，最常见的原因是：

1. **数据量增长导致全表扫描变慢**（缺索引）—— 最可能
2. **新增了 N+1 查询或关联加载** —— 代码变更引入
3. **表膨胀导致查询计划不准确** —— 长期运行积累
4. **连接池配置不当** —— 并发量上升后暴露

**建议你先把 `/api/users` 的完整代码和 `EXPLAIN ANALYZE` 的输出发给我，我可以直接帮你定位具体是哪个查询拖慢了整个接口。**
