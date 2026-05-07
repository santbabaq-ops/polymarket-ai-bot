# Gasless Polymarket 项目研究

## 研究发现

### 1. Polymarket 官方 CLOB Client (TypeScript)
- **仓库**: https://github.com/Polymarket/clob-client
- **核心发现**: Polymarket 的 CLOB API 本身就支持 gasless 交易！
- **原理**: 用户离线签名订单 (EIP-712) → 提交到 Polymarket API → Polymarket 的 relayer 代付 Gas 上链

```typescript
// 官方示例
const order = await client.createOrder({
  tokenID: "...",
  price: 0.5,
  size: 100,
  side: Side.BUY
});
const signedOrder = await client.signOrder(order);
// 直接 post，不需要自己付 gas
await client.postOrder(signedOrder);
```

**关键洞察**: 对于 CLOB 限价单/市价单，Polymarket 已经内置了 gasless 支持，不需要 Gelato！

### 2. Polymarket Python CLOB Client
- **仓库**: https://github.com/Polymarket/py-clob-client
- **我们已经在用**: 我们的 `polymarket_client.py` 就是基于这个

### 3. Polymarket CTF Exchange 合约
- **仓库**: https://github.com/polymarket/ctf-exchange
- **核心发现**: 合约已经支持 ERC2771Context (meta-transaction)
- **意义**: 任何支持 EIP-2771 的 relayer 都可以直接对接

### 4. Gelato Relay SDK
- **仓库**: https://github.com/gelatodigital/relay-sdk
- **功能**: 
  - 1Balance: 用 USDC 支付 gas
  - SponsoredCall: 项目方赞助用户 gas
  - ERC-2771 meta-transactions

### 5. Gelato Web3 Functions
- **仓库**: https://github.com/gelatodigital/web3-functions-sdk
- **用途**: 无需服务器的自动化
- **Polymarket 场景**: 自动止损、止盈、条件单执行

---

## 我们的改进方向

### 改进 1: 区分两种 Gasless 模式

| 场景 | 方案 | 是否需要 Gelato |
|-----|------|---------------|
| CLOB 限价/市价单 | Polymarket 原生 gasless | 否 |
| 链上操作 (approve, settle) | Gelato Relay | 是 |
| 自动化策略 (止损/止盈) | Gelato Web3 Functions | 是 |

### 改进 2: 简化 CLOB 交易 (去掉不必要的 Gelato)

对于标准的买卖单，直接用 Polymarket CLOB client 的 gasless 功能：

```python
# 当前代码 (过度设计)
order = build_order()
calldata = encode_for_gelato(order)
gelato.send_transaction(calldata)  # 不需要！

# 改进后 (直接用 CLOB)
order = client.create_order(...)
client.post_order(order)  # Polymarket 自动处理 gasless
```

### 改进 3: 添加 Gelato Web3 Functions 支持

用于自动化场景：
- 止损单自动执行
- 时间到期自动平仓
- 价格条件触发交易

### 改进 4: 1Balance 集成

让用户用 USDC 支付 gas，而不是完全免费：
- 更可持续
- Gelato 1Balance 支持 ERC-20 gas 支付
