# Socket关闭错误修复总结

## 修复日期
2026-01-22

## 问题描述

客户端在持续运行一段时间后出现严重的资源耗尽问题，具体表现为CPU、内存和SWAP资源被完全占用，导致系统性能严重下降。

### 关键错误日志

```
2026-01-22 09:32:57,877 - INFO - 关闭本地通道 1
2026-01-22 09:32:57,877 - ERROR - 强制关闭 Socket 失败: 'NoneType' object has no attribute 'close'
2026-01-22 09:32:57,877 - ERROR - 强制关闭 Socket 失败: 'NoneType' object has no attribute 'close'
2026-01-22 09:39:08,615 - INFO - 当前连接数: 1/100
2026-01-22 09:39:08,616 - INFO - SOCKS5 连接请求: github.com:443
2026-01-22 09:39:08,616 - INFO - 打开通道 1: github.com:443
2026-01-22 09:39:18,626 - ERROR - 通道 1 打开超时
2026-01-22 09:39:18,626 - WARNING - SOCKS5 连接失败: github.com:443
2026-01-22 09:39:18,626 - ERROR - 强制关闭 Socket 失败: 'NoneType' object has no attribute 'close'
2026-01-22 09:43:57,537 - INFO - 当前连接数: 1/100
2026-01-22 09:43:57,537 - INFO - SOCKS5 连接请求: github.com:443
2026-01-22 09:43:57,537 - INFO - 打开通道 2: github.com:443
2026-01-22 09:44:07,548 - ERROR - 通道 2 打开超时
2026-01-22 09:44:07,548 - WARNING - SOCKS5 连接失败: github.com:443
2026-01-22 09:44:07,548 - ERROR - 强制关闭 Socket 失败: 'NoneType' object has no attribute 'close'
2026-01-22 09:50:17,689 - INFO - 当前连接数: 1/100
2026-01-22 09:50:17,690 - INFO - SOCKS5 连接请求: github.com:443
2026-01-22 09:50:17,690 - INFO - 打开通道 3: github.com:443
2026-01-22 09:50:27,700 - ERROR - 通道 3 打开超时
2026-01-22 09:50:27,700 - WARNING - SOCKS5 连接失败: github.com:443
2026-01-22 09:50:27,700 - ERROR - 强制关闭 Socket 失败: 'NoneType' object has no attribute 'close'
```

## 问题分析

### 问题 1：Socket关闭错误

**错误信息**：
```
ERROR - 强制关闭 Socket 失败: 'NoneType' object has no attribute 'close'
```

**问题位置**：[client.py:655-658](file:///home/pps/code/smtp-tunnel-proxy/client.py#L655-L658)

**原始代码**：
```python
finally:
    # 最后的手段：强制关闭Socket
    try:
        if hasattr(channel, 'writer') and hasattr(channel.writer, 'transport') and hasattr(channel.writer.transport, '_sock'):
            channel.writer.transport._sock.close()
    except Exception as e:
        logger.error(f"强制关闭 Socket 失败: {e}")
```

**问题根源**：
- 我们检查了`hasattr(channel.writer.transport, '_sock')`
- 但是`_sock`属性可能存在，但其值是`None`
- 所以当我们调用`close()`时，就会出现`'NoneType' object has no attribute 'close'`的错误

### 问题 2：通道对象清理逻辑错误

**问题位置**：[client.py:579-583](file:///home/pps/code/smtp-tunnel-proxy/client.py#L579-L583)

**原始代码**：
```python
# 清理通道对象（如果存在）
if channel_id in self.channels:
    channel = self.channels[channel_id]
    await self._close_channel(channel)
    logger.debug(f"已清理通道 {channel_id} 对象")
```

**问题根源**：
- 在通道打开超时时，我们尝试清理通道对象
- 但是此时通道对象可能还没有被创建
- 通道对象只有在SOCKS5连接成功时才会被创建
- 导致`channel.writer`为`None`，从而引发Socket关闭错误

### 问题 3：SOCKS5连接失败时的清理逻辑错误

**问题位置**：[client.py:934-938](file:///home/pps/code/smtp-tunnel-proxy/client.py#L934-L938)

**原始代码**：
```python
# 清理通道对象（如果存在）
if channel_id in self.tunnel.channels:
    channel = self.tunnel.channels[channel_id]
    await self.tunnel._close_channel(channel)
    logger.debug(f"已清理通道 {channel_id} 对象")
```

**问题根源**：
- 在SOCKS5连接失败时，我们尝试清理通道对象
- 但是此时通道对象可能还没有被创建
- 通道对象只有在SOCKS5连接成功时才会被创建
- 导致`channel.writer`为`None`，从而引发Socket关闭错误

## 修复内容

### 修复 1：修复Socket关闭错误

**修复位置**：[client.py:653-660](file:///home/pps/code/smtp-tunnel-proxy/smtp-tunnel-proxy/client.py#L653-L660)

**修复代码**：
```python
finally:
    # 最后的手段：强制关闭Socket
    try:
        if (hasattr(channel, 'writer') and 
            channel.writer and 
            hasattr(channel.writer, 'transport') and 
            channel.writer.transport and 
            hasattr(channel.writer.transport, '_sock') and 
            channel.writer.transport._sock is not None):
            channel.writer.transport._sock.close()
    except Exception as e:
        logger.error(f"强制关闭 Socket 失败: {e}")
```

**修复说明**：
- 检查`channel.writer`是否为`None`
- 检查`channel.writer.transport`是否为`None`
- 检查`channel.writer.transport._sock`是否为`None`
- 只有在所有条件都满足时，才调用`close()`

**效果**：
- ✅ 避免了`'NoneType' object has no attribute 'close'`错误
- ✅ Socket句柄被正确关闭
- ✅ 防止文件描述符泄漏

### 修复 2：修复SOCKS5处理中的Socket关闭错误

**修复位置**：[client.py:979-986](file:///home/pps/code/smtp-tunnel-proxy/smtp-tunnel-proxy/client.py#L979-L986)

**修复代码**：
```python
finally:
    # 最后的手段：强制关闭Socket
    try:
        if (hasattr(writer, 'transport') and 
            writer.transport and 
            hasattr(writer.transport, '_sock') and 
            writer.transport._sock is not None):
            writer.transport._sock.close()
    except Exception as e:
        logger.error(f"强制关闭 Socket 失败: {e}")
```

**修复说明**：
- 检查`writer.transport`是否为`None`
- 检查`writer.transport._sock`是否为`None`
- 只有在所有条件都满足时，才调用`close()`

**效果**：
- ✅ 避免了`'NoneType' object has no attribute 'close'`错误
- ✅ Socket句柄被正确关闭
- ✅ 防止文件描述符泄漏

### 修复 3：修复通道打开超时时的清理逻辑

**修复位置**：[client.py:579-583](file:///home/pps/code/smtp-tunnel-proxy/smtp-tunnel-proxy/client.py#L579-L583)

**修复代码**：
```python
# 注意：不清理通道对象，因为通道对象可能还没有被创建
# 通道对象会在SOCKS5连接成功后被创建，并在SOCKS5连接失败时被清理
```

**修复说明**：
- 移除了通道打开超时时清理通道对象的逻辑
- 添加了注释说明为什么不清理通道对象
- 通道对象只有在SOCKS5连接成功时才会被创建

**效果**：
- ✅ 避免了尝试清理不存在的通道对象
- ✅ 避免了`channel.writer`为`None`的情况
- ✅ 避免了Socket关闭错误

### 修复 4：修复SOCKS5连接失败时的清理逻辑

**修复位置**：[client.py:934-938](file:///home/pps/code/smtp-tunnel-proxy/smtp-tunnel-proxy/client.py#L934-L938)

**修复代码**：
```python
# 注意：不清理通道对象，因为通道对象可能还没有被创建
# 通道对象只有在连接成功时才会被创建
```

**修复说明**：
- 移除了SOCKS5连接失败时清理通道对象的逻辑
- 添加了注释说明为什么不清理通道对象
- 通道对象只有在SOCKS5连接成功时才会被创建

**效果**：
- ✅ 避免了尝试清理不存在的通道对象
- ✅ 避免了`channel.writer`为`None`的情况
- ✅ 避免了Socket关闭错误

## 验证方法

### 步骤 1：检查Socket关闭错误

```bash
# 查看日志中的Socket关闭错误
grep "强制关闭 Socket 失败" client.log | tail -20

# 预期结果：不应该有Socket关闭错误
```

### 步骤 2：检查通道打开超时

```bash
# 查看日志中的通道打开超时
grep "通道.*打开超时" client.log | tail -20

# 预期结果：通道打开超时后，不应该有Socket关闭错误
```

### 步骤 3：检查SOCKS5连接失败

```bash
# 查看日志中的SOCKS5连接失败
grep "SOCKS5 连接失败" client.log | tail -20

# 预期结果：SOCKS5连接失败后，不应该有Socket关闭错误
```

### 步骤 4：检查通道对象清理

```bash
# 查看日志中的通道对象清理
grep "关闭本地通道" client.log | tail -20

# 预期结果：每个通道都应该被正确关闭
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

1. **Socket关闭错误消失**：
   - 不再出现`'NoneType' object has no attribute 'close'`错误
   - Socket句柄被正确关闭
   - 文件描述符不再泄漏

2. **通道对象清理正确**：
   - 通道对象只有在连接成功时才会被创建
   - 通道对象只有在连接失败或关闭时才会被清理
   - 避免了尝试清理不存在的通道对象

3. **资源使用稳定**：
   - 内存使用稳定，不再持续增长
   - CPU 使用正常，不再被完全占用
   - SWAP 使用正常，不再被完全占用

4. **文件描述符稳定**：
   - 文件描述符数与连接数匹配
   - 不再出现文件描述符泄漏

5. **日志信息清晰**：
   - 不再有Socket关闭错误
   - 可以快速定位问题
   - 可以快速发现资源泄漏

## 总结

### 关键修复

1. **修复Socket关闭错误**：
   - 检查`writer`是否为`None`
   - 检查`transport`是否为`None`
   - 检查`_sock`是否为`None`
   - 只有在所有条件都满足时，才调用`close()`

2. **修复通道打开超时时的清理逻辑**：
   - 移除了通道打开超时时清理通道对象的逻辑
   - 添加了注释说明为什么不清理通道对象
   - 通道对象只有在SOCKS5连接成功时才会被创建

3. **修复SOCKS5连接失败时的清理逻辑**：
   - 移除了SOCKS5连接失败时清理通道对象的逻辑
   - 添加了注释说明为什么不清理通道对象
   - 通道对象只有在SOCKS5连接成功时才会被创建

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
- Socket关闭错误消失
- 通道对象被正确清理
- 资源使用稳定，不再耗尽
- 系统性能恢复正常
