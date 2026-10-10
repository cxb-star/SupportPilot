# Mac / Linux 环境脚本

这个文件夹放 macOS / Linux 用的脚本：

- `setup.sh`：一键初始化 Mac/Linux 环境
  - 建虚拟环境
  - 装依赖
  - 生成 `.env`
  - 初始化数据库
  - 入库
  - 启动服务

## 用法

在项目根目录执行：

```bash
cd /path/to/agent_knowledge_self_built
bash setup/mac-linux/setup.sh
```

如果要换端口：

```bash
bash setup/mac-linux/setup.sh 8001
```

## 说明

- 不会碰 Docker
- 不产生额外“容器费用”
- 只是帮你把本地环境一次性搭好
