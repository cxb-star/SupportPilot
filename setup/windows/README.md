# Windows 环境脚本

这个文件夹放 Windows 用的脚本：

- `setup.ps1`：一键初始化 Windows 环境
  - 建虚拟环境
  - 装依赖
  - 生成 `.env`
  - 初始化数据库
  - 入库
  - 启动服务

## 用法

在项目根目录执行：

```powershell
cd C:\Users\bin\Documents\ChatGPT\boss专家\agent_knowledge_self_built
.\setup\windows\setup.ps1
```

如果要换端口：

```powershell
.\setup\windows\setup.ps1 -Port 8001
```

## 说明

- 不会碰 Docker
- 不产生额外“容器费用”
- 只是帮你把本地环境一次性搭好
