# SMTP 隧道客户端进程泄漏问题分析报告

## 1. 问题概述

客户端运行过程中出现进程数量持续增长且不释放的现象，导致系统资源消耗增加。

## 2. 代码结构分析

### 2.1 异步任务创建点

通过代码分析，识别出以下异步任务创建点：

1. **run_client() - 主循环**
   - 创建 `TunnelClient` 实例
   - 创建 `receiver_task` (第828行): `asyncio.create_task(tunnel._receiver_loop())`
   - 创建 SOCKS5 服务器: `asyncio.start_server()`

2. **SOCKS5Server.handle_client() - 处理每个客户端连接**
   - 每个客户端连接都会创建一个新的协程
   - 调用 `_forward_loop()` 进行数据转发

### 2.2 资源管理点

1. **通道管理 (Channel)**
   - `self.channels: Dict[int, Channel]` - 存储所有活跃通道
   - 每个通道包含 reader/writer 流

2. **连接事件管理**
   - `self.connect_events: Dict[int, asyncio.Event]` - 通道连接事件
   - `self.connect_results: Dict[int, bool]` - 连接结果缓存

3. **SOCKS5 服务器**
   - `socks_server` - 异步服务器对象

## 3. 发现的问题

### 问题 1: SOCKS5 客户端连接未正确关闭 (严重)

**位置**: `SOCKS5Server.handle_client()` 方法

**问题描述**:
- 在第658-661行,当隧道未连接时,直接 `writer.close()` 并返回,但未等待 `wait_closed()`
- 在第668-671行,当 SOCKS5 版本无效时,直接 `return`,未关闭 writer
- 在第681-684行,当未收到完整连接请求时,直接 `return`,未关闭 writer
- 在第693-697行,当命令不支持时,发送错误响应后直接 `return`,未关闭 writer
- 在第718-721行,当地址类型不支持时,直接 `return`,未关闭 writer

**影响**:
- 每次异常情况都会导致一个未关闭的连接
- 连接的 socket 和缓冲区不会被释放
- 随着时间推移,未关闭的连接会累积

**代码示例**:
```python
# 第668-671行 - 问题代码
if len(data) < 2 or data[0] != SOCKS5.VERSION:
    logger.warning(f"无效的 SOCKS5 版本: {data[0] if data else 'None'}")
    return  # ❌ 未关闭 writer
```

### 问题 2: asyncio.start_server 创建的任务未正确管理 (严重)

**位置**: `run_client()` 方法,第832-837行

**问题描述**:
- `asyncio.start_server()` 会为每个接受的连接创建一个后台任务
- 这些任务在 `socks_server.serve_forever()` 运行期间持续存在
- 当连接丢失重连时,旧的 `socks_server` 可能未完全关闭

**影响**:
- 每次重连都会创建新的 SOCKS5 服务器
- 旧服务器的任务可能仍在运行
- 导致任务数量持续增长

**代码示例**:
```python
# 第832-837行
socks_server = await asyncio.start_server(
    socks.handle_client,
    socks.host,
    socks.port,
    reuse_address=True
)
# ❌ 重连时,旧的 socks_server 可能未完全清理
```

### 问题 3: 通道事件和结果字典未完全清理 (中等)

**位置**: `open_channel()` 方法

**问题描述**:
- 在第531-532行,虽然清理了 `connect_events` 和 `connect_results`
- 但在异常情况下(如第527行的异常),可能未清理
- 在超时情况下(第533行),清理逻辑正常

**影响**:
- 少量内存泄漏
- 长时间运行后可能累积

**代码示例**:
```python
# 第524-527行
try:
    payload = make_connect_payload(host, port)
    await self.send_frame(FRAME_CONNECT, channel_id, payload)
    logger.debug(f"已发送通道 {channel_id} 连接请求")
except Exception as e:
    logger.error(f"发送通道 {channel_id} 连接请求失败: {e}")
    return channel_id, False  # ❌ 未清理 connect_events 和 connect_results
```

### 问题 4: receiver_task 取消后未等待完成 (轻微)

**位置**: `run_client()` 方法,第877-881行

**问题描述**:
- 在 finally 块中取消 `receiver_task`
- 使用 `await receiver_task` 等待,但捕获了 `CancelledError`
- 这是正确的做法,但可以改进

**影响**:
- 可能导致任务未完全清理

### 问题 5: TunnelClient 实例在重连时未完全清理 (严重)

**位置**: `run_client()` 方法

**问题描述**:
- 在第814行,每次循环都创建新的 `TunnelClient` 实例
- 在第874行,调用 `tunnel.disconnect()` 清理资源
- 但在异常情况下(如第868行的 OSError),可能未完全清理

**影响**:
- 旧的 `TunnelClient` 实例的资源可能未完全释放
- 包括通道、事件、连接等

## 4. 问题优先级

| 问题 | 严重程度 | 优先级 | 影响 |
|------|---------|--------|------|
| 问题 1: SOCKS5 连接未关闭 | 严重 | P0 | 直接导致进程泄漏 |
| 问题 2: SOCKS5 服务器任务未管理 | 严重 | P0 | 导致任务累积 |
| 问题 5: TunnelClient 未完全清理 | 严重 | P0 | 导致资源泄漏 |
| 问题 3: 事件字典未清理 | 中等 | P1 | 内存泄漏 |
| 问题 4: receiver_task 取消 | 轻微 | P2 | 潜在问题 |

## 5. 修复方案

### 修复 1: 确保 SOCKS5 客户端连接正确关闭

在 `handle_client()` 方法的所有提前返回点,确保关闭 writer:

```python
async def handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    channel = None
    try:
        # ... 现有代码 ...

    except Exception as e:
        logger.debug(f"SOCKS 错误: {e}")
    finally:
        # 清理: 通知服务器关闭通道,关闭客户端连接
        if channel:
            logger.debug(f"清理通道 {channel.channel_id}")
            await self.tunnel.close_channel_remote(channel.channel_id)
            await self.tunnel._close_channel(channel)

        # ✅ 确保在所有情况下都关闭 writer
        try:
            writer.close()
            await writer.wait_closed()
        except Exception as e:
            logger.debug(f"关闭客户端连接失败: {e}")
```

### 修复 2: 管理 SOCKS5 服务器生命周期

在重连前,确保完全关闭旧的 SOCKS5 服务器:

```python
async def run_client(config: ClientConfig, ca_cert: str):
    socks_server = None  # ✅ 跟踪服务器实例

    while True:
        # ... 现有代码 ...

        try:
            # 关闭旧的服务器 (如果存在)
            if socks_server:
                logger.info("关闭旧的 SOCKS5 服务器")
                socks_server.close()
                await socks_server.wait_closed()

            # 创建新的 SOCKS5 服务器
            socks_server = await asyncio.start_server(
                socks.handle_client,
                socks.host,
                socks.port,
                reuse_address=True
            )
            # ... 现有代码 ...

        except KeyboardInterrupt:
            logger.info("正在关闭...")
            await tunnel.disconnect()
            if socks_server:  # ✅ 关闭服务器
                socks_server.close()
                await socks_server.wait_closed()
            return 0
        finally:
            logger.info("清理资源")
            await tunnel.disconnect()
            receiver_task.cancel()
            try:
                await receiver_task
            except asyncio.CancelledError:
                pass
```

### 修复 3: 确保通道事件和结果字典清理

在 `open_channel()` 方法的异常情况下,也清理资源:

```python
async def open_channel(self, host: str, port: int) -> Tuple[int, bool]:
    # ... 现有代码 ...

    # 发送连接请求
    try:
        payload = make_connect_payload(host, port)
        await self.send_frame(FRAME_CONNECT, channel_id, payload)
        logger.debug(f"已发送通道 {channel_id} 连接请求")
    except Exception as e:
        logger.error(f"发送通道 {channel_id} 连接请求失败: {e}")
        # ✅ 清理事件和结果
        self.connect_events.pop(channel_id, None)
        self.connect_results.pop(channel_id, None)
        return channel_id, False

    # ... 现有代码 ...
```

### 修复 4: 改进 receiver_task 取消逻辑

确保任务完全取消:

```python
finally:
    logger.info("清理资源")
    await tunnel.disconnect()

    # ✅ 取消并等待接收器任务
    if not receiver_task.done():
        receiver_task.cancel()
        try:
            await asyncio.wait_for(receiver_task, timeout=5.0)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            logger.debug("接收器任务取消超时")
```

### 修复 5: 确保 TunnelClient 完全清理

在 disconnect() 方法中添加更详细的清理:

```python
async def disconnect(self):
    """断开连接并清理所有资源"""
    logger.info("开始断开连接")
    self.connected = False

    # 关闭所有通道
    channel_count = len(self.channels)
    logger.info(f"关闭 {channel_count} 个活跃通道")
    for channel in list(self.channels.values()):
        await self._close_channel(channel)

    # 关闭与服务器的连接
    if self.writer:
        try:
            self.writer.close()
            await asyncio.wait_for(self.writer.wait_closed(), timeout=2.0)
            logger.info("与服务器的连接已关闭")
        except Exception as e:
            logger.error(f"关闭与服务器的连接失败: {e}")

    # ✅ 清理所有事件和结果
    event_count = len(self.connect_events)
    result_count = len(self.connect_results)
    if event_count > 0 or result_count > 0:
        logger.warning(f"清理 {event_count} 个连接事件和 {result_count} 个连接结果")
    self.connect_events.clear()
    self.connect_results.clear()

    # 清理所有资源
    self.reader = None
    self.writer = None
    self.channels.clear()
    logger.info("连接断开,所有资源已清理")
```

## 6. 测试计划

### 6.1 单元测试
- 测试 SOCKS5 客户端连接在各种异常情况下的清理
- 测试通道打开失败时的资源清理
- 测试重连时的资源释放

### 6.2 集成测试
- 运行客户端并监控进程数量
- 模拟网络中断和重连
- 模拟大量并发连接

### 6.3 长时间运行测试
- 运行客户端 24 小时以上
- 监控进程数量和内存使用
- 验证资源稳定释放

## 7. 监控建议

### 7.1 进程监控
使用 `monitor_processes.py` 脚本:
```bash
python3 monitor_processes.py --interval 5 --duration 3600 --output monitor.csv
```

### 7.2 日志监控
关注以下日志:
- "清理通道"
- "关闭客户端连接"
- "清理资源"
- 警告级别的日志

### 7.3 系统资源监控
- 监控进程数量: `ps aux | grep client.py | wc -l`
- 监控内存使用: `ps aux | grep client.py | awk '{sum+=$6} END {print sum/1024}'`
- 监控文件描述符: `lsof -p <pid> | wc -l`

## 8. 总结

主要问题集中在:
1. **资源清理不完整**: 在异常情况下未正确关闭连接和清理资源
2. **任务管理不当**: SOCKS5 服务器的生命周期管理存在问题
3. **异常处理不完善**: 多个提前返回点未执行清理逻辑

建议优先修复 P0 级别的问题,这些修复将显著改善进程泄漏问题。
