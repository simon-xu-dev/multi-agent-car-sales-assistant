# CarSales Web Demo

交互式 Web 演示应用，展示 CarSales 多Agent汽车销售系统的架构、Agent协作流程、3个真实场景的执行Trace。

## 快速开始

```bash
# 安装依赖
npm install

# 启动开发服务器
npm run dev

# 构建生产版本
npm run build

# 预览生产版本
npm run preview
```

## 功能模块

### 1. 首页 - 项目概览
- 项目定位与核心亮点
- 8大Agent角色一览
- 10步自主成交流程预览

### 2. 架构图 - 系统架构
- Manager → TeamLeader → 8 Workers 分层架构可视化
- 数据流向：10步完整流程展示
- 风险控制策略：L0/L1自动执行、L2人工审批、L3人工介入

### 3. 场景演示 - 3个真实交易场景
- **DEAL-2001**: 二胎家庭SUV全链路成交
- **DEAL-2002**: 首购客户金融方案闭环
- **DEAL-2003**: 老客户置换与售后运营闭环

每个场景展示：
- 客户信息与画像
- 多渠道会话记录（官网/微信/电话/抖音）
- 推荐车型与报价
- 10步Agent协作流程
- 工具调用Trace时间线（可展开查看30+次工具调用详情）

### 4. Agent详情 - 8大Agent
- 职责定位与核心能力
- Skills与Tools清单
- Workflow步骤映射
- TeamLeader核心职责
- Worker创建策略
- 风险控制策略

## 技术栈

- **框架**: React 19 + Vite
- **样式**: Tailwind CSS
- **数据**: 真实场景JSON数据 + 执行Trace

## 数据来源

- `src/data/family_suv_deal.json` - DEAL-2001场景数据
- `src/data/first_car_finance.json` - DEAL-2002场景数据
- `src/data/trade_in_renewal.json` - DEAL-2003场景数据
- `src/data/DEAL-2001_trace.json` - DEAL-2001执行Trace
- `src/data/DEAL-2002_trace_full.json` - DEAL-2002执行Trace
- `src/data/DEAL-2003_trace.json` - DEAL-2003执行Trace
- `src/data/team_spec.json` - Agent定义与Workflow配置
- `src/data/agents.js` - Agent元数据

## 部署

可部署到任何静态站点托管服务：

```bash
npm run build
# 将 dist/ 目录部署到 Vercel / Netlify / GitHub Pages 等
```

## 评审使用说明

1. 本地运行：`npm install && npm run dev`，打开 http://localhost:5173
2. 首页快速了解项目定位与核心能力
3. 架构图查看系统分层与数据流向
4. 场景演示查看3个真实交易场景的完整执行过程
5. 点击"查看Trace"按钮展开工具调用时间线，查看Agent真实执行轨迹
6. Agent详情查看8大Agent的职责与能力定义
