# tools/ — 联调与测试夹具

## mock_agent.py — MockAgent（api-design §12 客户端夹具）

模拟 Agent WS 客户端，用于阶段2「注册→心跳→在线→连通性」与阶段3 exec 链路联调。
验收标准见架构师裁定（2026-08-22 21:27）：WS 鉴权连接 / hello+heartbeat≤30s+ping /
exec_log(seq)+exec_result+stop / 注册→online→断心跳90s→offline→conn 探测。

```bash
# 使用 backend venv（自带 websockets）
backend/.venv/Scripts/python.exe tools/mock_agent.py \
    --agent-id qa-mock-a1 --hostname hostB1 --ip 10.0.0.2 \
    --interval 5 --count 12 --exec-demo --verbose
```

| 参数 | 说明 |
|------|------|
| `--server` | 默认 `ws://127.0.0.1:8000` |
| `--agent-id` | Agent 标识 |
| `--hostname` / `--ip` | hello 帧上报的身份字段（§12 L229 载荷）；服务端方案A 自动绑定以此匹配预登记未绑定主机并回写 `agent_id` |
| `--token` | 显式 token；缺省自动派生（绑定=sha256(agent_id:SECRET_KEY)[:32]，未绑定回退 bootstrap=SECRET_KEY） |
| `--interval` / `--count` | 心跳间隔（≤30s）/ 次数（`--count 0` 持续发送） |
| `--hold-timeout` | 心跳停止后保持连接 >90s 再断开（演示离线判定路径） |
| `--exec-demo` | 响应 exec 下发：exec_log(seq 递增) ×3 + exec_result；stop 帧可中断 |

### 绑定路径（阶段2 方案A，agent_ws `_bind_host`）

hello 帧 hostname/ip **唯一**匹配一台预登记且未绑定的主机 → 服务端回写该主机
`agent_id` 并随心跳翻转 online；first-bind-wins、已绑他机/多候选/零候选均拒绑。
四条全链判定须使用全新未绑定夹具主机（架构师终裁 msg=36e361d8）。

### hello_ack 双帧语义（有意设计，非缺陷）

连接建立后服务端立即下发第一帧 `hello_ack`（握手问候，验收标准①锚点）；
收到客户端 hello 帧后再次应答 `hello_ack`（确认身份载荷已处理/绑定结果）。
即：**一连接两帧 hello_ack**——首帧证明链路与鉴权可用，次帧确认 hello 处理完成。
客户端不应将第二帧视为协议违规。
