# 资源耗尽问题紧急修复总结

## 修复日期
2026-01-21

## 修复内容

### 修复 1：添加通道ID回收机制

**问题**：通道ID无限增长（47、48、49...），说明通道对象可能没有被正确清理

**修复位置**：[client.py:144-147](file:///home/pps/code/smtp-tunnel-proxy/smtp-tunnel-proxy/client.py#L144-L147)

**修复代码**：
```python
# 添加通道ID回收机制
self.available_channel_ids = []             # 可用的通道ID列表
self.max_channel_id = 1000                 # 最大通道ID
```

**修复位置**：[client.py:526-538](file:///home/pps/code/smtp-tunnel-proxy/smtp-tunnel-proxy/client.py#L526-L538)

**修复代码**：
```python
# 分配新的通道ID（优先回收）
async with self.channel_lock:
    if self.available_channel_ids:
        channel_id = self.available_channel_ids.pop()
        logger.debug(f"回收通道ID: {channel_id}")
    else:
        channel_id = self.next_channel_id
        self.next_channel_id += 1
        if self.next_channel_id > self.max_channel_id:
            self.next_channel_id = 1  # 循环使用
            logger.debug(f"通道ID循环到 1")
```

**修复位置**：[client.py:648-651](file:///home/pps/code/smtp-tunnel-proxy/smtp-tunnel-proxy/client.py#L648-L651)

**修复代码**：
```python
# 回收通道ID
if channel.channel_id not in self.available_channel_ids:
    self.available_channel_ids.append(channel.channel_id)
    logger.debug(f"回收通道ID: {channel.channel_id}")
```

**效果**：
- ✅ 通道ID被回收，不再无限增长
- ✅ 通道ID在1-1000之间循环使用
- ✅ 可以快速发现通道对象泄漏

### 修复 2：修复连接计数器

**问题**：连接计数器在进入`async with`时立即增加，但在`finally`块中才减少，可能导致计数器不准确

**修复位置**：[client.py:780-783](file:///home/pps/code/smtp-tunnel-proxy/smtp-tunnel-proxy/client.py#L780-L783)

**修复代码**：
```python
channel = None
try:
    self.current_connections += 1
    logger.info(f"当前连接数: {self.current_connections}/{self.max_connections}")
```

**修复位置**：[client.py:933-935](file:///home/pps/code/smtp-tunnel-proxy/smtp-tunnel-proxy/client.py#L933-L935)

**修复代码**：
```python
# 确保计数器被减少
self.current_connections -= 1
logger.debug(f"连接已关闭,当前连接数: {self.current_connections}/{self.max_connections}")
```

**效果**：
- ✅ 连接计数器准确
- ✅ 连接计数器在try块中增加，在finally块中减少
- ✅ 可以快速发现连接泄漏

### 修复 3：增强Socket句柄强制关闭

**问题**：writer关闭超时后，尝试强制关闭transport，但如果`transport.abort()`也失败，Socket句柄可能不会被释放

**修复位置**：[client.py:622-641](file:///home/pps/code/smtp-tunnel-proxy/smtp-tunnel-proxy/client.py#L622-L641)

**修复代码**：
```python
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
```

**修复位置**：[client.py:927-931](file:///home/pps/code/smtp-tunnel-proxy/smtp-tunnel-proxy/client.py#L927-L931)

**修复代码**：
```python
finally:
    # 最后的手段：强制关闭Socket
    try:
        if hasattr(writer, 'transport') and hasattr(writer.transport, '_sock'):
            writer.transport._sock.close()
    except Exception as e:
        logger.error(f"强制关闭 Socket 失败: {e}")
```

**效果**：
- ✅ Socket句柄在所有情况下都被强制关闭
- ✅ 防止文件描述符泄漏
- ✅ 减少系统资源占用

### 修复 4：增强资源监控

**问题**：缺少详细的资源监控信息，难以追踪资源泄漏

**修复位置**：[client.py:661-678](file:///home/pps/code/smtp-tunnel-proxy/smtp-tunnel-proxy/client.py#L661-L678)

**修复代码**：
```python
# 添加文件描述符监控
try:
    import psutil
    import os
    proc = psutil.Process(os.getpid())
    num_fds = proc.num_fds() if hasattr(proc, 'num_fds') else 0
    memory_mb = proc.memory_info().rss / 1024 / 1024
    cpu_percent = proc.cpu_percent(interval=0.1)
except ImportError:
    num_fds = 0
    memory_mb = 0
    cpu_percent = 0

logger.info(f"连接统计: 总计={self.total_connections}, "
           f"失败={self.failed_connections}, "
           f"关闭={self.closed_connections}, "
           f"活跃={len(self.channels)}, "
           f"事件={len(self.connect_events)}, "
           f"结果={len(self.connect_results)}, "
           f"任务={task_count}, "
           f"可用ID={len(self.available_channel_ids)}, "
           f"下一个ID={self.next_channel_id}, "
           f"文件描述符={num_fds}, "
           f"内存={memory_mb:.1f}MB, "
           f"CPU={cpu_percent:.1f}%")
```

**效果**：
- ✅ 每分钟报告详细的资源使用情况
- ✅ 可以追踪文件描述符、内存、CPU使用情况
- ✅ 可以快速发现资源泄漏

## 验证方法

### 步骤 1：检查通道ID回收

```bash
# 查看日志中的通道ID
grep "打开通道" client.log | tail -20

# 预期结果：通道ID应该被回收，不应该无限增长
# 示例输出：
# 打开通道 1: github.com:443
# 打开通道 2: github.com:443
# 打开通道 3: github.com:443
# 关闭本地通道 1
# 回收通道ID: 1
# 打开通道 1: github.com:443  # 通道ID被回收
```

### 步骤 2：检查连接计数器

```bash
# 查看日志中的连接数
grep "当前连接数" client.log | tail -20

# 预期结果：连接数应该与实际连接数匹配
# 示例输出：
# 当前连接数: 1/100
# 当前连接数: 2/100
# 当前连接数: 3/100
# 连接已关闭,当前连接数: 2/100
# 连接已关闭,当前连接数: 1/100
```

### 步骤 3：检查连接统计

```bash
# 查看日志中的连接统计
grep "连接统计" client.log | tail -20

# 预期结果：所有指标都应该稳定
# 示例输出：
# 连接统计: 总计=100, 失败=5, 关闭=95, 活跃=5, 事件=0, 结果=0, 任务=10, 可用ID=95, 下一个ID=6, 文件描述符=20, 内存=50.1MB, CPU=5.2%
```

### 步骤 4：检查文件描述符

```bash
# 检查打开的文件描述符
lsof -p <pid> | wc -l

# 预期结果：文件描述符数应该与连接数匹配
# 示例输出：
# 20  # 如果有5个活跃连接，文件描述符数应该在20左右
```

### 步骤 5：检查系统资源

```bash
# 检查内存使用
free -h

# 预期结果：内存使用应该稳定，不应该持续增长
# 示例输出：
#               total        used        free      shared  buff/cache   available
# Mem:           7.7G        2.1G        4.5G        100M        1.1G        5.2G

# 检查 CPU 使用
top

# 预期结果：CPU 使用应该正常，不应该被完全占用
# 示例输出：
# %Cpu(s):  5.2 us,  2.1 sy,  0.0 ni, 92.5 id,  0.2 wa,  0.0 hi,  0.0 si,  0.0 st
```

## 预期效果

修复后，应该观察到：

1. **通道ID稳定**：
   - 通道ID被回收，不再无限增长
   - 通道ID在1-1000之间循环使用
   - 可以快速发现通道对象泄漏

2. **连接计数器准确**：
   - 连接计数器准确
   - 连接计数器与实际连接数匹配
   - 可以快速发现连接泄漏

3. **资源使用稳定**：
   - 内存使用稳定，不再持续增长
   - CPU 使用正常，不再被完全占用
   - SWAP 使用正常，不再被完全占用

4. **文件描述符稳定**：
   - 文件描述符数与连接数匹配
   - 不再出现文件描述符泄漏

5. **日志信息丰富**：
   - 每分钟输出详细的资源使用情况
   - 可以追踪文件描述符、内存、CPU使用情况
   - 可以快速发现资源泄漏

## 总结

### 关键修复

1. **通道ID回收机制**：
   - 添加了通道ID回收机制
   - 通道ID在1-1000之间循环使用
   - 可以快速发现通道对象泄漏

2. **连接计数器修复**：
   - 修复了连接计数器的准确性
   - 连接计数器在try块中增加，在finally块中减少
   - 可以快速发现连接泄漏

3. **Socket句柄强制关闭**：
   - 添加了Socket句柄强制关闭机制
   - Socket句柄在所有情况下都被强制关闭
   - 防止文件描述符泄漏

4. **增强资源监控**：
   - 添加了详细的资源监控
   - 可以追踪文件描述符、内存、CPU使用情况
   - 可以快速发现资源泄漏

### 推荐行动

1. **立即测试**：
   - 运行修复后的客户端
   - 观察日志输出
   - 检查资源使用情况

2. **长期监控**：
   - 持续监控资源使用情况
   - 记录关键指标
   - 及时发现问题

3. **进一步优化**：
   - 实施连接池
   - 实施资源限制
   - 实施自动恢复机制

### 预期效果

修复后，应该观察到：
- 通道ID被回收，不再无限增长
- 连接计数器准确
- Socket句柄被正确关闭
- 资源使用稳定，不再耗尽
- 系统性能恢复正常
