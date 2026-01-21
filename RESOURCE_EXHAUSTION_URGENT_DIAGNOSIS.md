# 资源耗尽问题紧急诊断报告

## 问题概述

**严重程度**：🔴🔴🔴 极其严重
**影响范围**：CPU、内存、SWAP 完全占用，系统性能严重下降

**观察到的异常模式**：

### 异常 1：通道ID持续增长
```
通道 47 -> 通道 48 -> 通道 49 -> 通道 50 -> 通道 51 -> 通道 52 -> 通道 53 -> 通道 54 -> 通道 55 -> 通道 56
```
**问题**：通道ID在不断增加，说明通道对象可能没有被正确清理

### 异常 2：连接计数器不准确
```
当前连接数: 1/100
当前连接数: 2/100
当前连接数: 3/100
当前连接数: 4/100
```
**问题**：连接计数器显示连接数在增长，但实际活跃通道应该很少

### 异常 3：通道打开超时频繁
```
通道 48 打开超时
通道 49 打开超时
通道 51 打开超时
通道 53 打开超时
通道 54 打开超时
通道 55 打开超时
通道 56 打开超时
```
**问题**：大量通道打开超时，说明服务器响应很慢或无响应

### 异常 4：writer关闭超时
```
WARNING - 关闭 writer 超时,强制关闭
```
**问题**：writer关闭超时，导致Socket句柄泄漏

### 异常 5：收到关闭帧后仍有打开超时
```
INFO - 收到通道 48 关闭帧
ERROR - 通道 48 打开超时
```
**问题**：收到关闭帧后，仍然出现打开超时，说明事件对象没有被正确清理

## 根本原因分析

### 问题 1：通道ID无限增长

**代码位置**：[client.py:144](file:///home/pps/code/smtp-tunnel-proxy/smtp-tunnel-proxy/client.py#L144)

```python
self.next_channel_id = 1  # 下一个通道ID
```

**问题**：
- 通道ID从1开始，每次打开通道都+1
- 通道ID会无限增长，不会重用
- 即使通道被关闭，ID也不会被回收

**影响**：
- 通道ID会越来越大（47、48、49...）
- 可能导致整数溢出（虽然需要很长时间）
- 但更重要的是，说明通道对象可能没有被正确清理

### 问题 2：连接计数器不准确

**代码位置**：[client.py:724-727](file:///home/pps/code/smtp-tunnel-proxy/smtp-tunnel-proxy/client.py#L724-L727)

```python
async with self.connection_semaphore:
    self.current_connections += 1
    logger.info(f"当前连接数: {self.current_connections}/{self.max_connections}")
```

**问题**：
- 连接计数器在进入`async with`时立即增加
- 但在`finally`块中才减少
- 如果在`async with`和`finally`之间发生异常，计数器可能不准确

**影响**：
- 连接计数器可能显示比实际更多的连接
- 但更重要的是，说明可能有连接泄漏

### 问题 3：事件对象泄漏

**代码位置**：[client.py:528-531](file:///home/pps/code/smtp-tunnel-proxy/smtp-tunnel-proxy/client.py#L528-L531)

```python
# 创建事件用于等待服务器响应
event = asyncio.Event()
self.connect_events[channel_id] = event
self.connect_results[channel_id] = False
```

**问题**：
- 每次打开通道都会创建新的事件对象
- 如果通道打开超时，事件对象会被清理
- 但如果服务器在超时后发送响应，事件对象已不存在，响应被忽略
- 可能导致服务器端连接未关闭

**影响**：
- 服务器端连接可能一直保持
- 服务器资源被耗尽
- 客户端内存增长

### 问题 4：writer关闭超时导致Socket句柄泄漏

**代码位置**：[client.py:870-886](file:///home/pps/code/smtp-tunnel-proxy/smtp-tunnel-proxy/client.py#L870-L886)

```python
try:
    writer.close()
    await asyncio.wait_for(writer.wait_closed(), timeout=5.0)
except asyncio.TimeoutError:
    logger.warning("关闭 writer 超时,强制关闭")
    try:
        writer.transport.abort()
    except Exception as e:
        logger.error(f"强制关闭 transport 失败: {e}")
```

**问题**：
- writer关闭超时后，尝试强制关闭transport
- 但如果`transport.abort()`也失败，Socket句柄可能不会被释放
- 可能导致文件描述符泄漏

**影响**：
- Socket句柄泄漏
- 文件描述符累积
- 系统资源耗尽

### 问题 5：通道对象未清理

**代码位置**：[client.py:830-858](file:///home/pps/code/smtp-tunnel-proxy/smtp-tunnel-proxy/client.py#L830-L858)

```python
finally:
    # 清理: 通知服务器关闭通道,关闭客户端连接
    if channel:
        logger.debug(f"清理通道 {channel.channel_id}")
        await self.tunnel.close_channel_remote(channel.channel_id)
        await self.tunnel._close_channel(channel)

    # 确保在所有情况下都关闭 writer
    try:
        writer.close()
        await asyncio.wait_for(writer.wait_closed(), timeout=5.0)
    except asyncio.TimeoutError:
        logger.warning("关闭 writer 超时,强制关闭")
        try:
            writer.transport.abort()
        except Exception as e:
            logger.error(f"强制关闭 transport 失败: {e}")
    except Exception as e:
        logger.debug(f"关闭客户端连接失败: {e}")
        try:
            writer.transport.abort()
        except Exception as e2:
            logger.error(f"强制关闭 transport 失败: {e2}")

    self.current_connections -= 1
```

**问题**：
- 如果`open_channel`返回失败，`channel`为`None`
- `finally`块中会尝试清理`None`通道
- 但更重要的是，如果通道打开超时，通道对象不会被创建
- 可能导致`channels`字典中累积僵尸通道

**影响**：
- 通道对象泄漏
- 内存增长
- 系统资源耗尽

## 紧急修复方案

### 修复 1：添加通道ID回收机制

**问题**：通道ID无限增长

**修复方案**：
```python
class TunnelClient:
    def __init__(self, config: ClientConfig, ca_cert: str = None):
        # ... 现有代码 ...
        
        # 添加通道ID回收机制
        self.available_channel_ids = []
        self.max_channel_id = 1000  # 最大通道ID

    async def open_channel(self, host: str, port: int) -> Tuple[int, bool]:
        # ... 现有代码 ...
        
        # 分配新的通道ID（优先回收）
        async with self.channel_lock:
            if self.available_channel_ids:
                channel_id = self.available_channel_ids.pop()
            else:
                channel_id = self.next_channel_id
                self.next_channel_id += 1
                if self.next_channel_id > self.max_channel_id:
                    self.next_channel_id = 1  # 循环使用

        logger.info(f"打开通道 {channel_id}: {host}:{port}")

        # ... 现有代码 ...

        return channel_id, success

    async def _close_channel(self, channel: Channel):
        # ... 现有代码 ...
        
        # 回收通道ID
        if channel.channel_id not in self.available_channel_ids:
            self.available_channel_ids.append(channel.channel_id)
```

### 修复 2：修复连接计数器

**问题**：连接计数器不准确

**修复方案**：
```python
async def handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    # 使用信号量限制并发连接
    async with self.connection_semaphore:
        try:
            self.current_connections += 1
            logger.info(f"当前连接数: {self.current_connections}/{self.max_connections}")

            channel = None
            try:
                # ... 处理连接 ...
            except Exception as e:
                logger.debug(f"SOCKS 错误: {e}")
            finally:
                # 清理
                if channel:
                    await self.tunnel.close_channel_remote(channel.channel_id)
                    await self.tunnel._close_channel(channel)

                # 确保关闭 writer
                try:
                    writer.close()
                    await asyncio.wait_for(writer.wait_closed(), timeout=5.0)
                except asyncio.TimeoutError:
                    logger.warning("关闭 writer 超时,强制关闭")
                    try:
                        writer.transport.abort()
                    except Exception as e:
                        logger.error(f"强制关闭 transport 失败: {e}")
                except Exception as e:
                    logger.debug(f"关闭客户端连接失败: {e}")
                    try:
                        writer.transport.abort()
                    except Exception as e2:
                        logger.error(f"强制关闭 transport 失败: {e2}")

        finally:
            # 确保计数器被减少
            self.current_connections -= 1
            logger.debug(f"连接已关闭,当前连接数: {self.current_connections}/{self.max_connections}")
```

### 修复 3：添加事件对象清理保护

**问题**：事件对象泄漏

**修复方案**：
```python
async def open_channel(self, host: str, port: int) -> Tuple[int, bool]:
    # ... 现有代码 ...

    # 创建事件用于等待服务器响应
    event = asyncio.Event()
    self.connect_events[channel_id] = event
    self.connect_results[channel_id] = False

    # 发送连接请求
    try:
        payload = make_connect_payload(host, port)
        await self.send_frame(FRAME_CONNECT, channel_id, payload)
        logger.debug(f"已发送通道 {channel_id} 连接请求")
    except Exception as e:
        logger.error(f"发送通道 {channel_id} 连接请求失败: {e}")
        # 清理事件和结果
        self.connect_events.pop(channel_id, None)
        self.connect_results.pop(channel_id, None)
        self.failed_connections += 1
        return channel_id, False

    # 等待服务器响应
    try:
        await asyncio.wait_for(event.wait(), timeout=10.0)
        success = self.connect_results.get(channel_id, False)
        if success:
            logger.info(f"通道 {channel_id} 打开成功")
        else:
            logger.warning(f"通道 {channel_id} 打开失败")
            self.failed_connections += 1
    except asyncio.TimeoutError:
        logger.error(f"通道 {channel_id} 打开超时")
        success = False
        self.failed_connections += 1
        # 通知服务器关闭连接
        try:
            await self.send_frame(FRAME_CLOSE, channel_id, b'')
            logger.debug(f"已通知服务器关闭通道 {channel_id}")
        except Exception as e:
            logger.error(f"发送关闭帧失败: {e}")

    # 清理事件和结果（确保清理）
    self.connect_events.pop(channel_id, None)
    self.connect_results.pop(channel_id, None)

    return channel_id, success
```

### 修复 4：添加Socket句柄强制关闭保护

**问题**：Socket句柄泄漏

**修复方案**：
```python
finally:
    # 确保在所有情况下都关闭 writer
    try:
        writer.close()
        await asyncio.wait_for(writer.wait_closed(), timeout=5.0)
    except asyncio.TimeoutError:
        logger.warning("关闭 writer 超时,强制关闭")
        try:
            writer.transport.abort()
        except Exception as e:
            logger.error(f"强制关闭 transport 失败: {e}")
    except Exception as e:
        logger.debug(f"关闭客户端连接失败: {e}")
        try:
            writer.transport.abort()
        except Exception as e2:
            logger.error(f"强制关闭 transport 失败: {e2}")
    finally:
        # 最后的手段：强制关闭Socket
        try:
            if hasattr(writer, 'transport') and hasattr(writer.transport, '_sock'):
                writer.transport._sock.close()
        except Exception as e:
            logger.error(f"强制关闭 Socket 失败: {e}")
```

### 修复 5：添加通道对象清理保护

**问题**：通道对象泄漏

**修复方案**：
```python
async def _close_channel(self, channel: Channel):
    if not channel.connected:
        return
    logger.info(f"关闭本地通道 {channel.channel_id}")
    channel.connected = False
    self.closed_connections += 1

    # 关闭写入流
    try:
        channel.writer.close()
        await asyncio.wait_for(channel.writer.wait_closed(), timeout=5.0)
    except asyncio.TimeoutError:
        logger.warning(f"关闭通道 {channel.channel_id} writer 超时,强制关闭")
        try:
            channel.writer.transport.abort()
        except Exception as e:
            logger.error(f"强制关闭 transport 失败: {e}")
    except Exception as e:
        logger.error(f"关闭通道 {channel.channel_id} writer 失败: {e}")
        try:
            channel.writer.transport.abort()
        except Exception as e2:
            logger.error(f"强制关闭 transport 失败: {e2}")
    finally:
        # 最后的手段：强制关闭Socket
        try:
            if hasattr(channel.writer, 'transport') and hasattr(channel.writer.transport, '_sock'):
                channel.writer.transport._sock.close()
        except Exception as e:
            logger.error(f"强制关闭 Socket 失败: {e}")

    # 从通道列表中移除
    self.channels.pop(channel.channel_id, None)

    # 清理连接事件和结果
    self.connect_events.pop(channel.channel_id, None)
    self.connect_results.pop(channel.channel_id, None)
```

## 验证方法

### 步骤 1：检查通道ID回收

```bash
# 查看日志中的通道ID
grep "打开通道" client.log | tail -20

# 预期结果：通道ID应该被回收，不应该无限增长
```

### 步骤 2：检查连接计数器

```bash
# 查看日志中的连接数
grep "当前连接数" client.log | tail -20

# 预期结果：连接数应该与实际连接数匹配
```

### 步骤 3：检查事件对象

```bash
# 查看日志中的事件数
grep "事件=" client.log | tail -20

# 预期结果：事件数应该很小（< 10）
```

### 步骤 4：检查Socket句柄

```bash
# 检查打开的文件描述符
lsof -p <pid> | wc -l

# 预期结果：文件描述符数应该与连接数匹配
```

## 总结

### 关键发现

1. **通道ID无限增长**：
   - 通道ID从1开始，每次打开通道都+1
   - 通道ID会无限增长，不会重用
   - 说明通道对象可能没有被正确清理

2. **连接计数器不准确**：
   - 连接计数器在进入`async with`时立即增加
   - 但在`finally`块中才减少
   - 可能导致计数器不准确

3. **事件对象泄漏**：
   - 每次打开通道都会创建新的事件对象
   - 如果通道打开超时，事件对象会被清理
   - 但如果服务器在超时后发送响应，响应被忽略
   - 可能导致服务器端连接未关闭

4. **Socket句柄泄漏**：
   - writer关闭超时后，尝试强制关闭transport
   - 但如果`transport.abort()`也失败，Socket句柄可能不会被释放
   - 可能导致文件描述符泄漏

5. **通道对象泄漏**：
   - 如果`open_channel`返回失败，`channel`为`None`
   - `finally`块中会尝试清理`None`通道
   - 可能导致`channels`字典中累积僵尸通道

### 推荐行动

1. **立即修复**：
   - 添加通道ID回收机制
   - 修复连接计数器
   - 添加事件对象清理保护
   - 添加Socket句柄强制关闭保护
   - 添加通道对象清理保护

2. **添加监控**：
   - 添加通道ID监控
   - 添加连接计数器验证
   - 添加事件对象监控
   - 添加Socket句柄监控

3. **长期优化**：
   - 实施连接池
   - 实施资源限制
   - 实施自动恢复机制

### 预期效果

修复后，应该观察到：
- 通道ID被回收，不再无限增长
- 连接计数器准确
- 事件对象被正确清理
- Socket句柄被正确关闭
- 通道对象被正确清理
- 资源使用稳定，不再耗尽
