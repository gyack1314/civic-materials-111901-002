# 本地来源契约

POST /snapshot 的空对象申请快照，返回 token、position、expires_at 和首个 next。沿 next 读取冻结行，每页一条，next=null 表示该快照遍历完毕；position 是原子目录提交边界，捕获期间不会变化。目录行有 id、city、year、blob、version。
GET /changes?after=位置 返回该位置之后的原子 commits；一项 commit 的 changes 不分开发布。through 表示响应覆盖到的提交位置。upsert 为整行，delete 为目录移出；重复读同一 after 合法。旧位置淘汰返回 410。原件由 blob 访问，引用者不同可以共享文件内容。
演练 phase=1 时 P-1 被 P-3 同提交替换，二者引用同一文件；phase=2 时 P-2 转为 2025 年并丢弃位置 0 的可续读资格。快照存活 20 个演练秒。支持独立重复申请快照，控制改变不修改已经创建的快照行。

演练来源由 Python 标准库 HTTP 服务启动，默认端口 8765。GET /health 可查询来源时间与阶段；POST /__admin/advance 接收 seconds、phase 推进本地情形；GET /__admin/log 回查实际请求。这些控制只供操作员调试来源，不能替代产品从正常入口取得资料。来源进程重启会清空其演练状态；采集端自己的保存目录由产品独立管理。
