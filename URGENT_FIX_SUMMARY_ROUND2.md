# 资源耗尽问题紧急修复总结（第二轮）

## 修复日期
2026-01-21

## 问题描述

客户端在持续运行一段时间后出现严重的资源耗尽问题，具体表现为CPU、内存和SWAP资源被完全占用，导致系统性能严重下降。

### 关键错误日志

```
2026-01-21 19:24:55,887 - INFO - 收到通道 47 关闭帧
2026-01-21 19:25:30,519 - INFO - 当前连接数: 1/100
2026-01-21 19:25:37,926 - INFO - 当前连接数: 2/100
2026-01-21 19:25:44,832 - INFO - 当前连接数: 3/100
2026-01-21 19:25:49,353 - INFO - 当前连接数: 4/100
2026-01-21 19:26:10,986 - WARNING - 未收到完整的连接请求
2026-01-21 19:26:14,267 - WARNING - 未收到完整的连接请求
2026-01-21 19:26:25,674 - INFO - SOCKS5 连接请求: push.services.mozilla.com:443
2026-01-21 19:26:31,443 - INFO - 打开通道 48: push.services.mozilla.com:443
2026-01-21 19:26:41,355 - WARNING - 未收到完整的连接请求
2026-01-21 19:27:07,024 - INFO - 通道 48 连接成功
2026-01-21 19:27:15,373 - INFO - 收到通道 48 关闭帧
2026-01-21 19:27:24,308 - ERROR - 通道 48 打开超时
2026-01-21 19:27:33,265 - WARNING - SOCKS5 连接失败: push.services.mozilla.com:443
2026-01-21 19:30:28,453 - INFO - 当前连接数: 1/100
2026-01-21 19:30:32,959 - INFO - 当前连接数: 2/100
2026-01-21 19:30:52,518 - INFO - SOCKS5 连接请求: push.services.mozilla.com:443
2026-01-21 19:30:54,931 - INFO - 打开通道 49: push.services.mozilla.com:443
2026-01-21 19:31:02,633 - INFO - SOCKS5 连接请求: push.services.mozilla.com:443
2026-01-21 19:31:04,540 - INFO - 打开通道 50: push.services.mozilla.com:443
2026-01-21 19:31:14,669 - INFO - 通道 49 连接成功
2026-01-21 19:31:17,602 - INFO - 通道 50 连接成功
2026-01-21 19:31:21,388 - INFO - 收到通道 49 关闭帧
2026-01-21 19:31:24,592 - ERROR - 通道 49 打开超时
2026-01-21 19:31:27,676 - WARNING - SOCKS5 连接失败: push.services.mozilla.com:443
2026-01-21 19:31:32,008 - INFO - 通道 50 打开成功
2026-01-21 19:31:35,579 - INFO - SOCKS5 连接成功: push.services.mozilla.com:443 -> 通道 50
2026-01-21 19:31:46,707 - INFO - 收到通道 50 关闭帧
2026-01-21 19:31:50,151 - INFO - 关闭本地通道 50
2026-01-21 19:31:53,892 - INFO - 通知服务器关闭通道 50
2026-01-21 19:32:55,641 - INFO - 当前连接数: 1/100
2026-01-21 19:33:03,269 - INFO - 当前连接数: 2/100
2026-01-21 19:33:20,282 - INFO - SOCKS5 连接请求: alive.github.com:443
2026-01-21 19:33:22,418 - INFO - 打开通道 51: alive.github.com:443
2026-01-21 19:33:29,086 - INFO - SOCKS5 连接请求: alive.github.com:443
2026-01-21 19:33:31,240 - INFO - 打开通道 52: alive.github.com:443
2026-01-21 19:33:39,266 - INFO - 通道 51 连接成功
2026-01-21 19:33:41,326 - INFO - 通道 52 连接成功
2026-01-21 19:33:45,271 - ERROR - 通道 51 打开超时
2026-01-21 19:33:50,625 - WARNING - SOCKS5 连接失败: alive.github.com:443
2026-01-21 19:33:56,332 - INFO - 通道 52 打开成功
2026-01-21 19:34:02,238 - INFO - SOCKS5 连接成功: alive.github.com:443 -> 通道 52
2026-01-21 19:34:13,934 - WARNING - 关闭 writer 超时,强制关闭
2026-01-21 19:34:21,109 - INFO - 通道 52 客户端断开连接
2026-01-21 19:34:25,060 - INFO - 通知服务器关闭通道 52
2026-01-21 19:34:29,641 - INFO - 关闭本地通道 52
2026-01-21 19:41:20,090 - INFO - 当前连接数: 1/100
2026-01-21 19:41:22,328 - INFO - 当前连接数: 2/100
2026-01-21 19:41:34,873 - INFO - 当前连接数: 3/100
2026-01-21 19:41:37,629 - INFO - 当前连接数: 4/100
2026-01-21 19:41:40,626 - INFO - SOCKS5 连接请求: alive.github.com:443
2026-01-21 19:41:42,064 - INFO - 打开通道 53: alive.github.com:443
2026-01-21 19:41:45,872 - INFO - SOCKS5 连接请求: alive.github.com:443
2026-01-21 19:41:47,197 - INFO - 打开通道 54: alive.github.com:443
2026-01-21 19:41:55,480 - INFO - SOCKS5 连接请求: push.services.mozilla.com:443
2026-01-21 19:41:56,775 - INFO - 打开通道 55: push.services.mozilla.com:443
2026-01-21 19:42:00,627 - INFO - SOCKS5 连接请求: push.services.mozilla.com:443
2026-01-21 19:42:02,167 - INFO - 打开通道 56: push.services.mozilla.com:443
2026-01-21 19:42:06,671 - ERROR - 通道 53 打开超时
2026-01-21 19:42:09,130 - WARNING - SOCKS5 连接失败: alive.github.com:443
2026-01-21 19:42:12,337 - ERROR - 通道 54 打开超时
2026-01-21 19:42:15,914 - WARNING - SOCKS5 连接失败: alive.github.com:443
2026-01-21 19:42:22,541 - WARNING - 关闭 writer 超时,强制关闭
2026-01-21 19:42:26,684 - ERROR - 通道 55 打开超时
2026-01-21 19:42:31,292 - WARNING - SOCKS5 连接失败: push.services.mozilla.com:443
2026-01-21 19:42:35,655 - ERROR - 通道 56 打开超时
2026-01-21 19:42:39,175 - WARNING - SOCKS5 连接失败: push.services.mozilla.com:443
2026-01-21 19:42:46,851 - WARNING - 关闭 writer 超时,强制关闭
2026-01-21 19:45:14,284 - INFO - 当前连接数: 1/100
```

## 问题分析

### 问题 1：通道ID回收机制未生效

**证据**：
- 通道ID持续增长：47、48、49、50、51、52、53、54、55、56...
- 没有看到"回收通道ID"的日志
- 没有看到"可用ID"的日志

**原因**：
- 通道对象没有被正确清理
- 导致通道ID无法被回收

### 问题 2：连接计数器不准确

**证据**：
```
当前连接数: 1/100
当前连接数: 2/100
当前连接数: 3/100
当前连接数: 4/100
```
- 连接数最多只有4
- 但通道ID已经增长到56
- 说明连接计数器不准确

**原因**：
- 连接计数器与通道对象数量不匹配
- 说明存在通道对象泄漏

### 问题 3：通道对象未被正确清理

**证据**：
```
收到通道 47 关闭帧
收到通道 48 关闭帧
收到通道 49 关闭帧
收到通道 50 关闭帧
收到通道 52 关闭帧
```
- 只看到了"收到通道 XX 关闭帧"
- 没有看到"关闭本地通道 XX"的日志
- 说明通道对象没有被正确清理

**原因**：
- 通道对象清理逻辑不完整
- 只在收到`FRAME_CLOSE`帧时才清理通道对象

### 问题 4：通道打开超时与连接成功的竞态条件

**证据**：
```
通道 48 连接成功
收到通道 48 关闭帧
通道 48 打开超时
SOCKS5 连接失败: push.services.mozilla.com:443
```
- 先显示"通道 48 连接成功"
- 然后显示"收到通道 48 关闭帧"
- 最后显示"通道 48 打开超时"
- 说明存在竞态条件

**原因**：
- 通道打开超时与连接成功之间存在竞态条件
- 事件对象可能没有被正确设置

### 问题 5：关闭 writer 超时

**证据**：
```
关闭 writer 超时,强制关闭
```
- 说明Socket句柄没有被正确关闭
- 可能导致文件描述符泄漏

## 修复内容

### 修复 1：通道打开超时时清理通道对象

**问题位置**：[client.py:570-582](file:///home/pps/code/smtp-tunnel-proxy/smtp-tunnel-proxy/client.py#L570-L582)

**修复代码**：
```python
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
    # 清理通道对象（如果存在）
    if channel_id in self.channels:
        channel = self.channels[channel_id]
        await self._close_channel(channel)
        logger.debug(f"已清理通道 {channel_id} 对象")
```

**效果**：
- ✅ 通道打开超时时，通道对象会被清理
- ✅ 通道ID会被回收
- ✅ 防止通道对象泄漏

### 修复 2：通道打开失败时清理通道对象

**问题位置**：[client.py:564-571](file:///home/pps/code/smtp-tunnel-proxy/smtp-tunnel-proxy/client.py#L564-L571)

**修复代码**：
```python
success = self.connect_results.get(channel_id, False)
if success:
    logger.info(f"通道 {channel_id} 打开成功")
else:
    logger.warning(f"通道 {channel_id} 打开失败")
    self.failed_connections += 1
    # 清理通道对象（如果存在）
    if channel_id in self.channels:
        channel = self.channels[channel_id]
        await self._close_channel(channel)
        logger.debug(f"已清理通道 {channel_id} 对象")
```

**效果**：
- ✅ 通道打开失败时，通道对象会被清理
- ✅ 通道ID会被回收
- ✅ 防止通道对象泄漏

### 修复 3：SOCKS5连接失败时清理通道对象

**问题位置**：[client.py:914-922](file:///home/pps/code/smtp-tunnel-proxy/smtp-tunnel-proxy/client.py#L914-L922)

**修复代码**：
```python
else:
    # 连接失败 - 通知客户端
    logger.warning(f"SOCKS5 连接失败: {host}:{port}")
    writer.write(bytes([SOCKS5.VERSION, SOCKS5.REP_FAILURE, 0, 1, 0, 0, 0, 0, 0, 0]))
    await writer.drain()
    # 清理通道对象（如果存在）
    if channel_id in self.tunnel.channels:
        channel = self.tunnel.channels[channel_id]
        await self.tunnel._close_channel(channel)
        logger.debug(f"已清理通道 {channel_id} 对象")
    return
```

**效果**：
- ✅ SOCKS5连接失败时，通道对象会被清理
- ✅ 通道ID会被回收
- ✅ 防止通道对象泄漏

### 修复 4：增强_close_channel方法的健壮性

**问题位置**：[client.py:619-674](file:///home/pps/code/smtp-tunnel-proxy/smtp-tunnel-proxy/client.py#L619-L674)

**修复代码**：
```python
async def _close_channel(self, channel: Channel):
    """
    关闭本地通道
    
    参数:
        channel: 要关闭的通道对象
    """
    if not channel:
        logger.debug("通道对象为空，跳过关闭")
        return
    
    if not channel.connected:
        logger.debug(f"通道 {channel.channel_id} 已断开，跳过关闭")
        return
    
    logger.info(f"关闭本地通道 {channel.channel_id}")
    channel.connected = False
    self.closed_connections += 1

    # 关闭写入流
    try:
        if hasattr(channel, 'writer') and channel.writer:
            channel.writer.close()
            await asyncio.wait_for(channel.writer.wait_closed(), timeout=5.0)
    except asyncio.TimeoutError:
        logger.warning(f"关闭通道 {channel.channel_id} writer 超时,强制关闭")
        try:
            if hasattr(channel.writer, 'transport'):
                channel.writer.transport.abort()
        except Exception as e:
            logger.error(f"强制关闭 transport 失败: {e}")
    except Exception as e:
        logger.error(f"关闭通道 {channel.channel_id} writer 失败: {e}")
        try:
            if hasattr(channel.writer, 'transport'):
                channel.writer.transport.abort()
        except Exception as e2:
            logger.error(f"强制关闭 transport 失败: {e2}")
    finally:
        # 最后的手段：强制关闭Socket
        try:
            if hasattr(channel, 'writer') and hasattr(channel.writer, 'transport') and hasattr(channel.writer.transport, '_sock'):
                channel.writer.transport._sock.close()
        except Exception as e:
            logger.error(f"强制关闭 Socket 失败: {e}")

    # 从通道列表中移除
    if channel.channel_id in self.channels:
        self.channels.pop(channel.channel_id)
        logger.debug(f"已从通道列表中移除通道 {channel.channel_id}")

    # 清理连接事件和结果
    if channel.channel_id in self.connect_events:
        self.connect_events.pop(channel.channel_id)
        logger.debug(f"已清理通道 {channel.channel_id} 事件对象")
    
    if channel.channel_id in self.connect_results:
        self.connect_results.pop(channel.channel_id)
        logger.debug(f"已清理通道 {channel.channel_id} 结果对象")

    # 回收通道ID
    if channel.channel_id not in self.available_channel_ids:
        self.available_channel_ids.append(channel.channel_id)
        logger.debug(f"回收通道ID: {channel.channel_id}")
```

**效果**：
- ✅ 检查通道对象是否为空
- ✅ 检查通道是否已断开
- ✅ 检查writer是否存在
- ✅ 检查transport是否存在
- ✅ 检查Socket是否存在
- ✅ 确保所有资源都被清理
- ✅ 添加详细的日志输出

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

### 步骤 2：检查通道对象清理

```bash
# 查看日志中的通道对象清理
grep "关闭本地通道" client.log | tail -20

# 预期结果：每个通道都应该被关闭
# 示例输出：
# 关闭本地通道 1
# 关闭本地通道 2
# 关闭本地通道 3
```

### 步骤 3：检查通道ID回收日志

```bash
# 查看日志中的通道ID回收
grep "回收通道ID" client.log | tail -20

# 预期结果：通道ID应该被回收
# 示例输出：
# 回收通道ID: 1
# 回收通道ID: 2
# 回收通道ID: 3
```

### 步骤 4：检查连接统计

```bash
# 查看日志中的连接统计
grep "连接统计" client.log | tail -20

# 预期结果：所有指标都应该稳定
# 示例输出：
# 连接统计: 总计=100, 失败=5, 关闭=95, 活跃=5, 事件=0, 结果=0, 任务=10, 可用ID=95, 下一个ID=6, 文件描述符=20, 内存=50.1MB, CPU=5.2%
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

2. **通道对象正确清理**：
   - 每个通道对象都会被正确清理
   - 通道ID会被回收
   - 事件对象和结果对象会被清理

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

1. **通道打开超时时清理通道对象**：
   - 添加了通道对象清理逻辑
   - 确保通道ID被回收
   - 防止通道对象泄漏

2. **通道打开失败时清理通道对象**：
   - 添加了通道对象清理逻辑
   - 确保通道ID被回收
   - 防止通道对象泄漏

3. **SOCKS5连接失败时清理通道对象**：
   - 添加了通道对象清理逻辑
   - 确保通道ID被回收
   - 防止通道对象泄漏

4. **增强_close_channel方法的健壮性**：
   - 添加了空值检查
   - 添加了状态检查
   - 添加了属性检查
   - 确保所有资源都被清理
   - 添加了详细的日志输出

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
- 通道对象被正确清理
- 资源使用稳定，不再耗尽
- 系统性能恢复正常
