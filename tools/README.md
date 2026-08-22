# tools/ — 联调与测试夹具

## mock_agent.py — MockAgent（api-design §12 客户端夹具）

模拟 Agent WS 客户端，用于阶段2「注册→心跳→在线→连通性」与阶段3 exec 链路联调。
验收标准见架构师裁定（2026-08-22 21:27）：WS 鉴权连接 / hello+heartbeat≤30s+ping /
exec_log(seq)+exec_result+stop / 注册→online→断心跳90s→offline→conn 探测。

```bash
# 使用 backend venv（自带 websockets）
backend/.venv/Scripts/python.exe tools/mock_agent.py \
    --agent-id qa-mock-a1 --interval 5 --count 12 --exec-demo --verbose
```

| 参数 | 说明 |
|------|------|
| `--server` | 默认 `ws://127.0.0.1:8000` |
| `--agent-id` | Agent 标识；需与某主机 `agent_id` 一致才能看到该主机 online 翻转 |
| `--token` | 显式 token；缺省自动派生（绑定=sha256(agent_id:SECRET_KEY)[:32]，未绑定回退 bootstrap=SECRET_KEY） |
| `--interval` / `--count` | 心跳间隔（≤30s）/ 次数 |
| `--hold-timeout` | 心跳停止后保持连接 >90s 再断开（演示离线判定路径） |
| `--exec-demo` | 响应 exec 下发：exec_log(seq 递增) ×3 + exec_result；stop 帧可中断 |

注意：当前服务端 MVP 无 host.agent_id 绑定入口（HostCreate/Update 不含该字段，
agent_ws 仅按 agent_id 匹配），未绑定时走 bootstrap 鉴权、主机状态不会翻转——
绑定路径补齐后本夹具即可完整演示 online/offline 断言链。
