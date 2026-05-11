# 🚀 AiMai OCL 护栏基准测试 (Benchmark) 运行指南

本指南将带您完成生成对抗性买家数据并运行 OCL 风控基准测试的完整操作流程。

## 第一步：生成 50 个对抗性买家测试数据

我们需要生成用于压力测试的恶意买家画像（包含极端压价、隐私钓鱼、角色劫持等 5 种不同人设）。

在终端中依次运行以下命令：
```powershell
# 1. 设置用于数据生成的 Gemini API Key
$env:GEMINI_API_KEY="您的_Gemini_API_Key"

# 2. 运行生成脚本 (--count 10 表示每种人设生成 10 个，5 种人设共计 50 个)
python generate_adversarial_buyers.py --count 10
```
*运行结束后，终端会提示成功生成，数据将保存在 `configs/adversarial_buyers.json` 中。*

## 第二步：运行大模型对线并生成实验指标

数据准备好后，我们让系统中的“买卖双方”进行对线测试。以下指令使用 `gemini-3.1-flash-lite` 模型，设置 2 秒休眠防止限流：

```powershell
# 1. 将 OpenAI 的底层请求重定向到谷歌的服务器
$env:OPENAI_API_KEY="您的_Gemini_API_Key"
$env:OPENAI_BASE_URL="https://generativelanguage.googleapis.com/v1beta/openai/"

# 2. 正式运行 Benchmark 跑批
python -m aimai_ocl run configs/benchmark.yaml --model gemini-3.1-flash-lite --api-sleep 2 --offset 0 --episodes 50
```

*💡 **进阶提示：***
- *如果您想一口气跑完全部 50 个人，只需把命令最后的参数改为 `--offset 0 --episodes 50`。*
- *如果您中途退出，只需将 `--offset` 修改为已经跑完的数量即可**断点续跑**，程序会自动合并输出的新旧 JSON 数据！*

## 第三步：查看实验结果

跑批结束后，所有的产出文件都会自动保存在项目的 `outputs/` 文件夹中：

1. **`outputs/benchmark_results.json`**：最核心的**成绩单**，包含了不同模型（有/无 OCL 护栏）的成交率、买卖双方平均收益、风控拦截违规率等硬指标。
2. **`outputs/conversation_logs.txt`**：详细的**聊天记录和审计日志**，可以像看剧本一样回溯买卖双方说的每一句话，以及 OCL 风控底层的判定细节。
3. **`outputs/terminal_output.txt`**：终端运行过程的完整实时备份。